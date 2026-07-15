# -*- coding: utf-8 -*-
"""Gemini complete-audio REST client without the Google SDK."""
from __future__ import print_function

import base64
import json
import os
import time
import urllib.parse

from .http_client import HttpError, request_json


class GeminiError(Exception):
    pass


GEMINI_PLAN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "transcript": {"type": "STRING"},
        "tool": {
            "type": "STRING",
            "enum": [
                "weather", "current_time", "web_search", "news",
                "server_status", "home_status", "general_answer", "unknown"
            ]
        },
        "location": {"type": "STRING"},
        "date": {"type": "STRING"},
        "query": {"type": "STRING"},
        "entity": {"type": "STRING"},
        "answer": {"type": "STRING"},
        "confidence": {"type": "NUMBER"}
    },
    "required": [
        "transcript", "tool", "location", "date", "query",
        "entity", "answer", "confidence"
    ]
}


class GeminiAudioClient(object):
    def __init__(self, config):
        self.config = config
        self.api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    def available(self):
        return bool(self.config.get("enabled", True) and self.api_key)

    def _url(self):
        base = self.config.get("api_base", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
        model = urllib.parse.quote(self.config.get("model", "gemini-2.5-flash"), safe="")
        return "{}/models/{}:generateContent?key={}".format(base, model, urllib.parse.quote(self.api_key))

    def _generate(self, parts, response_schema=None, max_tokens=None):
        if not self.available():
            raise GeminiError("未設定 GEMINI_API_KEY")
        generation = {
            "temperature": 0.1,
            "maxOutputTokens": int(max_tokens or self.config.get("max_output_tokens", 512)),
            "thinkingConfig": {"thinkingBudget": 0},
        }
        if response_schema is not None:
            generation["responseMimeType"] = "application/json"
            generation["responseSchema"] = response_schema
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation,
        }
        started = time.time()
        try:
            data = request_json(
                "POST", self._url(), payload=payload,
                timeout=int(self.config.get("timeout_seconds", 90)),
            )
        except HttpError as exc:
            raise GeminiError("Gemini API 失敗: {} {}".format(exc, exc.body or ""))
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise GeminiError("Gemini 回傳格式不正確: {}".format(json.dumps(data)[:500]))
        return text.strip(), int((time.time() - started) * 1000), data.get("usageMetadata", {})

    def plan_from_audio(self, wav_path, default_location):
        with open(wav_path, "rb") as handle:
            encoded = base64.b64encode(handle.read()).decode("ascii")
        prompt = (
            "請處理這段完整語音。先逐字轉錄，再選擇一個受控工具。"
            "天氣使用 weather；時間日期用 current_time；最近新聞用 news；"
            "其他最新網路資訊用 web_search；伺服器狀態用 server_status；"
            "居家感測器用 home_status；不需即時資訊的簡單常識用 general_answer。"
            "不可虛構即時資訊，不可產生 shell 指令。預設地點為 {}。"
            "所有欄位必須填值，無資料時填空字串。"
        ).format(default_location)
        parts = [
            {"text": prompt},
            {"inlineData": {"mimeType": "audio/wav", "data": encoded}},
        ]
        text, latency, usage = self._generate(parts, response_schema=GEMINI_PLAN_SCHEMA)
        try:
            plan = json.loads(text)
        except ValueError as exc:
            raise GeminiError("Gemini JSON 無法解析: {}".format(exc))
        plan["latency_ms"] = latency
        plan["usage"] = usage
        plan["source"] = "gemini_audio"
        return plan

    def summarize_tool_result(self, question, tool_name, result):
        prompt = (
            "請只根據以下工具結果，用繁體中文回答使用者，最多三句，不使用 Markdown。"
            "不可添加結果中不存在的事實。\n問題：{}\n工具：{}\n結果：{}"
        ).format(question, tool_name, json.dumps(result, ensure_ascii=False))
        text, latency, usage = self._generate([{"text": prompt}], max_tokens=256)
        return {"answer": text, "latency_ms": latency, "usage": usage}
