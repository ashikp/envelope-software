#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "==> Installing build deps (editable + PyInstaller)..."
pip install -q -e ".[dev]"
echo "==> Running PyInstaller (clean output)..."
rm -rf build/envelope-studio dist/EnvelopeStudio
pyinstaller -y envelope-studio.spec
echo "==> Done: dist/EnvelopeStudio/"
ls -la dist/EnvelopeStudio 2>/dev/null || ls -la dist/
