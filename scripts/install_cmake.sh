#!/usr/bin/env bash
set -euo pipefail

VERSION="${CMAKE_VERSION:-3.28.3}"
ARCH="$(uname -m)"
case "$ARCH" in
  aarch64|arm64) PACKAGE_ARCH="aarch64" ;;
  x86_64|amd64) PACKAGE_ARCH="x86_64" ;;
  *) echo "不支援的架構: $ARCH" >&2; exit 1 ;;
esac

URL="https://github.com/Kitware/CMake/releases/download/v${VERSION}/cmake-${VERSION}-linux-${PACKAGE_ARCH}.tar.gz"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

wget -O "$TMP/cmake.tar.gz" "$URL"
tar -xzf "$TMP/cmake.tar.gz" -C "$TMP"
sudo rm -rf "/opt/cmake-${VERSION}"
sudo mv "$TMP/cmake-${VERSION}-linux-${PACKAGE_ARCH}" "/opt/cmake-${VERSION}"
sudo ln -sf "/opt/cmake-${VERSION}/bin/cmake" /usr/local/bin/cmake
sudo ln -sf "/opt/cmake-${VERSION}/bin/ctest" /usr/local/bin/ctest
sudo ln -sf "/opt/cmake-${VERSION}/bin/cpack" /usr/local/bin/cpack
cmake --version
