#!/usr/bin/env bash
set -euo pipefail

DEVICE="${1:-default}"
OUTPUT="${2:-/tmp/edge-mic-test.wav}"

echo "ALSA 裝置："
arecord -l || true

echo "使用 $DEVICE 錄製 5 秒至 $OUTPUT"
arecord -D "$DEVICE" -f S16_LE -r 16000 -c 1 -d 5 "$OUTPUT"
echo "播放測試錄音"
aplay "$OUTPUT"
