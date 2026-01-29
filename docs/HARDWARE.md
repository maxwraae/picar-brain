# PiCar-X Hardware Reference

Complete hardware capabilities and control interface for the PiCar-X robot platform.

## Motor Control

### Basic Movement
```python
from picarx import Picarx
px = Picarx()

# Forward/backward with speed 0-100
px.forward(50)    # Move forward at speed 50
px.backward(30)   # Move backward at speed 30
px.stop()         # Stop all motors
```

### Steering
```python
# Steering servo: -30 (left) to +30 (right)
px.set_dir_servo_angle(-30)  # Turn wheels left
px.set_dir_servo_angle(0)    # Wheels straight
px.set_dir_servo_angle(30)   # Turn wheels right
```

### Individual Motor Control
```python
# Direct motor control: motor 1 (left), motor 2 (right)
px.set_motor_speed(1, 50)    # Left motor forward at 50
px.set_motor_speed(2, -50)   # Right motor backward at 50
```

## Camera Servos

### Pan (horizontal rotation)
```python
# Pan servo: -90 (left) to +90 (right)
px.set_cam_pan_angle(-90)   # Look far left
px.set_cam_pan_angle(0)     # Look center
px.set_cam_pan_angle(90)    # Look far right
```

### Tilt (vertical rotation)
```python
# Tilt servo: -35 (down) to +65 (up)
px.set_cam_tilt_angle(-35)  # Look down
px.set_cam_tilt_angle(0)    # Look straight
px.set_cam_tilt_angle(65)   # Look up
px.set_cam_tilt_angle(20)   # Default position
```

### Reset All
```python
# Reset to neutral: stop motors, center all servos
px.reset()  # Sets steering=0, pan=0, tilt=0, motors stopped
```

## Sensors

### Ultrasonic Distance Sensor
```python
# Returns distance in cm (0-400 range)
distance = px.get_distance()
print(f"Object is {distance} cm away")

# Example usage
if distance < 20:
    px.stop()  # Stop if obstacle within 20cm
```

### Grayscale Sensor (Line/Cliff Detection)
```python
# Get raw grayscale data (3 sensors: left, center, right)
values = px.get_grayscale_data()  # Returns [val1, val2, val3]

# Line tracking status
status = px.get_line_status(values)
# Returns: [0,0,0] (no line), [1,0,0] (line left),
#          [0,1,0] (line center), [0,0,1] (line right)

# Cliff detection (edge/table detection)
is_cliff = px.get_cliff_status(values)
# Returns: True if edge detected, False otherwise
```

## Pre-Built Actions

Located in `gpt_examples/preset_actions.py`. These are complex movements combining multiple servos/motors.

### Available Actions
```python
from gpt_examples.preset_actions import *

# Expressions
nod(px)              # Nod head up/down (yes gesture)
shake_head(px)       # Shake head left/right (no gesture)
wave_hands(px)       # Wave steering wheels
think(px)            # Thinking pose (pan, tilt, steering combined)

# Emotions
act_cute(px)         # Small forward/backward wiggles
celebrate(px)        # Victory celebration movements
depressed(px)        # Sad head movements
resist(px)           # Resistance wiggle

# Complex
twist_body(px)       # Body twist using motors + servos
rub_hands(px)        # Rub hands together motion
```

### Example Usage
```python
from picarx import Picarx
from gpt_examples.preset_actions import nod, shake_head
import time

px = Picarx()
px.reset()

nod(px)           # Say yes
time.sleep(0.5)
shake_head(px)    # Say no
px.reset()
```

## App Control (Manual Control via WebSocket)

### Setup
```python
from sunfounder_controller import SunFounderController

sc = SunFounderController()
sc.set_name("Picarx-Leon")
sc.set_type("Picarx")
sc.start()  # Starts WebSocket server on port 8765
```

### Reading Controls
```python
# Joystick K (movement control)
joystick = sc.get("K")
if joystick:
    direction = joystick[0]  # -100 (left) to +100 (right)
    speed = joystick[1]      # -100 (backward) to +100 (forward)

# Joystick Q (camera control)
cam_joy = sc.get("Q")
if cam_joy:
    pan = cam_joy[0]    # Horizontal
    tilt = cam_joy[1]   # Vertical

# Buttons
if sc.get("A"):    # Button A pressed
    pass
if sc.get("B"):    # Button B pressed
    pass

# Switches
if sc.get("I"):    # Switch I (line tracking mode)
    pass
if sc.get("E"):    # Switch E (obstacle avoidance)
    pass

# Speech commands
speak = sc.get("speak")
if speak:
    # Voice command string (e.g., "forward", "left", "stop")
    pass
```

### Example Control Loop
```python
while True:
    # Get joystick input
    joystick = sc.get("K")
    if joystick:
        # Map joystick to steering angle
        angle = int(joystick[0] * 0.3)  # -30 to +30
        speed = joystick[1]

        px.set_dir_servo_angle(angle)
        if speed > 0:
            px.forward(speed)
        elif speed < 0:
            px.backward(-speed)
        else:
            px.stop()

    time.sleep(0.05)
```

## Hardware Specs Summary

| Component | Range | Notes |
|-----------|-------|-------|
| **Motors** | 0-100 | Speed values, signed for direction |
| **Steering** | -30 to +30 | Degrees, negative=left, positive=right |
| **Camera Pan** | -90 to +90 | Degrees horizontal |
| **Camera Tilt** | -35 to +65 | Degrees vertical |
| **Ultrasonic** | 0-400 cm | Distance measurement |
| **Grayscale** | 3 sensors | Line tracking / cliff detection |

## Common Patterns

### Safe Movement with Obstacle Detection
```python
distance = px.get_distance()
if distance > 30:
    px.forward(50)
elif distance > 10:
    px.forward(20)  # Slow down
else:
    px.stop()       # Too close
```

### Cliff Detection Safety
```python
values = px.get_grayscale_data()
if px.get_cliff_status(values):
    px.stop()
    px.backward(30)
    time.sleep(0.5)
    px.stop()
```

### Smooth Head Movement
```python
# Pan left to right smoothly
for angle in range(-90, 91, 10):
    px.set_cam_pan_angle(angle)
    time.sleep(0.1)
```
