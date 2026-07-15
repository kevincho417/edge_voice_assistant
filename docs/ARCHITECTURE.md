# 系統架構

## Local Pipeline

```text
USB MIC
  → ALSA 16 kHz PCM
  → Energy VAD
  → 同一段 utterance.wav
  → whisper.cpp tiny/base
  → Rule-first router
  → Qwen2.5-0.5B（規則無法判斷時）
  → 受控 Python Tool Executor
  → Qwen2.5-0.5B 整理工具結果
  → espeak-ng
```

本地模型沒有任意網路權限。它只輸出結構化 ToolPlan，Python 驗證工具名稱及參數後才執行。

## Gemini Pipeline

```text
同一段 utterance.wav
  → Base64 inlineData
  → Gemini complete-audio API
  → transcript + ToolPlan JSON
  → 同一套受控 Tool Executor
  → Gemini 根據工具 JSON 整理回答
  → espeak-ng
```

Gemini 收到完整音訊，但即時天氣、新聞和搜尋資料仍由工具層取得，避免模型憑記憶猜測。

## 執行模式

- `local`：所有語音辨識、路由與回答整理在本地；網路只由指定工具使用。
- `gemini`：完整 WAV 傳給 Gemini，再使用本地受控工具。
- `compare`：同一份 WAV 依序執行 Local 與 Gemini，畫面並列結果。
- `hybrid`：Local 優先；Local 失敗或無法決定工具時才送 Gemini。

## 為何採半雙工

Jetson Nano 4GB 運算與記憶體有限。系統先完成一段話的 VAD 切句，再辨識與回答。TTS 播放期間不啟動新的錄音，避免喇叭回音造成重複辨識。使用 USB 耳麥可進一步降低回音。
