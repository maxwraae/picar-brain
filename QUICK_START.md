# Quick Start Guide - PiCar Voice Assistant

## TL;DR - Deploy and Run

```bash
# On your Mac (from picar-brain directory):
./deploy_to_pi.sh

# Then SSH to Pi and run:
ssh pi@192.168.1.101
source ~/picar-brain/venv/bin/activate
python3 voice_assistant.py
```

## What You Built

A simplified, long-term Swedish voice assistant for Leon's PiCar that:
- ✅ Uses Chat Completions API (not deprecated Assistants API)
- ✅ Maintains conversation history in memory
- ✅ Uses Piper TTS for Swedish speech
- ✅ Has a fun robot personality for a 9-year-old
- ✅ Can move, spin, dance, nod, and shake its head

## Files Created

| File | Purpose |
|------|---------|
| `voice_assistant.py` | Main voice assistant code |
| `setup_voice_assistant.sh` | Setup virtual environment and dependencies |
| `test_voice_assistant.sh` | Test all components |
| `deploy_to_pi.sh` | Deploy from Mac to Pi |
| `requirements.txt` | Python dependencies |
| `VOICE_ASSISTANT_README.md` | Detailed documentation |
| `QUICK_START.md` | This file |

## Step-by-Step Setup

### Option 1: Automatic (Recommended)

```bash
# From your Mac, in picar-brain directory:
chmod +x deploy_to_pi.sh
./deploy_to_pi.sh
```

This will:
1. Copy all files to Pi
2. Run setup (create venv, install packages)
3. Run tests
4. Tell you how to start the assistant

### Option 2: Manual

```bash
# 1. Copy files to Pi
scp voice_assistant.py setup_voice_assistant.sh test_voice_assistant.sh \
    requirements.txt VOICE_ASSISTANT_README.md \
    pi@192.168.1.101:~/picar-brain/

# 2. SSH to Pi
ssh pi@192.168.1.101

# 3. Run setup
cd ~/picar-brain
chmod +x setup_voice_assistant.sh test_voice_assistant.sh
./setup_voice_assistant.sh

# 4. Run tests
./test_voice_assistant.sh

# 5. Start assistant
source ~/picar-brain/venv/bin/activate
python3 voice_assistant.py
```

## How It Works

```
Leon speaks
    ↓
Microphone captures audio
    ↓
OpenAI Whisper transcribes (Swedish)
    ↓
GPT-4 thinks with conversation history
    ↓
Returns JSON: {"answer": "text", "actions": ["spin_right"]}
    ↓
Piper TTS speaks answer in Swedish
    ↓
PiCar executes actions
    ↓
Ready for next question
```

## Available Actions

- `forward` - Drive forward
- `backward` - Drive backward
- `spin_right` - Spin clockwise
- `spin_left` - Spin counter-clockwise
- `dance` - Wiggle dance
- `nod` - Nod head (yes)
- `shake_head` - Shake head (no)
- `stop` - Stop all movement

## Example Conversations

**Leon:** "Hej! Kan du snurra?"
**PiCar:** "Woohoo! Jag snurrar runt!" *spins*

**Leon:** "Vill du dansa?"
**PiCar:** "Ja, jag älskar att dansa!" *dances*

**Leon:** "Kan du köra framåt?"
**PiCar:** "Såklart! Vroom vroom!" *drives forward*

## Troubleshooting

### No sound from speaker
```bash
# Test speaker
speaker-test -t sine -f 1000 -l 1 -D plughw:1,0

# Check if speaker is enabled
pinctrl get 20  # Should show: op dh
```

### Microphone not working
```bash
# Test microphone
arecord -D plughw:3,0 -f cd -d 3 /tmp/test.wav
aplay /tmp/test.wav

# List audio devices
arecord -l
```

### Piper TTS not working
```bash
# Test Piper
echo "Hej Leon!" | piper \
    --model ~/.local/share/piper/sv_SE-nst-medium.onnx \
    --output_file /tmp/test.wav

aplay /tmp/test.wav
```

### OpenAI API errors
```bash
# Check API key
cd ~/picar-brain
source venv/bin/activate
python3 -c "from keys import OPENAI_API_KEY; print('Key starts with:', OPENAI_API_KEY[:10])"

# Test API
python3 -c "
import openai
from keys import OPENAI_API_KEY
openai.api_key = OPENAI_API_KEY
print(openai.Model.list())
"
```

### PiCar not moving
```bash
# Test PiCar
cd ~/picar-brain
python3 -c "
from picarx import Picarx
import time
px = Picarx()
px.forward(30)
time.sleep(1)
px.stop()
print('PiCar test complete')
"
```

## Stopping the Assistant

Press `Ctrl+C` in the terminal. The assistant will:
1. Say goodbye in Swedish
2. Stop the car
3. Reset to default position
4. Exit cleanly

## Monitoring

Watch the terminal for status messages:
- 🎤 Listening for speech
- 📝 Shows what Leon said
- 💭 Thinking (calling GPT)
- 🤖 Shows response
- 🎬 Shows actions being executed
- ⚡ Executing each action

## Next Steps

Ideas for enhancement:
1. Add more actions (obstacle avoidance, follow me mode)
2. Add camera vision (describe what you see)
3. Add sound effects (beeps, engine sounds)
4. Add multiple personalities
5. Offline mode with Vosk STT
6. Timer-based reminders

## Support

If something doesn't work:
1. Run test script: `./test_voice_assistant.sh`
2. Check logs in terminal output
3. Verify all hardware connections
4. Check network connectivity for OpenAI API

## Credits

Built for Leon's 9th birthday. Have fun with your talking robot car!

---

**Version:** 1.0
**Date:** 2026-01-27
**API:** OpenAI Chat Completions (gpt-4)
**TTS:** Piper (Swedish)
**STT:** OpenAI Whisper
