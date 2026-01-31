# PiCar Brain

Voice-controlled robot car for Leon. Wake word "Jarvis", speaks Swedish.

## Quick Reference

| Item | Value |
|------|-------|
| Pi hostname | `picar.local` |
| Pi user | `pi` |
| Pi password | `leon` |
| Project path | `/home/pi/picar-brain` |
| Phone app service | `picar-app` (port 8765) |
| Voice service | `voice` (Hey Jarvis) |
| Wake word | "Jarvis" |

## Fresh Install

### 1. Flash SD Card

Use Raspberry Pi Imager with **Raspberry Pi OS 64-bit Lite**.

Configure in Imager settings:
- Hostname: `picar`
- Username: `pi`
- Password: `leon`
- WiFi: Your network
- Enable SSH with password auth

### 2. First Boot

Insert SD card, power on, wait 2-3 minutes.

```bash
ssh pi@picar.local
```

### 3. Clone and Setup

```bash
cd ~
git clone https://github.com/maxwraae/picar-brain.git
cd picar-brain
./setup.sh
```

### 4. Add API Keys

```bash
cp keys.example.py keys.py
nano keys.py
```

Add your OpenAI API key and Picovoice access key.

### 5. Test Hardware

```bash
./test.sh
```

Checks: I2C, camera, mic, speaker, Python imports, API keys.

### 6. Reboot

```bash
sudo reboot
```

After reboot, voice service starts automatically.

## Deployment

**Edit on Mac, push to GitHub:**
```bash
cd ~/picar-setup/picar-brain
git add -A && git commit -m "message" && git push
```

**Pull on Pi:**
```bash
ssh pi@picar.local
cd ~/picar-brain && git pull
sudo systemctl restart voice      # or picar-app
```

## Services

| Service | What it does | Auto-start |
|---------|--------------|------------|
| `voice` | Voice assistant (Hey Jarvis) | Yes |
| `picar-app` | Phone app control (SunFounder app) | No |

**Note:** Only run ONE service at a time. Both control the same hardware.

**Commands:**
```bash
# Voice assistant (default)
sudo systemctl status voice
journalctl -u voice -f              # Live logs

# Switch to phone app
sudo systemctl stop voice
sudo systemctl start picar-app      # Runs on port 8765 + 9000
```

## Architecture

```
"Jarvis" (wake word)
    → Porcupine detection (local)
    → Recording with VAD (stops on silence)
    → Whisper transcription (OpenAI)
    → GPT response (Swedish robot personality)
    → TTS playback (OpenAI)
    → 3 second follow-up window
```

**Full details:** See [ARCHITECTURE.md](ARCHITECTURE.md) for complete system logic.

## Files

| File | Purpose |
|------|---------|
| `voice_assistant.py` | Main voice assistant |
| `app_control.py` | Phone app control |
| `actions.py` | Robot movement actions |
| `exploration.py` | Autonomous exploration mode |
| `memory.py` | Conversation memory |
| `keys.py` | API keys (not in git) |
| `sounds/` | Audio feedback files |

## Logs

**Log file:** `/home/pi/picar-brain/voice.log`

```bash
# Watch live
tail -f ~/picar-brain/voice.log

# Last 50 lines
tail -50 ~/picar-brain/voice.log

# Systemd logs
journalctl -u voice -f
```

Log rotates at 5MB, keeps 3 backups.

## Troubleshooting

**Self-test shows "TTS test failed" warning:**
- This is normal. The Piper TTS test fails but OpenAI TTS (primary) works fine.
- The service continues despite the warning.

**Service won't start:**
```bash
tail -50 ~/picar-brain/voice.log   # Check log file
journalctl -u voice -n 50          # Check systemd
cd ~/picar-brain && python3 voice_assistant.py   # Test manually
```

**Wake word not detected:**
- Check Picovoice access key in keys.py
- Check USB mic is connected: `arecord -l`

**No sound output:**
- Check speaker connection
- Test: `aplay /usr/share/sounds/alsa/Front_Center.wav`

**Git pull fails:**
```bash
git stash && git pull && git stash pop
```

## API Keys Required

1. **OpenAI API key** - for Whisper, GPT, TTS
2. **Picovoice access key** - for wake word detection (free tier available)

Get Picovoice key at: https://console.picovoice.ai/
