#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/opt/edge-voice-assistant}"
RUN_USER="${RUN_USER:-${SUDO_USER:-$USER}}"

sudo mkdir -p "$INSTALL_DIR"
sudo cp -a "$SOURCE_DIR/." "$INSTALL_DIR/"
sudo chown -R "$RUN_USER:$RUN_USER" "$INSTALL_DIR"

if [[ ! -f "$INSTALL_DIR/config/config.json" ]]; then
  cp "$INSTALL_DIR/config/config.example.json" "$INSTALL_DIR/config/config.json"
fi

sudo mkdir -p /etc
if [[ ! -f /etc/edge-voice-assistant.env ]]; then
  sudo cp "$INSTALL_DIR/systemd/edge-voice-assistant.env.example" /etc/edge-voice-assistant.env
  sudo chmod 600 /etc/edge-voice-assistant.env
fi

sed -e "s|@USER@|$RUN_USER|g" -e "s|@PROJECT_ROOT@|$INSTALL_DIR|g" \
  "$INSTALL_DIR/systemd/edge-voice-assistant.service" | \
  sudo tee /etc/systemd/system/edge-voice-assistant.service >/dev/null
sed -e "s|@USER@|$RUN_USER|g" \
  "$INSTALL_DIR/systemd/llama-server.service" | \
  sudo tee /etc/systemd/system/edge-llama-server.service >/dev/null

sudo systemctl daemon-reload

echo "專案已安裝至 $INSTALL_DIR"
echo "下一步："
echo "1. 編輯 $INSTALL_DIR/config/config.json"
echo "2. 編輯 /etc/edge-voice-assistant.env"
echo "3. sudo systemctl enable --now edge-llama-server edge-voice-assistant"
