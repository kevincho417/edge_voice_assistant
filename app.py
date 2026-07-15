#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse
import os
import signal
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.assistant import VoiceAssistantService
from src.config import load_config
from src.web_server import DashboardServer


def parse_args():
    parser = argparse.ArgumentParser(description="Jetson Nano Edge Voice Assistant")
    parser.add_argument(
        "--config",
        default=os.environ.get("EDGE_ASSISTANT_CONFIG", os.path.join(PROJECT_ROOT, "config", "config.json")),
        help="JSON config path",
    )
    parser.add_argument("--mode", choices=["local", "gemini", "compare", "hybrid"])
    parser.add_argument("--listen", action="store_true", help="啟動後立即持續監聽")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)
    assistant = VoiceAssistantService(config)
    if args.mode:
        assistant.set_mode(args.mode)

    def shutdown(signum, frame):
        print("收到停止訊號 {}".format(signum))
        assistant.stop_event.set()
        assistant.stop_always_listening()
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    if args.listen:
        assistant.start_always_listening()
    server = DashboardServer(config, assistant)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("停止服務")


if __name__ == "__main__":
    main()
