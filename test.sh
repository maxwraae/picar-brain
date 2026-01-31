#!/bin/bash
# Quick hardware test - run after setup.sh, before reboot
echo "=== PiCar Hardware Test ==="
echo ""

PASS=0
FAIL=0

# Test 1: I2C
echo -n "I2C devices: "
if i2cdetect -y 1 2>/dev/null | grep -q "[0-9a-f][0-9a-f]"; then
    echo "✓ Found"
    ((PASS++))
else
    echo "✗ None found (robot-hat not connected?)"
    ((FAIL++))
fi

# Test 2: Camera
echo -n "Camera: "
if ls /dev/video* >/dev/null 2>&1; then
    echo "✓ Found"
    ((PASS++))
else
    echo "✗ Not found (check cable)"
    ((FAIL++))
fi

# Test 3: USB Mic
echo -n "USB Microphone: "
if arecord -l 2>/dev/null | grep -qi "usb\|mic"; then
    echo "✓ Found"
    ((PASS++))
else
    echo "✗ Not found (plug in USB mic)"
    ((FAIL++))
fi

# Test 4: Speaker (robot-hat)
echo -n "Speaker device: "
if aplay -l 2>/dev/null | grep -qi "robot\|sunfounder\|card 2"; then
    echo "✓ Found"
    ((PASS++))
else
    echo "⚠ Not found (may work after reboot with dtoverlay)"
    ((FAIL++))
fi

# Test 5: Python imports
echo -n "Python imports: "
if python3 -c "from picarx import Picarx; from robot_hat import Music" 2>/dev/null; then
    echo "✓ OK"
    ((PASS++))
else
    echo "✗ Failed (run setup.sh first)"
    ((FAIL++))
fi

# Test 6: API keys
echo -n "API keys: "
if [ -f ~/picar-brain/keys.py ]; then
    if grep -q "sk-your" ~/picar-brain/keys.py; then
        echo "⚠ Not configured (edit keys.py)"
    else
        echo "✓ Configured"
        ((PASS++))
    fi
else
    echo "✗ Missing (cp keys.example.py keys.py)"
    ((FAIL++))
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ $FAIL -eq 0 ]; then
    echo "Ready to reboot!"
else
    echo "Fix issues above, then reboot."
fi
