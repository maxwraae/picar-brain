#!/bin/bash
# Deploy Voice Assistant to Raspberry Pi
# Run this from your Mac

PI_HOST="192.168.1.101"
PI_USER="pi"
PI_PASS="Leon"
PI_PATH="/home/pi/picar-brain"

echo "=========================================="
echo "Deploying Voice Assistant to PiCar"
echo "=========================================="
echo ""
echo "Target: ${PI_USER}@${PI_HOST}:${PI_PATH}"
echo ""

# Check if we're in the right directory
if [ ! -f "voice_assistant.py" ]; then
    echo "❌ Error: voice_assistant.py not found"
    echo "Please run this script from the picar-brain directory"
    exit 1
fi

# Test connection
echo "🔌 Testing connection to Pi..."
if ! ping -c 1 -W 2 $PI_HOST > /dev/null 2>&1; then
    echo "❌ Error: Cannot reach Pi at $PI_HOST"
    echo "Please check:"
    echo "  1. Pi is powered on"
    echo "  2. Pi is connected to network"
    echo "  3. IP address is correct"
    exit 1
fi
echo "✓ Pi is reachable"
echo ""

# Copy files
echo "📤 Copying files to Pi..."
sshpass -p "$PI_PASS" scp -o StrictHostKeyChecking=no \
    voice_assistant.py \
    setup_voice_assistant.sh \
    test_voice_assistant.sh \
    requirements.txt \
    VOICE_ASSISTANT_README.md \
    ${PI_USER}@${PI_HOST}:${PI_PATH}/ || {
    echo "❌ Error: Failed to copy files"
    echo "If you don't have sshpass, install it: brew install hudochenkov/sshpass/sshpass"
    echo ""
    echo "Or copy manually:"
    echo "  scp voice_assistant.py setup_voice_assistant.sh test_voice_assistant.sh requirements.txt VOICE_ASSISTANT_README.md pi@${PI_HOST}:${PI_PATH}/"
    exit 1
}
echo "✓ Files copied"
echo ""

# Make scripts executable
echo "🔧 Setting permissions..."
sshpass -p "$PI_PASS" ssh -o StrictHostKeyChecking=no ${PI_USER}@${PI_HOST} \
    "chmod +x ${PI_PATH}/setup_voice_assistant.sh ${PI_PATH}/test_voice_assistant.sh" || {
    echo "❌ Error: Failed to set permissions"
    exit 1
}
echo "✓ Permissions set"
echo ""

# Ask if user wants to run setup
echo "=========================================="
echo "Files deployed successfully!"
echo "=========================================="
echo ""
read -p "Do you want to run setup on the Pi now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "🚀 Running setup on Pi..."
    echo ""
    sshpass -p "$PI_PASS" ssh -o StrictHostKeyChecking=no ${PI_USER}@${PI_HOST} \
        "cd ${PI_PATH} && ./setup_voice_assistant.sh"

    echo ""
    echo "Setup complete! Now run tests..."
    echo ""

    sshpass -p "$PI_PASS" ssh -o StrictHostKeyChecking=no ${PI_USER}@${PI_HOST} \
        "cd ${PI_PATH} && ./test_voice_assistant.sh"

    echo ""
    echo "=========================================="
    echo "✅ Deployment and setup complete!"
    echo "=========================================="
    echo ""
    echo "To start the voice assistant:"
    echo "  1. SSH to Pi: ssh pi@${PI_HOST}"
    echo "  2. Activate venv: source ~/picar-brain/venv/bin/activate"
    echo "  3. Run assistant: python3 voice_assistant.py"
    echo ""
else
    echo ""
    echo "Setup skipped. To run setup manually:"
    echo "  1. SSH to Pi: ssh pi@${PI_HOST}"
    echo "  2. Run: cd ${PI_PATH} && ./setup_voice_assistant.sh"
    echo "  3. Test: ./test_voice_assistant.sh"
    echo ""
fi
