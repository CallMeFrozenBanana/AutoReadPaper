#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  arp_python="${PYTHON_BIN:-}"
  if [ -z "$arp_python" ]; then
    for candidate in python3 python3.12 python3.11 /opt/homebrew/bin/python3; do
      if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        arp_python="$candidate"
        break
      fi
    done
  fi
  if [ -z "$arp_python" ]; then
    echo '需要 Python 3.11+。安装后重试，或设置 PYTHON_BIN=/path/to/python。'
    exit 1
  fi
  "$arp_python" -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install -e . --no-deps
npm --prefix web ci --cache "${npm_config_cache:-$PWD/tmp/npm-cache}"
npm --prefix web run build
printf '\n安装完成。运行 ./scripts/start.sh，然后打开 http://127.0.0.1:8765\n'
