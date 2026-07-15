#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f "$ROOT/config/config.json" ]]; then
  cp "$ROOT/config/config.example.json" "$ROOT/config/config.json"
fi
exec python3 "$ROOT/app.py" --config "$ROOT/config/config.json" "$@"
