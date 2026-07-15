#!/usr/bin/env bash
set -euo pipefail

PREFIX="${WHISPER_PREFIX:-/opt/whisper.cpp}"
REF="${WHISPER_REF:-v1.8.5}"
MODEL="${WHISPER_MODEL:-tiny}"
JOBS="${BUILD_JOBS:-2}"

sudo rm -rf "$PREFIX"
sudo git clone --depth 1 --branch "$REF" https://github.com/ggml-org/whisper.cpp.git "$PREFIX"
sudo chown -R "${SUDO_USER:-$USER}:${SUDO_USER:-$USER}" "$PREFIX"

cmake -S "$PREFIX" -B "$PREFIX/build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DWHISPER_CUDA=OFF \
  -DCMAKE_C_COMPILER=gcc-8 \
  -DCMAKE_CXX_COMPILER=g++-8
cmake --build "$PREFIX/build" --config Release -j "$JOBS"

cd "$PREFIX"
sh ./models/download-ggml-model.sh "$MODEL"
echo "Whisper 完成: $PREFIX/build/bin/whisper-cli"
echo "模型: $PREFIX/models/ggml-${MODEL}.bin"
