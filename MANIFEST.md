# 專案內容清單

- `app.py`：主服務與 Dashboard 啟動入口
- `process_wav.py`：既有 WAV 的 Local/Gemini/Compare 測試
- `export_history.py`：SQLite 歷史紀錄匯出 CSV
- `config/config.json`：可直接修改的執行設定
- `src/audio.py`：USB MIC ALSA 收音與 VAD
- `src/whisper_local.py`：whisper.cpp adapter
- `src/local_llm.py`：Qwen 0.5B llama-server adapter
- `src/gemini_audio.py`：Gemini 完整音訊 REST adapter
- `src/router.py`：規則優先與本地模型工具路由
- `src/tools.py`：受控網路與本地工具
- `src/assistant.py`：四種模式與狀態機
- `src/web_server.py`：零依賴 Dashboard server
- `web/`：瀏覽器顯示介面
- `scripts/`：系統、CMake、Whisper、llama.cpp、模型及專案安裝
- `systemd/`：常駐服務
- `tests/`：單元測試
- `docs/`：架構、安全及教學實驗說明
