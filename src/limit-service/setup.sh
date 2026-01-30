#!/usr/bin/env bash
set -e

echo "==> Setting up virtualenv..."
python3 -m venv venv
source venv/bin/activate

echo "==> Installing Python deps..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Done. Activate with: source venv/bin/activate"