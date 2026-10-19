#!/bin/bash
# Mac and Linux entry point. The real launcher is start.py.
set -euo pipefail

cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  exec python3 start.py
fi

if command -v python >/dev/null 2>&1; then
  exec python start.py
fi

echo "Python was not found. Install Python 3.10, 3.11, 3.12, or 3.13 and run ./start.sh again."
exit 1
