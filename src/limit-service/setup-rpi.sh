#!/usr/bin/env bash
set -e

echo "==> Installing system packages (needs sudo)..."
sudo apt-get update
sudo apt-get install -y python3-dev build-essential

echo "==> Setting up virtualenv..."
python3 -m venv .venv
source .venv/bin/activate

echo "==> Installing Python deps..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Done. Activate with: source .venv/bin/activate"