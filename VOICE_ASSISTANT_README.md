# PiCar Voice Assistant

A simplified, long-term voice assistant for the PiCar using Chat Completions API and Piper TTS.

## Features

- **Chat Completions API** (not deprecated Assistants API)
- **Conversation memory** (keeps last 10 exchanges in context)
- **Piper TTS** for Swedish voice output
- **OpenAI Whisper** for speech recognition
- **Fun robot personality** designed for Leon (9 years old)
- **Actions**: forward, backward, spin, dance, nod, shake head

## Architecture

```
┌─────────────┐
│   Listen    │  speech_recognition + Whisper API
└──────┬──────┘
       │
┌──────▼──────┐
│   Think     │  OpenAI Chat Completions API
└──────┬──────┘  (conversation history maintained)
       │
┌──────▼──────┐
│   Speak     │  Piper TTS (Swedish)
└──────┬──────┘
       │
┌──────▼──────┐
│   Act       │  PiCar movements
└─────────────┘
```

## Setup on Raspberry Pi

1. **Copy files to Pi:**
   ```bash
   scp voice_assistant.py setup_voice_assistant.sh requirements.txt pi@192.168.1.101:~/picar-brain/
   ```

2. **SSH into Pi:**
   ```bash
   ssh pi@192.168.1.101
   ```

3. **Run setup:**
   ```bash
   cd ~/picar-brain
   chmod +x setup_voice_assistant.sh
   ./setup_voice_assistant.sh
   ```

4. **Activate virtual environment:**
   ```bash
   source ~/picar-brain/venv/bin/activate
   ```

5. **Run the assistant:**
   ```bash
   python3 voice_assistant.py
   ```

## System Prompt

The assistant has a fun, playful personality:
- Speaks Swedish only
- Short responses (1-2 sentences)
- Playful expressions like "Woohoo!", "Vroom vroom!"
- Always returns JSON: `{"answer": "text", "actions": ["list"]}`

## Available Actions

| Action | Description |
|--------|-------------|
| `forward` | Drive forward for 1.5 seconds |
| `backward` | Drive backward for 1.5 seconds |
| `spin_right` | Spin 360° clockwise |
| `spin_left` | Spin 360° counter-clockwise |
| `dance` | Wiggle back and forth |
| `nod` | Nod head (yes gesture) |
| `shake_head` | Shake head (no gesture) |
| `stop` | Stop all movement |

## Configuration

Edit these in `voice_assistant.py`:

- `PIPER_MODEL`: Path to Piper Swedish model (default: `~/.local/share/piper/sv_SE-nst-medium.onnx`)
- `MIC_DEVICE`: Microphone device (default: `plughw:3,0`)
- `SPEAKER_DEVICE`: Speaker device (default: `plughw:1,0`)

## Testing Components

### Test Piper TTS:
```bash
echo "Hej Leon!" | piper --model ~/.local/share/piper/sv_SE-nst-medium.onnx --output_file /tmp/test.wav
aplay /tmp/test.wav
```

### Test Microphone:
```bash
arecord -D plughw:3,0 -f cd -d 3 /tmp/test.wav
aplay /tmp/test.wav
```

### Test PiCar:
```bash
cd ~/picar-brain
python3 -c "from picarx import Picarx; import time; px = Picarx(); px.forward(30); time.sleep(1); px.stop()"
```

## Conversation History

The assistant maintains conversation context:
- Keeps system prompt + last 20 messages (10 exchanges)
- Allows for natural, continuous conversations
- Remembers what Leon said earlier in the session

## Error Handling

- **Timeout**: If no speech detected in 10 seconds, loops back to listening
- **Unknown speech**: Asks Leon to repeat
- **API errors**: Graceful fallback responses
- **Keyboard interrupt**: Clean shutdown with goodbye message

## Comparison with Old System

| Feature | Old (gpt_car.py) | New (voice_assistant.py) |
|---------|------------------|---------------------------|
| API | Assistants API (deprecated) | Chat Completions (stable) |
| Memory | Thread-based | In-process history |
| TTS | OpenAI TTS | Piper (offline) |
| STT | OpenAI Whisper | OpenAI Whisper |
| Complexity | High (threads, images) | Simple (linear loop) |
| Language | Configurable | Swedish-first |
| Long-term | ❌ Deprecated Aug 2026 | ✅ Stable API |

## Future Enhancements

Potential additions:
- Offline STT with Vosk
- More complex actions (obstacle avoidance, follow commands)
- Vision integration (camera input)
- Sound effects
- Multiple personalities
- Timer-based reminders

## License

For Leon's personal use. Have fun!
