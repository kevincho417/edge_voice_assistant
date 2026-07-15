#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, ROOT)

from src.config import load_config


class ConfigTest(unittest.TestCase):
    def test_load(self):
        cfg = load_config(os.path.join(ROOT, "config", "config.example.json"))
        self.assertTrue(os.path.isabs(cfg["storage"]["database"]))
        self.assertEqual(cfg["assistant"]["mode"], "local")


if __name__ == "__main__":
    unittest.main()
