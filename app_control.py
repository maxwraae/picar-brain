#!/usr/bin/env python3
"""PiCar App Control - patched for Python 3.13"""

import os
os.getlogin = lambda: "pi"  # Patch for systemd

from sunfounder_controller import SunFounderController
from picarx import Picarx
from robot_hat import utils, Music
from vilib import Vilib
from time import sleep

utils.reset_mcu()
sleep(0.2)

sc = SunFounderController()
sc.set_name("Picarx-Leon")
sc.set_type("Picarx")
sc.set("video", "http://192.168.1.101:9000/mjpg")  # Tell app where video is
sc.start()

px = Picarx()
speed = 0

AVOID_OBSTACLES_SPEED = 40
SafeDistance = 40
DangerDistance = 20
LINE_TRACK_SPEED = 10
LINE_TRACK_ANGLE_OFFSET = 20

User = "pi"
UserHome = "/home/pi"
SOUNDS_DIR = f"{UserHome}/picar-brain/sounds"

# Music can fail if audio device busy - don't crash
try:
    music = Music()
except Exception as e:
    print(f"⚠️ Music init failed: {e}")
    music = None

def horn():
    if music is None:
        return
    try:
        utils.run_command("sudo killall pulseaudio")
        music.sound_play_threading(f"{SOUNDS_DIR}/car-double-horn.wav")
    except Exception:
        pass

def avoid_obstacles():
    distance = px.get_distance()
    if distance >= SafeDistance:
        px.set_dir_servo_angle(0)
        px.forward(AVOID_OBSTACLES_SPEED)
    elif distance >= DangerDistance:
        px.set_dir_servo_angle(30)
        px.forward(AVOID_OBSTACLES_SPEED)
        sleep(0.1)
    else:
        px.set_dir_servo_angle(-30)
        px.backward(AVOID_OBSTACLES_SPEED)
        sleep(0.5)

def get_status(val_list):
    _state = px.get_line_status(val_list)
    if _state == [0, 0, 0]:
        return "stop"
    elif _state[1] == 1:
        return "forward"
    elif _state[0] == 1:
        return "right"
    elif _state[2] == 1:
        return "left"

last_line_state = "stop"

def line_track():
    global last_line_state
    gm_val_list = px.get_grayscale_data()
    gm_state = get_status(gm_val_list)
    if gm_state != "stop":
        last_line_state = gm_state
    if gm_state == "forward":
        px.set_dir_servo_angle(0)
        px.forward(LINE_TRACK_SPEED)
    elif gm_state == "left":
        px.set_dir_servo_angle(LINE_TRACK_ANGLE_OFFSET)
        px.forward(LINE_TRACK_SPEED)
    elif gm_state == "right":
        px.set_dir_servo_angle(-LINE_TRACK_ANGLE_OFFSET)
        px.forward(LINE_TRACK_SPEED)

def main():
    global speed, last_line_state
    
    Vilib.camera_start(vflip=False, hflip=False)
    Vilib.display(local=False, web=True)
    sleep(2)
    
    print("PiCar App Control started!")
    print("WebSocket: port 8765")
    print("Video: http://192.168.1.101:9000/mjpg")
    
    while True:
        sleep(0.05)
        
        # Buttons
        if sc.get("A") == True:
            horn()
        if sc.get("B") == True:
            px.set_cam_pan_angle(0)
            px.set_cam_tilt_angle(0)
        
        # Speech commands
        speak = sc.get("speak")
        if speak:
            speak = speak.lower()
            if "forward" in speak:
                px.forward(speed if speed else 30)
            elif "backward" in speak or "back" in speak:
                px.backward(speed if speed else 30)
            elif "left" in speak:
                px.set_dir_servo_angle(-30)
                px.forward(60)
                sleep(1.2)
                px.set_dir_servo_angle(0)
            elif "right" in speak:
                px.set_dir_servo_angle(30)
                px.forward(60)
                sleep(1.2)
                px.set_dir_servo_angle(0)
            elif "stop" in speak:
                px.stop()
        
        # Line track / Avoid obstacles switches
        line_track_switch = sc.get("I")
        avoid_obstacles_switch = sc.get("E")
        
        if line_track_switch:
            speed = LINE_TRACK_SPEED
            line_track()
        elif avoid_obstacles_switch:
            avoid_obstacles()
        else:
            # Joystick control
            Joystick_K = sc.get("K")
            if Joystick_K:
                dir_angle = utils.mapping(Joystick_K[0], -100, 100, -30, 30)
                speed = Joystick_K[1]
                px.set_dir_servo_angle(dir_angle)
                if speed > 0:
                    px.forward(speed)
                elif speed < 0:
                    px.backward(-speed)
                else:
                    px.stop()
        
        # Camera servo control
        Joystick_Q = sc.get("Q")
        if Joystick_Q:
            pan = min(90, max(-90, Joystick_Q[0]))
            tilt = min(65, max(-35, Joystick_Q[1]))
            px.set_cam_pan_angle(pan)
            px.set_cam_tilt_angle(tilt)
        
        # Color detection (safe)
        if sc.get("N"):
            Vilib.color_detect("red")
        else:
            Vilib.color_detect("close")
        
        # Face detection (safe)
        if sc.get("O"):
            Vilib.face_detect_switch(True)
        else:
            Vilib.face_detect_switch(False)
        
        # Object detection - DISABLED (needs tflite)
        # Skip P button - not available on Python 3.13

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    finally:
        print("Stopping...")
        px.stop()
        Vilib.camera_close()
