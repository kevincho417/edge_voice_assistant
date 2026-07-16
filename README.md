# Jetson Nano Edge Voice Assistant

這是一套針對 Jetson Nano 4GB 設計的半雙工居家語音助理與教學比較平台。

## 核心功能

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

## 網路設定（部署前必做）

Jetson Nano 需要透過網路下載套件和模型。以下提供兩種連線方式：

### 方式一：USB WiFi 接收器（推薦）

```bash
# Jetson 上插入 USB WiFi 後
sudo nmcli device wifi connect "你的WiFi名稱" password "你的WiFi密碼" ifname wlan0

# 若預設 gateway 走 eth0，需刪除讓流量走 WiFi
sudo ip route del default via 192.168.1.1 dev eth0
```

### 方式二：筆電 WiFi 共用（透過乙太網路線）

**Windows 筆電設定：**

1. 開啟「設定」→「網路和網際網路」→「行動熱點」或「WiFi」
2. 找到你正在使用的 WiFi 連線 → 「內容」→「共用」
3. 勾選「允許其他網路使用者透過這台電腦的網際網路連線來連線」
4. 家用網路連線選「乙太網路」→ 確定
5. Windows 會自動將乙太網路設為 `192.168.137.1`

**讓 Jetson 保持固定 IP（192.168.1.100）同時能上網：**

PowerShell（**以系統管理員身分執行**）：
```powershell
# 在乙太網路上加一個跟 Jetson 同網段的 IP
netsh interface ip add address "乙太網路" 192.168.1.1 255.255.255.0
```

**Jetson 上設定 gateway：**
```bash
sudo ip route add default via 192.168.1.1 dev eth0
```

### 驗證網路

```bash
# 測試外網連線
ping -c 2 8.8.8.8

# 測試 DNS
ping -c 2 github.com

# 測試 HTTPS（apt 可能不通，但 HTTPS 可以）
wget -q --spider https://github.com && echo "OK"
```

三個都通過即可開始部署。

---

## 快速部署（3 個指令）

在全新或重刷的 Jetson Nano 4GB 上（確認網路已通）：

```bash

# 2. Clone 並一鍵安裝（約 40-60 分鐘）
git clone https://github.com/kevincho417/edge_voice_assistant.git
cd edge_voice_assistant
bash scripts/setup_all.sh

# 3. （可選）設定 Gemini API key
nano .env

# 4. 啟動
bash scripts/watchdog.sh
```

### setup_all.sh 自動完成：

1. 安裝系統套件（apt 失敗時自動用 wget+dpkg 從 HTTPS 下載）
2. 安裝 cmake 3.28
3. 編譯 whisper.cpp v1.2.1（CPU）+ 下載 base 模型
4. 編譯 llama.cpp b2800 + 自動 patch NEON/CUDA（sm_53）
5. 下載 Gemma 2B Instruct Q4 模型
6. 安裝 opencc（簡轉繁）
7. 設定 config 和 .env

### 瀏覽器連線

瀏覽器麥克風需要 `localhost` 才能使用，透過 SSH tunnel 連線：

```bash
ssh -L 8000:127.0.0.1:8000 jetson@JETSON_IP
```

然後開啟 `http://localhost:8000`

## 目錄結構

```text
edge_voice_assistant/
├── app.py                  # 主程式入口
├── process_wav.py          # 離線 WAV 測試
├── export_history.py       # 匯出歷史紀錄
├── config/
│   ├── config.example.json # 設定範本
│   └── config.json         # 實際設定（git ignore）
├── src/
│   ├── assistant.py        # 語音助理狀態機
│   ├── audio.py            # ALSA 麥克風 + VAD
│   ├── whisper_local.py    # whisper.cpp 適配器 + opencc
│   ├── local_llm.py        # llama-server OpenAI 客戶端
│   ├── gemini_audio.py     # Gemini REST API（無 SDK）
│   ├── router.py           # 規則 + LLM 工具路由
│   ├── tools.py            # 白名單工具執行器
│   ├── tts.py              # espeak-ng 語音合成
│   ├── store.py            # SQLite 歷史儲存
│   ├── system_metrics.py   # GPU/RAM/溫度監控
│   ├── web_server.py       # HTTP Dashboard API
│   └── http_client.py      # urllib HTTP 客戶端
├── web/                    # 瀏覽器 Dashboard
├── scripts/
│   ├── setup_all.sh        # 一鍵部署腳本
│   ├── watchdog.sh         # 自動監控重啟
│   ├── install_system.sh   # 系統套件安裝
│   ├── install_cmake.sh    # cmake 升級
│   ├── build_whisper.sh    # whisper.cpp 編譯
│   ├── build_llama.sh      # llama.cpp 編譯
│   ├── download_models.sh  # 模型下載
│   └── run_dev.sh          # 開發模式啟動
├── systemd/                # systemd 服務檔
├── tests/                  # 單元測試
├── docs/                   # 架構文件
└── samples/                # 測試資料
```

## 系統架構

```
瀏覽器麥克風 → WAV 上傳 → Jetson Nano
                              ├── Local Pipeline:
                              │   ├── Whisper base (CPU, ~19s)
                              │   ├── 規則路由 → 工具執行 → 模板回答
                              │   └── LLM fallback → Gemma 2B (GPU)
                              └── Gemini Pipeline:
                                  ├── WAV → Gemini 2.5 Flash API
                                  └── ASR + 理解 + 工具路由 一步完成
```

## 模式說明

在 Dashboard 左上角下拉選單切換：

| 模式 | 說明 | 延遲 |
|------|------|------|
| **Local** | Whisper + Gemma 2B GPU + 工具（音訊不離開裝置） | ~20-50s |
| **Gemini** | WAV 直傳 Gemini 2.5 Flash（需 API key） | ~5-8s |
| **Compare** | 同一段 WAV 同時跑 Local 和 Gemini，並列比較 | 取較慢 |
| **Hybrid** | Local 優先，失敗或 unknown 時自動切 Gemini | 視情況 |

## 手動安裝步驟

若 `setup_all.sh` 不適用，可手動安裝：

### 1. 系統套件

```bash
# apt 方式
sudo apt-get update
sudo apt-get install -y gcc-8 g++-8 espeak-ng curl libcurl4-openssl-dev

# 若 apt 失敗（Ubuntu 18.04 EOL），用 wget 從 HTTPS 下載：
BASE="https://ports.ubuntu.com/ubuntu-ports/pool"
wget --no-check-certificate -O /tmp/gcc-8.deb "$BASE/universe/g/gcc-8/gcc-8_8.4.0-1ubuntu1~18.04_arm64.deb"
# （其他套件同理，詳見 setup_all.sh）
sudo dpkg -i /tmp/*.deb
```

### 2. cmake 3.13+

```bash
bash scripts/install_cmake.sh
```

### 3. whisper.cpp（CPU）

```bash
WHISPER_REF=v1.2.1 bash scripts/build_whisper.sh
wget -L -O /opt/whisper.cpp/models/ggml-base.bin \
  "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin"
```

Whisper 模型選擇：

| 模型 | 大小 | Jetson CPU 速度 | 中文準確度 |
|------|------|----------------|-----------|
| tiny | 77MB | ~9s | 差 |
| **base（推薦）** | 142MB | ~19s | 中等 |
| small | 461MB | ~70s | 好但太慢 |

### 4. llama.cpp b2800（CUDA GPU）

需要自動 patch NEON intrinsics（gcc-8 不支援 `vld1q_*_x4`）：

```bash
# setup_all.sh 已包含自動 patch，手動編譯請參考腳本中的 python3 patch 段落
export PATH="/usr/local/cuda/bin:$PATH"
cmake -S /opt/llama.cpp -B /opt/llama.cpp/build \
  -DCMAKE_BUILD_TYPE=Release \
  -DLLAMA_CUDA=ON -DLLAMA_NATIVE=ON -DLLAMA_CURL=ON \
  -DCMAKE_C_COMPILER=gcc-8 -DCMAKE_CXX_COMPILER=g++-8 \
  -DCMAKE_CUDA_ARCHITECTURES=53
cmake --build /opt/llama.cpp/build --config Release -j 1
```

### 5. 下載模型

```bash
wget -L -O /opt/models/gemma-2b-it-q4_k_m.gguf \
  "https://huggingface.co/lmstudio-community/gemma-1.1-2b-it-GGUF/resolve/main/gemma-1.1-2b-it-Q4_K_M.gguf"
```

### 6. 設定

```bash
cp .env.example .env
nano .env  # 加入 GEMINI_API_KEY（可選）
```

### 7. 啟動

```bash
# 推薦：Watchdog（自動啟動 llama-server + assistant，掛掉自動重啟）
bash scripts/watchdog.sh

# 或手動：
/opt/llama.cpp/build/bin/server \
  -m /opt/models/gemma-2b-it-q4_k_m.gguf \
  --alias gemma-2b-it \
  --host 127.0.0.1 --port 8080 \
  -c 256 -t 4 -ngl 99 -n 120 &

python3 app.py --mode local
```

`-ngl 99` 將所有層 offload 到 GPU（CUDA）。若記憶體不足可改 `-ngl 12`。

## 網路設定

Jetson Nano 透過筆電 WiFi 共用上網時：

```bash
# Jetson 上設定 gateway
sudo ip route add default via 192.168.1.1 dev eth0

# 筆電上（PowerShell 管理員）加 IP
netsh interface ip add address "乙太網路" 192.168.1.1 255.255.255.0
```

## Watchdog 功能

`scripts/watchdog.sh` 提供：

- 每 15 秒檢查 llama-server 和 assistant
- 服務掛掉自動重啟
- 可用記憶體 < 300MB 時自動清 cache
- 啟動時停用 Docker、清 cache 釋放記憶體

## 常見問題

### Whisper 辨識不準

- 使用 base 模型（比 tiny 好很多）
- opencc 自動簡轉繁
- 專業術語（如「捲積神經網路」）準確度有限，建議用 Gemini 模式

### llama-server 頻繁掛掉

Jetson Nano 4GB 記憶體有限，Gemma 2B 全 GPU offload 佔約 1.5GB。使用 watchdog.sh 自動重啟。也可用 `-ngl 12`（部分 GPU）減少記憶體但速度較慢。

### apt 安裝失敗

Ubuntu 18.04 已 EOL，`ports.ubuntu.com` 有時不可達。`setup_all.sh` 會自動切換到 wget 從 HTTPS 下載 .deb 安裝。

### Gemini API 失敗

```bash
# 確認 key 設定
grep GEMINI .env

# 測試連線
curl "https://generativelanguage.googleapis.com/v1beta/models?key=YOUR_KEY"
```

503/429 錯誤表示額度用完或服務忙，等待後重試或換 key。

## 測試與匯出

```bash
python3 -m unittest discover -s tests -v
python3 export_history.py --output results.csv
```

## 安全限制

- LLM 不能直接執行 Shell 或開啟任意 URL
- 所有工具和服務必須寫進設定檔白名單
- Web Dashboard 沒有登入功能，只應部署於可信任 LAN
- API key 存在 `.env`（git ignore，不會上傳）
