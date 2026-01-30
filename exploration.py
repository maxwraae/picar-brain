"""
Jarvis Exploration Module
Cute curious exploration - HEAD LEADS, BODY FOLLOWS. Like a curious creature.
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

# Speed
MOVE_SPEED = 15                # Minimum that works (below this motors don't move)

# Variable timing ranges (makes it feel organic)
MOVE_DURATION_MIN = 0.3        # seconds
MOVE_DURATION_MAX = 0.5        # seconds
PAUSE_MIN = 2.0                # seconds
PAUSE_MAX = 6.0                # seconds (variable - feels alive)
LOOK_INTERVAL_MIN = 10         # seconds
LOOK_INTERVAL_MAX = 20         # seconds
SPEAK_INTERVAL_MIN = 30        # seconds
SPEAK_INTERVAL_MAX = 60        # seconds

# Safety
SAFE_DISTANCE = 40             # cm
DANGER_DISTANCE = 25           # cm
CORNER_THRESHOLD = 3           # consecutive obstacles before "stuck"

MAX_EXPLORE_DURATION = 3600    # 1 hour max
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
    Returns dict with: what_i_see, direction, interesting
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
                            "text": """Du är Jarvis, en liten nyfiken robot som utforskar. Beskriv kort vad du ser.

Svara EXAKT i detta format:
SER: [vad du ser, max 8 ord]
RIKTNING: [forward/left/right/back]
INTRESSANT: [ja/nej]

Exempel:
SER: Golv, en blå sko, kabel
RIKTNING: forward
INTRESSANT: ja"""
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
            max_tokens=60
        )

        text = response.choices[0].message.content
        result = {"what_i_see": None, "direction": "forward", "interesting": False}

        # Parse response
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('SER:'):
                result["what_i_see"] = line.replace('SER:', '').strip()
            elif line.startswith('RIKTNING:'):
                direction = line.replace('RIKTNING:', '').strip().lower()
                if direction in ['forward', 'left', 'right', 'back']:
                    result["direction"] = direction
            elif line.startswith('INTRESSANT:'):
                interesting = line.replace('INTRESSANT:', '').strip().lower()
                result["interesting"] = interesting == 'ja'

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
        return result.get("what_i_see")
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# MOVEMENT - HEAD LEADS, BODY FOLLOWS
# ═══════════════════════════════════════════════════════════════════════════════

def stop():
    """Stop all movement."""
    px.stop()
    time.sleep(0.1)  # Let motors fully stop

def turn_head_to_direction(direction: str):
    """Turn head toward a direction (anticipation). Returns pan angle used."""
    angle_map = {
        'left': -45,
        'right': 45,
        'forward': 0,
        'back': 0  # When backing up, look forward (where we came from)
    }
    angle = angle_map.get(direction, 0)
    px.set_cam_pan_angle(angle)
    return angle

def move_forward_short():
    """Short creep forward (variable duration)."""
    px.stop()
    time.sleep(0.1)
    px.set_dir_servo_angle(0)
    px.forward(MOVE_SPEED)
    time.sleep(random.uniform(MOVE_DURATION_MIN, MOVE_DURATION_MAX))
    px.stop()
    time.sleep(0.1)

def turn_and_move(direction: str):
    """
    THE CUTE PART: Turn head first (anticipation), pause, then body follows.
    Direction: 'left', 'right', 'forward', 'back'
    """
    # 1. HEAD LEADS - look toward where we want to go
    turn_head_to_direction(direction)
    time.sleep(random.uniform(0.3, 0.5))  # ANTICIPATION PAUSE - "I'm going to go there!"

    # 2. BODY FOLLOWS
    px.stop()
    time.sleep(0.1)

    if direction == 'left':
        angle = random.randint(-35, -25)
        px.set_dir_servo_angle(angle)
        px.forward(MOVE_SPEED)
        time.sleep(random.uniform(MOVE_DURATION_MIN, MOVE_DURATION_MAX))
        px.stop()
        time.sleep(0.1)
        px.set_dir_servo_angle(0)

    elif direction == 'right':
        angle = random.randint(25, 35)
        px.set_dir_servo_angle(angle)
        px.forward(MOVE_SPEED)
        time.sleep(random.uniform(MOVE_DURATION_MIN, MOVE_DURATION_MAX))
        px.stop()
        time.sleep(0.1)
        px.set_dir_servo_angle(0)

    elif direction == 'forward':
        move_forward_short()

    elif direction == 'back':
        px.set_dir_servo_angle(0)
        px.backward(MOVE_SPEED)
        time.sleep(random.uniform(0.4, 0.6))
        px.stop()
        time.sleep(0.1)

    # DON'T reset head to center - keep looking where we went
    # Head stays in direction = curious creature effect
    # Head only resets during look_around() or reset_head()

def escape_corner(vision_clear_direction=None):
    """
    Escape when stuck - deliberate, staged, not frantic.
    If vision suggests a clear direction, use it.
    """
    print("[EXPLORE] Stuck! Escaping corner...")
    px.stop()
    time.sleep(0.1)

    # Determine which way looks clear
    clear_dir = vision_clear_direction if vision_clear_direction else random.choice(['left', 'right'])

    # Look toward the clear direction first
    turn_head_to_direction(clear_dir)
    time.sleep(0.5)

    # Back up in stages (deliberate, thinking through it)
    px.set_dir_servo_angle(0)
    px.backward(MOVE_SPEED)
    time.sleep(0.4)
    px.stop()
    time.sleep(0.3)

    px.backward(MOVE_SPEED)
    time.sleep(0.4)
    px.stop()
    time.sleep(0.3)

    # Turn and back up
    angle = random.randint(40, 60) * (1 if clear_dir == 'right' else -1)
    px.set_dir_servo_angle(angle)
    px.backward(MOVE_SPEED)
    time.sleep(0.4)
    px.stop()
    time.sleep(0.1)

    # Reset
    px.set_dir_servo_angle(0)
    px.set_cam_pan_angle(0)
    time.sleep(0.2)

def look_around():
    """Pan camera around curiously - left, center, right."""
    px.stop()
    time.sleep(0.1)

    # Look left
    px.set_cam_pan_angle(-50)
    time.sleep(0.6)

    # Look center
    px.set_cam_pan_angle(0)
    time.sleep(0.4)

    # Look right
    px.set_cam_pan_angle(50)
    time.sleep(0.6)

    # Back to center
    px.set_cam_pan_angle(0)
    time.sleep(0.3)

def look_at_something():
    """Tilt head curiously at something."""
    px.set_cam_tilt_angle(random.randint(-15, 15))
    px.set_cam_pan_angle(random.randint(-30, 30))

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
    Cute curious exploration - HEAD LEADS, BODY FOLLOWS.

    Flow:
    1. OBSERVE (every 10-20s variable) - stop, look around, take picture, ask vision
    2. DECIDE - stuck? interesting? obstacle? vision suggestion?
    3. ANTICIPATE - turn HEAD toward chosen direction first (THE CUTE PART)
    4. MOVE - short creep in that direction
    5. PAUSE - variable 2-6s (feels organic)
    6. QUICK CHECK - ultrasonic, wake word, timeout
    7. REPEAT
    """
    start_time = time.time()
    last_observation_time = time.time() - 999  # Force first observation
    last_speak_time = time.time()
    next_observation_interval = random.uniform(LOOK_INTERVAL_MIN, LOOK_INTERVAL_MAX)
    next_speak_interval = random.uniform(SPEAK_INTERVAL_MIN, SPEAK_INTERVAL_MAX)
    consecutive_obstacles = 0

    print("[EXPLORE] Starting cute curious exploration...")
    print("[EXPLORE] HEAD LEADS, BODY FOLLOWS")

    try:
        while True:
            now = time.time()
            elapsed = now - start_time

            # === TIMEOUT CHECK ===
            if elapsed >= max_duration:
                print("[EXPLORE] Timeout")
                return "timeout"

            # === WAKE WORD CHECK ===
            if check_wake_word_callback and check_wake_word_callback():
                print("[EXPLORE] Wake word detected!")
                stop()
                return "wake_word"

            # === FULL OBSERVATION (variable timing) ===
            if now - last_observation_time > next_observation_interval:
                print("[EXPLORE] === OBSERVE ===")
                stop()
                look_around()

                # Take picture and analyze with vision
                frame = capture_frame()
                vision_result = None
                chosen_direction = 'forward'  # default

                if frame is not None:
                    vision_result = analyze_scene(frame)
                    if vision_result:
                        print(f"[VISION] Ser: {vision_result['what_i_see']}")
                        print(f"[VISION] Förslag: {vision_result['direction']}, Intressant: {vision_result['interesting']}")

                        # Decide based on vision
                        if consecutive_obstacles >= CORNER_THRESHOLD:
                            # Stuck - escape with vision help
                            print("[EXPLORE] === STUCK - ESCAPING ===")
                            escape_corner(vision_clear_direction=vision_result['direction'])
                            consecutive_obstacles = 0
                            chosen_direction = None  # Already moved

                        elif vision_result['interesting']:
                            # Something interesting - go toward it
                            print(f"[EXPLORE] === INTERESTING! Going {vision_result['direction']} ===")
                            chosen_direction = vision_result['direction']

                        else:
                            # Follow vision suggestion
                            chosen_direction = vision_result['direction']
                            print(f"[EXPLORE] === Vision suggests: {chosen_direction} ===")

                # Move if we have a direction
                if chosen_direction:
                    turn_and_move(chosen_direction)

                # Reset timers with variable intervals
                last_observation_time = now
                next_observation_interval = random.uniform(LOOK_INTERVAL_MIN, LOOK_INTERVAL_MAX)
                print(f"[EXPLORE] Next observation in {next_observation_interval:.1f}s")

            # === QUICK MOVEMENT (between full observations) ===
            else:
                # Quick ultrasonic check
                distance = get_distance()

                if distance < DANGER_DISTANCE:
                    # Too close - turn away
                    print(f"[EXPLORE] Obstacle at {distance:.0f}cm - turning away")
                    turn_direction = random.choice(['left', 'right'])
                    turn_and_move(turn_direction)
                    consecutive_obstacles += 1

                elif distance < SAFE_DISTANCE:
                    # Getting close - slight turn
                    print(f"[EXPLORE] Close at {distance:.0f}cm - slight turn")
                    turn_direction = random.choice(['left', 'right'])
                    turn_and_move(turn_direction)
                    consecutive_obstacles = 0

                else:
                    # Safe - creep forward
                    if DEBUG:
                        print(f"[EXPLORE] Safe at {distance:.0f}cm - creeping forward")
                    turn_and_move('forward')
                    consecutive_obstacles = 0

            # === PAUSE (variable - feels organic) ===
            pause_duration = random.uniform(PAUSE_MIN, PAUSE_MAX)
            if DEBUG:
                print(f"[EXPLORE] Pausing {pause_duration:.1f}s...")
            time.sleep(pause_duration)

            # === SPEAK OCCASIONALLY (variable timing) ===
            # Use fresh time after pause
            speak_check_time = time.time()
            if on_thought_callback and (speak_check_time - last_speak_time > next_speak_interval):
                print("[EXPLORE] === TIME TO SPEAK ===")
                stop()
                look_at_something()
                time.sleep(0.4)

                # Take picture and describe
                frame = capture_frame()
                if frame is not None:
                    description = describe_scene(frame)
                    if description:
                        print(f"[EXPLORE] Speaking: {description}")
                        on_thought_callback(description)

                reset_head()
                last_speak_time = speak_check_time
                next_speak_interval = random.uniform(SPEAK_INTERVAL_MIN, SPEAK_INTERVAL_MAX)
                print(f"[EXPLORE] Next speak in {next_speak_interval:.1f}s")

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
