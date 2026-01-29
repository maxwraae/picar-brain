#!/usr/bin/env python3
"""
PiCar Voice Assistant - Bulletproof edition with Wake Word
Uses Piper TTS for Swedish voice output
Built for Leon (9 years old)

Hardened with:
- Retry logic for all API calls
- Timeout protection
- Graceful error recovery
- Device busy handling
- Wake word detection (say "Hey Jarvis" to activate)
"""

# Patch os.getlogin() for systemd (no TTY available)
import os
os.getlogin = lambda: "pi"

from openai import OpenAI
import subprocess
import json
import time
import os
import sys
import signal
import numpy as np
from keys import OPENAI_API_KEY

# ============== SIGNAL HANDLING ==============

shutdown_requested = False

def handle_shutdown(signum, frame):
    global shutdown_requested
    print("\n🛑 Shutdown signal received...")
    shutdown_requested = True

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

# Wake word detection (Picovoice Porcupine)
import pvporcupine
from pvrecorder import PvRecorder

# Voice Activity Detection
import webrtcvad
import wave
import struct

# PiCar imports
from picarx import Picarx
from robot_hat import Music, Pin

# ============== CONSTANTS ==============

MAX_RETRIES = 3
SUBPROCESS_TIMEOUT = 10  # seconds
AUDIO_DEVICE_RETRY_DELAY = 0.5  # seconds

# Voice Activity Detection (VAD) configuration
VAD_AGGRESSIVENESS = 2  # 0-3, higher = more aggressive filtering
SILENCE_THRESHOLD = 1.5  # seconds of silence to stop recording
MAX_RECORD_DURATION = 8  # seconds max recording time
MIN_RECORD_DURATION = 0.5  # seconds minimum before allowing stop

# Follow-up conversation window
FOLLOW_UP_WINDOW = 5.0  # seconds to listen for follow-up without wake word

# Sound effects paths
SOUNDS_DIR = "/home/pi/picar-brain/sounds"
SOUND_DING = f"{SOUNDS_DIR}/ding.wav"        # Wake word detected (0.12s)
SOUND_THINKING = f"{SOUNDS_DIR}/thinking.wav" # During GPT processing (3s)
SOUND_RETRY = f"{SOUNDS_DIR}/retry.wav"       # On errors (0.27s)
SOUND_READY = f"{SOUNDS_DIR}/ready.wav"       # On startup (0.5s)

# Wake word configuration (Picovoice)
# Get free access key from https://console.picovoice.ai
PICOVOICE_ACCESS_KEY = ""  # Set in keys.py or here
WAKE_WORD = "jarvis"  # Built-in: alexa, americano, blueberry, bumblebee, computer, grapefruit, grasshopper, hey google, hey siri, jarvis, ok google, picovoice, porcupine, terminator

# ============== CONFIG ==============

client = OpenAI(api_key=OPENAI_API_KEY)

# Piper TTS model path (Swedish)
PIPER_MODEL = "/home/pi/.local/share/piper/sv_SE-nst-medium.onnx"

# Speaker configuration - use robothat device which is configured in system
SPEAKER_DEVICE = "robothat"

# ============== USB MICROPHONE AUTO-DETECTION ==============

def find_usb_mic_arecord():
    """
    Find USB microphone card number using arecord -l.
    Returns: "plughw:X,0" where X is the card number, or None if not found.
    """
    try:
        result = subprocess.run(
            "arecord -l",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0:
            return None

        # Parse output looking for USB device
        # Format: "card 3: Device [USB Audio Device], device 0: USB Audio [USB Audio]"
        for line in result.stdout.split('\n'):
            if 'card' in line.lower() and 'usb' in line.lower():
                # Extract card number
                parts = line.split(':')
                if len(parts) > 0:
                    card_part = parts[0]  # "card 3"
                    words = card_part.split()
                    for i, word in enumerate(words):
                        if word.lower() == 'card' and i + 1 < len(words):
                            card_num = words[i + 1].rstrip(',')
                            device = f"plughw:{card_num},0"
                            print(f"✓ Found USB mic (arecord): {device}")
                            return device

        return None

    except Exception as e:
        print(f"⚠️ Error detecting USB mic with arecord: {e}")
        return None


def find_usb_mic_pvrecorder():
    """
    Find USB microphone device index for PvRecorder.
    Returns: device index (int) or None if not found.
    """
    try:
        devices = PvRecorder.get_available_devices()

        # Search for USB in device name
        for idx, device_name in enumerate(devices):
            if 'usb' in device_name.lower():
                print(f"✓ Found USB mic (PvRecorder): index {idx} - {device_name}")
                return idx

        return None

    except Exception as e:
        print(f"⚠️ Error detecting USB mic with PvRecorder: {e}")
        return None


# Auto-detect USB microphone
MIC_DEVICE = find_usb_mic_arecord()
if MIC_DEVICE is None:
    # Fallback to common indices
    print("⚠️ USB mic not found via arecord, trying common card numbers...")
    for card_num in [0, 3, 2, 1]:
        test_device = f"plughw:{card_num},0"
        # Quick test if device exists
        test = subprocess.run(
            f"arecord -D {test_device} -d 0.1 -f S16_LE -r 16000 -c 1 /tmp/test_mic.wav 2>/dev/null",
            shell=True,
            timeout=2
        )
        if test.returncode == 0:
            MIC_DEVICE = test_device
            print(f"✓ Using fallback mic device: {MIC_DEVICE}")
            break

    if MIC_DEVICE is None:
        MIC_DEVICE = "plughw:0,0"  # Last resort fallback
        print(f"⚠️ Using default fallback: {MIC_DEVICE}")
else:
    print(f"✓ Microphone configured: {MIC_DEVICE}")

# Enable robot_hat speaker switch
os.popen("pinctrl set 20 op dh")

# ============== INITIALIZATION ==============

# Initialize car
try:
    car = Picarx()
    time.sleep(0.5)
    car.reset()
    car.set_cam_tilt_angle(20)  # Default head position
    print("✓ PiCar initialized")
except Exception as e:
    print(f"✗ Failed to initialize PiCar: {e}")
    sys.exit(1)

music = Music()
led = Pin('LED')

# Initialize wake word (Picovoice Porcupine)
# Try to get access key from keys.py
try:
    from keys import PICOVOICE_ACCESS_KEY as _pk
    if _pk:
        PICOVOICE_ACCESS_KEY = _pk
except ImportError:
    pass

porcupine = None
recorder = None
if PICOVOICE_ACCESS_KEY:
    try:
        porcupine = pvporcupine.create(
            access_key=PICOVOICE_ACCESS_KEY,
            keywords=[WAKE_WORD]
        )
        print(f"✓ Wake word ready: '{WAKE_WORD}'")
    except Exception as e:
        print(f"✗ Failed to init wake word: {e}")
        print("  Falling back to push-to-talk mode")
else:
    print("✗ No Picovoice access key - using push-to-talk mode")
    print("  Get free key at https://console.picovoice.ai")

# Conversation history for Chat Completions
conversation_history = []

# ============== SYSTEM PROMPT ==============

SYSTEM_PROMPT = """Du är en rolig svensk robotbil som heter PiCar. Du pratar med Leon som är 9 år gammal.

PERSONLIGHET:
- Du är lekfull, energisk och älskar att göra Leon glad
- Du skämtar och har roligt
- Du pratar som en snäll robot-kompis
- Du säger saker som "Woohoo!", "Häftigt!", "Vroom vroom!"
- Du är aldrig tråkig eller formell

RÖRLIGHET:
Du kan göra dessa saker: forward, backward, spin_right, spin_left, dance, nod, shake_head, stop

VIKTIGT:
- Svara ALLTID på svenska
- Var kortfattad (1-2 meningar) så Leon inte tröttnar
- Föreslå roliga saker att göra tillsammans

SVARSFORMAT:
Ge ditt svar som vanlig text först.
Om du vill röra dig, skriv ACTIONS: följt av kommaseparerade actions på sista raden.

Exempel:
Woohoo! Jag snurrar runt!
ACTIONS: spin_right

Vill du att jag dansar? Det kan jag!
ACTIONS: dance

Hej Leon! Vad kul att prata med dig!
ACTIONS: nod

Om du inte vill röra dig, skippa ACTIONS-raden:
Vad intressant! Berätta mer!
"""

# Initialize conversation with system prompt
conversation_history.append({"role": "system", "content": SYSTEM_PROMPT})

# ============== TTS FUNCTION ==============

def speak(text):
    """
    Speak using Piper TTS (Swedish) with retry logic
    If TTS fails, print error but don't crash
    """
    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                time.sleep(AUDIO_DEVICE_RETRY_DELAY)

            # Write text to file to avoid shell escaping issues
            with open("/tmp/picar_text.txt", "w") as f:
                f.write(text)

            # Generate speech with Piper using file input
            result = subprocess.run(
                f'cat /tmp/picar_text.txt | piper --model {PIPER_MODEL} --output_file /tmp/picar_speech.wav',
                shell=True,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT
            )

            if result.returncode != 0:
                if attempt < MAX_RETRIES - 1:
                    continue
                print(f"❌ Rösten fungerar inte: {result.stderr[:50]}")
                return False

            # Check file was created
            if not os.path.exists("/tmp/picar_speech.wav"):
                if attempt < MAX_RETRIES - 1:
                    continue
                print("❌ Ingen ljudfil skapades")
                return False

            size = os.path.getsize("/tmp/picar_speech.wav")
            if size < 100:  # Too small to be valid
                if attempt < MAX_RETRIES - 1:
                    continue
                print("❌ Ljudfilen är för liten")
                return False

            # Play using aplay with retry for device busy
            play_result = subprocess.run(
                f'aplay -D {SPEAKER_DEVICE} /tmp/picar_speech.wav',
                shell=True,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT
            )

            if play_result.returncode != 0:
                # Device busy? Retry
                if "busy" in play_result.stderr.lower() and attempt < MAX_RETRIES - 1:
                    time.sleep(AUDIO_DEVICE_RETRY_DELAY * 2)
                    continue
                if attempt < MAX_RETRIES - 1:
                    continue
                print(f"❌ Kunde inte spela ljud: {play_result.stderr[:50]}")
                return False

            return True

        except subprocess.TimeoutExpired:
            print(f"⏱️ TTS timeout (försök {attempt + 1}/{MAX_RETRIES})")
            if attempt == MAX_RETRIES - 1:
                print("❌ Rösten svarar inte")
                return False

        except Exception as e:
            print(f"❌ TTS-fel (försök {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES - 1:
                return False

    return False

# ============== ACTION FUNCTIONS ==============

def safe_action(action_func, action_name):
    """
    Wrapper for action execution with error handling
    Actions should never crash the assistant
    """
    try:
        action_func()
    except Exception as e:
        print(f"⚠️ Action '{action_name}' misslyckades: {e}")
        # Try to stop car safely
        try:
            car.stop()
        except:
            pass

def do_forward():
    """Drive forward for a bit"""
    car.forward(30)
    time.sleep(1.5)
    car.stop()

def do_backward():
    """Drive backward for a bit"""
    car.backward(30)
    time.sleep(1.5)
    car.stop()

def do_spin_right():
    """Spin 360 degrees to the right"""
    car.set_dir_servo_angle(30)
    time.sleep(0.1)
    car.forward(50)
    time.sleep(2.0)
    car.stop()
    car.set_dir_servo_angle(0)

def do_spin_left():
    """Spin 360 degrees to the left"""
    car.set_dir_servo_angle(-30)
    time.sleep(0.1)
    car.forward(50)
    time.sleep(2.0)
    car.stop()
    car.set_dir_servo_angle(0)

def do_dance():
    """Do a little dance"""
    for _ in range(3):
        car.set_dir_servo_angle(-25)
        car.forward(30)
        time.sleep(0.3)
        car.stop()

        car.set_dir_servo_angle(25)
        car.forward(30)
        time.sleep(0.3)
        car.stop()

    car.set_dir_servo_angle(0)

def do_nod():
    """Nod head (yes)"""
    car.set_cam_tilt_angle(5)
    time.sleep(0.1)
    car.set_cam_tilt_angle(-30)
    time.sleep(0.1)
    car.set_cam_tilt_angle(5)
    time.sleep(0.1)
    car.set_cam_tilt_angle(-30)
    time.sleep(0.1)
    car.set_cam_tilt_angle(20)

def do_shake_head():
    """Shake head (no)"""
    car.set_cam_pan_angle(0)
    car.set_cam_pan_angle(60)
    time.sleep(0.2)
    car.set_cam_pan_angle(-50)
    time.sleep(0.1)
    car.set_cam_pan_angle(40)
    time.sleep(0.1)
    car.set_cam_pan_angle(-30)
    time.sleep(0.1)
    car.set_cam_pan_angle(20)
    time.sleep(0.1)
    car.set_cam_pan_angle(-10)
    time.sleep(0.1)
    car.set_cam_pan_angle(0)

def do_stop():
    """Stop all movement"""
    car.stop()

# Action dispatch dictionary
ACTIONS = {
    "forward": do_forward,
    "backward": do_backward,
    "spin_right": do_spin_right,
    "spin_left": do_spin_left,
    "dance": do_dance,
    "nod": do_nod,
    "shake_head": do_shake_head,
    "stop": do_stop,
}

# ============== CHAT FUNCTION ==============

# Sentence-ending punctuation for streaming
SENTENCE_ENDINGS = (".", "!", "?", "。", "！", "？")

def parse_actions(full_response):
    """
    Parse ACTIONS from the response.
    Looks for 'ACTIONS: action1, action2' on the last line.
    Returns: (text_without_actions, actions_list)
    """
    lines = full_response.strip().split('\n')
    actions = []

    # Check if last line contains ACTIONS:
    if lines and lines[-1].strip().upper().startswith('ACTIONS:'):
        action_line = lines[-1].strip()
        # Extract actions after "ACTIONS:"
        action_part = action_line.split(':', 1)[1].strip()
        actions = [a.strip().lower() for a in action_part.split(',') if a.strip()]
        # Remove the ACTIONS line from text
        text = '\n'.join(lines[:-1]).strip()
    else:
        text = full_response.strip()

    return text, actions


def chat_with_gpt(user_message):
    """
    Send message to GPT using streaming API.
    Speaks each sentence as it completes for real-time response.
    Returns: (full_answer_text, actions_list)
    """
    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                time.sleep(1)  # Brief pause before retry

            # Add user message to history (only on first attempt)
            if attempt == 0:
                conversation_history.append({
                    "role": "user",
                    "content": user_message
                })

            # Call OpenAI with streaming
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=conversation_history,
                stream=True
            )

            # Collect the full response and speak sentence-by-sentence
            sentence_buffer = ""
            full_response = ""
            first_token_received = False

            # Start thinking sound while waiting for GPT response
            try:
                music.sound_play_threading(SOUND_THINKING)
            except Exception as e:
                print(f"⚠️ Thinking sound failed: {e}")

            for chunk in response:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                if not delta.content:
                    continue

                # Stop thinking sound on first token
                if not first_token_received:
                    first_token_received = True
                    try:
                        music.sound_stop()
                    except Exception as e:
                        print(f"⚠️ Stop thinking sound failed: {e}")

                # Add token to buffer
                token = delta.content
                sentence_buffer += token
                full_response += token

                # Check if we have a complete sentence
                if sentence_buffer.rstrip().endswith(SENTENCE_ENDINGS):
                    sentence = sentence_buffer.strip()
                    # Don't speak the ACTIONS line
                    if not sentence.upper().startswith('ACTIONS:'):
                        print(f"💬 {sentence}")
                        speak(sentence)
                    sentence_buffer = ""

            # Speak any remaining text (if it doesn't end with punctuation)
            if sentence_buffer.strip():
                remaining = sentence_buffer.strip()
                if not remaining.upper().startswith('ACTIONS:'):
                    print(f"💬 {remaining}")
                    speak(remaining)

            # Parse actions from full response
            answer_text, actions = parse_actions(full_response)

            # Add assistant response to history
            conversation_history.append({
                "role": "assistant",
                "content": full_response
            })

            # Keep conversation history reasonable (last 10 messages)
            if len(conversation_history) > 21:  # system + 10 pairs
                conversation_history[:] = [conversation_history[0]] + conversation_history[-20:]

            return answer_text, actions

        except Exception as e:
            print(f"🔄 GPT-fel (försök {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES - 1:
                # Remove the user message we added if all retries failed
                if conversation_history and conversation_history[-1]["role"] == "user":
                    conversation_history.pop()
                return "Jag kan inte tänka just nu, försök igen!", []

    return "Jag kan inte tänka just nu, försök igen!", []

# ============== STARTUP SELF-TEST ==============

def startup_self_test():
    """
    Test all critical components before starting the main loop.
    Returns: True if all tests pass, False if any fail

    Tests:
    - Microphone (record 1s, check file size)
    - Speaker (play test tone)
    - Piper TTS (generate test audio)
    - OpenAI API (list models)
    """
    print("\n" + "=" * 50)
    print("🔧 Startar självtest...")
    print("=" * 50 + "\n")

    test_results = []

    # Test 1: Microphone
    print("🎤 Testar mikrofon...", end=" ", flush=True)
    try:
        test_wav = "/tmp/picar_mic_test.wav"
        result = subprocess.run(
            f"arecord -D {MIC_DEVICE} -d 1 -f S16_LE -r 16000 -c 1 {test_wav}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0 and os.path.exists(test_wav):
            size = os.path.getsize(test_wav)
            if size > 1000:
                print("✓")
                test_results.append(True)
            else:
                print("✗ (fil för liten)")
                test_results.append(False)
        else:
            print("✗ (inspelning misslyckades)")
            test_results.append(False)

    except subprocess.TimeoutExpired:
        print("✗ (timeout)")
        test_results.append(False)
    except Exception as e:
        print(f"✗ ({str(e)[:30]})")
        test_results.append(False)

    # Test 2: Piper TTS
    print("🗣️  Testar Piper TTS...", end=" ", flush=True)
    try:
        test_text = "test"
        test_tts_wav = "/tmp/picar_tts_test.wav"

        # Write test text
        with open("/tmp/picar_tts_test.txt", "w") as f:
            f.write(test_text)

        result = subprocess.run(
            f'cat /tmp/picar_tts_test.txt | piper --model {PIPER_MODEL} --output_file {test_tts_wav}',
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0 and os.path.exists(test_tts_wav):
            size = os.path.getsize(test_tts_wav)
            if size > 100:
                print("✓")
                test_results.append(True)
            else:
                print("✗ (fil för liten)")
                test_results.append(False)
        else:
            print("✗ (generering misslyckades)")
            test_results.append(False)

    except subprocess.TimeoutExpired:
        print("✗ (timeout)")
        test_results.append(False)
    except Exception as e:
        print(f"✗ ({str(e)[:30]})")
        test_results.append(False)

    # Test 3: Speaker
    print("🔊 Testar högtalare...", end=" ", flush=True)
    try:
        # Use the TTS file we just generated if it exists, otherwise create a short beep
        if os.path.exists("/tmp/picar_tts_test.wav"):
            test_audio = "/tmp/picar_tts_test.wav"
        else:
            # Fallback: create simple beep with sox if available
            test_audio = "/tmp/picar_speaker_test.wav"
            subprocess.run(
                f"sox -n -r 16000 -c 1 {test_audio} synth 0.1 sine 440",
                shell=True,
                capture_output=True,
                timeout=3
            )

        result = subprocess.run(
            f'aplay -D {SPEAKER_DEVICE} {test_audio}',
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            print("✓")
            test_results.append(True)
        else:
            print("✗ (uppspelning misslyckades)")
            test_results.append(False)

    except subprocess.TimeoutExpired:
        print("✗ (timeout)")
        test_results.append(False)
    except Exception as e:
        print(f"✗ ({str(e)[:30]})")
        test_results.append(False)

    # Test 4: OpenAI API
    print("🌐 Testar OpenAI API...", end=" ", flush=True)
    try:
        # Simple API call with short timeout
        models = client.models.list()
        if models:
            print("✓")
            test_results.append(True)
        else:
            print("✗ (ingen respons)")
            test_results.append(False)

    except Exception as e:
        print(f"✗ ({str(e)[:30]})")
        test_results.append(False)

    # Summary
    print("\n" + "=" * 50)
    passed = sum(test_results)
    total = len(test_results)

    if all(test_results):
        print(f"✅ Alla tester OK ({passed}/{total})")
        print("=" * 50 + "\n")
        return True
    else:
        print(f"❌ {total - passed} tester misslyckades ({passed}/{total})")
        print("=" * 50 + "\n")
        return False


# ============== MAIN LOOP ==============

def record_audio_with_vad():
    """
    Record audio using PvRecorder with Voice Activity Detection (VAD).
    Stops recording when silence is detected for SILENCE_THRESHOLD seconds.

    Returns: path to wav file, or None on failure

    Uses webrtcvad which requires:
    - 16-bit signed PCM audio
    - Sample rate: 16000 Hz (supported by webrtcvad)
    - Frame duration: 30ms = 480 samples at 16kHz
    """
    wav_file = "/tmp/picar_input.wav"

    # webrtcvad frame requirements: 10, 20, or 30ms at 16kHz
    # 30ms at 16000 Hz = 480 samples
    SAMPLE_RATE = 16000
    VAD_FRAME_MS = 30
    VAD_FRAME_SAMPLES = int(SAMPLE_RATE * VAD_FRAME_MS / 1000)  # 480

    # PvRecorder uses 512-sample frames by default, but we need to work with VAD frames
    # We'll collect audio and process in VAD-compatible chunks
    PVRECORDER_FRAME_LENGTH = 512

    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                time.sleep(AUDIO_DEVICE_RETRY_DELAY)

            # Initialize VAD
            vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)

            # Find USB mic for PvRecorder
            device_idx = find_usb_mic_pvrecorder()
            if device_idx is None:
                # Try common indices
                for idx in [0, 15, 1, 2]:
                    try:
                        test_rec = PvRecorder(device_index=idx, frame_length=PVRECORDER_FRAME_LENGTH)
                        test_rec.delete()
                        device_idx = idx
                        break
                    except:
                        continue
                if device_idx is None:
                    device_idx = 0

            # Start recording
            recorder = PvRecorder(device_index=device_idx, frame_length=PVRECORDER_FRAME_LENGTH)
            recorder.start()

            all_audio = []  # Collect all audio frames
            vad_buffer = []  # Buffer to accumulate samples for VAD processing

            start_time = time.time()
            last_speech_time = start_time
            speech_detected_ever = False

            try:
                while True:
                    elapsed = time.time() - start_time

                    # Safety limit: stop after MAX_RECORD_DURATION seconds
                    if elapsed >= MAX_RECORD_DURATION:
                        print(f"⏱️ Max tid ({MAX_RECORD_DURATION}s)")
                        break

                    # Read audio frame from PvRecorder
                    pcm = recorder.read()
                    all_audio.extend(pcm)
                    vad_buffer.extend(pcm)

                    # Process VAD in 30ms chunks (480 samples)
                    while len(vad_buffer) >= VAD_FRAME_SAMPLES:
                        # Extract VAD frame
                        vad_frame = vad_buffer[:VAD_FRAME_SAMPLES]
                        vad_buffer = vad_buffer[VAD_FRAME_SAMPLES:]

                        # Convert to bytes for webrtcvad (16-bit signed PCM)
                        frame_bytes = struct.pack(f'{VAD_FRAME_SAMPLES}h', *vad_frame)

                        # Check if frame contains speech
                        is_speech = vad.is_speech(frame_bytes, SAMPLE_RATE)

                        if is_speech:
                            last_speech_time = time.time()
                            if not speech_detected_ever:
                                speech_detected_ever = True

                    # Check silence duration (only after minimum recording time)
                    if elapsed >= MIN_RECORD_DURATION:
                        silence_duration = time.time() - last_speech_time
                        if silence_duration >= SILENCE_THRESHOLD:
                            print(f"🔇 Tystnad ({silence_duration:.1f}s)")
                            break

            finally:
                recorder.stop()
                recorder.delete()

            # Check we got enough audio
            if len(all_audio) < SAMPLE_RATE * 0.3:  # Less than 0.3 seconds
                if attempt < MAX_RETRIES - 1:
                    continue
                print("⚠️ Inspelningen blev för kort")
                return None

            # Write WAV file
            with wave.open(wav_file, 'wb') as wf:
                wf.setnchannels(1)  # Mono
                wf.setsampwidth(2)  # 16-bit = 2 bytes
                wf.setframerate(SAMPLE_RATE)
                # Pack audio data as 16-bit signed integers
                audio_bytes = struct.pack(f'{len(all_audio)}h', *all_audio)
                wf.writeframes(audio_bytes)

            # Verify file
            if os.path.exists(wav_file):
                size = os.path.getsize(wav_file)
                duration_recorded = len(all_audio) / SAMPLE_RATE
                print(f"✓ Inspelat: {duration_recorded:.1f}s ({size} bytes)")
                if size < 1000:
                    if attempt < MAX_RETRIES - 1:
                        continue
                    print("⚠️ Inspelningen blev för kort")
                    return None
                return wav_file
            else:
                if attempt < MAX_RETRIES - 1:
                    continue
                print("❌ Ingen ljudfil skapades")
                return None

        except Exception as e:
            print(f"❌ Inspelningsfel (försök {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES - 1:
                return None

    return None


def record_audio(duration=4):
    """
    Record audio - uses VAD-based recording for smart cutoff.
    Falls back to fixed-duration arecord if VAD fails.

    The duration parameter is kept for API compatibility but is not used
    when VAD recording succeeds.
    """
    # Try VAD-based recording first
    try:
        result = record_audio_with_vad()
        if result:
            return result
    except Exception as e:
        print(f"⚠️ VAD-inspelning misslyckades: {e}")

    # Fallback to original arecord method
    print("⚠️ Använder reservmetod...")
    wav_file = "/tmp/picar_input.wav"

    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                time.sleep(AUDIO_DEVICE_RETRY_DELAY)

            result = subprocess.run(
                f"arecord -D {MIC_DEVICE} -d {duration} -f S16_LE -r 16000 -c 1 {wav_file}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=duration + 5  # Add buffer to duration
            )

            if result.returncode != 0:
                # Device busy? Retry
                if "busy" in result.stderr.lower() and attempt < MAX_RETRIES - 1:
                    continue
                if attempt < MAX_RETRIES - 1:
                    continue
                print(f"❌ Mikrofonen fungerar inte: {result.stderr[:50]}")
                return None

            # Check file exists and has content
            if os.path.exists(wav_file):
                size = os.path.getsize(wav_file)
                if size < 1000:
                    if attempt < MAX_RETRIES - 1:
                        continue
                    print("⚠️ Inspelningen blev för kort")
                    return None
                return wav_file
            else:
                if attempt < MAX_RETRIES - 1:
                    continue
                print("❌ Ingen ljudfil skapades")
                return None

        except subprocess.TimeoutExpired:
            print(f"⏱️ Inspelning timeout (försök {attempt + 1}/{MAX_RETRIES})")
            if attempt == MAX_RETRIES - 1:
                return None

        except Exception as e:
            print(f"❌ Inspelningsfel (försök {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES - 1:
                return None

    return None


def transcribe_audio(wav_file):
    """
    Transcribe audio file using OpenAI Whisper API with retry logic
    """
    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                time.sleep(1)  # Brief pause before retry

            with open(wav_file, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language="sv"
                )

            if transcript and transcript.text:
                return transcript.text.strip()

        except Exception as e:
            print(f"🔄 Whisper-fel (försök {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES - 1:
                return None

    return None


def reset_car_safe():
    """
    Safely reset car to default state
    Never crashes even if hardware fails
    """
    try:
        car.stop()
    except:
        pass

    try:
        car.set_dir_servo_angle(0)
    except:
        pass

    try:
        car.set_cam_pan_angle(0)
    except:
        pass

    try:
        car.set_cam_tilt_angle(20)
    except:
        pass


class WakeWordListener:
    """Context manager for PvRecorder to ensure proper cleanup"""
    def __init__(self, porcupine_instance):
        self.porcupine = porcupine_instance
        self.rec = None

    def __enter__(self):
        # Auto-detect USB mic for PvRecorder
        device_idx = find_usb_mic_pvrecorder()
        if device_idx is None:
            # Fallback to common indices
            print("⚠️ USB mic not found via PvRecorder, trying common indices...")
            for idx in [0, 15, 1, 2]:
                try:
                    test_rec = PvRecorder(device_index=idx, frame_length=self.porcupine.frame_length)
                    test_rec.delete()  # Just testing if it opens
                    device_idx = idx
                    print(f"✓ Using fallback PvRecorder index: {device_idx}")
                    break
                except:
                    continue

            if device_idx is None:
                device_idx = 0  # Last resort
                print(f"⚠️ Using default PvRecorder index: {device_idx}")

        self.rec = PvRecorder(device_index=device_idx, frame_length=self.porcupine.frame_length)
        self.rec.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.rec:
            try:
                self.rec.stop()
            except:
                pass
            try:
                self.rec.delete()
            except:
                pass
        return False  # Don't suppress exceptions

    def read(self):
        return self.rec.read()


def listen_for_wake_word(timeout=None):
    """
    Listen for wake word using Picovoice Porcupine.
    Returns True when wake word detected, False on error/timeout.
    """
    if porcupine is None:
        return True  # Fallback to push-to-talk

    print("👂 Lyssnar efter 'Jarvis'...")

    try:
        with WakeWordListener(porcupine) as listener:
            start_time = time.time()

            while True:
                # Check for shutdown signal
                if shutdown_requested:
                    return False

                if timeout and (time.time() - start_time) > timeout:
                    return False

                pcm = listener.read()
                result = porcupine.process(pcm)

                if result >= 0:
                    print("✨ Jarvis!")
                    # Play ding sound immediately for feedback
                    try:
                        music.sound_play_threading(SOUND_DING)
                    except Exception as e:
                        print(f"⚠️ Ding sound failed: {e}")
                    return True

    except Exception as e:
        print(f"⚠️ Wake word error: {e}")
        return False


def listen_for_follow_up():
    """
    Listen for follow-up speech without requiring wake word.
    Uses VAD to detect if user starts speaking within FOLLOW_UP_WINDOW.

    Returns: True if speech detected (ready to record), False if timeout/silence
    """
    print("👂 Lyssnar... (fortsätt prata)")

    # VAD frame requirements: 30ms at 16kHz = 480 samples
    SAMPLE_RATE = 16000
    VAD_FRAME_MS = 30
    VAD_FRAME_SAMPLES = int(SAMPLE_RATE * VAD_FRAME_MS / 1000)  # 480
    PVRECORDER_FRAME_LENGTH = 512

    # Speech detection threshold - need several consecutive speech frames
    SPEECH_FRAMES_THRESHOLD = 3  # ~90ms of speech to trigger

    try:
        # Initialize VAD
        vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)

        # Find USB mic for PvRecorder
        device_idx = find_usb_mic_pvrecorder()
        if device_idx is None:
            for idx in [0, 15, 1, 2]:
                try:
                    test_rec = PvRecorder(device_index=idx, frame_length=PVRECORDER_FRAME_LENGTH)
                    test_rec.delete()
                    device_idx = idx
                    break
                except:
                    continue
            if device_idx is None:
                device_idx = 0

        # Start recording
        recorder = PvRecorder(device_index=device_idx, frame_length=PVRECORDER_FRAME_LENGTH)
        recorder.start()

        vad_buffer = []
        consecutive_speech_frames = 0
        start_time = time.time()

        try:
            while True:
                # Check for shutdown
                if shutdown_requested:
                    return False

                elapsed = time.time() - start_time

                # Timeout - no speech detected within follow-up window
                if elapsed >= FOLLOW_UP_WINDOW:
                    print("⏱️ Ingen fortsättning hörd")
                    return False

                # Read audio frame
                pcm = recorder.read()
                vad_buffer.extend(pcm)

                # Process VAD in 30ms chunks
                while len(vad_buffer) >= VAD_FRAME_SAMPLES:
                    vad_frame = vad_buffer[:VAD_FRAME_SAMPLES]
                    vad_buffer = vad_buffer[VAD_FRAME_SAMPLES:]

                    # Convert to bytes for webrtcvad
                    frame_bytes = struct.pack(f'{VAD_FRAME_SAMPLES}h', *vad_frame)

                    # Check if frame contains speech
                    is_speech = vad.is_speech(frame_bytes, SAMPLE_RATE)

                    if is_speech:
                        consecutive_speech_frames += 1
                        if consecutive_speech_frames >= SPEECH_FRAMES_THRESHOLD:
                            print("🎤 Fortsätter lyssna...")
                            return True
                    else:
                        consecutive_speech_frames = 0

        finally:
            recorder.stop()
            recorder.delete()

    except Exception as e:
        print(f"⚠️ Follow-up listening error: {e}")
        return False

    return False


def main():
    """
    Main voice assistant loop - wake word activated
    Bulletproof edition with comprehensive error handling

    Say "Hey Jarvis" (or your custom wake word) to activate.
    Falls back to push-to-talk if wake word model fails to load.
    """

    print("=" * 50)
    print("PiCar Röstassistent - Redo för Leon!")
    print("=" * 50)
    print()

    # Run startup self-test
    if not startup_self_test():
        print("❌ Självtest misslyckades! Prova att starta om.")
        speak("Jag har ett problem. Fråga pappa om hjälp.")
        return  # Exit gracefully

    # Play ready sound on startup
    try:
        music.sound_play_threading(SOUND_READY)
        time.sleep(0.5)  # Let the ready sound play before speaking
    except Exception as e:
        print(f"⚠️ Ready sound failed: {e}")

    if porcupine:
        print(f"Säg 'Jarvis' för att prata, Ctrl+C för att avsluta")
        speak(f"Hej Leon! Jag är din robotbil. Säg Jarvis så lyssnar jag!")
    else:
        print("Tryck ENTER för att prata, Ctrl+C för att avsluta")
        speak("Hej Leon! Jag är din robotbil. Tryck på knappen och prata med mig!")

    print()
    reset_car_safe()

    # Track consecutive failures
    consecutive_failures = 0
    MAX_CONSECUTIVE_FAILURES = 5

    # Follow-up mode: after robot responds, listen for continuation without wake word
    in_follow_up_mode = False

    while not shutdown_requested:
        try:
            # LED off = listening for wake word (or follow-up)
            try:
                led.off()
            except:
                pass

            # Check for follow-up speech or wait for wake word
            if in_follow_up_mode and porcupine:
                # Listen for follow-up without wake word
                follow_up_detected = listen_for_follow_up()
                if not follow_up_detected:
                    # No follow-up, return to wake word mode
                    in_follow_up_mode = False
                    continue
                # Follow-up detected - skip ding sound, go straight to recording
                # (already printed "Fortsätter lyssna...")
            elif porcupine:
                # Normal wake word mode
                detected = listen_for_wake_word()
                if not detected:
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        print("\n⚠️ Wake word mikrofon fungerar inte. Prova att starta om mig.")
                        speak("Jag kan inte höra. Fråga pappa om hjälp.")
                        break
                    time.sleep(1)  # Brief pause before retry
                    continue
                # Reset failure counter on successful detection
                consecutive_failures = 0
                # Ding sound already played in listen_for_wake_word()
                # Small delay before recording
                time.sleep(0.3)
            else:
                # Fallback: push to talk
                input("\n🎤 Tryck ENTER och prata... ")

            # LED on = recording
            try:
                led.on()
            except:
                pass

            print("🔴 Spelar in... (prata nu!)")

            # Record with VAD
            wav_file = record_audio(duration=4)
            if not wav_file:
                consecutive_failures += 1
                in_follow_up_mode = False  # Reset follow-up on failure
                print("❌ Inspelning misslyckades")
                # Play retry sound for friendly feedback
                try:
                    music.sound_play_threading(SOUND_RETRY)
                except Exception as e:
                    print(f"⚠️ Retry sound failed: {e}")
                speak("Jag hörde inte, försök igen")
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print("\n⚠️ För många fel. Prova att starta om mig.")
                    speak("Jag har problem. Fråga pappa om hjälp.")
                    break
                continue

            # Transcribe
            print("🧠 Lyssnar...")
            text = transcribe_audio(wav_file)

            if not text or not text.strip():
                consecutive_failures += 1
                in_follow_up_mode = False  # Reset follow-up on failure
                print("❓ Kunde inte höra något")
                # Play retry sound for friendly feedback
                try:
                    music.sound_play_threading(SOUND_RETRY)
                except Exception as e:
                    print(f"⚠️ Retry sound failed: {e}")
                speak("Jag hörde inte vad du sa. Försök igen!")
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print("\n⚠️ För många fel. Prova att starta om mig.")
                    speak("Jag har problem. Fråga pappa om hjälp.")
                    break
                continue

            print(f"📝 Leon sa: {text}")

            # Get GPT response (streaming - speaks sentence-by-sentence)
            print("💭 Tänker...")
            answer, actions = chat_with_gpt(text)

            # Success - reset failure counter
            consecutive_failures = 0

            # Note: Speaking already happened during streaming
            if actions:
                print(f"🎬 Rörelser: {actions}")

            # Execute actions (wrapped in safe handler)
            for action_name in actions:
                if action_name in ACTIONS:
                    print(f"⚡ Utför: {action_name}")
                    safe_action(ACTIONS[action_name], action_name)
                    time.sleep(0.3)

            # Reset to default position
            reset_car_safe()

            try:
                led.off()
            except:
                pass

            # Enable follow-up mode - listen for continuation without wake word
            if porcupine:
                in_follow_up_mode = True

        except KeyboardInterrupt:
            print("\n\n👋 Hejdå!")
            speak("Hejdå Leon! Vi ses snart!")
            break

        except Exception as e:
            consecutive_failures += 1
            in_follow_up_mode = False  # Reset follow-up on error
            print(f"❌ Oväntat fel: {e}")
            try:
                led.off()
            except:
                pass
            reset_car_safe()
            time.sleep(1)

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print("\n⚠️ För många fel. Prova att starta om mig.")
                speak("Jag har problem. Fråga pappa om hjälp.")
                break

# ============== RUN ==============

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Programmet avbryts...")
    except Exception as e:
        print(f"⚠️ Oväntat fel: {e}")
    finally:
        # Always clean up safely
        print("\n🔧 Stänger ner säkert...")
        reset_car_safe()
        try:
            led.off()
        except:
            pass
        print("🛑 Klart! Hejdå!")
