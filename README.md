# Jetson Nano Edge Voice Assistant

這是一套針對 Jetson Nano 4GB 設計的半雙工居家語音助理與教學比較平台。

核心功能：

- 瀏覽器麥克風錄音（透過 Web Audio API 上傳 WAV）
- whisper.cpp base 本地繁體中文 ASR（CPU）+ opencc 簡轉繁
- Gemma 2B Instruct (Google) 本地 LLM（CUDA GPU 加速，19 層全 offload）
- 規則優先工具路由 + LLM fallback
- 天氣（Open-Meteo + Nominatim）、時間、網路搜尋、新聞、Home Assistant、服務狀態工具
- Gemini 2.5 Flash 完整 WAV 音訊 API（雲端對比模式）
- Local / Gemini / Compare / Hybrid 四種模式
- 本地 espeak-ng 語音回答
- 瀏覽器 Dashboard（GPU 使用率、RAM、SWAP 即時監控）
- SQLite 歷史紀錄
- Watchdog 自動重啟 + 記憶體保護
- 純 Python 3.6+ 標準函式庫（+ opencc），不依賴 FastAPI 或新版 Google SDK

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

## 快速部署（一鍵安裝）

```bash
git clone https://github.com/kevincho417/edge_voice_assistant.git
cd edge_voice_assistant
bash scripts/setup_all.sh
```

此腳本自動完成以下所有步驟（約 30-60 分鐘）。若需手動安裝，請繼續閱讀。

## 1. Jetson 系統準備

```bash
cd edge_voice_assistant
chmod +x scripts/*.sh
./scripts/install_system.sh
./scripts/install_cmake.sh
```

重新登入或重開機，使使用者加入 `audio` 群組。

## 2. 音訊輸入

本專案使用**瀏覽器麥克風**錄音（透過 Web Audio API），麥克風插在筆電上即可，不需要接在 Jetson 上。

若要使用 Jetson 上的 USB 麥克風，修改 `config/config.json`：

```json
"audio": {"device": "plughw:2,0"}
```

裝置編號可用 `arecord -l` 查詢。

## 3. 建置本地 ASR 與 LLM

```bash
./scripts/build_whisper.sh
./scripts/build_llama.sh
./scripts/download_models.sh
```

預設：

- Whisper base（推薦）：`/opt/whisper.cpp/models/ggml-base.bin`
- llama-server（CUDA）：`/opt/llama.cpp/build/bin/server`
- Gemma 2B Instruct Q4：`/opt/models/gemma-2b-it-q4_k_m.gguf`

Whisper 模型選擇：

| 模型 | 大小 | Jetson CPU 速度 | 中文準確度 |
|------|------|----------------|-----------|
| tiny | 77MB | ~9s | 差 |
| base（推薦）| 142MB | ~19s | 中等 |
| small | 461MB | ~70s | 好但太慢 |

注意：Jetson Nano CUDA 10.2 需要特殊 patch 才能編譯 llama.cpp（NEON intrinsics + cuBLAS 相容）。詳見 scripts/ 中的編譯腳本。

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
/opt/llama.cpp/build/bin/server \
  -m /opt/models/gemma-2b-it-q4_k_m.gguf \
  --alias gemma-2b-it \
  --host 127.0.0.1 --port 8080 \
  -c 256 -t 4 -ngl 99 -n 120
```

`-ngl 99` 將所有層 offload 到 GPU（CUDA）。若記憶體不足可改 `-ngl 12`。

確認：

```bash
curl http://127.0.0.1:8080/v1/models
```

## 6. 啟動（推薦使用 Watchdog）

```bash
bash scripts/watchdog.sh
```

Watchdog 會自動啟動 llama-server 和 Dashboard，並每 15 秒檢查服務狀態，掛掉自動重啟，記憶體不足時自動清 cache。

或手動啟動：

```bash
./scripts/run_dev.sh --mode local
```

## 7. 瀏覽器連線

因為瀏覽器麥克風需要 `localhost` 才能使用，建議透過 SSH tunnel：

```bash
ssh -L 8000:127.0.0.1:8000 jetson@JETSON_IP
```

然後開啟 `http://localhost:8000`

## 8. 模式

在 Dashboard 左上角下拉選單切換：

- **Local**：Whisper base ASR + Gemma 2B GPU + 受控工具（音訊不離開裝置）
- **Gemini**：完整 WAV 傳給 Gemini 2.5 Flash，一步完成 ASR + 理解
- **Compare**：同一份 WAV 同時跑 Local 和 Gemini，並列比較
- **Hybrid**：Local 優先，失敗或 unknown 時自動切到 Gemini

## 9. 使用既有 WAV 測試

WAV 必須是 16-bit、16 kHz、mono。轉換：

```bash
ffmpeg -i input.mp3 -ar 16000 -ac 1 -c:a pcm_s16le test.wav
```

執行：

```bash
python3 process_wav.py --audio test.wav --mode compare
```

## 10. systemd 安裝

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

## 11. 常見問題

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

規則會優先處理天氣、時間、新聞及已知設備。問句（含「是什麼」「如何」等）自動走 general_answer。其他問題交給 Gemma 2B LLM fallback。可在 `src/router.py` 增加規則，或將複雜問題切到 Hybrid。

### llama-server 頻繁掛掉

Jetson Nano 4GB 記憶體有限，Gemma 2B 全 GPU offload 佔約 1.5GB。使用 watchdog.sh 自動重啟。也可用 `-ngl 12`（部分 GPU）減少記憶體但速度較慢。

### Gemini API 失敗

確認：

```bash
echo "$GEMINI_API_KEY"
ping -c 2 generativelanguage.googleapis.com
```

完整語音最長預設只有 15 秒，WAV 遠小於 inline audio 請求常見限制。

## 12. 測試與匯出

```bash
python3 -m unittest discover -s tests -v
python3 export_history.py --output results.csv
```

## 安全限制

本專案不讓 LLM 直接執行 Shell、開啟任意 URL 或自由控制 Home Assistant。所有工具與服務都必須寫進設定檔白名單。Web Dashboard 沒有登入功能，只應部署於可信任 LAN。
