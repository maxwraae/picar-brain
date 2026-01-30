"""
Jarvis Exploration Module
Curious, deliberate wandering - like a cautious creature exploring.
"""

import time
import random
import cv2
import numpy as np
import base64
from openai import OpenAI
from actions import px  # Use shared Picarx instance from actions module
from keys import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Motor minimum is ~15 (below that motors don't move due to static friction)
# We achieve "slow" feeling through short bursts + long pauses, not low PWM
CREEP_SPEED = 15         # Minimum working speed for motors
BACKUP_SPEED = 15        # Same for backup
SAFE_DISTANCE = 40       # cm - comfortable distance
DANGER_DISTANCE = 25     # cm - too close, back up
CORNER_THRESHOLD = 3     # Consecutive backups before "stuck"

# Timing - this is how we make it feel slow and deliberate
CREEP_DURATION = 0.4     # Short forward bursts (less distance per move)
PAUSE_DURATION = 1.5     # Long pauses between movements (feels thoughtful)
LOOK_INTERVAL = 12       # Seconds between looking around
SPEAK_INTERVAL = 30      # Seconds between saying something

MAX_EXPLORE_DURATION = 3600  # 1 hour max
DEBUG = True

# ═══════════════════════════════════════════════════════════════════════════════
# SENSORS
# ═══════════════════════════════════════════════════════════════════════════════

def get_distance() -> float:
    """Get ultrasonic distance in cm."""
    try:
        raw = px.ultrasonic.read()
        if raw < 2:
            if DEBUG:
                print(f"[SENSOR] Bad reading {raw}cm, assuming safe")
            return 100
        return raw
    except Exception as e:
        if DEBUG:
            print(f"[SENSOR] Error: {e}")
        return 100

# ═══════════════════════════════════════════════════════════════════════════════
# CAMERA
# ═══════════════════════════════════════════════════════════════════════════════

def capture_frame():
    """Capture a frame from the camera."""
    try:
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ret, frame = cap.read()
        cap.release()
        if ret:
            return cv2.resize(frame, (320, 240))
        return None
    except Exception as e:
        if DEBUG:
            print(f"[CAMERA] Error: {e}")
        return None

def analyze_scene(frame) -> dict:
    """
    Ask vision API to analyze the scene and suggest action.
    Returns dict with: description, action, stuck
    """
    if frame is None:
        return None

    try:
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        base64_image = base64.b64encode(buffer).decode('utf-8')

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Du är en liten robot som utforskar ett rum. Analysera bilden och svara i detta format:

BESKRIVNING: [Vad ser du? Max 10 ord på svenska]
SITUATION: [open/corner/blocked/wall]
FÖRSLAG: [forward/left/right/back]

Exempel:
BESKRIVNING: Jag ser ett bord och några stolar
SITUATION: open
FÖRSLAG: forward

BESKRIVNING: Hörn med väggar på två sidor
SITUATION: corner
FÖRSLAG: back"""
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
            max_tokens=80
        )

        text = response.choices[0].message.content
        result = {"description": None, "situation": "open", "action": "forward"}

        # Parse response
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('BESKRIVNING:'):
                result["description"] = line.replace('BESKRIVNING:', '').strip()
            elif line.startswith('SITUATION:'):
                sit = line.replace('SITUATION:', '').strip().lower()
                if sit in ['open', 'corner', 'blocked', 'wall']:
                    result["situation"] = sit
            elif line.startswith('FÖRSLAG:'):
                act = line.replace('FÖRSLAG:', '').strip().lower()
                if act in ['forward', 'left', 'right', 'back']:
                    result["action"] = act

        if DEBUG:
            print(f"[VISION] {result}")
        return result

    except Exception as e:
        if DEBUG:
            print(f"[VISION] Error: {e}")
        return None


def describe_scene(frame) -> str:
    """Simple scene description for speaking."""
    result = analyze_scene(frame)
    if result:
        return result.get("description")
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# MOVEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def stop():
    """Stop all movement."""
    px.stop()

def creep_forward():
    """Creep forward slowly for a short burst, then stop completely."""
    px.stop()  # Always start from stopped state
    px.set_dir_servo_angle(0)
    px.forward(CREEP_SPEED)
    time.sleep(CREEP_DURATION)
    px.stop()
    time.sleep(0.1)  # Let motors fully stop

def backup_and_turn(direction=None):
    """Back up and turn. Direction: -1=left, 1=right, None=random."""
    px.stop()  # Start from stopped

    if direction is None:
        direction = random.choice([-1, 1])

    # Back up straight first
    px.set_dir_servo_angle(0)
    px.backward(BACKUP_SPEED)
    time.sleep(0.5)
    px.stop()
    time.sleep(0.2)

    # Turn while backing
    angle = random.randint(35, 55) * direction
    px.set_dir_servo_angle(angle)
    px.backward(BACKUP_SPEED)
    time.sleep(0.5)

    # Reset and stop completely
    px.stop()
    px.set_dir_servo_angle(0)
    time.sleep(0.1)

def escape_corner():
    """Bigger maneuver to escape a corner - deliberate, not frantic."""
    print("[EXPLORE] Stuck! Escaping corner...")
    px.stop()

    # Back up a lot in stages (feels more deliberate)
    px.set_dir_servo_angle(0)
    px.backward(BACKUP_SPEED)
    time.sleep(0.6)
    px.stop()
    time.sleep(0.3)
    px.backward(BACKUP_SPEED)
    time.sleep(0.6)
    px.stop()
    time.sleep(0.3)

    # Big turn
    angle = random.randint(50, 70) * random.choice([-1, 1])
    px.set_dir_servo_angle(angle)
    px.backward(BACKUP_SPEED)
    time.sleep(0.6)

    # Reset and stop completely
    px.stop()
    px.set_dir_servo_angle(0)
    time.sleep(0.2)

def look_around():
    """Pan camera around curiously."""
    print("[EXPLORE] Looking around...")
    stop()

    # Look left
    px.set_cam_pan_angle(-50)
    time.sleep(0.6)

    # Look right
    px.set_cam_pan_angle(50)
    time.sleep(0.6)

    # Look center
    px.set_cam_pan_angle(0)
    time.sleep(0.3)

def look_at_something():
    """Tilt head curiously."""
    px.set_cam_tilt_angle(random.randint(-15, 15))
    px.set_cam_pan_angle(random.randint(-20, 20))

def reset_head():
    """Center the camera."""
    px.set_cam_pan_angle(0)
    px.set_cam_tilt_angle(0)

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN EXPLORATION
# ═══════════════════════════════════════════════════════════════════════════════

def explore(
    max_duration: int = MAX_EXPLORE_DURATION,
    on_thought_callback=None,
    check_wake_word_callback=None
) -> str:
    """
    Curious exploration loop.

    Behavior:
    - Creep forward slowly, pause, repeat
    - Stop and look around periodically
    - Take pictures and describe what we see
    - Detect when stuck in corner and escape
    - Say something occasionally via callback
    """
    start_time = time.time()
    last_look_time = time.time()
    last_speak_time = time.time()
    consecutive_backups = 0

    print("[EXPLORE] Starting curious exploration...")

    try:
        while True:
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed >= max_duration:
                print("[EXPLORE] Timeout")
                return "timeout"

            # Check wake word
            if check_wake_word_callback and check_wake_word_callback():
                print("[EXPLORE] Wake word detected!")
                stop()
                return "wake_word"

            # Get distance
            distance = get_distance()
            if DEBUG:
                print(f"[EXPLORE] Distance: {distance:.0f}cm")

            # === MOVEMENT DECISION ===

            if distance < DANGER_DISTANCE:
                # Too close - back up
                print(f"[EXPLORE] Too close ({distance:.0f}cm) - backing up")
                backup_and_turn()
                consecutive_backups += 1

                # Stuck in corner?
                if consecutive_backups >= CORNER_THRESHOLD:
                    escape_corner()
                    consecutive_backups = 0

            elif distance < SAFE_DISTANCE:
                # Getting close - turn slightly
                print(f"[EXPLORE] Close ({distance:.0f}cm) - turning")
                px.stop()
                angle = random.randint(15, 30) * random.choice([-1, 1])
                px.set_dir_servo_angle(angle)
                px.forward(CREEP_SPEED)
                time.sleep(0.3)
                px.stop()
                px.set_dir_servo_angle(0)
                time.sleep(0.1)
                consecutive_backups = 0

            else:
                # Safe - creep forward
                print(f"[EXPLORE] Safe ({distance:.0f}cm) - creeping")
                creep_forward()
                consecutive_backups = 0

            # Pause between movements
            time.sleep(PAUSE_DURATION)

            # === VISION CHECK ===

            now = time.time()
            if now - last_look_time > LOOK_INTERVAL:
                stop()
                look_around()

                # Take a picture and analyze
                frame = capture_frame()
                if frame is not None:
                    analysis = analyze_scene(frame)
                    if analysis:
                        print(f"[EXPLORE] Vision says: {analysis}")

                        # Use vision suggestion for next action
                        if analysis["situation"] in ["corner", "blocked"]:
                            print("[EXPLORE] Vision detected corner/blocked - escaping")
                            escape_corner()
                            consecutive_backups = 0
                        elif analysis["action"] == "left":
                            print("[EXPLORE] Vision suggests left")
                            px.stop()
                            px.set_dir_servo_angle(-30)
                            px.forward(CREEP_SPEED)
                            time.sleep(0.4)
                            px.stop()
                            px.set_dir_servo_angle(0)
                        elif analysis["action"] == "right":
                            print("[EXPLORE] Vision suggests right")
                            px.stop()
                            px.set_dir_servo_angle(30)
                            px.forward(CREEP_SPEED)
                            time.sleep(0.4)
                            px.stop()
                            px.set_dir_servo_angle(0)
                        elif analysis["action"] == "back":
                            print("[EXPLORE] Vision suggests back")
                            backup_and_turn()

                last_look_time = now

            # === SAY SOMETHING ===

            if on_thought_callback and (now - last_speak_time > SPEAK_INTERVAL):
                # Stop and look at something
                stop()
                look_at_something()
                time.sleep(0.3)

                # Take picture and describe
                frame = capture_frame()
                if frame is not None:
                    description = describe_scene(frame)
                    if description:
                        print(f"[EXPLORE] Saying: {description}")
                        on_thought_callback(description)

                reset_head()
                last_speak_time = now

    finally:
        stop()
        reset_head()
        print("[EXPLORE] Exploration ended")


# ═══════════════════════════════════════════════════════════════════════════════
# TESTING
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    def say_thought(text):
        print(f">>> WOULD SAY: {text}")

    result = explore(
        max_duration=60,
        on_thought_callback=say_thought,
        check_wake_word_callback=None
    )
    print(f"Result: {result}")
