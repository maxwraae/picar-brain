# Jarvis Implementation Plan

## The Vision

**What we're building:** A robot companion for Leon (9 years old) with genuine personality. Jarvis has dry Swedish humor, explores curiously, remembers conversations, and feels alive.

**The experience:** Leon says "Jarvis" → robot responds with personality → explores when idle → comments on what it sees → remembers things → responds when called again.

**Core principle:** The robot follows its attention. It moves toward interesting things, pauses when curious, speaks when moved.

---

## How to Work

You are the **senior dev** (Opus). Agents (Sonnet) implement.

**Pattern:**
1. Read the task
2. Spawn agent with the EXACT specification below
3. Agent implements EXACTLY as specified (no architectural decisions)
4. Review output
5. Next task

**Reference docs:**
- `docs/HARDWARE.md` — Hardware capabilities
- `docs/ARCHITECTURE.md` — Code structure, extension points
- `docs/JARVIS_SPEC.md` — Full personality spec

---

## What NOT to Touch

| System | Location | Why |
|--------|----------|-----|
| Wake word (Porcupine) | Lines 1344-1380 | Working |
| Audio recording (VAD) | Lines 1012-1150 | Tuned |
| Transcription (Whisper) | Lines 1245-1269 | Working |
| TTS (OpenAI streaming) | Lines 434-627 | Working |
| LED patterns | Lines 227-293 | Working |
| Sound effects | Lines 88-94 | Working |
| Interrupt system | Lines 296-362 | Working |

---

# PHASE 1: RESPONSE LAYER

---

## Task 1.1: Replace System Prompt

### Specification

**File:** `voice_assistant.py`

**Find:** The `SYSTEM_PROMPT` variable (around line 392-427)

**Replace with:** Copy the EXACT `SYSTEM_PROMPT` from `/Users/maxwraae/picar-setup/jarvis_v5.py` lines 86-367

**Also add to the prompt** (at the end, before the closing quotes):

```
═══════════════════════════════════════════════════════════════════════════════
SVARSFORMAT
═══════════════════════════════════════════════════════════════════════════════

Svara i detta format:

ACTIONS: action1, action2
Din text här.
MEMORY[entity]: observation

Entities:
- Leon: Fakta om Leon (intressen, humör, händelser)
- environment: Saker i rummet (objekt, platser)
- self: Saker om dig själv (händelser, upptäckter)

Regler:
- ACTIONS-raden kommer FÖRST (utelämna om ingen rörelse)
- Text i mitten (detta säger du högt)
- MEMORY-raden kommer SIST (utelämna om inget att minnas)
- Håll text kort: 1-3 meningar

Exempel:
ACTIONS: nod, look_at_person
Coolt! T-rex är klassisk.
MEMORY[Leon]: gillar dinosaurier, särskilt T-rex
```

**Success criteria:** When you chat with Jarvis, it responds in ACTIONS/text/MEMORY format with dry Swedish humor.

---

## Task 1.2: Update Response Parser

### Specification

**File:** `voice_assistant.py`

**The format** (LLM outputs this, we parse it):
```
ACTIONS: action1, action2
Text to speak here. Can be multiple lines.
More text if needed.
MEMORY: observation to remember
```

- ACTIONS line is optional, must be FIRST if present
- MEMORY line is optional, must be LAST if present
- Everything in between is text to speak (streams to TTS as before)

**Find:** The `parse_actions()` function (around line 741)

**Replace with:**

```python
def parse_response(response_text: str) -> tuple[list[str], str, tuple[str, str] | None]:
    """
    Parse structured response from LLM.
    Format: ACTIONS (first), text (middle), MEMORY[entity]: (last)
    Returns: (actions, message, (entity, observation) or None)
    """
    import re

    lines = response_text.strip().split('\n')
    actions = []
    memory = None
    text_lines = []

    # Find MEMORY line - search from end for first non-empty line starting with MEMORY
    memory_line_idx = None
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        if not line:
            continue
        if line.upper().startswith('MEMORY'):
            memory_line_idx = i
            # Parse memory with entity tag
            match = re.match(r'MEMORY\[(\w+)\]:\s*(.+)', line, re.IGNORECASE)
            if match:
                entity = match.group(1).lower()
                observation = match.group(2).strip()
                # Normalize entity
                if entity in ["leon"]:
                    entity = "Leon"
                elif entity in ["env", "environment", "rummet"]:
                    entity = "environment"
                elif entity in ["self", "jag", "själv"]:
                    entity = "self"
                else:
                    entity = entity.capitalize()
                memory = (entity, observation)
            elif ':' in line:
                # Fallback: MEMORY: text (auto-detect entity)
                text = line.split(':', 1)[1].strip()
                if text:
                    memory = detect_entity_from_memory(text)
            break
        else:
            break  # First non-empty non-MEMORY line from end, stop

    # Process remaining lines
    process_lines = lines[:memory_line_idx] if memory_line_idx else lines

    for i, line in enumerate(process_lines):
        line_stripped = line.strip()
        if i == 0 and line_stripped.upper().startswith('ACTIONS:'):
            action_str = line_stripped[8:].strip().strip('[]')
            actions = [a.strip().lower() for a in action_str.split(',') if a.strip()]
        else:
            text_lines.append(line)

    message = '\n'.join(text_lines).strip()
    return actions, message, memory

def detect_entity_from_memory(text: str) -> tuple[str, str]:
    """Auto-detect entity from untagged memory text."""
    lower = text.lower().strip()

    if lower.startswith("leon"):
        for prefix in ["leon's ", "leons ", "leon "]:
            if lower.startswith(prefix):
                return ("Leon", text[len(prefix):].strip())
        return ("Leon", text)

    if lower.startswith("jag "):
        return ("self", text[4:].strip())

    env_keywords = ["hittade", "såg", "rummet", "under", "bakom"]
    if any(kw in lower for kw in env_keywords):
        return ("environment", text)

    return ("general", text)
```

**DON'T change:** The streaming chat function. It already works. Just update where actions are parsed AFTER the full response is collected.

**Find:** Where actions are currently parsed (around line 1617)

**After getting full response, parse it:**

```python
# After chat completes and full response is available
actions, message_text, memory = parse_response(full_response)

# Save memory if present
if memory:
    save_memory("observation", memory)

# Execute actions
execute_actions(actions, table_mode=current_mode == "table_mode")
```

**Success criteria:**
- Streaming TTS still works (unchanged)
- ACTIONS extracted from first line
- MEMORY extracted from last line
- Text in between spoken via TTS

---

## Task 1.3: Create Action Library

### Specification

**Create file:** `actions.py` in the same directory as `voice_assistant.py`

**Contents:**

```python
"""
Jarvis Action Library
All physical actions the robot can perform.

This module owns the Picarx instance. Other modules import px from here.
"""

import time
from picarx import Picarx

# Single shared instance - other modules import this
px = Picarx()

# ═══════════════════════════════════════════════════════════════════════════════
# MOVEMENT ACTIONS (blocked in table_mode)
# ═══════════════════════════════════════════════════════════════════════════════

def move_forward():
    """Drive forward - shows interest, approaching"""
    px.set_dir_servo_angle(0)
    px.forward(30)
    time.sleep(1.5)
    px.stop()

def move_backward():
    """Drive backward - surprised, skeptical, retreating"""
    px.set_dir_servo_angle(0)
    px.backward(30)
    time.sleep(1.5)
    px.stop()

def turn_left():
    """Turn left"""
    px.set_dir_servo_angle(-30)
    px.forward(30)
    time.sleep(1.0)
    px.stop()
    px.set_dir_servo_angle(0)

def turn_right():
    """Turn right"""
    px.set_dir_servo_angle(30)
    px.forward(30)
    time.sleep(1.0)
    px.stop()
    px.set_dir_servo_angle(0)

def stop():
    """Stop all movement"""
    px.stop()

def rock_back_forth():
    """Rock back and forth - laughing, amused"""
    for _ in range(4):
        px.forward(40)
        time.sleep(0.15)
        px.backward(40)
        time.sleep(0.15)
    px.stop()

def dance():
    """Dance - celebration, joy (rare)"""
    # Wiggle steering while rocking
    for i in range(3):
        px.set_dir_servo_angle(-20)
        px.forward(30)
        time.sleep(0.3)
        px.set_dir_servo_angle(20)
        px.backward(30)
        time.sleep(0.3)
    px.set_dir_servo_angle(0)
    px.stop()
    # Add head movement
    look_around()

# ═══════════════════════════════════════════════════════════════════════════════
# HEAD ACTIONS (always allowed)
# ═══════════════════════════════════════════════════════════════════════════════

def look_up():
    """Look up - thinking, wondering"""
    px.set_cam_tilt_angle(30)

def look_down():
    """Look down - examining, tired, sad"""
    px.set_cam_tilt_angle(-30)

def look_left():
    """Look left"""
    px.set_cam_pan_angle(-45)

def look_right():
    """Look right"""
    px.set_cam_pan_angle(45)

def look_around():
    """Pan around - curious, exploring"""
    px.set_cam_pan_angle(-60)
    time.sleep(0.5)
    px.set_cam_pan_angle(0)
    time.sleep(0.5)
    px.set_cam_pan_angle(60)
    time.sleep(0.5)
    px.set_cam_pan_angle(0)

def look_at_person():
    """Center camera - attentive, listening"""
    px.set_cam_pan_angle(0)
    px.set_cam_tilt_angle(0)

def nod():
    """Nod - yes, agree, understand"""
    for _ in range(3):
        px.set_cam_tilt_angle(-15)
        time.sleep(0.15)
        px.set_cam_tilt_angle(10)
        time.sleep(0.15)
    px.set_cam_tilt_angle(0)

def shake_head():
    """Shake head - no, resigned amusement"""
    for _ in range(3):
        px.set_cam_pan_angle(-25)
        time.sleep(0.15)
        px.set_cam_pan_angle(25)
        time.sleep(0.15)
    px.set_cam_pan_angle(0)

def tilt_head():
    """Tilt head - confused, curious"""
    px.set_cam_pan_angle(20)
    px.set_cam_tilt_angle(-10)

def reset_head():
    """Reset head to center"""
    px.set_cam_pan_angle(0)
    px.set_cam_tilt_angle(0)

# ═══════════════════════════════════════════════════════════════════════════════
# ACTION REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

# Body movements - blocked in table_mode
BODY_ACTIONS = {
    "move_forward": move_forward,
    "move_backward": move_backward,
    "turn_left": turn_left,
    "turn_right": turn_right,
    "stop": stop,
    "rock_back_forth": rock_back_forth,
    "dance": dance,
}

# Head movements - always allowed
HEAD_ACTIONS = {
    "look_up": look_up,
    "look_down": look_down,
    "look_left": look_left,
    "look_right": look_right,
    "look_around": look_around,
    "look_at_person": look_at_person,
    "nod": nod,
    "shake_head": shake_head,
    "tilt_head": tilt_head,
}

# All actions combined
ALL_ACTIONS = {**BODY_ACTIONS, **HEAD_ACTIONS}

def execute_action(action_name: str, table_mode: bool = False) -> bool:
    """
    Execute an action by name.
    Returns True if executed, False if blocked or unknown.
    """
    action_name = action_name.lower().strip()

    # Check if body action and in table mode
    if table_mode and action_name in BODY_ACTIONS:
        print(f"Action '{action_name}' blocked - table mode active")
        return False

    # Get and execute action
    action_func = ALL_ACTIONS.get(action_name)
    if action_func:
        try:
            action_func()
            return True
        except Exception as e:
            print(f"Action '{action_name}' failed: {e}")
            return False
    else:
        print(f"Unknown action: {action_name}")
        return False

def execute_actions(action_list: list[str], table_mode: bool = False):
    """Execute a list of actions in order."""
    for action in action_list:
        execute_action(action, table_mode)
```

**In voice_assistant.py, add import:**

```python
from actions import execute_actions, reset_head
```

**Replace the action execution code** (around line 646-734) with:

```python
# Execute parsed actions
execute_actions(actions, table_mode=current_mode == "table_mode")
```

**Success criteria:** All actions work when called by name.

---

# PHASE 2: EXPLORATION

---

## Task 2.1: Create Exploration Module

### Specification

**Create file:** `exploration.py`

**Contents:**

```python
"""
Jarvis Exploration Module
Attention-based curious wandering.
"""

import time
import random
import cv2
import numpy as np
from actions import px  # Use shared Picarx instance from actions module

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

SAFE_DISTANCE = 40      # cm - safe to move forward
DANGER_DISTANCE = 20    # cm - must turn or back up
EXPLORE_SPEED = 25      # slower than normal
BACKUP_SPEED = 30
THOUGHT_INTERVAL_MIN = 30   # seconds between thoughts
THOUGHT_INTERVAL_MAX = 60
MAX_EXPLORE_DURATION = 3600  # 1 hour max

# ═══════════════════════════════════════════════════════════════════════════════
# SENSORS
# ═══════════════════════════════════════════════════════════════════════════════

def get_distance() -> float:
    """Get ultrasonic distance in cm."""
    try:
        return px.ultrasonic.read()
    except:
        return 100  # Assume safe if sensor fails

def is_cliff_detected() -> bool:
    """Check if cliff/edge detected by grayscale sensors."""
    try:
        return px.get_cliff_status(px.get_grayscale_data())
    except:
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# CAMERA & NOVELTY
# ═══════════════════════════════════════════════════════════════════════════════

# Store recent frames for novelty comparison
frame_history = []
MAX_HISTORY = 5

def capture_frame():
    """Capture a frame from the camera."""
    try:
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        cap.release()
        if ret:
            # Resize for faster processing
            return cv2.resize(frame, (160, 120))
        return None
    except:
        return None

def get_histogram(frame):
    """Convert frame to color histogram."""
    if frame is None:
        return None
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    return hist

def calculate_novelty(frame) -> float:
    """
    Calculate novelty score 0-1.
    Higher = more different from recent frames.
    """
    global frame_history

    if frame is None:
        return 0.0

    current_hist = get_histogram(frame)
    if current_hist is None:
        return 0.0

    if len(frame_history) == 0:
        frame_history.append(current_hist)
        return 1.0  # First frame is always novel

    # Compare to recent frames
    similarities = []
    for past_hist in frame_history:
        similarity = cv2.compareHist(current_hist, past_hist, cv2.HISTCMP_CORREL)
        similarities.append(similarity)

    # Novelty = 1 - average similarity
    avg_similarity = sum(similarities) / len(similarities)
    novelty = 1.0 - max(0, avg_similarity)

    # Update history
    frame_history.append(current_hist)
    if len(frame_history) > MAX_HISTORY:
        frame_history.pop(0)

    return novelty

# ═══════════════════════════════════════════════════════════════════════════════
# MOVEMENT PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════════

def move_forward_slow():
    """Move forward slowly."""
    px.set_dir_servo_angle(0)
    px.forward(EXPLORE_SPEED)

def stop_moving():
    """Stop all movement."""
    px.stop()

def backup_and_turn():
    """Back up and turn random direction."""
    px.stop()

    # Back up
    px.backward(BACKUP_SPEED)
    time.sleep(0.5)

    # Random turn
    angle = random.randint(30, 60) * random.choice([-1, 1])
    px.set_dir_servo_angle(angle)
    px.backward(BACKUP_SPEED)
    time.sleep(0.5)

    # Reset
    px.set_dir_servo_angle(0)
    px.stop()

def turn_slightly():
    """Turn slightly toward open space."""
    # Random small turn
    angle = random.randint(10, 25) * random.choice([-1, 1])
    px.set_dir_servo_angle(angle)
    px.forward(EXPLORE_SPEED)
    time.sleep(0.3)
    px.set_dir_servo_angle(0)

def pause_and_look():
    """Stop and look around curiously."""
    px.stop()

    # Pan camera around
    px.set_cam_pan_angle(-45)
    time.sleep(0.4)
    px.set_cam_pan_angle(45)
    time.sleep(0.4)
    px.set_cam_pan_angle(0)

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EXPLORATION LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def explore(
    max_duration: int = MAX_EXPLORE_DURATION,
    on_thought_callback=None,
    check_wake_word_callback=None
) -> str:
    """
    Main exploration loop.

    Args:
        max_duration: Maximum exploration time in seconds
        on_thought_callback: Function to call when robot wants to think out loud.
                            Called with (description: str) -> str (what to say)
        check_wake_word_callback: Function that returns True if wake word detected

    Returns:
        "wake_word" - Interrupted by wake word
        "table_mode" - Cliff detected, entering safe mode
        "timeout" - Max duration reached
    """
    start_time = time.time()
    last_thought_time = time.time()
    next_thought_interval = random.randint(THOUGHT_INTERVAL_MIN, THOUGHT_INTERVAL_MAX)

    print("Starting exploration...")

    try:
        while True:
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed >= max_duration:
                print("Exploration timeout")
                return "timeout"

            # Check wake word
            if check_wake_word_callback and check_wake_word_callback():
                print("Wake word detected during exploration")
                stop_moving()
                return "wake_word"

            # SAFETY: Check for cliff
            if is_cliff_detected():
                print("Cliff detected!")
                stop_moving()
                px.backward(BACKUP_SPEED)
                time.sleep(0.3)
                px.stop()
                return "table_mode"

            # Get distance
            distance = get_distance()

            # DANGER ZONE: Too close, back up
            if distance < DANGER_DISTANCE:
                backup_and_turn()
                continue

            # CAUTION ZONE: Getting close, turn slightly
            if distance < SAFE_DISTANCE:
                turn_slightly()
                continue

            # SAFE ZONE: Move forward
            move_forward_slow()

            # THOUGHT CHECK: Time for a thought?
            thought_elapsed = time.time() - last_thought_time
            if thought_elapsed >= next_thought_interval:
                # Pause and assess
                pause_and_look()

                # Capture frame and check novelty
                frame = capture_frame()
                novelty = calculate_novelty(frame)

                # If callback provided and novelty is interesting
                if on_thought_callback and novelty > 0.3:
                    # Robot might say something
                    response = on_thought_callback(novelty)
                    # Response is handled by callback (speaks if appropriate)

                # Reset thought timer
                last_thought_time = time.time()
                next_thought_interval = random.randint(THOUGHT_INTERVAL_MIN, THOUGHT_INTERVAL_MAX)

            # Small delay
            time.sleep(0.1)

    finally:
        # Always stop on exit
        stop_moving()
        print("Exploration ended")


# ═══════════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Simple test - explore for 30 seconds
    def dummy_thought(novelty):
        print(f"Novelty: {novelty:.2f}")
        return None

    result = explore(
        max_duration=30,
        on_thought_callback=dummy_thought,
        check_wake_word_callback=None
    )
    print(f"Exploration result: {result}")
```

**Success criteria:** Robot wanders, avoids obstacles, pauses periodically.

---

## Task 2.2: Vision API Integration

### Specification

**Add to `exploration.py`:**

```python
import base64
from openai import OpenAI

client = OpenAI()  # Uses OPENAI_API_KEY from environment

def describe_scene(frame) -> str:
    """
    Send frame to vision API, get description.
    Returns description in Swedish.
    """
    if frame is None:
        return "Kan inte se."

    try:
        # Encode frame as base64
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        base64_image = base64.b64encode(buffer).decode('utf-8')

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Beskriv kort vad du ser. Lista 3-5 objekt på svenska. Max 20 ord."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "low"
                            }
                        }
                    ]
                }
            ],
            max_tokens=50
        )

        return response.choices[0].message.content

    except Exception as e:
        print(f"Vision API error: {e}")
        return "Ser något."
```

**Success criteria:** `describe_scene(frame)` returns Swedish description of what camera sees.

---

## Task 2.3: Hook Exploration into Main Loop

### Specification

**File:** `voice_assistant.py`

**Add import at top:**

```python
from exploration import explore, describe_scene, capture_frame
```

**Add state tracking variable** (near other globals):

```python
current_mode = "listening"  # "listening", "conversation", "exploring", "table_mode"
last_conversation_time = time.time()
CONVERSATION_TIMEOUT = 30  # seconds before exploring
```

**Create the thought callback** (add as new function):

**Note:** This uses existing functions from voice_assistant.py:
- `client` - OpenAI client (already exists)
- `SYSTEM_PROMPT` - system prompt (already exists, updated in Task 1.1)
- `speak()` - TTS function (already exists)
- `execute_actions()` - from actions.py (created in Task 1.3)
- `parse_response()` - updated in Task 1.2

```python
def exploration_thought_callback(novelty: float) -> str:
    """
    Called during exploration when robot might think out loud.
    Returns what to say (or None to stay quiet).
    """
    # Only speak if novelty is high
    if novelty < 0.5:
        return None

    # Capture and describe scene
    frame = capture_frame()
    description = describe_scene(frame)

    # Ask LLM for a thought (non-streaming, short response)
    system_event = f"[SYSTEM: Du utforskar. Du ser: {description}. Tänk högt eller fortsätt utforska.]"

    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": system_event}
        ],
        max_tokens=100
    )

    full_response = response.choices[0].message.content
    actions, message, memory = parse_response(full_response)

    # Execute any actions
    if actions:
        execute_actions(actions, table_mode=False)

    # Save memory if present
    if memory:
        save_memory("discovery", memory)

    # Speak if there's a message
    if message and message.strip():
        speak(message)
        return message

    return None
```

**Add exploration trigger** (in main loop, after conversation ends, around line 1642):

```python
# After conversation, check if should explore
if not follow_up_mode:
    time_since_conversation = time.time() - last_conversation_time

    if time_since_conversation > CONVERSATION_TIMEOUT and current_mode != "table_mode":
        print("Entering exploration mode")
        current_mode = "exploring"

        result = explore(
            max_duration=3600,
            on_thought_callback=exploration_thought_callback,
            check_wake_word_callback=lambda: wake_word_detected  # Use existing detection
        )

        if result == "wake_word":
            current_mode = "listening"
            # Continue to normal conversation flow
        elif result == "table_mode":
            current_mode = "table_mode"
            # Send table mode message to LLM
            speak_system_event("[SYSTEM: Du upptäckte en kant. Säkerhetsläge aktiverat - ingen körning.]")
```

**Update conversation tracking** (when user speaks):

```python
# When user input is received (after transcription)
last_conversation_time = time.time()
current_mode = "conversation"
```

**Success criteria:** After 30s silence, robot explores. Wake word interrupts. Cliff triggers table mode.

---

# PHASE 3: SAFETY & MODES

---

## Task 3.1: Table Mode

### Specification

**Add to voice_assistant.py:**

```python
def enter_table_mode():
    """Enter safe mode - head movements only."""
    global current_mode
    current_mode = "table_mode"

    # Stop any movement
    px.stop()

    # Inform via system message
    speak_system_event("[SYSTEM: Du upptäckte en kant. Du står på ett bord. Säkerhetsläge - ingen körning.]")

def exit_table_mode():
    """Exit table mode, return to listening."""
    global current_mode
    current_mode = "listening"
    speak_system_event("[SYSTEM: Du är på golvet igen. Normal rörelse återställd.]")

def speak_system_event(event: str):
    """Send system event to LLM and speak response."""
    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": event}
        ],
        max_tokens=100
    )

    full_response = response.choices[0].message.content
    actions, message, memory = parse_response(full_response)

    # Execute actions (only head movements in table mode)
    if actions:
        execute_actions(actions, table_mode=(current_mode == "table_mode"))

    # Save memory if present
    if memory:
        save_memory("observation", memory)

    if message:
        speak(message)
```

**Add exit trigger** (in main loop, check user input for exit phrases):

```python
# After transcription, check for table mode exit
if current_mode == "table_mode":
    lower_text = text.lower()
    if "på golvet" in lower_text or "du är nere" in lower_text or "inte på bordet" in lower_text:
        exit_table_mode()
```

**Success criteria:** Cliff → table mode. Body actions blocked. Voice command exits.

---

## Task 3.2: Manual Control Detection

### Specification

**Add to voice_assistant.py:**

```python
from sunfounder_controller import SunFounderController

# Initialize controller (do once at startup)
try:
    controller = SunFounderController()
except:
    controller = None

last_manual_input_time = 0
MANUAL_CONTROL_TIMEOUT = 5  # seconds

def check_manual_control() -> bool:
    """Check if manual control is active."""
    global last_manual_input_time

    if controller is None:
        return False

    try:
        joystick = controller.get('K')
        if joystick and (abs(joystick[0]) > 5 or abs(joystick[1]) > 5):
            last_manual_input_time = time.time()
            return True
    except:
        pass

    # Check timeout
    if time.time() - last_manual_input_time < MANUAL_CONTROL_TIMEOUT:
        return True

    return False

def handle_manual_control():
    """Handle manual control mode."""
    global current_mode

    previous_mode = current_mode
    current_mode = "manual_control"

    # Inform Jarvis
    speak_system_event("[SYSTEM: Leon har tagit över kontrollerna. Du kan prata och röra huvudet men inte köra.]")

    # Loop while manual control active
    comment_interval = random.randint(5, 15)
    last_comment_time = time.time()

    while check_manual_control():
        # Occasional comment on the ride
        if time.time() - last_comment_time > comment_interval:
            joystick = controller.get('K') if controller else [0, 0]
            speed = abs(joystick[1]) if joystick else 0
            direction = "framåt" if joystick and joystick[1] > 0 else "bakåt"

            event = f"[SYSTEM: Leon kör dig manuellt. Fart: {speed}. Riktning: {direction}.]"
            speak_system_event(event)

            last_comment_time = time.time()
            comment_interval = random.randint(10, 20)

        time.sleep(0.1)

    # Manual control ended
    current_mode = previous_mode
    speak_system_event("[SYSTEM: Leon släppte kontrollerna. Du kan röra dig själv igen.]")
```

**Add check in main loop** (before exploration or conversation):

```python
# Check for manual control
if check_manual_control():
    handle_manual_control()
    continue  # Restart loop after manual control ends
```

**Success criteria:** App joystick → manual mode. Jarvis comments. 5s timeout → return.

---

# PHASE 4: MEMORY

---

## Memory Architecture

The memory system mirrors how Claude's own memory works:

1. **Storage**: Entity-based JSON file with observations per entity (Leon, environment, self)
2. **Injection**: Formatted memories added to system prompt before each API call
3. **Extraction**: LLM outputs MEMORY[entity]: line, parsed after response completes
4. **No extra API calls**: Memory flows through the single LLM call

Example memory.json:
```json
{
  "entities": {
    "Leon": {
      "observations": [
        {"content": "gillar dinosaurier", "timestamp": "2024-01-29T10:00:00"}
      ]
    }
  }
}
```

Example injection into prompt:
```
Du minns om Leon:
- gillar dinosaurier
```

---

## Task 4.1: Create Memory Module

### Specification

**Create file:** `memory.py`

```python
"""
Jarvis Memory Module
Entity-based persistent memory.
"""

import json
import os
import re
import tempfile
import shutil
from datetime import datetime

MEMORY_FILE = "memory.json"
MAX_OBSERVATIONS_PER_ENTITY = 20
MAX_OBSERVATIONS_IN_CONTEXT = 15

def load_memory() -> dict:
    """Load memory from file."""
    if not os.path.exists(MEMORY_FILE):
        return {"entities": {}}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Memory load error: {e}")
        return {"entities": {}}

def save_memory_file(memory: dict):
    """Atomic save - write to temp, then rename."""
    temp_fd, temp_path = tempfile.mkstemp(suffix='.json', dir=os.path.dirname(MEMORY_FILE) or '.')
    try:
        with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
        shutil.move(temp_path, MEMORY_FILE)
    except Exception as e:
        print(f"Memory save error: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)

def detect_entity(text: str) -> tuple[str, str]:
    """Auto-detect entity from text. Fallback for untagged MEMORY lines."""
    lower = text.lower().strip()

    # Leon references
    if lower.startswith("leon"):
        for prefix in ["leon's ", "leons ", "leon "]:
            if lower.startswith(prefix):
                return "Leon", text[len(prefix):].strip()
        return "Leon", text

    # Self references
    if lower.startswith("jag "):
        return "self", text[4:].strip()

    # Environment keywords
    env_keywords = ["hittade", "såg", "rummet", "under", "bakom", "golvet", "bordet"]
    if any(kw in lower for kw in env_keywords):
        return "environment", text

    return "general", text

def parse_memory_line(line: str) -> tuple[str, str] | None:
    """
    Parse MEMORY line with explicit or auto-detected entity.

    Formats:
      MEMORY[Leon]: gillar dinosaurier
      MEMORY: Leon gillar dinosaurier
    """
    line = line.strip()
    if not line.upper().startswith('MEMORY'):
        return None

    # Try explicit tag: MEMORY[entity]: observation
    match = re.match(r'MEMORY\[(\w+)\]:\s*(.+)', line, re.IGNORECASE)
    if match:
        entity = match.group(1).lower()
        observation = match.group(2).strip()

        # Normalize entity names
        if entity in ["leon"]:
            entity = "Leon"
        elif entity in ["env", "environment", "rummet", "rum"]:
            entity = "environment"
        elif entity in ["self", "jag", "själv", "mig"]:
            entity = "self"
        else:
            entity = entity.capitalize()

        return entity, observation

    # Fallback: MEMORY: text
    if ':' in line:
        text = line.split(':', 1)[1].strip()
        if text:
            return detect_entity(text)

    return None

def add_observation(entity: str, observation: str):
    """Add observation to entity."""
    if not observation or not observation.strip():
        return

    memory = load_memory()

    if entity not in memory["entities"]:
        memory["entities"][entity] = {"observations": []}

    memory["entities"][entity]["observations"].append({
        "content": observation.strip(),
        "timestamp": datetime.now().isoformat()
    })

    # Prune if too many
    obs = memory["entities"][entity]["observations"]
    if len(obs) > MAX_OBSERVATIONS_PER_ENTITY:
        memory["entities"][entity]["observations"] = obs[-MAX_OBSERVATIONS_PER_ENTITY:]

    save_memory_file(memory)
    print(f"Memory saved: [{entity}] {observation}")

def format_memories_for_prompt() -> str:
    """Format memories for system prompt injection."""
    memory = load_memory()
    entities = memory.get("entities", {})

    if not entities:
        return ""

    sections = []
    total = 0

    # Priority order
    for entity, header in [
        ("Leon", "Du minns om Leon:"),
        ("self", "Du minns om dig själv:"),
        ("environment", "Du minns om rummet:"),
        ("general", "Du minns:")
    ]:
        if entity not in entities:
            continue

        observations = entities[entity].get("observations", [])
        if not observations:
            continue

        # Take most recent
        recent = observations[-5:]

        lines = [header]
        for obs in recent:
            lines.append(f"- {obs['content']}")
            total += 1
            if total >= MAX_OBSERVATIONS_IN_CONTEXT:
                break

        sections.append("\n".join(lines))

        if total >= MAX_OBSERVATIONS_IN_CONTEXT:
            break

    return "\n\n".join(sections)
```

**Success criteria:**
- Memories save to entity-based JSON structure
- Atomic file writes prevent corruption
- Entity detection works for tagged (MEMORY[Leon]:) and untagged (MEMORY: Leon...) formats

---

## Task 4.2: Integrate Memory with Chat

### Specification

**In voice_assistant.py, add import:**

```python
from memory import add_observation, format_memories_for_prompt
```

**Modify system prompt building** (where SYSTEM_PROMPT is used):

```python
def get_full_system_prompt() -> str:
    """Get system prompt with current memory context."""
    memory_context = format_memories_for_prompt()

    if memory_context:
        return SYSTEM_PROMPT + "\n\n" + memory_context
    return SYSTEM_PROMPT
```

**Use in chat function:**

```python
# In chat_with_gpt or wherever messages are built
messages = [
    {"role": "system", "content": get_full_system_prompt()},
    # ... rest of messages
]
```

**After parsing response, save memory:**

```python
# After parse_response()
actions, message, memory = parse_response(full_response)

if memory:
    entity, observation = memory
    add_observation(entity, observation)
```

**Success criteria:** Memories injected into prompt. New memories saved from responses.

---

# PHASE 5: DEPLOY & TEST

---

## Task 5.1: Deploy

### Commands

```bash
# On Mac
cd /Users/maxwraae/picar-setup/picar-brain
git add -A
git commit -m "Jarvis v5: personality, actions, exploration, memory"
git push

# On Pi
ssh pi@picar.lan
cd /home/pi/picar-brain
git pull
sudo systemctl restart voice

# Watch logs
journalctl -u voice -f
```

---

## Task 5.2: Test Checklist

Run each test. Mark complete when working.

- [ ] **Wake word:** Say "Jarvis" → responds
- [ ] **Personality:** Response is in Swedish with dry humor
- [ ] **JSON format:** Responses parse correctly
- [ ] **Actions - nod:** "nicka" → head nods
- [ ] **Actions - shake:** "skaka på huvudet" → head shakes
- [ ] **Actions - move:** "kom hit" → moves forward
- [ ] **Actions - rock:** Tell a joke → rocks back and forth
- [ ] **Exploration start:** Wait 30s silence → starts wandering
- [ ] **Exploration avoid:** Approaches wall → turns away
- [ ] **Exploration thought:** During exploration → occasionally comments
- [ ] **Wake interrupts:** Say "Jarvis" during exploration → stops, listens
- [ ] **Cliff detection:** Near edge → stops, enters table mode
- [ ] **Table mode block:** In table mode, ask to move → refuses, head only
- [ ] **Table mode exit:** Say "du är på golvet" → exits table mode
- [ ] **Manual control:** Use app joystick → Jarvis comments on ride
- [ ] **Memory save:** Tell Jarvis something → restart → remembers
- [ ] **Memory in context:** Jarvis references past conversations

---

## Task 5.3: Rollback

If something breaks:

```bash
# On Pi
cd /home/pi/picar-brain
git log --oneline          # Find last good commit
git checkout <commit-hash>  # Go back
sudo systemctl restart voice
```

---

# FILES TO CREATE

| File | Purpose |
|------|---------|
| `actions.py` | Action library |
| `exploration.py` | Exploration module |
| `memory.py` | Memory persistence |

# FILES TO MODIFY

| File | Changes |
|------|---------|
| `voice_assistant.py` | System prompt, parser, integrations |

---

# SEQUENCE

Execute in this order:

1. Task 1.1: Replace system prompt
2. Task 1.2: Update response parser
3. Task 1.3: Create action library
4. Task 4.1: Create memory module
5. Task 4.2: Integrate memory with chat
6. Task 2.1: Create exploration module
7. Task 2.2: Add vision API integration
8. Task 2.3: Hook exploration into main loop
9. Task 3.1: Table mode
10. Task 3.2: Manual control detection
11. Task 5.1: Deploy
12. Task 5.2: Test

Each task is independent. One agent per task. Verify before proceeding.
