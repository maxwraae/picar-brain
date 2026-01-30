# PiCar Voice Assistant

Voice-controlled robot car for Leon (9 years old). Swedish language, wake word activated.

## Quick Reference

| Item | Value |
|------|-------|
| Hardware | Raspberry Pi 5 + PiCar-X chassis |
| Pi hostname | `picar.local` |
| Pi user | `pi` |
| Pi password | `leon` |
| Pi IP | `192.168.1.101` (may change) |
| Project path on Pi | `/home/pi/picar-brain` |
| App control service | `picar-app` (for SunFounder app) |
| Voice service | `voice` (voice assistant) |
| Wake word | "Jarvis" |

## Connect to Pi

```bash
ssh pi@picar.local
# Password: leon

# Or with sshpass:
sshpass -p 'leon' ssh pi@picar.local
```

## Deployment

**From Mac (this repo at `~/picar-setup/picar-brain/`):**
```bash
git add -A && git commit -m "message" && git push
```

**On the Pi:**
```bash
cd ~/picar-brain && git pull
sudo systemctl restart picar-app  # For SunFounder app
# OR
sudo systemctl restart voice      # For voice assistant
```

**Check service status:**
```bash
sudo systemctl status picar-app
journalctl -u picar-app -f  # Live logs
```

## SunFounder App Connection

1. Open SunFounder PiCar-X app on phone
2. Connect to same WiFi as Pi
3. Enter Pi IP: `192.168.1.101` (or find with `ping picar.local`)
4. App connects on port 8765

## Architecture

```
User says "Jarvis"
    → Porcupine wake word detection (local, Picovoice)
    → *ding* sound + LED solid on

User speaks
    → PvRecorder captures audio with VAD (webrtcvad)
    → Stops on 1.5s silence or 8s max

Transcription
    → OpenAI Whisper API (Swedish)
    → Validates: min 2 words, filters noise patterns

Processing
    → *thinking* sound + LED fast blink
    → GPT-5 mini streaming (Swedish robot personality)
    → LED slow pulse when speaking

Speech
    → OpenAI TTS streaming (gpt-4o-mini-tts, voice: onyx)
    → Volume boosted 3x for small speaker
    → Plays via aplay to robothat device

Follow-up
    → 3 second window to continue without wake word
    → Silent exit if noise detected (prevents loops)
```

## Key Files

| File | Purpose |
|------|---------|
| `voice_assistant.py` | Main application |
| `keys.py` | API keys (OPENAI_API_KEY, PICOVOICE_ACCESS_KEY) |
| `sounds/` | Audio feedback (ding, thinking, retry, ready, listening) |

## Configuration Constants

In `voice_assistant.py`:

```python
# Wake word
WAKE_WORD = "jarvis"

# Voice Activity Detection
VAD_AGGRESSIVENESS = 3      # 0-3, strictest
SILENCE_THRESHOLD = 1.5     # seconds to stop recording
MAX_RECORD_DURATION = 8     # seconds max
FOLLOW_UP_WINDOW = 3.0      # seconds for follow-up

# Speech validation (filters noise)
MIN_WORDS_FOR_VALID_SPEECH = 2
NOISE_TRANSCRIPTIONS = {...}  # Common Whisper hallucinations

# TTS
TTS_MODEL = "tts-1"
TTS_VOICE = "onyx"          # Deep male voice
TTS_VOLUME_BOOST = 3.0      # Amplify for small speaker
USE_OPENAI_TTS = True       # False = use Piper (local, lower quality)

# Hardware
SPEAKER_DEVICE = "plughw:2,0"  # Robot-hat speaker (card 2)
MIC_DEVICE = "plughw:3,0"      # USB mic (card 3)
```

## LED Patterns

| State | Pattern |
|-------|---------|
| Waiting for wake word | Off |
| Recording/Listening | Solid on |
| Thinking/Processing | Fast blink |
| Speaking | Slow pulse |

## Sound Effects

| Sound | When | Duration |
|-------|------|----------|
| ding.wav | Wake word detected | 0.12s |
| thinking.wav | GPT processing | 3s (loops) |
| retry.wav | Error/retry needed | 0.27s |
| ready.wav | Startup complete | 0.5s |
| listening.wav | Your turn to speak | 0.2s |

## Troubleshooting

**Robot keeps talking to itself:**
- Noise detection triggering follow-up
- Check `MIN_WORDS_FOR_VALID_SPEECH` (should be 2+)
- Check `VAD_AGGRESSIVENESS` (should be 3)
- Check `FOLLOW_UP_WINDOW` (should be 3.0 or less)

**Voice too quiet:**
- Increase `TTS_VOLUME_BOOST` (currently 3.0)
- Check `amixer` levels on Pi

**Wake word not detected:**
- Check Picovoice access key in `keys.py`
- Check USB mic connected and detected
- Try different wake words (alexa, computer, etc.)

**Service won't start:**
```bash
# Check logs
journalctl -u voice -n 50

# Test manually
cd /home/pi/picar-brain
python3 voice_assistant.py
```

**Git pull fails on Pi:**
```bash
# If uncommitted changes on Pi
cd /home/pi/picar-brain
git stash
git pull
git stash pop  # if you want changes back
```

## Dependencies (on Pi)

```bash
# Python packages
pip install openai pvporcupine pvrecorder webrtcvad numpy

# System packages
sudo apt install aplay piper  # piper for fallback TTS

# Piper Swedish model
mkdir -p ~/.local/share/piper
# Download sv_SE-nst-medium.onnx
```

## Service Setup

The systemd service file at `/etc/systemd/system/voice.service`:
```ini
[Unit]
Description=PiCar Voice Assistant
After=network.target sound.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/picar-brain
ExecStart=/usr/bin/python3 /home/pi/picar-brain/voice_assistant.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable with:
```bash
sudo systemctl enable voice
sudo systemctl start voice
```

## Robot Personality

Swedish robot car named PiCar. Playful, energetic, loves making Leon happy. Says things like "Woohoo!", "Vroom vroom!". Short responses (1-2 sentences). Can do physical actions: forward, backward, spin, dance, nod, shake head.

## API Costs

Per conversation (~10 exchanges):
- Whisper: ~$0.006 (1 min audio)
- GPT-5 mini: ~$0.01
- TTS: ~$0.015 (1000 chars)
- **Total: ~$0.03/conversation**

## History

- Started with Piper TTS (local, mediocre Swedish)
- Upgraded to OpenAI TTS streaming for better quality + lower latency
- Added wake word (Porcupine) instead of push-to-talk
- Added VAD for smart recording cutoff
- Added follow-up conversation window
- Added noise filtering to prevent false triggers
- Added LED patterns for visual feedback
