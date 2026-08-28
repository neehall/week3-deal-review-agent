#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
  echo "No .env found -- copy .env.example to .env and add your OPENAI_API_KEY first."
  exit 1
fi

streamlit run app/streamlit_app.py
