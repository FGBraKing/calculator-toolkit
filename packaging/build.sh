#!/bin/zsh
# 打包成 macOS 单文件 App（产物：dist/CalculatorToolkit.app）
set -euo pipefail
cd "$(dirname "$0")/.."

ROOT="$PWD"
UV_CACHE_DIR="$ROOT/.uv-cache" PYINSTALLER_CONFIG_DIR="$ROOT/.pyinstaller" \
  uv run --with pyinstaller pyinstaller \
  --noconfirm --clean --onefile --windowed \
  --name "CalculatorToolkit" \
  --osx-bundle-identifier local.calculator-toolkit \
  --paths . \
  --collect-submodules app \
  --collect-submodules uvicorn \
  --add-data "$ROOT/static:static" \
  --add-data "$ROOT/app/templates:app/templates" \
  --workpath "$ROOT/.build" --distpath "$ROOT/dist" --specpath "$ROOT/.build" \
  packaging/entry.py

rm -f "$ROOT/dist/CalculatorToolkit"
echo "完成：$(du -sh "$ROOT/dist/CalculatorToolkit.app" | cut -f1)"
