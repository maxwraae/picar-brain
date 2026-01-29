# Pre-Flight Checklist

Use this before deploying to ensure everything will work.

## Local Mac Checks

### Files Present
```bash
cd /Users/maxwraae/picar-setup/picar-brain

# Check all files exist
ls -l voice_assistant.py           # ✓ Should exist
ls -l setup_voice_assistant.sh     # ✓ Should exist
ls -l deploy_to_pi.sh              # ✓ Should exist
ls -l test_voice_assistant.sh      # ✓ Should exist
ls -l requirements.txt             # ✓ Should exist
ls -l keys.py                      # ✓ Should exist
```

### Scripts Executable
```bash
# Make sure scripts can run
ls -l *.sh | grep "x"              # All should have x permission
```

### Syntax Valid
```bash
# Python syntax check
python3 -m py_compile voice_assistant.py
# Should complete without errors
```

## Raspberry Pi Checks

### Network
```bash
# Can you reach the Pi?
ping -c 3 192.168.1.101
# Should get 3 replies
```

### SSH Access
```bash
# Can you login?
ssh pi@192.168.1.101 "echo Connected"
# Should print: Connected
```

### Existing Setup
```bash
# Check what's already on Pi
ssh pi@192.168.1.101 "ls -la ~/picar-brain"
# Should show picar-brain directory exists
```

### Piper TTS
```bash
# Is Piper installed?
ssh pi@192.168.1.101 "which piper"
# Should show: /usr/local/bin/piper or similar

# Does Swedish model exist?
ssh pi@192.168.1.101 "ls ~/.local/share/piper/sv_SE-nst-medium.onnx"
# Should show the model file
```

### Microphone
```bash
# Is microphone connected?
ssh pi@192.168.1.101 "arecord -l | grep 'card 3'"
# Should show microphone device
```

### PiCar Library
```bash
# Can we import picarx?
ssh pi@192.168.1.101 "python3 -c 'from picarx import Picarx; print(\"OK\")'"
# Should print: OK
```

### OpenAI Key
```bash
# Is API key configured?
ssh pi@192.168.1.101 "python3 -c 'from keys import OPENAI_API_KEY; print(\"Key:\", OPENAI_API_KEY[:10])'"
# Should show first 10 chars of key
```

## Pre-Deployment Checklist

- [ ] All local files created (10 files)
- [ ] Scripts are executable (chmod +x applied)
- [ ] Python syntax validates
- [ ] Can ping Pi at 192.168.1.101
- [ ] Can SSH to Pi
- [ ] Piper TTS installed on Pi
- [ ] Swedish model exists on Pi
- [ ] Microphone connected (card 3)
- [ ] PiCar library works
- [ ] OpenAI API key configured

## If All Checks Pass

**You're ready to deploy!**

```bash
cd /Users/maxwraae/picar-setup/picar-brain
./deploy_to_pi.sh
```

## If Checks Fail

### Cannot reach Pi
1. Is Pi powered on?
2. Is Pi connected to WiFi?
3. Check IP with: `arp -a | grep raspberrypi`

### SSH fails
1. Password is: Leon
2. Try: `ssh -v pi@192.168.1.101` for debug

### Piper not found
1. Install: `pip install piper-tts`
2. Download model from Piper releases

### Microphone not detected
1. Check USB connection
2. Run: `lsusb` on Pi
3. Try different USB port

### PiCar library fails
1. Re-install: `cd ~/picar-x && sudo python3 setup.py install`
2. Check permissions

### API key missing
1. Create: `~/picar-brain/keys.py`
2. Add: `OPENAI_API_KEY = "sk-..."`

## Post-Deployment Checks

After running `deploy_to_pi.sh`:

```bash
# SSH to Pi
ssh pi@192.168.1.101

# Check virtual environment created
ls ~/picar-brain/venv
# Should exist

# Check packages installed
source ~/picar-brain/venv/bin/activate
pip list | grep -E "openai|SpeechRecognition|pyaudio"
# Should show all three

# Run tests
cd ~/picar-brain
./test_voice_assistant.sh
# Should show mostly passing tests

# Try starting assistant
python3 voice_assistant.py
# Should start without errors
# Press Ctrl+C to stop
```

## Final Safety Check

Before Leon uses it:

1. **Test volume**: Make sure speaker isn't too loud
2. **Test movements**: Ensure car has clearance (no obstacles)
3. **Test microphone**: Verify it picks up Leon's voice
4. **Test emergency stop**: Ctrl+C should stop immediately
5. **Clear area**: Remove obstacles from car's path

## Emergency Stop

If something goes wrong while running:

1. Press **Ctrl+C** in terminal
2. Or SSH from another terminal: `ssh pi@192.168.1.101 "pkill -f voice_assistant"`
3. Physical: Power off Pi

## Quick Reference Commands

```bash
# Deploy from Mac
./deploy_to_pi.sh

# SSH to Pi
ssh pi@192.168.1.101

# Activate environment
source ~/picar-brain/venv/bin/activate

# Run tests
./test_voice_assistant.sh

# Start assistant
python3 voice_assistant.py

# Stop assistant
Ctrl+C

# View logs (while running)
# Just watch terminal output

# Restart assistant
python3 voice_assistant.py
```

## Troubleshooting Quick Fix

If anything fails during deployment:

```bash
# Start fresh
ssh pi@192.168.1.101
cd ~/picar-brain
rm -rf venv
./setup_voice_assistant.sh
./test_voice_assistant.sh
```

## Ready?

If all checkboxes are checked, run:

```bash
./deploy_to_pi.sh
```

And have fun! 🚗🤖🎉
