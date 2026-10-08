#!/usr/bin/env bash
# First-time setup for macOS / Linux. Windows users: run setup.bat instead.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python 3.11+ was not found. Install it from https://www.python.org/downloads/ and re-run." >&2
  exit 1
fi

echo "[1/4] Creating a private Python environment (.venv)..."
"$PYTHON" -m venv .venv

echo "[2/4] Installing packages (a few minutes)..."
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "[3/4] Installing the headless browser used for JavaScript-only job pages..."
.venv/bin/python -m playwright install chromium

echo "[4/4] Checking for Ollama..."
if command -v ollama >/dev/null 2>&1; then
  echo "Ollama found."
else
  echo "Ollama was not found. Install it from https://ollama.com/download, then run: ollama pull qwen3.5:latest" >&2
fi

echo
echo "Setup complete. Next: ./start.sh, then open the Setup page in your browser."
echo "You also need credentials.json from Google Cloud: see docs/GETTING_STARTED.md."
