# -*- coding: utf-8 -*-
"""whisper.cpp command-line adapter."""
from __future__ import print_function

import os
import subprocess
import time

try:
    import opencc
    _converter = opencc.OpenCC("s2t")
    def s2t(text):
        return _converter.convert(text)
except ImportError:
    def s2t(text):
        return text


class WhisperError(Exception):
    pass


class WhisperCpp(object):
    def __init__(self, config):
        self.config = config

    def available(self):
        return os.path.isfile(self.config.get("binary", "")) and os.path.isfile(
            self.config.get("model", "")
        )

    def transcribe(self, wav_path):
        binary = self.config.get("binary")
        model = self.config.get("model")
        if not os.path.isfile(binary):
            raise WhisperError("找不到 whisper-cli: {}".format(binary))
        if not os.path.isfile(model):
            raise WhisperError("找不到 Whisper 模型: {}".format(model))

        command = [
            binary,
            "-m", model,
            "-f", wav_path,
            "-l", str(self.config.get("language", "zh")),
            "-t", str(self.config.get("threads", 4)),
            "-nt",
            "--prompt", "以下是繁體中文語音的逐字稿。",
        ]
        started = time.time()
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = process.communicate(timeout=int(self.config.get("timeout_seconds", 120)))
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise WhisperError("Whisper 辨識逾時")

        if process.returncode != 0:
            raise WhisperError(
                "Whisper 失敗: {}".format(stderr.decode("utf-8", "replace").strip())
            )

        transcript = stdout.decode("utf-8", "replace").strip()

        transcript = " ".join(transcript.split())
        if not transcript:
            raise WhisperError("Whisper 沒有輸出文字")
        transcript = s2t(transcript)
        return {
            "transcript": transcript,
            "latency_ms": int((time.time() - started) * 1000),
            "backend": "whisper.cpp",
        }
