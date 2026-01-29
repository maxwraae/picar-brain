#!/bin/bash
# Setup script for PiCar Voice Assistant
# Run this on the Raspberry Pi

set -e

echo "=========================================="
echo "PiCar Voice Assistant Setup"
echo "=========================================="
echo ""

# Check if running on Pi
if [ ! -f /proc/device-tree/model ] || ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    echo "⚠️  Warning: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Navigate to picar-brain directory
cd ~/picar-brain || {
    echo "❌ Error: ~/picar-brain directory not found"
    exit 1
}

echo "📁 Working directory: $(pwd)"
echo ""

# Create virtual environment
echo "🐍 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "✓ Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install system dependencies for PyAudio
echo "📦 Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y portaudio19-dev python3-pyaudio

# Install Python packages
echo "📥 Installing Python packages..."
pip install SpeechRecognition==3.10.0
pip install openai==0.28.1
pip install PyAudio==0.2.13

# Note: piper-tts is already installed system-wide, no need to install again

echo ""
echo "=========================================="
echo "✅ Setup complete!"
echo "=========================================="
echo ""
echo "To run the voice assistant:"
echo "  1. Activate the virtual environment:"
echo "     source ~/picar-brain/venv/bin/activate"
echo ""
echo "  2. Run the assistant:"
echo "     python3 voice_assistant.py"
echo ""
echo "To test Piper TTS manually:"
echo "  echo 'Hej Leon!' | piper --model ~/.local/share/piper/sv_SE-nst-medium.onnx --output_file /tmp/test.wav && aplay /tmp/test.wav"
echo ""
