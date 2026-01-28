#!/usr/bin/env python3
"""Simple video server for PiCar - no keyboard input needed"""

import os
os.getlogin = lambda: "pi"  # Patch for systemd

from robot_hat.utils import reset_mcu
from vilib import Vilib
from time import sleep
import signal
import sys

reset_mcu()
sleep(0.2)

def signal_handler(sig, frame):
    print("Shutting down...")
    Vilib.camera_close()
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

print("Starting PiCar video server...")
Vilib.camera_start(vflip=False, hflip=False)
Vilib.display(local=False, web=True)

print("Video streaming at http://192.168.1.101:9000/mjpg")

# Keep running
while True:
    sleep(1)
