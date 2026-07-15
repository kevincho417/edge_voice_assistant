# -*- coding: utf-8 -*-
"""Dependency-free HTTP server and browser dashboard API."""
from __future__ import print_function

import json
import mimetypes
import os
import socketserver
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .assistant import AssistantBusyError


class ThreadingHttpServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


class DashboardServer(object):
    def __init__(self, config, assistant):
        self.config = config
        self.assistant = assistant
        self.web_root = os.path.join(config.get("project_root"), "web")
        handler = self._make_handler()
        web_cfg = config.get("web", {})
        self.httpd = ThreadingHttpServer(
            (web_cfg.get("host", "0.0.0.0"), int(web_cfg.get("port", 8000))), handler
        )

    def _make_handler(self):
        dashboard = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "EdgeVoiceAssistant/1.0"

            def log_message(self, fmt, *args):
                print("[web] " + fmt % args)

            def _json(self, status, payload):
                raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(raw)

            def _read_json(self):
                length = int(self.headers.get("Content-Length", "0") or "0")
                if not length:
                    return {}
                raw = self.rfile.read(length)
                try:
                    return json.loads(raw.decode("utf-8"))
                except ValueError:
                    return {}

            def _static(self, relative):
                relative = relative.lstrip("/") or "index.html"
                safe = os.path.abspath(os.path.join(dashboard.web_root, relative))
                if not safe.startswith(os.path.abspath(dashboard.web_root) + os.sep) and safe != os.path.join(dashboard.web_root, "index.html"):
                    self.send_error(403)
                    return
                if not os.path.isfile(safe):
                    self.send_error(404)
                    return
                with open(safe, "rb") as handle:
                    raw = handle.read()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(safe)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(raw)

            def _audio(self, turn_id):
                history = dashboard.assistant.history(limit=1000)
                path = None
                for item in history:
                    if item.get("id") == turn_id:
                        path = item.get("audio_path")
                        break
                if not path or not os.path.isfile(path):
                    self.send_error(404)
                    return
                with open(path, "rb") as handle:
                    raw = handle.read()
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == "/api/status":
                    self._json(200, dashboard.assistant.status())
                    return
                if parsed.path == "/api/history":
                    query = parse_qs(parsed.query)
                    limit = int((query.get("limit") or ["30"])[0])
                    self._json(200, {"items": dashboard.assistant.history(min(limit, 200))})
                    return
                if parsed.path.startswith("/api/audio/"):
                    self._audio(parsed.path.rsplit("/", 1)[-1])
                    return
                if parsed.path == "/":
                    self._static("index.html")
                    return
                self._static(parsed.path)

            def do_POST(self):
                if self.path == "/api/record":
                    try:
                        dashboard.assistant.trigger_once()
                        self._json(202, {"ok": True})
                    except AssistantBusyError as exc:
                        self._json(409, {"ok": False, "error": str(exc)})
                    return
                if self.path == "/api/upload_audio":
                    try:
                        dashboard.assistant.trigger_from_upload(self.rfile, self.headers)
                        self._json(202, {"ok": True})
                    except AssistantBusyError as exc:
                        self._json(409, {"ok": False, "error": str(exc)})
                    except Exception as exc:
                        self._json(400, {"ok": False, "error": str(exc)})
                    return
                if self.path == "/api/listen/start":
                    dashboard.assistant.start_always_listening()
                    self._json(200, {"ok": True})
                    return
                if self.path == "/api/listen/stop":
                    dashboard.assistant.stop_always_listening()
                    self._json(200, {"ok": True})
                    return
                if self.path == "/api/mode":
                    data = self._read_json()
                    try:
                        mode = dashboard.assistant.set_mode(data.get("mode", "local"))
                        self._json(200, {"ok": True, "mode": mode})
                    except Exception as exc:
                        self._json(400, {"ok": False, "error": str(exc)})
                    return
                self._json(404, {"error": "not found"})

        return Handler

    def serve_forever(self):
        address = self.httpd.server_address
        print("Dashboard: http://{}:{}".format(address[0], address[1]))
        self.httpd.serve_forever()
