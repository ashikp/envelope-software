#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "==> Installing build deps (editable + PyInstaller)..."
PY="${PYTHON:-python3}"
"$PY" -m pip install -q -e ".[dev]"
echo "==> Running PyInstaller (clean output)..."
rm -rf build/envelope-studio dist/EnvelopeStudio
"$PY" -m PyInstaller -y envelope-studio.spec
echo "==> Done: dist/EnvelopeStudio/"
ls -la dist/EnvelopeStudio 2>/dev/null || ls -la dist/
