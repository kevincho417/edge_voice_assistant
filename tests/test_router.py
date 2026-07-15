#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from src.router import RuleRouter


class RouterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "config", "config.example.json"), "r") as handle:
            cls.config = json.load(handle)
        cls.router = RuleRouter(cls.config)

    def test_weather(self):
        plan = self.router.route("今天台北會下雨嗎")
        self.assertEqual(plan.tool, "weather")
        self.assertEqual(plan.location, "台北")

    def test_time(self):
        self.assertEqual(self.router.route("現在幾點").tool, "current_time")

    def test_news(self):
        self.assertEqual(self.router.route("今天有什麼新聞").tool, "news")

    def test_server(self):
        plan = self.router.route("帕魯伺服器還活著嗎")
        self.assertEqual(plan.tool, "server_status")
        self.assertEqual(plan.entity, "palworld")

    def test_search(self):
        self.assertEqual(self.router.route("上網查一下 NVIDIA 最新 Jetson").tool, "web_search")


if __name__ == "__main__":
    unittest.main()
