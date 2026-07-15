# -*- coding: utf-8 -*-
"""Rule-first tool planning with optional local LLM fallback."""
from __future__ import print_function

import re


class ToolPlan(object):
    def __init__(self, tool="unknown", location="", date="", query="", entity="", answer="", confidence=0.0, source="rule"):
        self.tool = tool
        self.location = location
        self.date = date
        self.query = query
        self.entity = entity
        self.answer = answer
        self.confidence = float(confidence)
        self.source = source
        self.latency_ms = 0
        self.extra = {}

    def to_dict(self):
        data = {
            "tool": self.tool,
            "location": self.location,
            "date": self.date,
            "query": self.query,
            "entity": self.entity,
            "answer": self.answer,
            "confidence": self.confidence,
            "source": self.source,
            "latency_ms": self.latency_ms,
        }
        data.update(self.extra)
        return data

    @classmethod
    def from_dict(cls, data):
        plan = cls(
            tool=data.get("tool", "unknown"),
            location=data.get("location", ""),
            date=data.get("date", ""),
            query=data.get("query", ""),
            entity=data.get("entity", ""),
            answer=data.get("answer", ""),
            confidence=data.get("confidence", 0.0),
            source=data.get("source", "model"),
        )
        plan.latency_ms = int(data.get("latency_ms", 0))
        plan.extra = {key: value for key, value in data.items() if key not in plan.to_dict()}
        return plan


class RuleRouter(object):
    WEATHER_WORDS = ("天氣", "天气", "下雨", "降雨", "氣溫", "气温", "幾度", "几度", "颱風", "台风", "紫外線", "紫外线")
    TIME_WORDS = ("幾點", "几点", "現在時間", "现在时间", "今天幾號", "今天几号", "星期幾", "星期几", "日期")
    NEWS_WORDS = ("新聞", "新闻", "最新消息", "最近發生", "最近发生", "今日要聞", "今日要闻")
    SEARCH_WORDS = ("查一下", "搜尋", "搜索", "上網查", "上网查", "最新", "最近出的", "現在的", "现在的")

    def __init__(self, config):
        self.config = config
        self.default_location = config.get("assistant", {}).get("default_location", "Taipei")

    @staticmethod
    def _contains_any(text, words):
        lowered = text.lower()
        return any(word.lower() in lowered for word in words)

    def _extract_location(self, text):
        known = [
            "台北", "臺北", "新北", "桃園", "桃园", "新竹", "苗栗", "台中", "臺中",
            "彰化", "南投", "嘉義", "嘉义", "台南", "臺南", "高雄", "屏東", "屏东",
            "宜蘭", "宜兰", "花蓮", "花莲", "台東", "臺東", "台东", "基隆",
            "澎湖", "金門", "金门", "馬祖", "马祖"
        ]
        for name in known:
            if name in text:
                return name
        return self.default_location

    def _match_server(self, text):
        targets = self.config.get("tools", {}).get("server_status", {}).get("targets", {})
        lowered = text.lower()
        for key, item in targets.items():
            for alias in item.get("aliases", []):
                if str(alias).lower() in lowered:
                    return key
        return ""

    def _match_home_entity(self, text):
        entities = self.config.get("tools", {}).get("home_assistant", {}).get("entities", {})
        lowered = text.lower()
        for key, item in entities.items():
            for alias in item.get("aliases", []):
                if str(alias).lower() in lowered:
                    return key
        return ""

    def route(self, transcript):
        text = transcript.strip()
        if not text:
            return ToolPlan()

        if self._contains_any(text, self.WEATHER_WORDS):
            return ToolPlan(
                tool="weather", location=self._extract_location(text), date="today",
                query=text, confidence=0.98, source="rule"
            )
        if self._contains_any(text, self.TIME_WORDS):
            return ToolPlan(tool="current_time", query=text, confidence=0.99, source="rule")
        if self._contains_any(text, self.NEWS_WORDS):
            return ToolPlan(tool="news", query=text, confidence=0.92, source="rule")

        server = self._match_server(text)
        if server and self._contains_any(text, ("狀態", "有沒有開", "是否運作", "正常嗎", "還活著")):
            return ToolPlan(tool="server_status", entity=server, query=text, confidence=0.98, source="rule")

        home_entity = self._match_home_entity(text)
        if home_entity:
            return ToolPlan(tool="home_status", entity=home_entity, query=text, confidence=0.96, source="rule")

        if self._contains_any(text, self.SEARCH_WORDS):
            clean_query = re.sub(r"^(請|幫我|可以幫我)?(上網)?(查一下|搜尋)?", "", text).strip()
            return ToolPlan(tool="web_search", query=clean_query or text, confidence=0.82, source="rule")

        question_words = ("是什麼", "是什么", "什麼是", "什么是", "怎麼", "怎么",
                          "為什麼", "为什么", "如何", "可以嗎", "可以吗",
                          "解釋", "解释", "介紹", "介绍", "告訴我", "告诉我",
                          "?", "？", "嗎", "吗")
        if self._contains_any(text, question_words):
            return ToolPlan(tool="general_answer", query=text, confidence=0.75, source="rule")

        return ToolPlan(tool="unknown", query=text, confidence=0.2, source="rule")


class HybridRouter(object):
    def __init__(self, config, local_llm=None):
        self.config = config
        self.rules = RuleRouter(config)
        self.local_llm = local_llm

    def route(self, transcript):
        routing = self.config.get("routing", {})
        allowed = set(routing.get("allowed_tools", []))
        plan = self.rules.route(transcript)
        if plan.tool != "unknown" and plan.tool in allowed:
            return plan

        if routing.get("local_llm_fallback", True) and self.local_llm and self.local_llm.available():
            data = self.local_llm.plan(
                transcript,
                self.config.get("assistant", {}).get("default_location", "Taipei")
            )
            model_plan = ToolPlan.from_dict(data)
            if model_plan.tool not in allowed:
                model_plan.tool = "unknown"
                model_plan.confidence = 0.0
            return model_plan
        return plan
