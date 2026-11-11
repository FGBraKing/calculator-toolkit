#!/bin/bash
# 打包桌面版：macOS 为 .app 包（onedir），Windows / Linux 为单文件可执行。
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

# macOS 的 onefile + windowed 组合已被 PyInstaller 弃用（v7.0 将报错），改用 onedir
FLAGS=()
case "$OS" in
  macos) FLAGS=(--onedir --windowed --osx-bundle-identifier local.calculator-toolkit) ;;
  windows) FLAGS=(--onefile --noconsole) ;;
  linux) FLAGS=(--onefile) ;;
esac

UV_CACHE_DIR="$ROOT/.uv-cache" PYINSTALLER_CONFIG_DIR="$ROOT/.pyinstaller" \
  uv run --with pyinstaller pyinstaller \
  --noconfirm --clean \
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
    # onedir 模式除 .app 外还会生成同名目录，删掉让 dist 只剩 .app（CI 只打包 .app）
    rm -rf "$ROOT/dist/CalculatorToolkit"
    ARTIFACT="$ROOT/dist/CalculatorToolkit.app"
    ;;
  windows) ARTIFACT="$ROOT/dist/CalculatorToolkit.exe" ;;
  *) ARTIFACT="$ROOT/dist/CalculatorToolkit" ;;
esac

echo "完成 (${OS}): $ARTIFACT  $(du -sh "$ARTIFACT" | cut -f1)"
