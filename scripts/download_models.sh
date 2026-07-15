#!/usr/bin/env bash
set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/opt/models}"
QWEN_FILE="qwen2.5-0.5b-instruct-q4_k_m.gguf"
QWEN_URL="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/${QWEN_FILE}?download=true"

sudo mkdir -p "$MODEL_DIR"
sudo chown "${SUDO_USER:-$USER}:${SUDO_USER:-$USER}" "$MODEL_DIR"
wget -c -O "$MODEL_DIR/$QWEN_FILE" "$QWEN_URL"
ls -lh "$MODEL_DIR/$QWEN_FILE"
