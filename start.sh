#!/usr/bin/env bash
# Start the app on macOS / Linux. Windows users: run start.bat instead.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "Setup has not been run yet. Run ./setup.sh first." >&2
  exit 1
fi

echo "Starting Job Application Agent... a browser tab will open shortly."
echo "Keep this terminal open while you use the app; closing it stops the app."
exec .venv/bin/python -m streamlit run streamlit_app.py
