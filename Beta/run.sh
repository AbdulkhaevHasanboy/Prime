#!/usr/bin/env bash
# Quantum VRM - Python backend launcher
# Creates a local venv, installs deps, and starts the server.
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment (.venv)..."
  "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "Starting Quantum VRM (Python)..."
exec python server.py "$@"
