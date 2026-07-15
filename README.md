# Jetson Nano Edge Voice Assistant

這是一套針對 Jetson Nano 4GB 設計的半雙工居家語音助理與教學比較平台。

核心功能：

- USB 麥克風持續收音
- 能量式 VAD 自動切出一句話
- whisper.cpp 本地繁體中文 ASR
- Qwen2.5-0.5B Q4 本地工具路由與結果整理
- 天氣、時間、網路搜尋、新聞、Home Assistant、服務狀態工具
- Gemini 完整 WAV 音訊 API
- Local / Gemini / Compare / Hybrid 四種模式
- 本地 espeak-ng 語音回答
- 瀏覽器 Dashboard 與 SQLite 紀錄
- 純 Python 3.6+ 標準函式庫，不依賴 FastAPI 或新版 Google SDK

## 目錄

```text
edge_voice_assistant/
├── app.py
├── process_wav.py
├── export_history.py
├── config/config.example.json
├── src/
├── web/
├── scripts/
├── systemd/
├── tests/
├── docs/
├── samples/
└── data/
```

## 1. Jetson 系統準備

```bash
cd edge_voice_assistant
chmod +x scripts/*.sh
./scripts/install_system.sh
./scripts/install_cmake.sh
```

重新登入或重開機，使使用者加入 `audio` 群組。

## 2. 測試 USB 麥克風

```bash
arecord -l
./scripts/check_audio.sh default
```

若麥克風是 `card 1, device 0`：

```bash
./scripts/check_audio.sh plughw:1,0
```

然後修改 `config/config.json`：

```json
"audio": {"device": "plughw:1,0"}
```

## 3. 建置本地 ASR 與 LLM

```bash
./scripts/build_whisper.sh
./scripts/build_llama.sh
./scripts/download_models.sh
```

預設：

- Whisper multilingual tiny：`/opt/whisper.cpp/models/ggml-tiny.bin`
- llama-server：`/opt/llama.cpp/build/bin/llama-server`
- Qwen2.5-0.5B Q4：`/opt/models/qwen2.5-0.5b-instruct-q4_k_m.gguf`

若 tiny 中文準確度不足，可改用 base：

```bash
WHISPER_MODEL=base ./scripts/build_whisper.sh
```

並修改 config 的模型路徑。

## 4. 建立設定檔

```bash
cp config/config.example.json config/config.json
cp .env.example .env
```

測試時載入環境變數：

```bash
set -a
source .env
set +a
```

可選金鑰：

```bash
GEMINI_API_KEY=...
BRAVE_SEARCH_API_KEY=...
HOME_ASSISTANT_TOKEN=...
```

未設定 Brave Search 時，`web_search` 會退回 Wikipedia；天氣使用 Open-Meteo，不需要金鑰。

## 5. 啟動 llama-server

```bash
/opt/llama.cpp/build/bin/llama-server \
  -m /opt/models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
  --alias qwen2.5-0.5b-instruct \
  --host 127.0.0.1 --port 8080 \
  -c 1024 -t 4 -tb 4 -ngl 0 -n 160
```

確認：

```bash
curl http://127.0.0.1:8080/v1/models
```

## 6. 啟動 Dashboard

```bash
./scripts/run_dev.sh --mode local
```

瀏覽器開啟：

```text
http://JETSON_IP:8000
```

查詢 Jetson IP：

```bash
hostname -I
```

## 7. 模式

```bash
./scripts/run_dev.sh --mode local
./scripts/run_dev.sh --mode gemini
./scripts/run_dev.sh --mode compare
./scripts/run_dev.sh --mode hybrid
```

- Local：音訊不離開裝置；本地 Whisper + 0.5B + 受控工具。
- Gemini：完整音訊直接傳給 Gemini，再執行受控工具。
- Compare：同一份 WAV 執行兩次並列顯示。
- Hybrid：Local 優先，失敗或 unknown 時才送 Gemini。

## 8. 使用既有 WAV 測試

WAV 必須是 16-bit、16 kHz、mono。轉換：

```bash
ffmpeg -i input.mp3 -ar 16000 -ac 1 -c:a pcm_s16le test.wav
```

執行：

```bash
python3 process_wav.py --audio test.wav --mode compare
```

## 9. systemd 安裝

```bash
./scripts/install_project.sh
sudo nano /opt/edge-voice-assistant/config/config.json
sudo nano /etc/edge-voice-assistant.env
sudo systemctl enable --now edge-llama-server
sudo systemctl enable --now edge-voice-assistant
```

查看：

```bash
systemctl status edge-llama-server
systemctl status edge-voice-assistant
journalctl -u edge-voice-assistant -f
```

## 10. 常見問題

### 找不到麥克風

```bash
arecord -l
id
```

確認使用者在 `audio` 群組，並將裝置改成 `plughw:CARD,DEVICE`。

### Whisper 很慢

- 先用 tiny。
- context 和回答長度保持小。
- 不要同時開啟 Jetson 桌面與多個瀏覽器分頁。
- `BUILD_JOBS=2` 避免編譯時記憶體耗盡。

### 本地模型輸出錯誤工具

規則會優先處理天氣、時間、新聞及已知設備。其他問題才交給 0.5B。可在 `src/router.py` 增加規則，或將複雜問題切到 Hybrid。

### Gemini API 失敗

確認：

```bash
echo "$GEMINI_API_KEY"
ping -c 2 generativelanguage.googleapis.com
```

完整語音最長預設只有 15 秒，WAV 遠小於 inline audio 請求常見限制。

## 11. 測試與匯出

```bash
python3 -m unittest discover -s tests -v
python3 export_history.py --output results.csv
```

## 安全限制

本專案不讓 LLM 直接執行 Shell、開啟任意 URL 或自由控制 Home Assistant。所有工具與服務都必須寫進設定檔白名單。Web Dashboard 沒有登入功能，只應部署於可信任 LAN。
