# -*- coding: utf-8 -*-
"""Small JSON HTTP client based only on urllib."""
from __future__ import print_function

import json
import socket
import urllib.error
import urllib.parse
import urllib.request


class HttpError(Exception):
    def __init__(self, message, status=None, body=None):
        Exception.__init__(self, message)
        self.status = status
        self.body = body


def encode_query(params):
    cleaned = {}
    for key, value in params.items():
        if value is not None:
            cleaned[key] = value
    return urllib.parse.urlencode(cleaned)


def request_bytes(method, url, data=None, headers=None, timeout=20):
    request = urllib.request.Request(url=url, data=data, headers=headers or {})
    request.get_method = lambda: method.upper()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.getcode(), response.headers, response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()
        raise HttpError(
            "HTTP {} {}".format(exc.code, url),
            status=exc.code,
            body=body.decode("utf-8", "replace"),
        )
    except (urllib.error.URLError, socket.timeout) as exc:
        raise HttpError("網路請求失敗 {}: {}".format(url, exc))


def request_json(method, url, payload=None, headers=None, timeout=20):
    request_headers = {"Accept": "application/json", "User-Agent": "EdgeVoiceAssistant/1.0"}
    if headers:
        request_headers.update(headers)
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    _, _, raw = request_bytes(method, url, data=data, headers=request_headers, timeout=timeout)
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise HttpError("回傳內容不是合法 JSON: {}".format(exc), body=raw[:1000])
