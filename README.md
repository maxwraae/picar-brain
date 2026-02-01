# PiCar Brain

Voice-controlled robot car for Leon. Wake word "Jarvis", speaks Swedish.

## Quick Reference

| Item | Value |
|------|-------|
| Pi hostname | `picar.local` |
| SSH | `ssh pi@picar.local` (password: `leon`) |
| Project path | `/home/pi/picar-brain` |
| App service | `picar-app` (phone control) |
| Voice service | `voice` (Hey Jarvis) |

## Architecture

```
┌─────────────────────────────┐     ┌─────────────────────────────┐
│     app_control.py          │     │    voice_assistant.py       │
│     (picar-app service)     │     │    (voice service)          │
│                             │     │                             │
│  Picarx (motors/servos)     │     │  Button (GPIO 25)           │
│  Camera (Vilib)             │     │  LED feedback               │
│  SunFounder app (8765)      │     │  Speaker (TTS)              │
│  Socket server (5555) ◄─────┼─────┤  Mic + Whisper              │
│                             │     │  Wake word (Porcupine)      │
│  Executes: forward, turn,   │     │  GPT conversation           │
│  stop, camera pan/tilt      │     │  Socket client → sends cmds │
└─────────────────────────────┘     └─────────────────────────────┘
```

**Both services run simultaneously.** Voice sends movement commands to app via localhost socket (port 5555).

## Deployment

```bash
# On Mac: Edit, commit, push
cd ~/picar-setup/picar-brain
git add -A && git commit -m "message" && git push

# On Pi: Pull and restart
sshpass -p 'leon' ssh pi@picar.local "cd ~/picar-brain && git pull && sudo systemctl restart picar-app voice"
```

Or step by step:
```bash
ssh pi@picar.local
# Password: leon
cd ~/picar-brain
git pull
sudo systemctl restart picar-app voice
```

## Services

| Service | Port | What it does |
|---------|------|--------------|
| `picar-app` | 8765, 9000 | Motors, camera, phone app |
| `voice` | 5555→ | Wake word, TTS, GPT |

```bash
# Status
systemctl status picar-app voice

# Logs
journalctl -u voice -f
journalctl -u picar-app -f

# Restart
sudo systemctl restart picar-app voice
```

## Fresh Install

### 1. Flash SD Card

Use Raspberry Pi Imager with **Raspberry Pi OS 64-bit Lite**.

Configure:
- Hostname: `picar`
- Username: `pi` / Password: `leon`
- WiFi: Your network
- Enable SSH

### 2. Clone and Setup

```bash
ssh pi@picar.local
cd ~
git clone https://github.com/maxwraae/picar-brain.git
cd picar-brain
./setup.sh
```

### 3. Add API Keys

```bash
cp keys.example.py keys.py
nano keys.py
```

Add OpenAI API key and Picovoice access key.

### 4. Test and Reboot

```bash
./test.sh
sudo reboot
```

## Files

| File | Purpose |
|------|---------|
| `voice_assistant.py` | Voice assistant (socket client) |
| `app_control.py` | Phone app + socket server |
| `exploration.py` | Autonomous exploration (disabled) |
| `memory.py` | Conversation memory |
| `keys.py` | API keys (not in git) |

## Troubleshooting

**Check logs:**
```bash
tail -f ~/picar-brain/voice.log
journalctl -u voice -n 50
```

**Test socket:**
```bash
echo '{"action":"stop"}' | nc localhost 5555
```

**Audio not working:**
```bash
# Check Pipewire is disabled
systemctl --user status pipewire

# Test speaker directly
aplay -D plughw:1,0 /usr/share/sounds/alsa/Front_Center.wav
```

**Git pull conflict:**
```bash
git fetch origin && git reset --hard origin/main
```
