#!/usr/bin/env bash
# One-click setup for Jetson Nano 4GB
# Usage: git clone https://github.com/kevincho417/edge_voice_assistant.git
#        cd edge_voice_assistant && bash scripts/setup_all.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "=== Jetson Nano Edge Voice Assistant Setup ==="
echo "Project: $PROJECT_DIR"

# 1. System packages
echo "[1/7] Installing system packages..."
bash "$PROJECT_DIR/scripts/install_system.sh"

# 2. Install newer cmake
echo "[2/7] Installing cmake 3.28..."
bash "$PROJECT_DIR/scripts/install_cmake.sh"

# 3. Build whisper.cpp (CPU, v1.2.1)
echo "[3/7] Building whisper.cpp v1.2.1 (CPU)..."
export WHISPER_REF=v1.2.1
bash "$PROJECT_DIR/scripts/build_whisper.sh"
# Download base model
wget -L -O /opt/whisper.cpp/models/ggml-base.bin \
  "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin"

# 4. Build llama.cpp b2800 with CUDA + patches
echo "[4/7] Building llama.cpp b2800 with CUDA..."
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
PYEOF

export PATH="/usr/local/cuda/bin:$PATH"
cmake -S "$LLAMA_PREFIX" -B "$LLAMA_PREFIX/build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DLLAMA_CUDA=ON -DLLAMA_NATIVE=ON -DLLAMA_CURL=ON \
  -DCMAKE_C_COMPILER=gcc-8 -DCMAKE_CXX_COMPILER=g++-8 \
  -DCMAKE_CUDA_ARCHITECTURES=53
cmake --build "$LLAMA_PREFIX/build" --config Release -j 1
echo "llama-server: $LLAMA_PREFIX/build/bin/server"

# 5. Download models
echo "[5/7] Downloading Gemma 2B model..."
sudo mkdir -p /opt/models
sudo chown "${SUDO_USER:-$USER}:${SUDO_USER:-$USER}" /opt/models
wget -L -O /opt/models/gemma-2b-it-q4_k_m.gguf \
  "https://huggingface.co/lmstudio-community/gemma-1.1-2b-it-GGUF/resolve/main/gemma-1.1-2b-it-Q4_K_M.gguf"

# 6. Install opencc
echo "[6/7] Installing opencc..."
pip3 install opencc-python-reimplemented

# 7. Setup config and env
echo "[7/7] Setting up config..."
cd "$PROJECT_DIR"
if [ ! -f config/config.json ]; then
  cp config/config.example.json config/config.json
fi
if [ ! -f .env ]; then
  cp .env.example .env
fi

# Update config for current setup
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

# Stop docker to save memory
sudo systemctl stop docker 2>/dev/null || true
sudo systemctl disable docker 2>/dev/null || true

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit .env and add your GEMINI_API_KEY (optional)"
echo "2. Start with watchdog:"
echo "   bash scripts/watchdog.sh"
echo "3. Open browser: http://JETSON_IP:8000"
echo "   Or use SSH tunnel: ssh -L 8000:127.0.0.1:8000 jetson@JETSON_IP"
echo "   Then open: http://localhost:8000"
