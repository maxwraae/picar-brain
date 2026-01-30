# PiCar-X Setup Guide

Complete setup instructions for Raspberry Pi 5 with PiCar-X robot.

## Requirements
- Raspberry Pi 5
- SD Card (32GB+)
- PiCar-X robot kit from SunFounder
- WiFi network

## Fresh Install

### 1. Flash SD Card
Use Raspberry Pi Imager to flash **Raspberry Pi OS 64-bit Lite**.

Configure in Imager settings:
- Hostname: `picar`
- Username: `pi`
- Password: `leon`
- WiFi: Your network credentials
- Enable SSH with password auth
- Timezone: Your timezone

### 2. First Boot
Insert SD card, power on, wait 2-3 minutes.

Test connection:
```bash
ping picar.local
ssh pi@picar.local
```

### 3. Install System Dependencies
```bash
sudo apt update && sudo apt install -y python3-pip python3-opencv
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
```

### 4. Install SunFounder Libraries
```bash
cd ~
git clone https://github.com/sunfounder/robot-hat.git
cd robot-hat && sudo python3 setup.py install

cd ~
git clone https://github.com/sunfounder/picar-x.git
cd picar-x && sudo python3 setup.py install

cd ~
git clone https://github.com/sunfounder/sunfounder-controller.git
cd sunfounder-controller && sudo python3 setup.py install

cd ~
git clone https://github.com/sunfounder/vilib.git
cd vilib && sudo python3 install.py
```

### 5. Install Python Packages
```bash
pip3 install openai --break-system-packages
```

### 6. Clone This Repo
```bash
cd ~
git clone https://github.com/maxwraae/picar-brain.git
```

### 7. Create API Keys
```bash
cp ~/picar-brain/keys.example.py ~/picar-brain/keys.py
# Edit keys.py with your OpenAI API key
```

### 8. Fix Permissions
```bash
sudo mkdir -p /opt/picar-x
sudo chown pi:pi /opt/picar-x
```

### 9. Fix systemd Compatibility
The picarx library uses `os.getlogin()` which fails under systemd. Fix:
```bash
sudo sed -i 's/os.getlogin()/"pi"/g' /usr/local/lib/python3.13/dist-packages/picarx-2.0.5-py3.13.egg/picarx/picarx.py
```

### 10. Setup Auto-Start Service
Create `/home/pi/start_picar_app.sh`:
```bash
#!/bin/bash
export LOGNAME=pi
export USER=pi
cd /home/pi/picar-x/example
exec /usr/bin/python3 13.app_control.py
```

Make executable:
```bash
chmod +x /home/pi/start_picar_app.sh
```

Create systemd service `/etc/systemd/system/picar-app.service`:
```ini
[Unit]
Description=PiCar-X App Control
After=network.target

[Service]
Type=simple
User=pi
Environment=LOGNAME=pi
Environment=USER=pi
WorkingDirectory=/home/pi/picar-x/example
ExecStart=/home/pi/start_picar_app.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable picar-app
sudo systemctl start picar-app
```

## Testing

### Test Motors
```bash
python3 -c "
from picarx import Picarx
import time
px = Picarx()
px.forward(15)
time.sleep(0.3)
px.stop()
print('Motor test complete')
"
```

### Test Camera
```bash
python3 -c "
from picamera2 import Picamera2
cam = Picamera2()
config = cam.create_still_configuration(main={'size': (640, 480)})
cam.configure(config)
cam.start()
import time
time.sleep(1)
frame = cam.capture_array()
cam.stop()
print(f'Camera works! Shape: {frame.shape}')
"
```

### Test App Control
Connect with SunFounder PiCar-X app on your phone.

## Known Issues

### pygame/ALSA Audio Error
Under systemd, pygame can't access audio device. The app control may crash on audio init. Working on fix.

## Software Versions (as of 2026-01-30)
- Raspberry Pi OS: Debian Trixie (64-bit)
- Python: 3.13
- robot-hat: 2.3.5
- picar-x: 2.0.5
- vilib: 0.3.18
- picamera2: 0.3.33
