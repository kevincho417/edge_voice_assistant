# -*- coding: utf-8 -*-
"""Voice assistant orchestration and state machine."""
from __future__ import print_function

import copy
import json
import os
import threading
import time
import uuid

from .audio import AlsaVadRecorder, AudioError
from .gemini_audio import GeminiAudioClient, GeminiError
from .local_llm import LocalLlmClient, LocalLlmError
from .router import HybridRouter, ToolPlan
from .store import HistoryStore
from .system_metrics import collect_metrics
from .tools import ToolExecutor, ToolError
from .tts import EspeakTts, TtsError
from .whisper_local import WhisperCpp, WhisperError


VALID_MODES = ("local", "gemini", "compare", "hybrid")


class AssistantBusyError(Exception):
    pass


def now_id():
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def template_answer(tool_name, result):
    if tool_name == "weather":
        return (
            "{}今天{}，最高溫約{}度，最低溫約{}度，最高降雨機率約百分之{}。"
        ).format(
            result.get("location", "該地區"), result.get("description", ""),
            result.get("temperature_max_c", "未知"), result.get("temperature_min_c", "未知"),
            result.get("precipitation_probability_max_percent", "未知")
        )
    if tool_name == "current_time":
        return "今天是{}{}，現在時間是{}。".format(
            result.get("date", ""), result.get("weekday", ""), result.get("time", "")
        )
    if tool_name in ("web_search", "news"):
        items = result.get("results") or []
        if not items:
            return "目前沒有查到可用結果。"
        first = items[0]
        return "查到的第一筆結果是：{}。來源為{}。".format(
            first.get("title", "未命名"), first.get("source", result.get("provider", "網路搜尋"))
        )
    if tool_name == "server_status":
        status = result.get("status") or "未知"
        return "{}目前狀態為{}。".format(result.get("entity", "服務"), status)
    if tool_name == "home_status":
        return "{}目前是{}{}。".format(
            result.get("friendly_name", result.get("entity", "裝置")),
            result.get("state", "未知"), result.get("unit", "")
        )
    return "工具已執行完成。"


class VoiceAssistantService(object):
    def __init__(self, config):
        self.config = config
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.listen_stop_event = threading.Event()
        self.worker = None
        self.listener = None
        self.mode = config.get("assistant", {}).get("mode", "local")
        if self.mode not in VALID_MODES:
            self.mode = "local"

        self.state = {
            "state": "idle",
            "message": "待機",
            "mode": self.mode,
            "busy": False,
            "always_listening": False,
            "audio_level": 0.0,
            "audio_rms": 0,
            "last_turn": None,
            "last_error": "",
            "updated_at": time.time(),
        }

        self.recorder = AlsaVadRecorder(config.get("audio", {}), self._on_audio_level)
        self.whisper = WhisperCpp(config.get("whisper", {}))
        self.local_llm = LocalLlmClient(config.get("local_llm", {}))
        self.gemini = GeminiAudioClient(config.get("gemini", {}))
        self.router = HybridRouter(config, self.local_llm)
        self.tools = ToolExecutor(config)
        self.tts = EspeakTts(config.get("tts", {}))
        self.store = HistoryStore(config.get("storage", {}).get("database"))

    def _set_state(self, state=None, message=None, **kwargs):
        with self.lock:
            if state is not None:
                self.state["state"] = state
            if message is not None:
                self.state["message"] = message
            self.state.update(kwargs)
            self.state["updated_at"] = time.time()

    def _on_audio_level(self, rms, normalized):
        with self.lock:
            self.state["audio_rms"] = int(rms)
            self.state["audio_level"] = round(float(normalized), 3)
            self.state["updated_at"] = time.time()

    def status(self):
        with self.lock:
            result = copy.deepcopy(self.state)
        result["metrics"] = collect_metrics()
        result["capabilities"] = {
            "whisper": self.whisper.available(),
            "local_llm": self.local_llm.available(),
            "gemini": self.gemini.available(),
            "tts": self.tts.available(),
        }
        return result

    def set_mode(self, mode):
        if mode not in VALID_MODES:
            raise ValueError("不支援的模式：{}".format(mode))
        with self.lock:
            if self.state.get("busy"):
                raise AssistantBusyError("系統忙碌中，無法切換模式")
            self.mode = mode
            self.state["mode"] = mode
            self.state["updated_at"] = time.time()
        return mode

    def trigger_once(self):
        with self.lock:
            if self.state.get("busy"):
                raise AssistantBusyError("系統正在處理上一段語音")
            self.state["busy"] = True
            self.state["last_error"] = ""
        self.worker = threading.Thread(target=self._capture_and_process_safe)
        self.worker.daemon = True
        self.worker.start()

    def trigger_from_upload(self, rfile, headers):
        import cgi
        with self.lock:
            if self.state.get("busy"):
                raise AssistantBusyError("系統正在處理上一段語音")
            self.state["busy"] = True
            self.state["last_error"] = ""

        content_type = headers.get("Content-Type", "")
        if "multipart/form-data" in content_type:
            form = cgi.FieldStorage(fp=rfile, headers=headers, environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
            })
            file_item = form["audio"]
            audio_data = file_item.file.read()
        else:
            length = int(headers.get("Content-Length", 0))
            audio_data = rfile.read(length)

        turn_id = now_id()
        recordings_dir = self.config.get("storage", {}).get("recordings_dir")
        if not os.path.isdir(recordings_dir):
            os.makedirs(recordings_dir)
        wav_path = os.path.join(recordings_dir, turn_id + ".wav")
        with open(wav_path, "wb") as f:
            f.write(audio_data)

        self.worker = threading.Thread(target=self._process_uploaded_safe, args=(turn_id, wav_path))
        self.worker.daemon = True
        self.worker.start()

    def _process_uploaded_safe(self, turn_id, wav_path):
        try:
            self._process_uploaded(turn_id, wav_path)
        except Exception as exc:
            self._set_state(state="error", message=str(exc), last_error=str(exc))
        finally:
            self._set_state(state="idle", message="待機", busy=False, audio_level=0.0, audio_rms=0)

    def _process_uploaded(self, turn_id, wav_path):
        self._set_state(state="processing", message="處理上傳語音", turn_id=turn_id)
        mode = self.mode
        turn = {
            "id": turn_id,
            "mode": mode,
            "audio": {"path": wav_path, "source": "browser_upload"},
            "audio_url": "/api/audio/{}".format(turn_id),
            "local": None,
            "gemini": None,
            "selected": None,
            "created_at": time.time(),
        }

        if mode in ("local", "compare", "hybrid"):
            turn["local"] = self.run_local(wav_path)
        if mode in ("gemini", "compare"):
            turn["gemini"] = self.run_gemini(wav_path)
        elif mode == "hybrid":
            local_result = turn.get("local") or {}
            if (not local_result.get("ok")) or local_result.get("plan", {}).get("tool") == "unknown":
                if self.gemini.available():
                    turn["gemini"] = self.run_gemini(wav_path)

        turn["selected"] = self._select_result(turn)
        self.store.save(turn_id, mode, wav_path, turn)
        self._set_state(state="completed", message="處理完成", last_turn=turn)

        selected = turn.get("selected") or {}
        answer = selected.get("answer", "")
        if answer and self.config.get("assistant", {}).get("speak_response", True):
            self._set_state(state="speaking", message="播放本地語音回答")
            try:
                self.tts.speak(answer)
            except TtsError as exc:
                selected["tts_error"] = str(exc)

        if not self.config.get("storage", {}).get("keep_recordings", True):
            try:
                os.remove(wav_path)
            except OSError:
                pass

    def _capture_and_process_safe(self):
        try:
            self.capture_and_process()
        except Exception as exc:
            self._set_state(state="error", message=str(exc), last_error=str(exc))
        finally:
            self._set_state(state="idle", message="待機", busy=False, audio_level=0.0, audio_rms=0)

    def capture_and_process(self):
        turn_id = now_id()
        recordings_dir = self.config.get("storage", {}).get("recordings_dir")
        if not os.path.isdir(recordings_dir):
            os.makedirs(recordings_dir)
        wav_path = os.path.join(recordings_dir, turn_id + ".wav")

        self._set_state(state="listening", message="等待使用者說話", turn_id=turn_id)
        audio_meta = self.recorder.record_utterance(wav_path, stop_event=self.stop_event)
        self._set_state(state="processing", message="處理語音", audio_level=0.0)

        mode = self.mode
        turn = {
            "id": turn_id,
            "mode": mode,
            "audio": audio_meta,
            "audio_url": "/api/audio/{}".format(turn_id),
            "local": None,
            "gemini": None,
            "selected": None,
            "created_at": time.time(),
        }

        if mode in ("local", "compare", "hybrid"):
            turn["local"] = self.run_local(wav_path)
        if mode in ("gemini", "compare"):
            turn["gemini"] = self.run_gemini(wav_path)
        elif mode == "hybrid":
            local_result = turn.get("local") or {}
            if (not local_result.get("ok")) or local_result.get("plan", {}).get("tool") == "unknown":
                if self.gemini.available():
                    turn["gemini"] = self.run_gemini(wav_path)

        turn["selected"] = self._select_result(turn)
        self.store.save(turn_id, mode, wav_path, turn)
        self._set_state(state="completed", message="處理完成", last_turn=turn)

        selected = turn.get("selected") or {}
        answer = selected.get("answer", "")
        if answer and self.config.get("assistant", {}).get("speak_response", True):
            self._set_state(state="speaking", message="播放本地語音回答")
            try:
                self.tts.speak(answer)
            except TtsError as exc:
                selected["tts_error"] = str(exc)

        if not self.config.get("storage", {}).get("keep_recordings", True):
            try:
                os.remove(wav_path)
            except OSError:
                pass
        return turn

    def _select_result(self, turn):
        mode = turn.get("mode")
        local = turn.get("local")
        gemini = turn.get("gemini")
        if mode == "local":
            return local
        if mode == "gemini":
            return gemini
        if mode == "hybrid":
            if local and local.get("ok") and local.get("plan", {}).get("tool") != "unknown":
                return local
            return gemini or local
        preference = self.config.get("assistant", {}).get("compare_speak_method", "local")
        if preference == "gemini":
            return gemini or local
        return local or gemini

    def run_local(self, wav_path):
        started = time.time()
        result = {"method": "local", "ok": False}
        try:
            self._set_state(state="local_asr", message="本地 Whisper 辨識中")
            asr = self.whisper.transcribe(wav_path)
            transcript = asr["transcript"]
            self._set_state(state="local_route", message="本地工具路由中")
            plan = self.router.route(transcript)
            plan_dict = plan.to_dict()

            answer = ""
            tool_result = None
            answer_latency = 0
            if plan.tool == "general_answer":
                if plan.answer:
                    answer = plan.answer
                elif self.local_llm.available():
                    generated = self.local_llm.answer_general(transcript)
                    answer = generated["answer"]
                    answer_latency = generated.get("latency_ms", 0)
                else:
                    answer = "本地小模型目前未啟動，無法回答一般問題。"
            elif plan.tool == "unknown":
                answer = "我無法確定要使用哪個工具，請換個方式描述。"
            else:
                self._set_state(state="local_tool", message="執行受控資訊工具")
                tool_result = self.tools.execute(plan)
                answer = template_answer(plan.tool, tool_result)

            result.update({
                "ok": True,
                "transcript": transcript,
                "asr": asr,
                "plan": plan_dict,
                "tool_result": tool_result,
                "answer": answer,
                "answer_latency_ms": answer_latency,
                "total_latency_ms": int((time.time() - started) * 1000),
            })
        except (WhisperError, LocalLlmError, ToolError, Exception) as exc:
            result["error"] = str(exc)
            result["total_latency_ms"] = int((time.time() - started) * 1000)
        return result

    def run_gemini(self, wav_path):
        started = time.time()
        result = {"method": "gemini", "ok": False}
        try:
            self._set_state(state="gemini_audio", message="完整語音傳送至 Gemini")
            plan_data = self.gemini.plan_from_audio(
                wav_path,
                self.config.get("assistant", {}).get("default_location", "Taipei")
            )
            plan = ToolPlan.from_dict(plan_data)
            allowed = set(self.config.get("routing", {}).get("allowed_tools", []))
            if plan.tool not in allowed:
                raise GeminiError("Gemini 選擇了未允許的工具")

            answer = ""
            tool_result = None
            answer_latency = 0
            if plan.tool == "general_answer":
                answer = plan.answer or "Gemini 未提供回答。"
            elif plan.tool == "unknown":
                answer = "Gemini 無法判斷這段語音的需求。"
            else:
                self._set_state(state="gemini_tool", message="Gemini 路徑執行受控工具")
                tool_result = self.tools.execute(plan)
                self._set_state(state="gemini_answer", message="Gemini 整理工具結果")
                generated = self.gemini.summarize_tool_result(
                    plan_data.get("transcript", ""), plan.tool, tool_result
                )
                answer = generated["answer"]
                answer_latency = generated.get("latency_ms", 0)

            result.update({
                "ok": True,
                "transcript": plan_data.get("transcript", ""),
                "plan": plan.to_dict(),
                "tool_result": tool_result,
                "answer": answer,
                "audio_plan_latency_ms": plan_data.get("latency_ms", 0),
                "answer_latency_ms": answer_latency,
                "total_latency_ms": int((time.time() - started) * 1000),
            })
        except (GeminiError, ToolError, Exception) as exc:
            result["error"] = str(exc)
            result["total_latency_ms"] = int((time.time() - started) * 1000)
        return result

    def start_always_listening(self):
        with self.lock:
            if self.listener and self.listener.is_alive():
                return
            self.listen_stop_event.clear()
            self.state["always_listening"] = True
        self.listener = threading.Thread(target=self._listen_loop)
        self.listener.daemon = True
        self.listener.start()

    def stop_always_listening(self):
        self.listen_stop_event.set()
        self._set_state(always_listening=False)

    def _listen_loop(self):
        try:
            while not self.listen_stop_event.is_set():
                with self.lock:
                    busy = self.state.get("busy")
                if not busy:
                    try:
                        self.trigger_once()
                    except AssistantBusyError:
                        pass
                while self.worker and self.worker.is_alive() and not self.listen_stop_event.is_set():
                    time.sleep(0.2)
                time.sleep(0.3)
        finally:
            self._set_state(always_listening=False)

    def history(self, limit=50):
        return self.store.list(limit=limit)
