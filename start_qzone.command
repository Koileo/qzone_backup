#!/bin/zsh

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR" || exit 1

if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON="$PROJECT_DIR/.venv/bin/python"
else
  PYTHON="python3"
fi

if ! "$PYTHON" -c "import aiohttp, demjson3, loguru, lxml, PIL, qrcode, requests" 2>/dev/null; then
  echo "运行依赖尚未安装，请先执行："
  echo "  python3 -m pip install -e \"$PROJECT_DIR\""
  echo
  read "REPLY?按回车关闭窗口……"
  exit 1
fi

"$PYTHON" "$PROJECT_DIR/main.py"
STATUS=$?

echo
read "REPLY?程序已结束，按回车关闭窗口……"
exit $STATUS
