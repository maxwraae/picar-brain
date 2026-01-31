# System Architecture

How the voice assistant works, end to end.

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        voice_assistant.py                        │
│                         (Main Loop)                              │
├─────────────────────────────────────────────────────────────────┤
│  1. Wait for wake word "Jarvis"    ← Porcupine (local)          │
│  2. Record speech                  ← PvRecorder + VAD           │
│  3. Transcribe                     ← OpenAI Whisper             │
│  4. Think & decide                 ← OpenAI GPT                 │
│  5. Speak response                 ← OpenAI TTS                 │
│  6. Execute actions                ← actions.py → Picarx        │
│  7. Listen for follow-up (3 sec)                                │
│  8. Loop back to 1                                              │
└─────────────────────────────────────────────────────────────────┘
```

## File Responsibilities

### voice_assistant.py (Main)
The orchestrator. Runs the main loop.

```python
main()
├── startup_self_test()      # Test mic, speaker, motors
├── while not shutdown:
│   ├── listen_for_wake_word()     # "Jarvis"
│   ├── led_listening()            # LED solid on
│   ├── record_audio_with_vad()    # Record until silence
│   ├── transcribe_audio()         # Whisper API
│   ├── led_thinking()             # LED fast blink
│   ├── chat_with_gpt()            # Get response + actions
│   ├── led_talking()              # LED slow pulse
│   ├── speak()                    # TTS playback
│   ├── execute_actions()          # Move robot
│   └── listen_for_follow_up()     # 3 sec window
```

### actions.py (Robot Movement)
Owns the Picarx hardware instance. All movement goes through here.

```python
px = Picarx()  # Single shared instance

# Movement
move_forward()      # Drive forward 1.5 sec
move_backward()     # Drive backward 1.5 sec
turn_left()         # Turn left
turn_right()        # Turn right
stop()              # Stop motors

# Head/Camera
look_up(), look_down(), look_left(), look_right()
look_around()       # Scan environment
nod(), shake_head() # Expressive gestures

# Complex
dance()             # Happy dance
rock_back_forth()   # Excited wiggle

# Execution
execute_action(name)     # Run single action by name
execute_actions([list])  # Run list of actions
```

### exploration.py (Autonomous Mode)
Curious exploration - robot moves on its own, describes what it sees.

```python
explore(duration, callback)
├── while exploring:
│   ├── get_distance()           # Ultrasonic sensor
│   ├── capture_frame()          # Camera snapshot
│   ├── analyze_scene(frame)     # GPT-4 Vision: what's interesting?
│   ├── describe_scene(frame)    # Narrate what we see
│   ├── move_forward_short()     # Small movement
│   ├── look_around()            # Scan with head
│   └── callback(description)    # Tell user what we found
```

### memory.py (Conversation Memory)
Remembers things across conversations.

```python
add_observation(entity, text)    # Store a memory
format_memories_for_prompt()     # Get memories for GPT context
```

### keys.py (Secrets)
API credentials. Not in git.

```python
OPENAI_API_KEY = "sk-..."
PICOVOICE_ACCESS_KEY = "..."
```

## Data Flow

### Wake Word → Response

```
User says "Jarvis"
    │
    ▼
┌──────────────────┐
│ Porcupine        │  Local wake word detection
│ (pvporcupine)    │  No internet needed
└────────┬─────────┘
         │ detected
         ▼
┌──────────────────┐
│ PvRecorder       │  Capture audio
│ + webrtcvad      │  Stop on 1.5s silence (or 8s max)
└────────┬─────────┘
         │ audio bytes
         ▼
┌──────────────────┐
│ OpenAI Whisper   │  Speech-to-text (Swedish)
│ (API)            │  Returns transcribed text
└────────┬─────────┘
         │ "Kör framåt"
         ▼
┌──────────────────┐
│ OpenAI GPT       │  Decide response + actions
│ (API)            │  System prompt has personality
└────────┬─────────┘
         │ "Woohoo! Jag kör!" + [move_forward]
         ▼
┌──────────────────┐
│ OpenAI TTS       │  Text-to-speech (Swedish)
│ (API)            │  Streams audio
└────────┬─────────┘
         │ audio stream
         ▼
┌──────────────────┐
│ aplay            │  Play through speaker
│ (robot-hat)      │  plughw:2,0
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ actions.py       │  Execute movement
│ → Picarx         │  move_forward()
└──────────────────┘
```

### GPT Response Format

GPT returns structured text that gets parsed:

```
[action1][action2] Spoken response text
```

Example:
```
[nod][move_forward] Woohoo! Nu kör vi!
```

Parsed into:
- actions: ["nod", "move_forward"]
- speech: "Woohoo! Nu kör vi!"

## Hardware Connections

```
┌─────────────────────────────────────────┐
│           Raspberry Pi 5                 │
├─────────────────────────────────────────┤
│                                          │
│  ┌──────────────┐    ┌───────────────┐  │
│  │ Robot HAT 5  │────│ Motors (x2)   │  │
│  │ (I2C)        │    │ Servo (x3)    │  │
│  │              │    │ Speaker       │  │
│  │              │    │ Ultrasonic    │  │
│  └──────────────┘    └───────────────┘  │
│                                          │
│  ┌──────────────┐    ┌───────────────┐  │
│  │ Camera       │────│ picamera2     │  │
│  │ (CSI)        │    │               │  │
│  └──────────────┘    └───────────────┘  │
│                                          │
│  ┌──────────────┐                        │
│  │ USB Mic      │────  Input audio       │
│  │              │                        │
│  └──────────────┘                        │
│                                          │
└─────────────────────────────────────────┘
```

## Modes

### Listening Mode (default)
- Waiting for "Jarvis"
- LED off

### Conversation Mode
- Recording → LED solid
- Thinking → LED fast blink
- Speaking → LED slow pulse
- Follow-up window (3 sec)

### Exploration Mode
- Triggered by voice command
- Robot moves autonomously
- Describes what it sees
- Can be interrupted with "Jarvis"

### Table Mode (safety)
- Activated when edge detected
- Disables wheel movement
- Head movements still work

## Error Handling

- **API failures:** Retry 3x with backoff
- **Audio device busy:** Retry with delay
- **Wake word init fails:** Falls back to push-to-talk
- **Hardware errors:** Log and continue
- **Shutdown signal:** Graceful cleanup

## Logging

All events logged to `/home/pi/picar-brain/voice.log`

```
2024-01-30 22:45:01 [INFO] === Voice Assistant Starting ===
2024-01-30 22:45:02 [INFO] ✓ Wake word ready: 'jarvis'
2024-01-30 22:45:15 [INFO] Wake word detected
2024-01-30 22:45:16 [DEBUG] Recording started
2024-01-30 22:45:19 [DEBUG] Silence detected, stopping
2024-01-30 22:45:20 [INFO] Transcribed: "Kör framåt"
2024-01-30 22:45:21 [DEBUG] GPT response: [move_forward] Woohoo!
2024-01-30 22:45:23 [INFO] Speaking: "Woohoo! Nu kör vi!"
2024-01-30 22:45:25 [INFO] Executing: move_forward
```
