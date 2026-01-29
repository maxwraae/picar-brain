# voice_assistant.py Architecture

Understanding the structure and extension points in the voice assistant codebase.

## Core Loop Flow

```
1. Wake Word Detection ("Jarvis")
   ↓
2. Record Audio (with VAD - Voice Activity Detection)
   ↓
3. Transcribe (OpenAI Whisper)
   ↓
4. Chat with GPT (streaming response)
   ↓
5. Parse Actions (extract ACTIONS: line)
   ↓
6. Execute Actions (motor movements)
   ↓
7. Reset to Listening State
```

## File Structure Overview

```
voice_assistant.py (1687 lines)
├── CONSTANTS (lines 55-120)
│   ├── Retry/timeout settings
│   ├── VAD configuration
│   ├── Sound effect paths
│   └── TTS settings
│
├── INITIALIZATION (lines 213-390)
│   ├── PiCar hardware setup
│   ├── Wake word (Porcupine)
│   ├── LED control
│   └── System prompt
│
├── CORE FUNCTIONS (lines 434-869)
│   ├── TTS (OpenAI + Piper fallback)
│   ├── Chat with GPT (streaming)
│   └── Action parsing/execution
│
├── AUDIO PIPELINE (lines 1012-1269)
│   ├── VAD-based recording
│   ├── Wake word listening
│   └── Follow-up detection
│
└── MAIN LOOP (lines 1474-1687)
    └── State machine logic
```

## Extension Points

### 1. State Machine Logic (Line ~1523)

The main loop handles different states. **Modify here** to add new modes or behaviors.

```python
# Line ~1521-1653: Main state machine
while not shutdown_requested:
    # Check for wake word or follow-up
    if not skip_wake_word:
        led_idle()
        if in_follow_up_mode and porcupine:
            follow_up_detected = listen_for_follow_up()
        elif porcupine:
            detected = listen_for_wake_word()

    # Record audio
    led_listening()
    wav_file = record_audio(duration=4)

    # Process response
    answer, actions = chat_with_gpt(text)

    # Execute actions
    for action_name in actions:
        safe_action(ACTIONS[action_name], action_name)
```

**Extension opportunities:**
- Add new operating modes (exploring, manual_control, table_mode)
- Implement timers for autonomous behavior
- Add sensor-based triggers (cliff detection → system message)

### 2. Action Parsing (Line ~1617)

Actions are parsed from GPT response and executed sequentially.

```python
# Line ~1617: Get GPT response with actions
answer, actions = chat_with_gpt(text)

# Line ~1633-1637: Execute actions
for action_name in actions:
    if action_name in ACTIONS:
        safe_action(ACTIONS[action_name], action_name)
```

**Add new actions here:**
```python
# Current actions (line 725-734)
ACTIONS = {
    "forward": do_forward,
    "backward": do_backward,
    "spin_right": do_spin_right,
    "spin_left": do_spin_left,
    "dance": do_dance,
    "nod": do_nod,
    "shake_head": do_shake_head,
    "stop": do_stop,
}

# To add new actions:
def do_rock_back_forth():
    for _ in range(3):
        car.forward(10)
        time.sleep(0.2)
        car.backward(10)
        time.sleep(0.2)
    car.stop()

ACTIONS["rock_back_forth"] = do_rock_back_forth
```

### 3. Autonomous Behavior (Line ~1642)

Currently resets to listening mode. **Modify here** to add autonomous exploration.

```python
# Line ~1642: After actions complete
reset_car_safe()
led_idle()

# Extension: Add autonomous mode
if time_since_last_interaction > AUTONOMOUS_TIMEOUT:
    enter_autonomous_mode()  # Your function

def enter_autonomous_mode():
    # Periodic exploration
    # Send system prompts to LLM
    # Camera vision → text descriptions
    prompt = "[SYSTEM: Du utforskar. Du ser: golv, vägg, röd sko.]"
    answer, actions = chat_with_gpt(prompt)
```

## What NOT to Touch

These are robust and tested - modify only if necessary:

### Voice Pipeline (Lines 434-627)
- `speak_openai()` - TTS with interruption support
- `speak_piper()` - Fallback TTS
- Retry logic and error handling

### Audio Recording (Lines 1012-1269)
- `record_audio_with_vad()` - Voice activity detection
- `listen_for_wake_word()` - Porcupine integration
- `listen_for_follow_up()` - Conversation continuation

### LED Patterns (Lines 227-293)
- Background threading for visual feedback
- Synchronized with speech/thinking states

### Sound Effects (Lines 88-94)
- Startup/thinking/listening sounds
- Integrated with robot_hat Music()

### Interruption System (Lines 295-362)
- Allows "Jarvis" to interrupt ongoing speech
- Wake word detection during TTS playback

## Existing Actions

Defined in lines 646-733:

| Action | Duration | Description |
|--------|----------|-------------|
| `forward` | 1.5s | Drive forward at speed 30 |
| `backward` | 1.5s | Drive backward at speed 30 |
| `spin_right` | 2.0s | 360° spin right (wheels at 30°) |
| `spin_left` | 2.0s | 360° spin left (wheels at -30°) |
| `dance` | ~2s | Wiggle left-right 3 times |
| `nod` | ~0.4s | Head tilt down-up-down (yes) |
| `shake_head` | ~0.7s | Head pan left-right-left (no) |
| `stop` | instant | Stop all motors |

## System Prompt (Lines 392-427)

The personality and behavior instructions for GPT. Located at line 394:

```python
SYSTEM_PROMPT = """Du är en rolig svensk robotbil som heter PiCar...

PERSONLIGHET:
- Lekfull, energisk, älskar att göra Leon glad
- Skämtar och har roligt
- Pratar som en robot-kompis

RÖRLIGHET:
Du kan göra: forward, backward, spin_right, spin_left, dance, nod, shake_head, stop

SVARSFORMAT:
Ge svar som text först.
Om du vill röra dig, skriv ACTIONS: följt av actions på sista raden.
"""
```

**Modify this to:**
- Change personality
- Add new actions to the list
- Change response format
- Add system message handling

## Key Variables

```python
# Global state
conversation_history = []  # GPT conversation memory
shutdown_requested = False  # Clean shutdown flag
in_follow_up_mode = False   # Continue without wake word
skip_wake_word = False      # After interruption

# Hardware
car = Picarx()              # Robot control
music = Music()             # Sound playback
led = Pin('LED')            # Visual feedback

# Configuration
MIC_DEVICE = "plughw:X,0"   # Auto-detected USB mic
SPEAKER_DEVICE = "robothat"  # Audio output
USE_OPENAI_TTS = True       # vs Piper fallback
ENABLE_FOLLOW_UP = False    # Conversation mode
```

## Conversation Flow

```python
# Line ~764-868: GPT streaming with sentence-by-sentence TTS
def chat_with_gpt(user_message):
    # Add to history
    conversation_history.append({"role": "user", "content": user_message})

    # Stream response
    for chunk in response:
        sentence_buffer += token

        # Speak each complete sentence immediately
        if sentence_buffer.endswith((".", "!", "?")):
            speak(sentence_buffer)
            sentence_buffer = ""

    # Parse actions from full response
    answer_text, actions = parse_actions(full_response)

    return answer_text, actions
```

## Adding New Features - Quick Reference

### 1. New Action
```python
# Define function (around line 720)
def do_new_action():
    car.forward(20)
    time.sleep(1)
    car.stop()

# Register in ACTIONS dict (around line 725)
ACTIONS["new_action"] = do_new_action

# Update system prompt (line 404)
# Add "new_action" to the list of available actions
```

### 2. System Events (Autonomous Mode)
```python
# In main loop, add periodic check
last_autonomous_tick = time.time()

while not shutdown_requested:
    # ... existing code ...

    # Autonomous tick every 30 seconds
    if in_autonomous_mode:
        if time.time() - last_autonomous_tick > 30:
            # Get sensor data
            distance = car.get_distance()

            # Create system prompt
            prompt = f"[SYSTEM: Du utforskar. Avstånd framåt: {distance}cm]"
            answer, actions = chat_with_gpt(prompt)

            # Execute actions
            for action in actions:
                if action in ACTIONS:
                    safe_action(ACTIONS[action], action)

            last_autonomous_tick = time.time()
```

### 3. New Sensor Integration
```python
# Read sensor
grayscale_data = car.get_grayscale_data()
is_cliff = car.get_cliff_status(grayscale_data)

# React in main loop
if is_cliff:
    car.stop()
    prompt = "[SYSTEM: Klippa upptäckt! Du är på ett bord.]"
    answer, actions = chat_with_gpt(prompt)
```

## Error Handling Pattern

The codebase uses consistent retry logic:

```python
for attempt in range(MAX_RETRIES):
    try:
        # Do operation
        return success_value
    except Exception as e:
        print(f"Error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
        if attempt == MAX_RETRIES - 1:
            return fallback_value
        time.sleep(RETRY_DELAY)
```

Use this pattern when adding new hardware/API interactions.
