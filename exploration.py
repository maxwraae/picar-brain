"""
Jarvis Exploration Module
Attention-based curious wandering.
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

SAFE_DISTANCE = 30      # cm - safe to move forward (was 40)
DANGER_DISTANCE = 15    # cm - must turn or back up (was 20)
EXPLORE_SPEED = 20      # slower exploration (was 25)
BACKUP_SPEED = 20       # slower backup (was 30)
DEBUG_DISTANCE = True   # Print distance readings
THOUGHT_INTERVAL_MIN = 30   # seconds between thoughts
THOUGHT_INTERVAL_MAX = 60
MAX_EXPLORE_DURATION = 3600  # 1 hour max

# Manual control detection - DISABLED (sensor too noisy)
# MANUAL_CONTROL_CLOSE = 5    # cm - too close, likely picked up
# MANUAL_CONTROL_JUMP = 50    # cm - sudden distance jump
MANUAL_CONTROL_ENABLED = False  # Set True to re-enable

# ═══════════════════════════════════════════════════════════════════════════════
# SENSORS
# ═══════════════════════════════════════════════════════════════════════════════

def get_distance() -> float:
    """Get ultrasonic distance in cm."""
    try:
        dist = px.ultrasonic.read()
        # Sensor returns negative or very small values when failing
        # Minimum reliable reading is ~2cm
        if dist < 2:
            return 100  # Assume safe if sensor fails
        return dist
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
    previous_distance = None  # Track previous distance for manual control detection

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
            if DEBUG_DISTANCE:
                print(f"📏 Distance: {distance:.1f}cm")

            # MANUAL CONTROL DETECTION: Disabled due to sensor noise
            # if MANUAL_CONTROL_ENABLED and previous_distance is not None:
            #     distance_change = abs(distance - previous_distance)
            #     if distance < 5 or distance_change > 50:
            #         print(f"Manual control detected! Distance: {distance}cm")
            #         stop_moving()
            #         return "manual_control"

            previous_distance = distance

            # DANGER ZONE: Too close, back up
            if distance < DANGER_DISTANCE:
                print(f"⚠️ DANGER ({distance:.0f}cm < {DANGER_DISTANCE}) - backing up")
                backup_and_turn()
                continue

            # CAUTION ZONE: Getting close, turn slightly
            if distance < SAFE_DISTANCE:
                print(f"🔶 CAUTION ({distance:.0f}cm < {SAFE_DISTANCE}) - turning")
                turn_slightly()
                continue

            # SAFE ZONE: Move forward
            print(f"✅ SAFE ({distance:.0f}cm) - forward")
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
