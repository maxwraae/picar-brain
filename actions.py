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
