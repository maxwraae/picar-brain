#!/bin/bash
# Test script for Voice Assistant components
# Run on Raspberry Pi to verify everything works

echo "=========================================="
echo "Voice Assistant Component Tests"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Test function
test_component() {
    echo -n "Testing $1... "
    if eval "$2" > /tmp/test_output.log 2>&1; then
        echo -e "${GREEN}✓ PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "${RED}✗ FAIL${NC}"
        echo "  Error: $(cat /tmp/test_output.log | head -n 3)"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

# 1. Check if venv exists
echo "1. Environment Checks"
echo "---------------------"
test_component "Virtual environment exists" "[ -d ~/picar-brain/venv ]"
test_component "keys.py exists" "[ -f ~/picar-brain/keys.py ]"
test_component "Piper model exists" "[ -f ~/.local/share/piper/sv_SE-nst-medium.onnx ]"
echo ""

# 2. Check Python imports (activate venv first)
echo "2. Python Dependencies"
echo "---------------------"
if [ -d ~/picar-brain/venv ]; then
    source ~/picar-brain/venv/bin/activate

    test_component "speech_recognition" "python3 -c 'import speech_recognition'"
    test_component "openai" "python3 -c 'import openai'"
    test_component "pyaudio" "python3 -c 'import pyaudio'"
    test_component "picarx" "python3 -c 'from picarx import Picarx'"
    test_component "robot_hat" "python3 -c 'from robot_hat import Music, Pin'"
else
    echo -e "${YELLOW}⚠️  Virtual environment not found, skipping Python tests${NC}"
fi
echo ""

# 3. Hardware checks
echo "3. Hardware Tests"
echo "---------------------"

# Test Piper TTS
echo -n "Testing Piper TTS... "
if echo "Test" | piper --model ~/.local/share/piper/sv_SE-nst-medium.onnx --output_file /tmp/piper_test.wav 2>/dev/null; then
    echo -e "${GREEN}✓ PASS${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))

    # Check if audio file was created
    if [ -f /tmp/piper_test.wav ]; then
        SIZE=$(stat -f%z /tmp/piper_test.wav 2>/dev/null || stat -c%s /tmp/piper_test.wav)
        echo "  Generated audio file: ${SIZE} bytes"
    fi
else
    echo -e "${RED}✗ FAIL${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Test speaker
echo -n "Testing speaker (you should hear a beep)... "
if speaker-test -t sine -f 1000 -l 1 -D plughw:1,0 > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PASS${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
else
    echo -e "${RED}✗ FAIL${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Test microphone
echo -n "Testing microphone... "
if arecord -D plughw:3,0 -f cd -d 1 /tmp/mic_test.wav > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PASS${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))

    if [ -f /tmp/mic_test.wav ]; then
        SIZE=$(stat -f%z /tmp/mic_test.wav 2>/dev/null || stat -c%s /tmp/mic_test.wav)
        echo "  Recorded audio: ${SIZE} bytes"
    fi
else
    echo -e "${RED}✗ FAIL${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

echo ""

# 4. API Key check
echo "4. OpenAI API"
echo "---------------------"
if [ -d ~/picar-brain/venv ]; then
    source ~/picar-brain/venv/bin/activate

    echo -n "Testing OpenAI API key... "
    RESULT=$(python3 -c "
from keys import OPENAI_API_KEY
import openai
openai.api_key = OPENAI_API_KEY
try:
    openai.Model.list()
    print('success')
except Exception as e:
    print(f'error: {e}')
" 2>&1)

    if echo "$RESULT" | grep -q "success"; then
        echo -e "${GREEN}✓ PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "${RED}✗ FAIL${NC}"
        echo "  $RESULT"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
fi

echo ""

# 5. Quick syntax check
echo "5. Code Validation"
echo "---------------------"
if [ -d ~/picar-brain/venv ]; then
    source ~/picar-brain/venv/bin/activate

    echo -n "Checking voice_assistant.py syntax... "
    if python3 -m py_compile ~/picar-brain/voice_assistant.py 2>/dev/null; then
        echo -e "${GREEN}✓ PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "${RED}✗ FAIL${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
fi

echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "Passed: ${GREEN}${TESTS_PASSED}${NC}"
echo -e "Failed: ${RED}${TESTS_FAILED}${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed! Ready to run voice assistant.${NC}"
    echo ""
    echo "To start the assistant:"
    echo "  source ~/picar-brain/venv/bin/activate"
    echo "  python3 ~/picar-brain/voice_assistant.py"
else
    echo -e "${YELLOW}⚠️  Some tests failed. Please fix errors above.${NC}"
fi

echo ""
