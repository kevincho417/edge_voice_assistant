#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y \
  alsa-utils \
  build-essential \
  ca-certificates \
  curl \
  espeak-ng \
  ffmpeg \
  gcc-8 \
  g++-8 \
  git \
  libcurl4-openssl-dev \
  pkg-config \
  python3 \
  python3-dev \
  unzip \
  wget

sudo usermod -aG audio "${SUDO_USER:-$USER}"
echo "系統套件安裝完成。請重新登入或重開機，讓 audio 群組生效。"
