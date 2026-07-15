# -*- coding: utf-8 -*-
"""Allowlisted information tools. The LLM never receives arbitrary network or shell access."""
from __future__ import print_function

import datetime
import json
import os
import subprocess
import time
import urllib.parse
import xml.etree.ElementTree as ET

from .http_client import HttpError, encode_query, request_json, request_bytes


class ToolError(Exception):
    pass


WMO_ZH = {
    0: "晴朗", 1: "大致晴朗", 2: "局部多雲", 3: "陰天",
    45: "有霧", 48: "霧淞", 51: "毛毛雨", 53: "毛毛雨",
    55: "較強毛毛雨", 56: "凍毛毛雨", 57: "強凍毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "凍雨", 67: "強凍雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "陣雨", 81: "較強陣雨", 82: "強陣雨",
    85: "陣雪", 86: "強陣雪", 95: "雷雨", 96: "雷雨伴隨冰雹", 99: "強雷雨伴隨冰雹"
}


class ToolExecutor(object):
    def __init__(self, config):
        self.config = config
        self.cache = {}

    def execute(self, plan):
        handlers = {
            "weather": self.weather,
            "current_time": self.current_time,
            "web_search": self.web_search,
            "news": self.news,
            "server_status": self.server_status,
            "home_status": self.home_status,
        }
        handler = handlers.get(plan.tool)
        if handler is None:
            raise ToolError("工具 {} 不需要或不允許執行".format(plan.tool))
        started = time.time()
        result = handler(plan)
        result["tool_latency_ms"] = int((time.time() - started) * 1000)
        result["tool"] = plan.tool
        return result

    def _cache_get(self, key):
        item = self.cache.get(key)
        if item and item[0] > time.time():
            return item[1]
        return None

    def _cache_set(self, key, value, seconds):
        self.cache[key] = (time.time() + int(seconds), value)

    def _geocode(self, cfg, location):
        """Try Open-Meteo geocoding, fallback to Nominatim if blocked."""
        # Try with original name first, then Nominatim
        for query in [location]:
            geo_url = cfg.get("geocoding_url") + "?" + encode_query({
                "name": query, "count": 5, "language": "zh", "format": "json"
            })
            try:
                geo = request_json("GET", geo_url, timeout=15)
                results = geo.get("results") or []
                # Prefer Taiwan results
                for r in results:
                    if r.get("country_code") == "TW" or "台" in r.get("country", "") or "臺" in r.get("country", ""):
                        return r
                if results:
                    return results[0]
            except HttpError:
                pass
        # Fallback: Nominatim (OpenStreetMap) — handles Chinese natively, bias to Taiwan
        nom_url = "https://nominatim.openstreetmap.org/search?" + encode_query({
            "q": location, "format": "json", "limit": 1, "accept-language": "zh",
            "countrycodes": "tw",
        })
        try:
            nom = request_json("GET", nom_url, headers={
                "User-Agent": "EdgeVoiceAssistant/1.0"
            }, timeout=15)
            if nom:
                return {
                    "name": nom[0].get("display_name", location).split(",")[0],
                    "latitude": float(nom[0]["lat"]),
                    "longitude": float(nom[0]["lon"]),
                    "admin1": "",
                    "country": "",
                }
        except (HttpError, KeyError, ValueError, IndexError):
            pass
        return None

    def weather(self, plan):
        cfg = self.config.get("tools", {}).get("weather", {})
        if not cfg.get("enabled", True):
            raise ToolError("天氣工具未啟用")
        location = plan.location or self.config.get("assistant", {}).get("default_location", "Taipei")
        cache_key = "weather:" + location
        cached = self._cache_get(cache_key)
        if cached:
            result = dict(cached)
            result["cached"] = True
            return result

        place = self._geocode(cfg, location)
        if not place:
            raise ToolError("找不到地點：{}".format(location))

        forecast_url = cfg.get("forecast_url") + "?" + encode_query({
            "latitude": place.get("latitude"),
            "longitude": place.get("longitude"),
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": cfg.get("timezone", "Asia/Taipei"),
            "forecast_days": 3,
        })
        try:
            forecast = request_json("GET", forecast_url, timeout=20)
        except HttpError as exc:
            raise ToolError(str(exc))
        daily = forecast.get("daily", {})
        if not daily.get("time"):
            raise ToolError("天氣 API 沒有回傳每日預報")
        index = 0
        code = int(daily.get("weather_code", [0])[index])
        result = {
            "location": place.get("name", location),
            "admin1": place.get("admin1", ""),
            "country": place.get("country", ""),
            "date": daily["time"][index],
            "description": WMO_ZH.get(code, "天氣代碼 {}".format(code)),
            "weather_code": code,
            "temperature_max_c": daily.get("temperature_2m_max", [None])[index],
            "temperature_min_c": daily.get("temperature_2m_min", [None])[index],
            "precipitation_probability_max_percent": daily.get("precipitation_probability_max", [None])[index],
            "source": "Open-Meteo",
            "cached": False,
        }
        self._cache_set(cache_key, result, cfg.get("cache_seconds", 600))
        return result

    def current_time(self, plan):
        now = datetime.datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        return {
            "iso": now.isoformat(),
            "date": "{}年{}月{}日".format(now.year, now.month, now.day),
            "time": "{:02d}:{:02d}".format(now.hour, now.minute),
            "weekday": weekdays[now.weekday()],
            "source": "Jetson system clock",
        }

    def web_search(self, plan):
        cfg = self.config.get("tools", {}).get("web_search", {})
        if not cfg.get("enabled", True):
            raise ToolError("網路搜尋工具未啟用")
        query = plan.query.strip()
        if not query:
            raise ToolError("搜尋關鍵字是空的")
        provider = cfg.get("provider", "brave")
        if provider == "brave" and os.environ.get("BRAVE_SEARCH_API_KEY"):
            return self._brave_search(query, cfg)
        if cfg.get("fallback_wikipedia", True):
            return self._wikipedia_search(query, cfg)
        raise ToolError("未設定 BRAVE_SEARCH_API_KEY，且 Wikipedia fallback 已關閉")

    def _brave_search(self, query, cfg):
        url = cfg.get("brave_url") + "?" + encode_query({
            "q": query, "count": int(cfg.get("max_results", 5)), "search_lang": "zh-hant"
        })
        try:
            data = request_json(
                "GET", url,
                headers={"X-Subscription-Token": os.environ.get("BRAVE_SEARCH_API_KEY")},
                timeout=20,
            )
        except HttpError as exc:
            raise ToolError(str(exc))
        items = []
        for item in (data.get("web", {}).get("results") or [])[: int(cfg.get("max_results", 5))]:
            items.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "age": item.get("age", ""),
            })
        return {"query": query, "provider": "Brave Search", "results": items}

    def _wikipedia_search(self, query, cfg):
        url = "https://zh.wikipedia.org/w/api.php?" + encode_query({
            "action": "query", "list": "search", "srsearch": query,
            "format": "json", "utf8": 1, "srlimit": int(cfg.get("max_results", 5))
        })
        try:
            data = request_json("GET", url, timeout=20)
        except HttpError as exc:
            raise ToolError(str(exc))
        items = []
        for item in data.get("query", {}).get("search", []):
            title = item.get("title", "")
            snippet = item.get("snippet", "").replace("<span class=\"searchmatch\">", "").replace("</span>", "")
            items.append({
                "title": title,
                "url": "https://zh.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                "description": snippet,
            })
        return {"query": query, "provider": "Wikipedia", "results": items}

    def news(self, plan):
        cfg = self.config.get("tools", {}).get("news", {})
        if not cfg.get("enabled", True):
            raise ToolError("新聞工具未啟用")
        query = plan.query or "台灣 即時新聞"
        url = cfg.get("rss_url") + "?" + encode_query({
            "q": query,
            "hl": cfg.get("language", "zh-TW"),
            "gl": cfg.get("country", "TW"),
            "ceid": "{}:{}".format(cfg.get("country", "TW"), cfg.get("language", "zh-TW").split("-")[0])
        })
        try:
            _, _, raw = request_bytes("GET", url, headers={"User-Agent": "EdgeVoiceAssistant/1.0"}, timeout=20)
            root = ET.fromstring(raw)
        except Exception as exc:
            raise ToolError("新聞 RSS 讀取失敗: {}".format(exc))
        items = []
        for node in root.findall("./channel/item")[: int(cfg.get("max_results", 5))]:
            items.append({
                "title": node.findtext("title") or "",
                "url": node.findtext("link") or "",
                "published": node.findtext("pubDate") or "",
                "source": (node.findtext("source") or "Google News"),
            })
        return {"query": query, "provider": "Google News RSS", "results": items}

    def server_status(self, plan):
        cfg = self.config.get("tools", {}).get("server_status", {})
        if not cfg.get("enabled", True):
            raise ToolError("伺服器狀態工具未啟用")
        item = cfg.get("targets", {}).get(plan.entity)
        if not item:
            raise ToolError("不允許查詢的服務：{}".format(plan.entity))
        command = item.get("command")
        if not isinstance(command, list) or not command:
            raise ToolError("服務命令設定錯誤")
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise ToolError("服務狀態查詢逾時")
        return {
            "entity": plan.entity,
            "status": stdout.decode("utf-8", "replace").strip(),
            "return_code": process.returncode,
            "stderr": stderr.decode("utf-8", "replace").strip(),
            "source": "allowlisted local command",
        }

    def home_status(self, plan):
        cfg = self.config.get("tools", {}).get("home_assistant", {})
        if not cfg.get("enabled", False):
            raise ToolError("Home Assistant 尚未啟用")
        item = cfg.get("entities", {}).get(plan.entity)
        if not item:
            raise ToolError("不允許查詢的 Home Assistant entity")
        token = os.environ.get("HOME_ASSISTANT_TOKEN", "")
        if not token:
            raise ToolError("未設定 HOME_ASSISTANT_TOKEN")
        entity_id = item.get("entity_id")
        url = cfg.get("base_url").rstrip("/") + "/api/states/" + urllib.parse.quote(entity_id, safe=".")
        try:
            data = request_json("GET", url, headers={"Authorization": "Bearer " + token}, timeout=15)
        except HttpError as exc:
            raise ToolError(str(exc))
        return {
            "entity": plan.entity,
            "entity_id": entity_id,
            "state": data.get("state"),
            "unit": data.get("attributes", {}).get("unit_of_measurement", ""),
            "friendly_name": data.get("attributes", {}).get("friendly_name", plan.entity),
            "source": "Home Assistant",
        }
