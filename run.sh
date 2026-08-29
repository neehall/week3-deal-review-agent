#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
  echo "No .env found -- copy .env.example to .env and add your ANTHROPIC_API_KEY first."
  exit 1
fi

# PYTHONPATH must include the repo root -- Streamlit only adds the target
# script's own directory (app/) to sys.path, so `from app.graph import ...`
# fails as a bare module-not-found without this.
PYTHONPATH="$PWD" streamlit run app/streamlit_app.py
