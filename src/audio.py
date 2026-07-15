# -*- coding: utf-8 -*-
"""ALSA microphone capture with an energy-based VAD."""
from __future__ import print_function

import audioop
import collections
import os
import subprocess
import time
import wave


class AudioError(Exception):
    pass


class AlsaVadRecorder(object):
    def __init__(self, config, level_callback=None):
        self.config = config
        self.level_callback = level_callback

    def _command(self):
        return [
            "arecord",
            "-q",
            "-D", str(self.config.get("device", "default")),
            "-t", "raw",
            "-f", "S16_LE",
            "-r", str(self.config.get("sample_rate", 16000)),
            "-c", str(self.config.get("channels", 1)),
        ]

    def record_utterance(self, output_path, stop_event=None):
        sample_rate = int(self.config.get("sample_rate", 16000))
        channels = int(self.config.get("channels", 1))
        sample_width = int(self.config.get("sample_width", 2))
        frame_ms = int(self.config.get("frame_ms", 20))
        frame_bytes = int(sample_rate * frame_ms / 1000.0) * sample_width * channels

        pre_roll_frames = max(1, int(self.config.get("pre_roll_ms", 400) / frame_ms))
        start_frames_required = max(1, int(self.config.get("start_speech_ms", 100) / frame_ms))
        end_silence_frames = max(1, int(self.config.get("end_silence_ms", 700) / frame_ms))
        max_frames = max(1, int(self.config.get("max_utterance_seconds", 15) * 1000 / frame_ms))
        max_wait_frames = max(1, int(self.config.get("max_wait_seconds", 30) * 1000 / frame_ms))

        vad_cfg = self.config.get("vad", {})
        calibration_frames = max(1, int(vad_cfg.get("calibration_ms", 800) / frame_ms))
        minimum_rms = int(vad_cfg.get("minimum_rms", 250))
        noise_multiplier = float(vad_cfg.get("noise_multiplier", 3.0))

        process = subprocess.Popen(
            self._command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        ring = collections.deque(maxlen=pre_roll_frames)
        utterance = []
        noise_samples = []
        speech_run = 0
        silence_run = 0
        started = False
        waited = 0
        peak_rms = 0
        start_time = time.time()

        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    raise AudioError("錄音已取消")

                frame = process.stdout.read(frame_bytes)
                if not frame or len(frame) < frame_bytes:
                    stderr = process.stderr.read().decode("utf-8", "replace")
                    raise AudioError("麥克風串流中斷: {}".format(stderr.strip()))

                rms = audioop.rms(frame, sample_width)
                peak_rms = max(peak_rms, rms)
                if self.level_callback:
                    normalized = min(1.0, float(rms) / 5000.0)
                    self.level_callback(rms, normalized)

                if len(noise_samples) < calibration_frames and not started:
                    noise_samples.append(rms)
                noise_floor = sum(noise_samples) / float(max(1, len(noise_samples)))
                threshold = max(minimum_rms, int(noise_floor * noise_multiplier))
                is_speech = rms >= threshold

                if not started:
                    waited += 1
                    ring.append(frame)
                    if is_speech:
                        speech_run += 1
                    else:
                        speech_run = 0
                    if speech_run >= start_frames_required:
                        started = True
                        utterance.extend(list(ring))
                        silence_run = 0
                    elif waited >= max_wait_frames:
                        raise AudioError("等待語音逾時")
                else:
                    utterance.append(frame)
                    if is_speech:
                        silence_run = 0
                    else:
                        silence_run += 1
                    if silence_run >= end_silence_frames:
                        break
                    if len(utterance) >= max_frames:
                        break
        finally:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            if self.level_callback:
                self.level_callback(0, 0.0)

        if not utterance:
            raise AudioError("沒有錄到有效語音")

        directory = os.path.dirname(output_path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"".join(utterance))

        duration = len(utterance) * frame_ms / 1000.0
        return {
            "path": output_path,
            "duration_seconds": round(duration, 3),
            "peak_rms": peak_rms,
            "threshold_rms": threshold,
            "capture_seconds": round(time.time() - start_time, 3),
        }
