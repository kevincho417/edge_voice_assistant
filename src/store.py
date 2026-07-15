# -*- coding: utf-8 -*-
"""SQLite history storage."""
from __future__ import print_function

import json
import os
import sqlite3
import threading
import time


class HistoryStore(object):
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def _init_db(self):
        with self.lock:
            conn = self._connect()
            try:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS turns ("
                    "id TEXT PRIMARY KEY, created_at REAL NOT NULL, mode TEXT NOT NULL, "
                    "audio_path TEXT, payload TEXT NOT NULL)"
                )
                conn.commit()
            finally:
                conn.close()

    def save(self, turn_id, mode, audio_path, payload):
        with self.lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO turns(id, created_at, mode, audio_path, payload) VALUES (?, ?, ?, ?, ?)",
                    (turn_id, time.time(), mode, audio_path, json.dumps(payload, ensure_ascii=False)),
                )
                conn.commit()
            finally:
                conn.close()

    def list(self, limit=50):
        with self.lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT id, created_at, mode, audio_path, payload FROM turns ORDER BY created_at DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
            finally:
                conn.close()
        results = []
        for row in rows:
            try:
                payload = json.loads(row[4])
            except ValueError:
                payload = {}
            results.append({
                "id": row[0], "created_at": row[1], "mode": row[2],
                "audio_path": row[3], "payload": payload,
            })
        return results
