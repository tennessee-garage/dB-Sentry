#!/usr/bin/env bash
set -e

echo "==> Installing system packages (needs sudo)..."
sudo apt-get update
sudo apt-get install -y python3-dev build-essential libfreetype-dev libjpeg-dev \
                        python3-gpiozero python3-rpi.gpio

echo "==> Setting up virtualenv..."
python3 -m venv venv --system-site-packages
source venv/bin/activate

echo "==> Installing Python deps..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Installing systemd service..."
sudo cp db-sentry-interface.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable db-sentry-interface

echo "Done! Service installed and enabled."
echo ""
echo "To start the service:"
echo "  sudo systemctl start db-sentry-interface"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u db-sentry-interface -f"
echo ""
echo "To run interactively for development:"
echo "  source venv/bin/activate"
echo "  sudo venv/bin/python3 main.py"