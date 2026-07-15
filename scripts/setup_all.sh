#!/usr/bin/env bash
# One-click setup for Jetson Nano 4GB
# Usage: git clone https://github.com/kevincho417/edge_voice_assistant.git
#        cd edge_voice_assistant && bash scripts/setup_all.sh
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "=== Jetson Nano Edge Voice Assistant Setup ==="
echo "Project: $PROJECT_DIR"

# ─── 1. System packages ─────────────────────────────────────────────
echo "[1/7] Installing system packages..."
NEED_PKGS=""
which gcc-8    >/dev/null 2>&1 || NEED_PKGS="$NEED_PKGS gcc-8"
which g++-8    >/dev/null 2>&1 || NEED_PKGS="$NEED_PKGS g++-8"
which espeak-ng >/dev/null 2>&1 || NEED_PKGS="$NEED_PKGS espeak-ng"
which curl     >/dev/null 2>&1 || NEED_PKGS="$NEED_PKGS curl"
dpkg -s libcurl4-openssl-dev >/dev/null 2>&1 || NEED_PKGS="$NEED_PKGS libcurl4-openssl-dev"

if [ -z "$NEED_PKGS" ]; then
  echo "All system packages already installed"
else
  echo "Need:$NEED_PKGS"
  # Try apt first
  if sudo apt-get update -qq 2>/dev/null && sudo apt-get install -y $NEED_PKGS 2>/dev/null; then
    echo "Installed via apt"
  else
    echo "apt failed, downloading .deb via wget (HTTPS)..."
    DEB_DIR="/tmp/debs"
    mkdir -p "$DEB_DIR"
    BASE="https://ports.ubuntu.com/ubuntu-ports/pool"
    W="wget --no-check-certificate -q"
    $W -O "$DEB_DIR/cpp-8.deb"              "$BASE/universe/g/gcc-8/cpp-8_8.4.0-1ubuntu1~18.04_arm64.deb"
    $W -O "$DEB_DIR/gcc-8.deb"              "$BASE/universe/g/gcc-8/gcc-8_8.4.0-1ubuntu1~18.04_arm64.deb"
    $W -O "$DEB_DIR/g++-8.deb"              "$BASE/universe/g/gcc-8/g++-8_8.4.0-1ubuntu1~18.04_arm64.deb"
    $W -O "$DEB_DIR/libgcc-8-dev.deb"       "$BASE/main/g/gcc-8/libgcc-8-dev_8.4.0-1ubuntu1~18.04_arm64.deb"
    $W -O "$DEB_DIR/libstdc++-8-dev.deb"    "$BASE/universe/g/gcc-8/libstdc++-8-dev_8.4.0-1ubuntu1~18.04_arm64.deb"
    $W -O "$DEB_DIR/libasan5.deb"           "$BASE/main/g/gcc-8/libasan5_8.4.0-1ubuntu1~18.04_arm64.deb"
    $W -O "$DEB_DIR/libubsan1.deb"          "$BASE/main/g/gcc-8/libubsan1_8.4.0-1ubuntu1~18.04_arm64.deb"
    $W -O "$DEB_DIR/espeak-ng.deb"          "$BASE/universe/e/espeak-ng/espeak-ng_1.49.2+dfsg-1_arm64.deb"
    $W -O "$DEB_DIR/curl.deb"               "$BASE/main/c/curl/curl_7.58.0-2ubuntu3.24_arm64.deb"
    $W -O "$DEB_DIR/libcurl4-openssl-dev.deb" "$BASE/main/c/curl/libcurl4-openssl-dev_7.58.0-2ubuntu3.24_arm64.deb"
    sudo dpkg -i "$DEB_DIR"/*.deb 2>/dev/null || true
    echo "Installed via wget+dpkg"
  fi
fi
sudo usermod -aG audio "${SUDO_USER:-$USER}" 2>/dev/null || true

# Verify
for cmd in gcc-8 g++-8 espeak-ng curl; do
  which "$cmd" >/dev/null 2>&1 || { echo "ERROR: $cmd not found"; exit 1; }
done
echo "System packages OK"

# ─── 2. cmake ────────────────────────────────────────────────────────
echo "[2/7] Checking cmake..."
CMAKE_VER="$(cmake --version 2>/dev/null | head -1 | grep -oP '\d+\.\d+' | head -1)"
if [ "$(echo "$CMAKE_VER" | cut -d. -f1)" -ge 3 ] && [ "$(echo "$CMAKE_VER" | cut -d. -f2)" -ge 13 ] 2>/dev/null; then
  echo "cmake $CMAKE_VER OK (>= 3.13)"
else
  echo "Installing cmake 3.28..."
  bash "$PROJECT_DIR/scripts/install_cmake.sh"
fi

# ─── 3. Whisper.cpp (CPU, v1.2.1) ───────────────────────────────────
echo "[3/7] Building whisper.cpp..."
if [ -f /opt/whisper.cpp/build/bin/main ] && [ -f /opt/whisper.cpp/models/ggml-base.bin ]; then
  echo "whisper.cpp already built, skipping"
else
  WHISPER_PREFIX="/opt/whisper.cpp"
  sudo rm -rf "$WHISPER_PREFIX"
  sudo git clone --depth 1 --branch v1.2.1 https://github.com/ggml-org/whisper.cpp.git "$WHISPER_PREFIX"
  sudo chown -R "${SUDO_USER:-$USER}:${SUDO_USER:-$USER}" "$WHISPER_PREFIX"

  cmake -S "$WHISPER_PREFIX" -B "$WHISPER_PREFIX/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DWHISPER_CUDA=OFF \
    -DCMAKE_C_COMPILER=gcc-8 \
    -DCMAKE_CXX_COMPILER=g++-8
  cmake --build "$WHISPER_PREFIX/build" --config Release -j 2

  # Download base model (wget, not the buggy shell script)
  wget -L -O "$WHISPER_PREFIX/models/ggml-base.bin" \
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin"
  echo "Whisper: $WHISPER_PREFIX/build/bin/main"
fi

# ─── 4. llama.cpp b2800 with CUDA ───────────────────────────────────
echo "[4/7] Building llama.cpp with CUDA..."
if [ -f /opt/llama.cpp/build/bin/server ]; then
  echo "llama.cpp already built, skipping"
else
  LLAMA_PREFIX="/opt/llama.cpp"
  sudo rm -rf "$LLAMA_PREFIX"
  sudo git clone https://github.com/ggml-org/llama.cpp.git "$LLAMA_PREFIX"
  sudo chown -R "${SUDO_USER:-$USER}:${SUDO_USER:-$USER}" "$LLAMA_PREFIX"
  cd "$LLAMA_PREFIX" && git checkout b2800

  # Patch NEON intrinsics for gcc-8
  python3 - << 'PYEOF'
path = "/opt/llama.cpp/ggml-impl.h"
with open(path) as f:
    c = f.read()
marker = "#define ggml_vld1q_s8_x4  vld1q_s8_x4\n"
if marker in c and "ggml_vld1q_s8_x4_f" not in c:
    patch = """
#if defined(__aarch64__) && defined(__GNUC__) && __GNUC__ < 9
#undef ggml_vld1q_s8_x2
#undef ggml_vld1q_u8_x2
#undef ggml_vld1q_s8_x4
#undef ggml_vld1q_u8_x4
static inline int8x16x2_t __attribute__((always_inline)) ggml_vld1q_s8_x2_f(const int8_t * p) {
    int8x16x2_t r; r.val[0]=vld1q_s8(p); r.val[1]=vld1q_s8(p+16); return r; }
static inline uint8x16x2_t __attribute__((always_inline)) ggml_vld1q_u8_x2_f(const uint8_t * p) {
    uint8x16x2_t r; r.val[0]=vld1q_u8(p); r.val[1]=vld1q_u8(p+16); return r; }
static inline int8x16x4_t __attribute__((always_inline)) ggml_vld1q_s8_x4_f(const int8_t * p) {
    int8x16x4_t r; r.val[0]=vld1q_s8(p); r.val[1]=vld1q_s8(p+16); r.val[2]=vld1q_s8(p+32); r.val[3]=vld1q_s8(p+48); return r; }
static inline uint8x16x4_t __attribute__((always_inline)) ggml_vld1q_u8_x4_f(const uint8_t * p) {
    uint8x16x4_t r; r.val[0]=vld1q_u8(p); r.val[1]=vld1q_u8(p+16); r.val[2]=vld1q_u8(p+32); r.val[3]=vld1q_u8(p+48); return r; }
#define ggml_vld1q_s8_x2 ggml_vld1q_s8_x2_f
#define ggml_vld1q_u8_x2 ggml_vld1q_u8_x2_f
#define ggml_vld1q_s8_x4 ggml_vld1q_s8_x4_f
#define ggml_vld1q_u8_x4 ggml_vld1q_u8_x4_f
#endif
"""
    c = c[:c.index(marker)+len(marker)] + patch + c[c.index(marker)+len(marker):]
    with open(path, "w") as f:
        f.write(c)
    print("NEON patched")
else:
    print("Already patched or marker not found")
PYEOF

  export PATH="/usr/local/cuda/bin:$PATH"
  cmake -S "$LLAMA_PREFIX" -B "$LLAMA_PREFIX/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_CUDA=ON -DLLAMA_NATIVE=ON -DLLAMA_CURL=ON \
    -DCMAKE_C_COMPILER=gcc-8 -DCMAKE_CXX_COMPILER=g++-8 \
    -DCMAKE_CUDA_ARCHITECTURES=53
  cmake --build "$LLAMA_PREFIX/build" --config Release -j 1
  echo "llama-server: $LLAMA_PREFIX/build/bin/server"
fi

# ─── 5. Download model ──────────────────────────────────────────────
echo "[5/7] Downloading Gemma 2B model..."
sudo mkdir -p /opt/models
sudo chown "${SUDO_USER:-$USER}:${SUDO_USER:-$USER}" /opt/models
if [ -f /opt/models/gemma-2b-it-q4_k_m.gguf ]; then
  echo "Model already downloaded"
else
  wget -L -O /opt/models/gemma-2b-it-q4_k_m.gguf \
    "https://huggingface.co/lmstudio-community/gemma-1.1-2b-it-GGUF/resolve/main/gemma-1.1-2b-it-Q4_K_M.gguf"
fi

# ─── 6. Python deps ─────────────────────────────────────────────────
echo "[6/7] Installing opencc..."
pip3 install opencc-python-reimplemented 2>/dev/null || pip3 install --user opencc-python-reimplemented

# ─── 7. Config ───────────────────────────────────────────────────────
echo "[7/7] Setting up config..."
cd "$PROJECT_DIR"
[ -f .env ] || cp .env.example .env
[ -f config/config.json ] || cp config/config.example.json config/config.json

# Fix config path in .env to match actual project location
sed -i "s|EDGE_ASSISTANT_CONFIG=.*|EDGE_ASSISTANT_CONFIG=$PROJECT_DIR/config/config.json|" .env

python3 -c "
import json
with open('config/config.json') as f:
    cfg = json.load(f)
cfg['whisper']['binary'] = '/opt/whisper.cpp/build/bin/main'
cfg['whisper']['model'] = '/opt/whisper.cpp/models/ggml-base.bin'
with open('config/config.json', 'w') as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print('Config updated')
"

# Free memory
sudo systemctl stop docker 2>/dev/null || true
sudo systemctl disable docker 2>/dev/null || true
sudo sh -c "echo 3 > /proc/sys/vm/drop_caches" 2>/dev/null || true

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Start:"
echo "  bash scripts/watchdog.sh"
echo ""
echo "Browser (use SSH tunnel for mic access):"
echo "  ssh -L 8000:127.0.0.1:8000 jetson@\$(hostname -I | awk '{print \$1}')"
echo "  Open: http://localhost:8000"
echo ""
echo "Optional: edit .env to add GEMINI_API_KEY"
echo "=========================================="
