#!/bin/bash
# Start PiCar Voice Assistant
# Usage: ./start.sh

cd /home/pi/picar-brain

# Activate virtual environment
source venv/bin/activate

# Run the assistant
sudo venv/bin/python3 voice_assistant.py
