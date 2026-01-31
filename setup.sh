#!/bin/bash
# PiCar-Brain Setup Script
# Run this on a fresh Raspberry Pi 5 after cloning the repo to ~/picar-brain
set -e

REPO_DIR="$HOME/picar-brain"

# Check we're in the right place
if [ "$(pwd)" != "$REPO_DIR" ]; then
    echo "ERROR: This script must be run from $REPO_DIR"
    echo "Run: cd ~/picar-brain && ./setup.sh"
    exit 1
fi

echo "=== PiCar-Brain Setup ==="
echo ""

# 1. System packages
echo "[1/7] Installing system packages..."
sudo apt update
sudo apt install -y python3-pip python3-opencv libportaudio2

# 2. Enable I2C, SPI, Camera
echo "[2/7] Enabling hardware interfaces..."
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_camera 0
# Add user to required groups
sudo usermod -aG audio,video,i2c,gpio pi 2>/dev/null || true

# 3. Install SunFounder libraries
echo "[3/7] Installing SunFounder libraries (this takes a few minutes)..."
cd /tmp

echo "  - robot-hat..."
if [ ! -d "robot-hat" ]; then
    git clone --quiet https://github.com/sunfounder/robot-hat.git
fi
cd robot-hat && sudo python3 setup.py install > /dev/null 2>&1
cd /tmp

echo "  - picar-x..."
if [ ! -d "picar-x" ]; then
    git clone --quiet https://github.com/sunfounder/picar-x.git
fi
cd picar-x && sudo python3 setup.py install > /dev/null 2>&1
cd /tmp

echo "  - vilib..."
if [ ! -d "vilib" ]; then
    git clone --quiet https://github.com/sunfounder/vilib.git
fi
cd vilib && sudo python3 install.py > /dev/null 2>&1
cd /tmp

echo "  - sunfounder-controller..."
if [ ! -d "sunfounder-controller" ]; then
    git clone --quiet https://github.com/sunfounder/sunfounder-controller.git
fi
cd sunfounder-controller && sudo python3 setup.py install > /dev/null 2>&1

cd "$REPO_DIR"

# 4. Python packages
echo "[4/7] Installing Python packages..."
pip3 install --break-system-packages -r requirements.txt > /dev/null 2>&1

# 5. dtoverlay for robot-hat hardware
echo "[5/7] Configuring kernel overlay..."
if ! grep -q "dtoverlay=sunfounder-robothat5" /boot/firmware/config.txt; then
    echo "dtoverlay=sunfounder-robothat5" | sudo tee -a /boot/firmware/config.txt > /dev/null
    echo "  Added dtoverlay to config.txt"
else
    echo "  Already configured"
fi

# 6. Create required directories
echo "[6/7] Setting up directories..."
sudo mkdir -p /opt/picar-x
sudo chown pi:pi /opt/picar-x

# 7. Install services
echo "[7/7] Installing services..."
sudo cp services/*.service /etc/systemd/system/
sudo systemctl daemon-reload
# Only enable voice by default (voice and picar-app conflict - both control the hardware)
sudo systemctl enable voice > /dev/null 2>&1
echo "  Voice service enabled (starts on boot)"
echo "  Phone app available: sudo systemctl start picar-app"

echo ""
echo "=== Setup Complete ==="
echo ""

# Check for keys.py
if [ ! -f "$REPO_DIR/keys.py" ]; then
    echo "NEXT: Set up your API keys"
    echo ""
    echo "  cp keys.example.py keys.py"
    echo "  nano keys.py"
    echo ""
    echo "You need:"
    echo "  - OpenAI API key (https://platform.openai.com/api-keys)"
    echo "  - Picovoice key (https://console.picovoice.ai/)"
    echo ""
    echo "Then reboot: sudo reboot"
else
    echo "keys.py found. Ready to reboot."
    echo ""
    echo "  sudo reboot"
    echo ""
    echo "After reboot, check: sudo systemctl status voice picar-app"
fi
