#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ] || [ ! -f web/dist/index.html ]; then
  echo '请先运行 ./scripts/setup.sh 完成安装。'
  exit 1
fi
exec .venv/bin/python -m autoreadpaper.cli serve "$@"
