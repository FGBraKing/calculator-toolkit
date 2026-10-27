#!/bin/bash
# 打包单文件桌面版（macOS / Windows / Linux）。
# PyInstaller 不支持交叉编译，需在目标系统上运行；CI 用三平台矩阵调用本脚本。
set -euo pipefail
cd "$(dirname "$0")/.."

# Git Bash 下把 /d/a/... 转成 D:/a/...，否则 PyInstaller 找不到 --add-data 的源路径
if pwd -W >/dev/null 2>&1; then
  ROOT="$(pwd -W)"
else
  ROOT="$PWD"
fi

case "$(uname -s)" in
  Darwin) OS=macos; SEP=":" ;;
  Linux) OS=linux; SEP=":" ;;
  MINGW*|MSYS*|CYGWIN*) OS=windows; SEP=";" ;;
  *)
    echo "不支持的平台: $(uname -s)" >&2
    exit 1
    ;;
esac

FLAGS=()
case "$OS" in
  macos) FLAGS=(--windowed --osx-bundle-identifier local.calculator-toolkit) ;;
  windows) FLAGS=(--noconsole) ;;
esac

UV_CACHE_DIR="$ROOT/.uv-cache" PYINSTALLER_CONFIG_DIR="$ROOT/.pyinstaller" \
  uv run --with pyinstaller pyinstaller \
  --noconfirm --clean --onefile \
  --name CalculatorToolkit \
  ${FLAGS[@]+"${FLAGS[@]}"} \
  --paths . \
  --collect-submodules app \
  --collect-submodules uvicorn \
  --add-data "$ROOT/static${SEP}static" \
  --add-data "$ROOT/app/templates${SEP}app/templates" \
  --workpath "$ROOT/.build" --distpath "$ROOT/dist" --specpath "$ROOT/.build" \
  packaging/entry.py

case "$OS" in
  macos)
    rm -f "$ROOT/dist/CalculatorToolkit"
    ARTIFACT="$ROOT/dist/CalculatorToolkit.app"
    ;;
  windows) ARTIFACT="$ROOT/dist/CalculatorToolkit.exe" ;;
  *) ARTIFACT="$ROOT/dist/CalculatorToolkit" ;;
esac

echo "完成（$OS）：$ARTIFACT  $(du -sh "$ARTIFACT" | cut -f1)"
