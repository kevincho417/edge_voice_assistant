# -*- coding: utf-8 -*-
"""Local speech synthesis through espeak-ng."""
from __future__ import print_function

import shutil
import subprocess


class TtsError(Exception):
    pass


class EspeakTts(object):
    def __init__(self, config):
        self.config = config

    def available(self):
        return bool(self.config.get("enabled", True) and shutil.which(self.config.get("binary", "espeak-ng")))

    def speak(self, text):
        if not text or not self.config.get("enabled", True):
            return
        binary = self.config.get("binary", "espeak-ng")
        command = [
            binary,
            "-v", str(self.config.get("voice", "cmn")),
            "-s", str(self.config.get("speed", 150)),
            "-a", str(self.config.get("volume", 100)),
            text,
        ]
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _, stderr = process.communicate(timeout=int(self.config.get("timeout_seconds", 60)))
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise TtsError("TTS 播放逾時")
        if process.returncode != 0:
            raise TtsError(stderr.decode("utf-8", "replace").strip())
