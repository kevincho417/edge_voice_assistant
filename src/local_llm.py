# -*- coding: utf-8 -*-
"""OpenAI-compatible llama-server client for a small local model."""
from __future__ import print_function

import json
import re
import time

from .http_client import HttpError, request_json


class LocalLlmError(Exception):
    pass


TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {
            "type": "string",
            "enum": [
                "weather", "current_time", "web_search", "news",
                "server_status", "home_status", "general_answer", "unknown"
            ]
        },
        "location": {"type": "string"},
        "date": {"type": "string"},
        "query": {"type": "string"},
        "entity": {"type": "string"},
        "answer": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1}
    },
    "required": ["tool", "location", "date", "query", "entity", "answer", "confidence"],
    "additionalProperties": False
}


class LocalLlmClient(object):
    def __init__(self, config):
        self.config = config

    def available(self):
        if not self.config.get("enabled", True):
            return False
        try:
            request_json("GET", self.config.get("base_url").rstrip("/") + "/models", timeout=2)
            return True
        except Exception:
            return False

    def _chat(self, messages, max_tokens, response_schema=None, temperature=None):
        url = self.config.get("base_url").rstrip("/") + "/chat/completions"
        payload = {
            "model": self.config.get("model", "local"),
            "messages": messages,
            "temperature": self.config.get("temperature", 0.1) if temperature is None else temperature,
            "max_tokens": int(max_tokens),
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False}
        }
        if response_schema is not None:
            payload["response_format"] = {"type": "json_schema", "schema": response_schema}
        started = time.time()
        try:
            data = request_json(
                "POST", url, payload=payload,
                headers={"Authorization": "Bearer no-key"},
                timeout=int(self.config.get("timeout_seconds", 120)),
            )
        except HttpError as exc:
            # Older llama-server builds may not implement response_format.
            if response_schema is not None and exc.status in (400, 404, 422, 500):
                payload["response_format"] = {"type": "json_object"}
                try:
                    data = request_json(
                        "POST", url, payload=payload,
                        headers={"Authorization": "Bearer no-key"},
                        timeout=int(self.config.get("timeout_seconds", 120)),
                    )
                except HttpError:
                    payload.pop("response_format", None)
                    try:
                        data = request_json(
                            "POST", url, payload=payload,
                            headers={"Authorization": "Bearer no-key"},
                            timeout=int(self.config.get("timeout_seconds", 120)),
                        )
                    except HttpError as retry_exc:
                        raise LocalLlmError(str(retry_exc))
            else:
                raise LocalLlmError(str(exc))
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LocalLlmError("llama-server 回傳格式不正確")
        return content.strip(), int((time.time() - started) * 1000), data.get("timings", {})

    @staticmethod
    def _extract_json(text):
        try:
            return json.loads(text)
        except ValueError:
            match = re.search(r"\{.*\}", text, flags=re.S)
            if not match:
                raise LocalLlmError("本地模型未輸出 JSON")
            try:
                return json.loads(match.group(0))
            except ValueError as exc:
                raise LocalLlmError("本地模型 JSON 無法解析: {}".format(exc))

    def plan(self, transcript, default_location):
        system = (
            "你是繁體中文居家語音助理的工具路由器。只能選擇 schema 內的工具。"
            "天氣、降雨、溫度使用 weather；現在時間日期使用 current_time；"
            "最近新聞使用 news；需要查網路的最新資訊使用 web_search；"
            "伺服器是否運作使用 server_status；居家感測器狀態使用 home_status；"
            "不需即時資料的簡單常識可使用 general_answer 並在 answer 填極短回答。"
            "不可假裝已查詢網路，不可產生 shell 指令。缺少地點時使用預設地點。"
        )
        user = "預設地點：{}\n使用者：{}".format(default_location, transcript)
        content, latency, timings = self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            self.config.get("max_plan_tokens", 160),
            response_schema=TOOL_SCHEMA,
            temperature=0.0,
        )
        plan = self._extract_json(content)
        plan["latency_ms"] = latency
        plan["timings"] = timings
        plan["source"] = "local_llm"
        return plan

    def answer_general(self, question):
        system = (
            "你是運行在 Jetson Nano 的繁體中文語音助理。"
            "回答最多三句，不使用 Markdown，不聲稱擁有即時資料。"
            "若問題需要最新資訊，明確說必須使用網路工具查詢。"
        )
        content, latency, timings = self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": question}],
            self.config.get("max_answer_tokens", 120),
            temperature=0.2,
        )
        return {"answer": content, "latency_ms": latency, "timings": timings}

    def summarize_tool_result(self, question, tool_name, result):
        system = (
            "你是繁體中文語音助理。只能根據提供的工具結果回答，最多三句。"
            "保留重要數值與來源，不得增加工具結果沒有的事實。"
        )
        user = "問題：{}\n工具：{}\n結果：{}".format(
            question, tool_name, json.dumps(result, ensure_ascii=False)
        )
        content, latency, timings = self._chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            self.config.get("max_answer_tokens", 120),
            temperature=0.1,
        )
        return {"answer": content, "latency_ms": latency, "timings": timings}
