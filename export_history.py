#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse
import csv
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from src.config import load_config
from src.store import HistoryStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=os.path.join(ROOT, "config", "config.json"))
    parser.add_argument("--output", default="assistant_history.csv")
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    config = load_config(args.config)
    store = HistoryStore(config["storage"]["database"])
    rows = store.list(args.limit)
    with open(args.output, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "id", "created_at", "mode", "local_transcript", "local_tool", "local_latency_ms",
            "gemini_transcript", "gemini_tool", "gemini_latency_ms"
        ])
        for row in rows:
            turn = row.get("payload", {})
            local = turn.get("local") or {}
            gemini = turn.get("gemini") or {}
            writer.writerow([
                row.get("id"), row.get("created_at"), row.get("mode"),
                local.get("transcript", ""), (local.get("plan") or {}).get("tool", ""), local.get("total_latency_ms", ""),
                gemini.get("transcript", ""), (gemini.get("plan") or {}).get("tool", ""), gemini.get("total_latency_ms", "")
            ])
    print("已輸出 {}".format(os.path.abspath(args.output)))


if __name__ == "__main__":
    main()
