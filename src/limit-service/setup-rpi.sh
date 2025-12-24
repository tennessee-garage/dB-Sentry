#!/usr/bin/env bash
set -e

echo "==> Installing system packages (needs sudo)..."
sudo apt-get update
sudo apt-get install -y python3-dev build-essential libfreetype-dev libjpeg-dev \
                        python3-gpiozero python3-pigpio pigpio python3-rpi.gpio
sudo systemctl enable --now pigpiod

echo "==> Setting up virtualenv..."
python3 -m venv venv --system-site-packages
source .venv/bin/activate

echo "==> Installing Python deps..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Done. Activate with: source .venv/bin/activate"