#!/usr/bin/env bash
set -euo pipefail

PREFIX="${LLAMA_PREFIX:-/opt/llama.cpp}"
REF="${LLAMA_REF:-master}"
JOBS="${BUILD_JOBS:-2}"

sudo rm -rf "$PREFIX"
sudo git clone https://github.com/ggml-org/llama.cpp.git "$PREFIX"
sudo chown -R "${SUDO_USER:-$USER}:${SUDO_USER:-$USER}" "$PREFIX"
cd "$PREFIX"
if [[ "$REF" != "master" ]]; then
  git checkout "$REF"
fi

cmake -S "$PREFIX" -B "$PREFIX/build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_CUDA=OFF \
  -DGGML_NATIVE=ON \
  -DLLAMA_CURL=ON \
  -DCMAKE_C_COMPILER=gcc-8 \
  -DCMAKE_CXX_COMPILER=g++-8
cmake --build "$PREFIX/build" --config Release -j "$JOBS" --target llama-server llama-cli

echo "llama-server 完成: $PREFIX/build/bin/llama-server"
