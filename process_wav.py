#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run an existing 16 kHz mono PCM WAV through Local/Gemini/Compare."""
from __future__ import print_function

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from src.assistant import VoiceAssistantService
from src.config import load_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--mode", choices=["local", "gemini", "compare", "hybrid"], default="compare")
    parser.add_argument("--config", default=os.path.join(ROOT, "config", "config.json"))
    args = parser.parse_args()

    config = load_config(args.config)
    service = VoiceAssistantService(config)
    result = {"mode": args.mode, "audio": os.path.abspath(args.audio)}
    if args.mode in ("local", "compare", "hybrid"):
        result["local"] = service.run_local(args.audio)
    if args.mode in ("gemini", "compare"):
        result["gemini"] = service.run_gemini(args.audio)
    elif args.mode == "hybrid":
        local = result.get("local", {})
        if (not local.get("ok")) or (local.get("plan", {}).get("tool") == "unknown"):
            result["gemini"] = service.run_gemini(args.audio)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
