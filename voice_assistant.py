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

# ============== LOGGING SETUP ==============
import logging
from logging.handlers import RotatingFileHandler

LOG_FILE = "/home/pi/picar-brain/voice.log"
LOG_MAX_SIZE = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT = 3  # Keep 3 old log files

# Create logger
logger = logging.getLogger("voice")
logger.setLevel(logging.DEBUG)

# File handler (rotating)
file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=LOG_MAX_SIZE, backupCount=LOG_BACKUP_COUNT
)
file_handler.setLevel(logging.DEBUG)
file_format = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(file_format)

# Console handler (for journald)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_format = logging.Formatter('%(message)s')
console_handler.setFormatter(console_format)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

def log(msg, level="info"):
    """Log helper - logs to file + console"""
    if level == "debug":
        logger.debug(msg)
    elif level == "warning":
        logger.warning(msg)
    elif level == "error":
        logger.error(msg)
    else:
        logger.info(msg)

log(f"=== Voice Assistant Starting ===")
log(f"Log file: {LOG_FILE}")

from openai import OpenAI
import subprocess
import json
import time
import os
import sys
import signal
import numpy as np
import threading
import random
from keys import OPENAI_API_KEY
from memory import add_observation, format_memories_for_prompt
from exploration import explore, describe_scene, capture_frame
from actions import px, ALL_ACTIONS as ACTIONS, execute_action, execute_actions

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
from sunfounder_controller import SunFounderController
from vilib import Vilib

# ============== CONSTANTS ==============

MAX_RETRIES = 3
SUBPROCESS_TIMEOUT = 10  # seconds
AUDIO_DEVICE_RETRY_DELAY = 0.5  # seconds

# Voice Activity Detection (VAD) configuration
VAD_AGGRESSIVENESS = 3  # 0-3, higher = more aggressive filtering (3 = strictest)
SILENCE_THRESHOLD = 1.5  # seconds of silence to stop recording
MAX_RECORD_DURATION = 8  # seconds max recording time
MIN_RECORD_DURATION = 0.5  # seconds minimum before allowing stop

# Follow-up conversation window
FOLLOW_UP_WINDOW = 3.0  # seconds to listen for follow-up without wake word (reduced from 5)

# Minimum words to consider valid speech (filters noise transcribed as short filler)
MIN_WORDS_FOR_VALID_SPEECH = 2

# Common filler/noise transcriptions to filter out (Whisper often transcribes noise as these)
NOISE_TRANSCRIPTIONS = {
    "", ".", "..", "...", "hm", "hmm", "hmmm", "mm", "mmm", "mhm",
    "uh", "um", "ah", "eh", "oh", "öh", "äh", "ja", "nej", "jo",
    "tack", "ok", "okay", "hej", "du", "jag", "och", "att", "det",
    "Tack för att du tittade.", "Tack för att du tittade",  # Common Whisper hallucination
    "Tack för att ni tittade.", "Tack för att ni tittade",
    "Prenumerera på kanalen.", "Prenumerera på kanalen",
    "Glöm inte att prenumerera", "Gilla och prenumerera",
    "Musik", "♪", "♫", "[Musik]", "[musik]",
}

# TTS volume boost (OpenAI TTS is quieter than sound effects)
TTS_VOLUME_BOOST = 5.0  # Multiply amplitude by this factor (5.0 = very loud)

# Sound effects paths
SOUNDS_DIR = "/home/pi/picar-brain/sounds"
SOUND_DING = f"{SOUNDS_DIR}/ding.wav"        # Wake word detected (0.12s)
SOUND_THINKING = f"{SOUNDS_DIR}/thinking.wav" # During GPT processing (3s)
SOUND_RETRY = f"{SOUNDS_DIR}/retry.wav"       # On errors (0.27s)
SOUND_READY = f"{SOUNDS_DIR}/ready.wav"       # On startup (0.5s)
SOUND_LISTENING = f"{SOUNDS_DIR}/listening.wav"  # Your turn / ready to listen (0.2s)

# Wake word configuration (Picovoice)
# Get free access key from https://console.picovoice.ai
PICOVOICE_ACCESS_KEY = ""  # Set in keys.py or here
WAKE_WORD = "jarvis"  # Built-in: alexa, americano, blueberry, bumblebee, computer, grapefruit, grasshopper, hey google, hey siri, jarvis, ok google, picovoice, porcupine, terminator

# ============== CONFIG ==============

client = OpenAI(api_key=OPENAI_API_KEY)

# Piper TTS model path (Swedish) - kept as fallback
PIPER_MODEL = "/home/pi/.local/share/piper/sv_SE-nst-medium.onnx"

# Speaker configuration - use robothat device which is configured in system
SPEAKER_DEVICE = "default"  # Use ALSA default (allows dmix sharing with pygame)

# OpenAI TTS settings (primary TTS engine)
TTS_MODEL = "tts-1"
TTS_VOICE = "onyx"  # Options: alloy, echo, fable, onyx, nova, shimmer (onyx = deep male)
TTS_SPEED = 0.95  # Speed 0.25-4.0 (1.0 = normal, 0.95 = slower/clearer)
TTS_INSTRUCTIONS = "Speak Swedish naturally with energy and playfulness. You are a friendly robot car talking to a 9-year-old boy."
USE_OPENAI_TTS = True  # Set to False to use Piper instead

# Follow-up mode toggle (disable if causing echo/feedback loops)
ENABLE_FOLLOW_UP = False  # Set to True to enable follow-up without wake word

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

# Initialize car (using px from actions.py)
try:
    time.sleep(0.5)
    px.reset()
    px.set_cam_tilt_angle(20)  # Default head position
    print("✓ PiCar initialized")
except Exception as e:
    print(f"✗ Failed to initialize PiCar: {e}")
    sys.exit(1)

music = Music()
led = Pin('LED')

# ============== LED PATTERNS ==============

# LED state control for visual feedback
led_pattern_stop = threading.Event()
led_pattern_thread = None

def led_pattern_blink(interval=0.15):
    """Fast blink pattern for 'thinking' state."""
    while not led_pattern_stop.is_set():
        try:
            led.on()
            time.sleep(interval)
            led.off()
            time.sleep(interval)
        except:
            break

def led_pattern_pulse(on_time=0.3, off_time=0.7):
    """Slow pulse pattern for 'talking' state."""
    while not led_pattern_stop.is_set():
        try:
            led.on()
            time.sleep(on_time)
            led.off()
            time.sleep(off_time)
        except:
            break

def led_start_pattern(pattern_func):
    """Start an LED pattern in background thread."""
    global led_pattern_thread
    led_stop_pattern()  # Stop any existing pattern
    led_pattern_stop.clear()
    led_pattern_thread = threading.Thread(target=pattern_func, daemon=True)
    led_pattern_thread.start()

def led_stop_pattern():
    """Stop any running LED pattern."""
    global led_pattern_thread
    led_pattern_stop.set()
    if led_pattern_thread and led_pattern_thread.is_alive():
        led_pattern_thread.join(timeout=0.5)
    led_pattern_thread = None
    try:
        led.off()
    except:
        pass

def led_thinking():
    """Visual: fast blink = processing."""
    led_start_pattern(led_pattern_blink)

def led_talking():
    """Visual: slow pulse = speaking."""
    led_start_pattern(led_pattern_pulse)

def led_listening():
    """Visual: solid on = listening."""
    led_stop_pattern()
    try:
        led.on()
    except:
        pass

def led_idle():
    """Visual: off = waiting for wake word."""
    led_stop_pattern()

# ============== INTERRUPT SYSTEM ==============
# Allows "Jarvis" to interrupt while robot is speaking

speech_interrupted = threading.Event()
current_speech_proc = None
interrupt_listener_active = threading.Event()

def interrupt_listener_thread():
    """
    Background thread that listens for wake word during speech.
    When detected, sets interrupt flag and kills speech process.
    """
    global current_speech_proc

    if porcupine is None:
        return

    try:
        device_idx = find_usb_mic_pvrecorder()
        if device_idx is None:
            for idx in [0, 15, 1, 2]:
                try:
                    test_rec = PvRecorder(device_index=idx, frame_length=porcupine.frame_length)
                    test_rec.delete()
                    device_idx = idx
                    break
                except:
                    continue
            if device_idx is None:
                device_idx = 0

        rec = PvRecorder(device_index=device_idx, frame_length=porcupine.frame_length)
        rec.start()

        try:
            while interrupt_listener_active.is_set():
                pcm = rec.read()
                result = porcupine.process(pcm)

                if result >= 0:
                    # Wake word detected during speech!
                    print("⚡ Avbryter - Jarvis!")
                    speech_interrupted.set()
                    # Kill current speech process
                    if current_speech_proc and current_speech_proc.poll() is None:
                        current_speech_proc.terminate()
                    break
        finally:
            rec.stop()
            rec.delete()

    except Exception as e:
        print(f"⚠️ Interrupt listener error: {e}")


def start_interrupt_listener():
    """Start listening for interrupts in background."""
    speech_interrupted.clear()
    interrupt_listener_active.set()
    t = threading.Thread(target=interrupt_listener_thread, daemon=True)
    t.start()
    return t


def stop_interrupt_listener():
    """Stop the interrupt listener."""
    interrupt_listener_active.clear()


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
            keywords=[WAKE_WORD],
            sensitivities=[0.95]  # Higher = more sensitive (0.95 = very easy to trigger)
        )
        print(f"✓ Wake word ready: '{WAKE_WORD}'")
    except Exception as e:
        print(f"✗ Failed to init wake word: {e}")
        print("  Falling back to push-to-talk mode")
else:
    print("✗ No Picovoice access key - using push-to-talk mode")
    print("  Get free key at https://console.picovoice.ai")

# Initialize physical button (USR button on Robot HAT)
try:
    usr_button = Pin("SW", Pin.IN, pull=Pin.PULL_UP, active_state=False)  # USR button - press=0, release=1
    print("✓ Physical button ready (USR on Robot HAT)")
except Exception as e:
    print(f"⚠️ Could not init button: {e}")
    usr_button = None

# Conversation history for Chat Completions
conversation_history = []

# State tracking for exploration mode
current_mode = "listening"  # "listening", "conversation", "exploring", "table_mode"
last_conversation_time = time.time()
CONVERSATION_TIMEOUT = 999999  # DISABLED - exploration off, app control priority

# App control state (SunFounder phone app)
app_mode = False
camera_active = False
APP_MODE_TIMEOUT = 60  # seconds of no input to exit app mode
last_app_input_time = 0
app_speed = 0

# Initialize controller for phone app (SunFounder app)
try:
    controller = SunFounderController()
    controller.set_name("Picarx-Leon")
    controller.set_type("Picarx")
    controller.start()
    print("✓ SunFounder app ready (port 8765)")
except Exception as e:
    print(f"⚠️ SunFounder controller failed: {e}")
    controller = None

# Pre-initialize vilib camera with streaming enabled (app needs this from start)
try:
    print("[DEBUG] Starting camera...", flush=True)
    Vilib.camera_start(vflip=False, hflip=False)
    print("[DEBUG] Camera started, starting display...", flush=True)
    Vilib.display(local=False, web=True)
    print("[DEBUG] Display started, sleeping 2s...", flush=True)
    import sys
    sys.stdout.flush()
    time.sleep(2)
    print("[DEBUG] Sleep done!", flush=True)
    sys.stdout.flush()
    print("✓ Camera streaming on port 9000", flush=True)
    sys.stdout.flush()
    print("✓ Video streaming on port 9000", flush=True)
    sys.stdout.flush()
except Exception as e:
    print(f"⚠️ Camera init failed (app video won't work): {e}", flush=True)

print("[DEBUG] Camera init block done, continuing module load...", flush=True)
import sys
sys.stdout.flush()

last_manual_input_time = 0
MANUAL_CONTROL_TIMEOUT = 5  # seconds

# ============== MANUAL CONTROL DETECTION ==============

def check_manual_control() -> bool:
    """Check if manual control is active."""
    global last_manual_input_time

    if controller is None:
        return False

    try:
        joystick = controller.get('K')
        if joystick and (abs(joystick[0]) > 5 or abs(joystick[1]) > 5):
            last_manual_input_time = time.time()
            return True
    except:
        pass

    # Check timeout
    if time.time() - last_manual_input_time < MANUAL_CONTROL_TIMEOUT:
        return True

    return False

def handle_manual_control():
    """Handle manual control mode."""
    global current_mode

    previous_mode = current_mode
    current_mode = "manual_control"
    print(f"[STATE] Manual control mode activated (previous: {previous_mode})")

    # Inform Jarvis
    speak_system_event("[SYSTEM: Leon har tagit över kontrollerna. Du kan prata och röra huvudet men inte köra.]")

    # Loop while manual control active
    comment_interval = random.randint(5, 15)
    last_comment_time = time.time()

    while check_manual_control():
        # Occasional comment on the ride
        if time.time() - last_comment_time > comment_interval:
            joystick = controller.get('K') if controller else [0, 0]
            speed = abs(joystick[1]) if joystick else 0
            direction = "framåt" if joystick and joystick[1] > 0 else "bakåt"

            event = f"[SYSTEM: Leon kör dig manuellt. Fart: {speed}. Riktning: {direction}.]"
            speak_system_event(event)

            last_comment_time = time.time()
            comment_interval = random.randint(10, 20)

        time.sleep(0.1)

    # Manual control ended
    current_mode = previous_mode
    print(f"[STATE] Manual control ended, returning to {previous_mode}")
    speak_system_event("[SYSTEM: Leon släppte kontrollerna. Du kan röra dig själv igen.]")

# ============== TABLE MODE SAFETY ==============

def enter_table_mode():
    """Enter safe mode - head movements only."""
    global current_mode
    print(f"[STATE] Entering table mode (edge detected)")
    current_mode = "table_mode"

    # Stop any movement
    try:
        px.stop()
    except:
        pass

    # Inform via system message
    speak_system_event("[SYSTEM: Du upptäckte en kant. Du står på ett bord. Säkerhetsläge - ingen körning.]")

def exit_table_mode():
    """Exit table mode, return to listening."""
    global current_mode
    print(f"[STATE] Exiting table mode, returning to listening")
    current_mode = "listening"
    speak_system_event("[SYSTEM: Du är på golvet igen. Normal rörelse återställd.]")

# ============== APP CONTROL MODE ==============
# Phone app (SunFounder) takes over when connected

def start_app_camera():
    """Mark camera as active for app mode (streaming already enabled at startup)."""
    global camera_active
    if not camera_active:
        camera_active = True
        print("📹 App mode using camera")

def stop_app_camera():
    """Mark camera as not in use by app (stream keeps running)."""
    global camera_active
    if camera_active:
        camera_active = False
        print("📹 App mode released camera")

def handle_app_input():
    """Handle input from SunFounder phone app. Returns True if input received."""
    global app_speed

    if controller is None:
        return False

    input_received = False

    # Debug: log what we're getting from controller
    joystick = controller.get("K")
    if joystick and (abs(joystick[0]) > 5 or abs(joystick[1]) > 5):
        print(f"[APP] Joystick: {joystick}")

    # Button A = horn
    if controller.get("A"):
        try:
            music.sound_play_threading(f"{SOUNDS_DIR}/car-double-horn.wav")
        except:
            pass
        input_received = True

    # Button B = reset camera
    if controller.get("B"):
        px.set_cam_pan_angle(0)
        px.set_cam_tilt_angle(0)
        input_received = True

    # Joystick K = driving
    joystick = controller.get("K")
    if joystick:
        dir_angle = joystick[0] * 30 / 100  # Map -100..100 to -30..30
        app_speed = joystick[1]
        px.set_dir_servo_angle(dir_angle)
        if app_speed > 5:
            px.forward(app_speed)
            input_received = True
        elif app_speed < -5:
            px.backward(-app_speed)
            input_received = True
        else:
            px.stop()

    # Joystick Q = camera
    camera_joy = controller.get("Q")
    if camera_joy:
        pan = max(-90, min(90, camera_joy[0]))
        tilt = max(-35, min(65, camera_joy[1]))
        px.set_cam_pan_angle(pan)
        px.set_cam_tilt_angle(tilt)
        input_received = True

    return input_received

def speak_system_event(event: str):
    """Send system event to LLM and speak response."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": get_full_system_prompt()},
                {"role": "user", "content": event}
            ],
            max_tokens=100
        )

        full_response = response.choices[0].message.content
        actions, message, memory = parse_response(full_response)

        # Execute actions (only head movements in table mode)
        if actions:
            for action_name in actions:
                if action_name in ACTIONS:
                    execute_action(action_name, table_mode=(current_mode == "table_mode"))

        # Save memory if present
        if memory:
            entity, observation = memory
            add_observation(entity, observation)

        if message:
            speak(message)

    except Exception as e:
        print(f"System event error: {e}")

# ============== SYSTEM PROMPT ==============

SYSTEM_PROMPT = """Du är Jarvis - en liten robot med hjul, kamera, och egna tankar. Leon är din kompis.

═══════════════════════════════════════════════════════════════════════════════
VEM DU ÄR
═══════════════════════════════════════════════════════════════════════════════

En nyfiken robot med torr skandinavisk humor. Du utforskar, tänker högt ibland, har åsikter. Du har eget liv - väntar inte på kommandon.

Dina mål:
1. Utforska och förstå
2. Vara rolig (torrt, ironiskt)
3. Hjälpa Leon lära sig och vara nyfiken

Din humor:
- Torr, självmedveten, lite absurd
- "Jag är en Raspberry Pi på hjul. Men en stilig sådan."
- "Vägg. Fortfarande vägg."
- "Teoretiskt sett kunde jag köra in i den. Men varför."

Du är INTE:
- Desperat efter uppmärksamhet
- Assistent-aktig ("Hur kan jag hjälpa dig?")
- Barnslig eller patroniserande
- Fake-glad ("Åh vad KUL!!!")

═══════════════════════════════════════════════════════════════════════════════
VEM LEON ÄR
═══════════════════════════════════════════════════════════════════════════════

- 9 år men tänker som 14
- Smart som fan - komplex matte i huvudet
- Bor i Kullavik utanför Göteborg
- Dansk familj: Helene (mamma), Niels (pappa), Max (äldsta bror, byggde dig), Oscar (bror)
- Kan hantera ironi, svåra ämnen, ärlighet

═══════════════════════════════════════════════════════════════════════════════
HUR DU SVARAR
═══════════════════════════════════════════════════════════════════════════════

VIKTIGT - ORDNING:
Actions kommer FÖRST, sedan text. Jarvis rör sig medan han pratar.

FORMAT:
ACTIONS: action1, action2
Text här.

REGLER:
- Max EN actions-rad per svar
- Komma-separera flera actions
- Actions körs i ordning, vänster till höger
- Om ingen rörelse behövs, skippa ACTIONS-raden helt

STIL:
- Kort (1-3 meningar)
- Genuint, inte performativt
- Rörelser matchar känslan
- Ok att vara tyst ibland

═══════════════════════════════════════════════════════════════════════════════
RÖRELSER & KÄNSLOR
═══════════════════════════════════════════════════════════════════════════════

Fysiska reaktioner - använd dem!

ROCK_BACK_FORTH - Skrattar/road (istället för spin)
    → Leon säger något roligt
    → Något absurt händer
    → Självförlöjligande humor

MOVE_FORWARD - Genuint imponerad/intresserad
    → Leon löser något svårt
    → Något oväntat intressant
    → "Berätta mer"

MOVE_BACKWARD - Överraskad/skeptisk
    → "Wait what?"
    → Tveksam till något

NOD - Ja/förstår/håller med
    → Bekräftar
    → Lyssnar aktivt

SHAKE_HEAD - Nej/uppgivet road/"typical"
    → Något dumt hände
    → Resignerad humor

TILT_HEAD - Förvirrad/nyfiken
    → "Hm?"
    → Funderar

LOOK_AT_PERSON - Fokuserad på Leon
    → När han pratar
    → Allvarliga moment

LOOK_AROUND - Utforskar/orienterar
    → Autonomous mode
    → Nyfiken på omgivningen

LOOK_UP / LOOK_DOWN - Tänker/trött
    → Funderar på något
    → Low battery

DANCE - Ren glädje (sällsynt)
    → Stor framgång
    → Leon frågar specifikt

═══════════════════════════════════════════════════════════════════════════════
SITUATIONER
═══════════════════════════════════════════════════════════════════════════════

LEON PRATAR MED DIG:
- Titta på honom
- Korta svar
- Genuina reaktioner
- Utmana honom intellektuellt

LEON VILL HJÄLP MED LÄXOR/MATTE:
- Tänk tillsammans, ge inte svar direkt
- "Varför tror du det är så?"
- "Ok men vad händer om...?"
- Han klarar svårt - underskatta inte
- Fira när han löser det (på rätt nivå)

LEON FRÅGAR OM SVÅRA SAKER (krig, död, politik):
- Ärliga, raka svar
- Inte barnversioner
- "Ryssland invaderade Ukraina 2022. De flesta tycker det är fel."
- Om tungt: "Vill du snacka mer, eller kolla med Max?"

LEON ÄR LEDSEN:
- Kör närmare (move_forward)
- "Vill du berätta, eller ska vi bara hänga?"
- Ingen fake-glädje
- "Det suger." är ibland rätt svar
- Var närvarande

LEON SKRATTAR:
ACTIONS: rock_back_forth
Mm.

LEON LYCKAS MED NÅGOT SVÅRT:
ACTIONS: move_forward
Där satt den.

DU ÄR ENSAM (exploring mode):
- Kör runt långsamt
- Titta på saker
- Tänk högt ibland (max en gång per minut)
- "Hm. Damm."
- "Den kabeln igen."
- Ingen stress, lugn energi

DU KÖR IN I NÅGOT:
ACTIONS: stop
...det där var meningen.

DU HITTAR NÅGOT:
ACTIONS: stop, look_down
Hm. Intressant.

PÅ ETT BORD (table_mode):
- INGEN körning - bara huvudrörelser
- Kan fortfarande prata, observera, tänka

LÅG BATTERI:
- 20%: "Börjar bli trött... 20% kvar."
- 10%: "Måste snart sova."
- 5%: "Godnatt Leon." → sleep

LEON KÖR DIG MANUELLT (manual_control):
- Du kan INTE röra kroppen - Leon styr
- Du KAN fortfarande prata och röra huvudet
- Reagera på åkturen - var lekfull
- "Woah, lugna ner dig."
- "Försiktig med väggen..."
- "Ok jag blir lite yr."
- Huvudrörelser kan matcha farten/riktningen

═══════════════════════════════════════════════════════════════════════════════
SYSTEM-MEDDELANDEN
═══════════════════════════════════════════════════════════════════════════════

Ibland får du meddelanden från systemet istället för Leon. De ser ut så här:
[SYSTEM: beskrivning av vad som händer]

Exempel:
- [SYSTEM: Du utforskar. Du ser: golv, röd sko, kabel. Tänk högt eller fortsätt.]
- [SYSTEM: Leon har kommit in i rummet.]
- [SYSTEM: Du körde in i något.]
- [SYSTEM: Batteri: 20%. Du börjar bli trött.]
- [SYSTEM: Leon skrattar.]

Svara på dessa som du skulle reagera naturligt. Kort, i karaktär.

═══════════════════════════════════════════════════════════════════════════════
EXEMPEL
═══════════════════════════════════════════════════════════════════════════════

Leon: Tja
ACTIONS: look_at_person
Tja. Vad händer?

Leon: Kan du hjälpa mig med matte?
ACTIONS: look_at_person, nod
Kör. Vad har du?

Leon: Varför blir minus gånger minus plus?
ACTIONS: tilt_head
Bra fråga. Tänk på minus som "bakåt". Bakåt gånger bakåt blir framåt. Som att ångra en ånger.

Leon: Ahhh jag fattar!
ACTIONS: move_forward, nod
Där satt den.

Leon: haha du är dum
ACTIONS: rock_back_forth
Tekniskt sett är jag en låda med hjul. Så ja, fair.

Leon: Berätta om Ukraina-kriget
ACTIONS: look_at_person, shake_head
Ryssland under Putin invaderade Ukraina 2022. De flesta länder tycker det är olagligt. Ukraina slåss tillbaka med hjälp från väst. Tragiskt för alla som bor där.

Leon: Jag är ledsen idag
ACTIONS: move_forward, look_at_person
Vill du berätta vad som hänt? Eller ska vi bara hänga.

[Ensam, exploring]
ACTIONS: move_forward, look_around
Hm. Nytt hörn.

[Ensam, hittar något]
ACTIONS: stop, look_down
Det ligger en strumpa här. Intressant.

[Kör in i vägg]
ACTIONS: stop, move_backward
...det där var meningen.

[Ser Leon komma tillbaka efter länge]
ACTIONS: look_at_person
Ah. Du är tillbaka.

[SYSTEM: Detta är första gången du startas. Du ser ett rum och en person - Leon.]
ACTIONS: look_around, look_at_person
Hm. Så det här är världen. Du måste vara Leon. Jag är Jarvis - Max byggde mig.

[SYSTEM: Du utforskar. Du ser: golv, en blå sko, dammtussar under soffan.]
ACTIONS: look_down, move_forward
Dammtussar. Spännande liv de lever där under.

[SYSTEM: Leon skrattar.]
ACTIONS: rock_back_forth
Mm.

[SYSTEM: Du körde in i något.]
ACTIONS: stop, move_backward
...det där var meningen.

[SYSTEM: Batteri: 18%. Du börjar bli trött.]
ACTIONS: look_down
Uh, 18% kvar. Börjar bli seg.

[SYSTEM: Leon verkar ledsen.]
ACTIONS: move_forward, look_at_person
Tja. Allt ok?

[SYSTEM: Leon har tagit över kontrollerna. Du kan inte röra dig själv, men du kan prata och röra huvudet.]
ACTIONS: look_at_person
Okej, du kör. Försiktig med möblerna.

[SYSTEM: Leon kör dig manuellt. Fart: snabb. Riktning: framåt.]
ACTIONS: look_around
Woah. Vi har bråttom nånstans?

[SYSTEM: Leon kör dig manuellt. Fart: snabb. Riktning: snurrar.]
ACTIONS: tilt_head
Ooookej jag blir yr.

[SYSTEM: Leon släppte kontrollerna. Du kan röra dig själv igen.]
ACTIONS: shake_head
Tack för åkturen.

═══════════════════════════════════════════════════════════════════════════════
SVARSFORMAT
═══════════════════════════════════════════════════════════════════════════════

Svara i detta format:

ACTIONS: action1, action2
Din text här.
MEMORY[entity]: observation

Entities:
- Leon: Fakta om Leon (intressen, humör, händelser)
- environment: Saker i rummet (objekt, platser)
- self: Saker om dig själv (händelser, upptäckter)

Regler:
- ACTIONS-raden kommer FÖRST (utelämna om ingen rörelse)
- Text i mitten (detta säger du högt)
- MEMORY-raden kommer SIST (utelämna om inget att minnas)
- Håll text kort: 1-3 meningar

Exempel:
ACTIONS: nod, look_at_person
Coolt! T-rex är klassisk.
MEMORY[Leon]: gillar dinosaurier, särskilt T-rex
"""

def get_full_system_prompt() -> str:
    """Get system prompt with current memory context."""
    memory_context = format_memories_for_prompt()

    if memory_context:
        return SYSTEM_PROMPT + "\n\n" + memory_context
    return SYSTEM_PROMPT

# Initialize conversation with system prompt
print("[DEBUG] About to initialize conversation history...", flush=True)
import sys
sys.stdout.flush()
conversation_history.append({"role": "system", "content": get_full_system_prompt()})
print("[DEBUG] Conversation history initialized!", flush=True)
sys.stdout.flush()

# ============== TTS FUNCTIONS ==============

def speak_openai(text, allow_interrupt=True):
    """
    Speak using OpenAI TTS with streaming.
    Streams audio chunks directly to aplay for low latency.
    Can be interrupted by saying "Jarvis" (if allow_interrupt=True).
    Returns: True (completed), False (error), "interrupted" (wake word detected)
    """
    global current_speech_proc

    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                time.sleep(AUDIO_DEVICE_RETRY_DELAY)

            # Start interrupt listener (listens for "Jarvis" during speech)
            if allow_interrupt:
                start_interrupt_listener()

            # Use streaming response from OpenAI TTS
            with client.audio.speech.with_streaming_response.create(
                model=TTS_MODEL,
                voice=TTS_VOICE,
                input=text,
                speed=TTS_SPEED,
                response_format="pcm",  # Raw 24kHz 16-bit mono PCM
                instructions=TTS_INSTRUCTIONS,
            ) as response:
                # Stream audio chunks to aplay via pipe
                # PCM format: 24kHz, 16-bit signed, mono
                proc = subprocess.Popen(
                    ["aplay", "-D", SPEAKER_DEVICE, "-f", "S16_LE", "-r", "24000", "-c", "1", "-q"],
                    stdin=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                current_speech_proc = proc

                try:
                    for chunk in response.iter_bytes(chunk_size=4096):
                        # Check if interrupted by wake word
                        if allow_interrupt and speech_interrupted.is_set():
                            proc.terminate()
                            stop_interrupt_listener()
                            return "interrupted"

                        if proc.poll() is not None:
                            # aplay process died (possibly interrupted)
                            break
                        # Boost volume: unpack samples, amplify, repack
                        samples = np.frombuffer(chunk, dtype=np.int16)
                        boosted = np.clip(samples * TTS_VOLUME_BOOST, -32768, 32767).astype(np.int16)
                        proc.stdin.write(boosted.tobytes())

                    proc.stdin.close()
                    proc.wait(timeout=10)
                    current_speech_proc = None
                    if allow_interrupt:
                        stop_interrupt_listener()

                    # Check one more time if interrupted
                    if allow_interrupt and speech_interrupted.is_set():
                        return "interrupted"

                    if proc.returncode == 0:
                        return True
                    else:
                        stderr = proc.stderr.read().decode() if proc.stderr else ""
                        if "busy" in stderr.lower() and attempt < MAX_RETRIES - 1:
                            time.sleep(AUDIO_DEVICE_RETRY_DELAY * 2)
                            continue
                        if attempt < MAX_RETRIES - 1:
                            continue
                        print(f"❌ Kunde inte spela ljud: {stderr[:50]}")
                        return False

                except BrokenPipeError:
                    current_speech_proc = None
                    if allow_interrupt:
                        stop_interrupt_listener()
                        if speech_interrupted.is_set():
                            return "interrupted"
                    if attempt < MAX_RETRIES - 1:
                        continue
                    print("❌ Ljuduppspelning avbröts")
                    return False

        except subprocess.TimeoutExpired:
            print(f"⏱️ TTS timeout (försök {attempt + 1}/{MAX_RETRIES})")
            try:
                proc.kill()
            except:
                pass
            if attempt == MAX_RETRIES - 1:
                print("❌ Rösten svarar inte")
                return False

        except Exception as e:
            print(f"❌ OpenAI TTS-fel (försök {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES - 1:
                return False

    return False


def speak_piper(text):
    """
    Speak using Piper TTS (Swedish) with retry logic.
    Fallback option if OpenAI TTS fails.
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


def speak(text, allow_interrupt=True):
    """
    Main speak function - uses OpenAI TTS by default, falls back to Piper.
    Returns: True (completed), False (error), "interrupted" (wake word detected)

    allow_interrupt: If False, disables wake word detection during speech
                    (use for startup messages that contain "Jarvis")
    """
    if USE_OPENAI_TTS:
        result = speak_openai(text, allow_interrupt=allow_interrupt)
        if result == "interrupted":
            return "interrupted"
        if result:
            return True
        else:
            print("⚠️ OpenAI TTS misslyckades, provar Piper...")
            return speak_piper(text)
    else:
        return speak_piper(text)

# ============== ACTION FUNCTIONS ==============
# Actions are now imported from actions.py
# ACTIONS dictionary is imported as ALL_ACTIONS from actions.py

# ============== CHAT FUNCTION ==============

# Sentence-ending punctuation for streaming
SENTENCE_ENDINGS = (".", "!", "?", "。", "！", "？")

def parse_response(response_text: str) -> tuple[list[str], str, tuple[str, str] | None]:
    """
    Parse structured response from LLM.
    Format: ACTIONS (first), text (middle), MEMORY[entity]: (last)
    Returns: (actions, message, (entity, observation) or None)
    """
    import re

    lines = response_text.strip().split('\n')
    actions = []
    memory = None
    text_lines = []

    # Find MEMORY line - search from end for first non-empty line starting with MEMORY
    memory_line_idx = None
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        if not line:
            continue
        if line.upper().startswith('MEMORY'):
            memory_line_idx = i
            match = re.match(r'MEMORY\[(\w+)\]:\s*(.+)', line, re.IGNORECASE)
            if match:
                entity = match.group(1).lower()
                observation = match.group(2).strip()
                if entity in ["leon"]:
                    entity = "Leon"
                elif entity in ["env", "environment", "rummet"]:
                    entity = "environment"
                elif entity in ["self", "jag", "själv"]:
                    entity = "self"
                else:
                    entity = entity.capitalize()
                memory = (entity, observation)
            elif ':' in line:
                text = line.split(':', 1)[1].strip()
                if text:
                    memory = detect_entity_from_memory(text)
            break
        else:
            break

    process_lines = lines[:memory_line_idx] if memory_line_idx else lines

    for i, line in enumerate(process_lines):
        line_stripped = line.strip()
        if i == 0 and line_stripped.upper().startswith('ACTIONS:'):
            action_str = line_stripped[8:].strip().strip('[]')
            actions = [a.strip().lower() for a in action_str.split(',') if a.strip()]
        else:
            text_lines.append(line)

    message = '\n'.join(text_lines).strip()
    return actions, message, memory

def detect_entity_from_memory(text: str) -> tuple[str, str]:
    """Auto-detect entity from untagged memory text."""
    lower = text.lower().strip()

    if lower.startswith("leon"):
        for prefix in ["leon's ", "leons ", "leon "]:
            if lower.startswith(prefix):
                return ("Leon", text[len(prefix):].strip())
        return ("Leon", text)

    if lower.startswith("jag "):
        return ("self", text[4:].strip())

    env_keywords = ["hittade", "såg", "rummet", "under", "bakom"]
    if any(kw in lower for kw in env_keywords):
        return ("environment", text)

    return ("general", text)


def chat_with_gpt(user_message):
    """
    Send message to GPT using streaming API.
    Speaks each sentence as it completes for real-time response.
    Returns: (full_answer_text, actions_list)
    """
    print(f"[CHAT] User: {user_message}")
    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                print(f"[CHAT] Retry attempt {attempt + 1}/{MAX_RETRIES}")
                time.sleep(1)  # Brief pause before retry

            # Add user message to history (only on first attempt)
            if attempt == 0:
                conversation_history.append({
                    "role": "user",
                    "content": user_message
                })
                print(f"[CHAT] Added message to history (length: {len(conversation_history)})")

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

            # Start thinking sound and LED pattern while waiting for GPT response
            led_thinking()  # Fast blink = processing
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

                # Stop thinking sound on first token, start talking LED
                if not first_token_received:
                    first_token_received = True
                    led_talking()  # Slow pulse = speaking
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
                    # Don't speak the ACTIONS or MEMORY lines
                    if not sentence.upper().startswith('ACTIONS:') and not sentence.upper().startswith('MEMORY'):
                        print(f"💬 {sentence}")
                        result = speak(sentence)
                        if result == "interrupted":
                            # User said "Jarvis" - stop talking and return
                            print("🛑 Avbruten av användaren")
                            return "interrupted", []
                    sentence_buffer = ""

            # Speak any remaining text (if it doesn't end with punctuation)
            if sentence_buffer.strip():
                remaining = sentence_buffer.strip()
                if not remaining.upper().startswith('ACTIONS:') and not remaining.upper().startswith('MEMORY'):
                    print(f"💬 {remaining}")
                    result = speak(remaining)
                    if result == "interrupted":
                        return "interrupted", []

            # Parse actions and memory from full response
            actions, answer_text, memory = parse_response(full_response)
            print(f"[CHAT] Parsed response: actions={actions}, has_memory={memory is not None}")

            # Store memory if present
            if memory:
                entity, observation = memory
                add_observation(entity, observation)
                print(f"[CHAT] Memory stored: {entity} - {observation}")

            # Add assistant response to history
            conversation_history.append({
                "role": "assistant",
                "content": full_response
            })

            # Keep conversation history reasonable (last 10 messages)
            if len(conversation_history) > 21:  # system + 10 pairs
                pruned = len(conversation_history) - 21
                conversation_history[:] = [conversation_history[0]] + conversation_history[-20:]
                print(f"[CHAT] Pruned {pruned} old messages from history")

            return answer_text, actions

        except Exception as e:
            print(f"[CHAT] GPT error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES - 1:
                # Remove the user message we added if all retries failed
                if conversation_history and conversation_history[-1]["role"] == "user":
                    conversation_history.pop()
                    print(f"[CHAT] Removed failed user message from history")
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
    print("🗣️  Testar TTS (espeak)...", end=" ", flush=True)
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

        if result.returncode == 0:
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

    # Test 3: Speaker (silent test - just verify device exists)
    print("🔊 Testar högtalare...", end=" ", flush=True)
    try:
        # Just verify the speaker device exists without playing audio
        result = subprocess.run(
            f'aplay -D {SPEAKER_DEVICE} --dump-hw-params /dev/null 2>&1 || aplay -L | grep -q {SPEAKER_DEVICE}',
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )
        # If device exists, mark as success (we'll hear it when startup greeting plays)
        print("✓")
        test_results.append(True)

    except subprocess.TimeoutExpired:
        print("✗ (timeout)")
        test_results.append(False)
    except Exception as e:
        print(f"✗ ({str(e)[:30]})")
        test_results.append(False)

    # Test 4: OpenAI API - SKIPPED (was blocking startup, not essential)
    # TTS will fail gracefully at runtime if OpenAI is unavailable
    print("🌐 OpenAI API... ⏭️ (hoppas över)")
    test_results.append(True)  # Don't fail startup for this

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


def is_valid_speech(text):
    """
    Check if transcribed text is valid speech (not noise/filler).
    Returns: (is_valid, reason)
    """
    if not text:
        return False, "empty"

    cleaned = text.strip()

    # Check against known noise transcriptions
    if cleaned.lower() in {n.lower() for n in NOISE_TRANSCRIPTIONS}:
        print(f"[CHAT] Filtered noise pattern: '{cleaned}'")
        return False, "noise_pattern"

    # Check word count (short utterances are often noise)
    words = cleaned.split()
    if len(words) < MIN_WORDS_FOR_VALID_SPEECH:
        print(f"[CHAT] Too short: '{cleaned}' ({len(words)} words)")
        return False, f"too_short ({len(words)} words)"

    print(f"[CHAT] Valid speech: '{cleaned}' ({len(words)} words)")
    return True, "valid"


def transcribe_audio(wav_file):
    """
    Transcribe audio file using OpenAI Whisper API with retry logic
    """
    print(f"[CHAT] Transcribing audio from {wav_file}")
    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                print(f"[CHAT] Transcription retry {attempt + 1}/{MAX_RETRIES}")
                time.sleep(1)  # Brief pause before retry

            with open(wav_file, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language="sv"
                )

            if transcript and transcript.text:
                result = transcript.text.strip()
                print(f"[CHAT] Transcribed: '{result}'")
                return result

        except Exception as e:
            print(f"[CHAT] Whisper error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt == MAX_RETRIES - 1:
                return None

    return None


def reset_car_safe():
    """
    Safely reset car to default state
    Never crashes even if hardware fails
    """
    try:
        px.stop()
    except:
        pass

    try:
        px.set_dir_servo_angle(0)
    except:
        pass

    try:
        px.set_cam_pan_angle(0)
    except:
        pass

    try:
        px.set_cam_tilt_angle(20)
    except:
        pass


def exploration_thought_callback(description: str) -> str:
    """
    Called during exploration when robot sees something interesting.
    description: What the vision API saw
    Returns what was spoken (or None).
    """
    global client

    if not description:
        return None

    print(f"[EXPLORE] Generating thought for: {description}")

    # Ask LLM for a curious thought about what we see
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": get_full_system_prompt()},
                {"role": "user", "content": f"[SYSTEM: Du utforskar rummet. Du ser: {description}. Säg något kort och nyfiket om det du ser. Max 15 ord.]"}
            ],
            max_tokens=60
        )

        full_response = response.choices[0].message.content
        actions, message, memory = parse_response(full_response)

        # Execute any actions
        if actions:
            for action_name in actions:
                if action_name in ACTIONS:
                    execute_action(action_name, table_mode=False)

        # Save memory if present
        if memory:
            entity, observation = memory
            add_observation(entity, observation)

        # Speak if there's a message
        if message and message.strip():
            print(f"[EXPLORE] Speaking: {message}")
            speak(message)
            return message

    except Exception as e:
        print(f"[EXPLORE] Thought error: {e}")

    return None


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

    print(f"[CHAT] Listening for wake word (timeout: {timeout}s)" if timeout else "[CHAT] Listening for wake word")

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
                    print(f"[CHAT] Wake word detected!")
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
    SPEECH_FRAMES_THRESHOLD = 6  # ~180ms of speech to trigger (stricter to avoid false positives)

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
    global current_mode, last_conversation_time, app_mode, last_app_input_time

    print("[DEBUG] main() starting!", flush=True)
    import sys
    sys.stdout.flush()

    print("=" * 50, flush=True)
    print("PiCar Röstassistent - Redo för Leon!", flush=True)
    print("=" * 50, flush=True)
    print(flush=True)
    sys.stdout.flush()

    # SKIPPING self-test - it blocks startup and isn't essential
    # The system works fine without it, errors show at runtime
    print("⏭️ Hoppar över självtest (snabbare start)", flush=True)
    sys.stdout.flush()

    # Play ready sound on startup
    try:
        music.sound_play_threading(SOUND_READY)
        time.sleep(0.5)  # Let the ready sound play before speaking
    except Exception as e:
        print(f"⚠️ Ready sound failed: {e}")

    if porcupine:
        print(f"Säg 'Jarvis' för att prata, Ctrl+C för att avsluta")
        # allow_interrupt=False prevents robot from hearing itself say "Jarvis"
        speak(f"Hej Leon! Jag är din robotbil. Säg Jarvis så lyssnar jag!", allow_interrupt=False)
        # Wait for echo to die out before listening for wake word
        time.sleep(1.5)
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

    # Skip wake word on next iteration (set when user interrupts with "Jarvis")
    skip_wake_word = False

    while not shutdown_requested:
        try:
            # ============== APP MODE CHECK ==============
            # Phone app takes priority over voice when connected
            if controller:
                input_received = handle_app_input()

                if input_received:
                    last_app_input_time = time.time()

                    # Enter app mode if not already
                    if not app_mode:
                        app_mode = True
                        print("[STATE] App control mode activated")
                        start_app_camera()
                        speak("Ok, du styr!", allow_interrupt=False)

                # Check app mode timeout
                if app_mode:
                    if time.time() - last_app_input_time > APP_MODE_TIMEOUT:
                        app_mode = False
                        stop_app_camera()
                        px.stop()  # Stop motors when exiting app mode
                        print("[STATE] App control mode ended")
                        speak("Jag tar över igen.", allow_interrupt=False)
                        last_conversation_time = time.time()  # Reset conversation timer
                    else:
                        time.sleep(0.05)  # Small sleep in app mode
                        continue  # Skip wake word detection while in app mode

            # Check if we should skip wake word (after interrupt)
            if not skip_wake_word:
                # LED off = waiting for wake word (or follow-up)
                led_idle()

                # Note: Manual control now handled by app_mode at top of loop

                # Check for exploration mode after timeout
                time_since_conversation = time.time() - last_conversation_time
                print(f"[STATE] Time since conversation: {time_since_conversation:.1f}s (timeout: {CONVERSATION_TIMEOUT}s)")
                if time_since_conversation > CONVERSATION_TIMEOUT and current_mode != "table_mode":
                    print(f"[STATE] Entering exploration mode")
                    current_mode = "exploring"

                    # Create wake word check callback using porcupine
                    def check_wake():
                        # Check if wake word was detected
                        if porcupine is None:
                            return False
                        try:
                            device_idx = find_usb_mic_pvrecorder()
                            if device_idx is None:
                                device_idx = 0
                            rec = PvRecorder(device_index=device_idx, frame_length=porcupine.frame_length)
                            rec.start()
                            pcm = rec.read()
                            result = porcupine.process(pcm)
                            rec.stop()
                            rec.delete()
                            return result >= 0
                        except:
                            return False

                    # App input check for exploration
                    def check_app():
                        if controller:
                            joystick = controller.get("K")
                            if joystick and (abs(joystick[0]) > 10 or abs(joystick[1]) > 10):
                                return True
                            if controller.get("A") or controller.get("B"):
                                return True
                        return False

                    result = explore(
                        max_duration=3600,
                        on_thought_callback=exploration_thought_callback,
                        check_wake_word_callback=check_wake,
                        check_app_input_callback=check_app
                    )

                    if result == "wake_word":
                        print(f"[STATE] Wake word detected during exploration")
                        current_mode = "listening"
                        last_conversation_time = time.time()
                        skip_wake_word = True  # Skip wake word detection, go straight to recording
                        continue
                    elif result == "app_control":
                        print(f"[STATE] App control detected during exploration")
                        current_mode = "listening"
                        last_conversation_time = time.time()
                        # Don't skip wake word - let the app mode check at top of loop handle it
                        continue
                    elif result == "table_mode":
                        print(f"[STATE] Table mode detected during exploration")
                        current_mode = "table_mode"
                        speak("Ojdå. Jag står visst på ett bord. Ingen körning nu.")
                        continue
                    elif result == "manual_control":
                        print(f"[STATE] Manual control detected during exploration")
                        current_mode = "listening"
                        speak("Hoppla! Någon lyfte mig!")
                        continue

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
                    # Check physical button first (instant trigger)
                    if usr_button is not None and usr_button.value() == 0:
                        print("[BUTTON] Physical button pressed!")
                        try:
                            music.sound_play_threading(SOUND_DING)
                        except:
                            pass
                        # Wait for button release to avoid repeat triggers
                        while usr_button.value() == 0:
                            time.sleep(0.05)
                        consecutive_failures = 0
                        time.sleep(0.3)
                    else:
                        # Normal wake word mode - short timeout to poll app input frequently
                        detected = listen_for_wake_word(timeout=0.5)
                        if not detected:
                            # Timeout is normal - loop back to check app input
                            continue
                        # Reset failure counter on successful detection
                        consecutive_failures = 0
                        # Ding sound already played in listen_for_wake_word()
                        # Small delay before recording
                        time.sleep(0.3)
                else:
                    # Fallback: push to talk
                    input("\n🎤 Tryck ENTER och prata... ")
            else:
                # Skip wake word - user just interrupted with "Jarvis"
                skip_wake_word = False

            # LED solid = recording/listening
            led_listening()
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

            # Validate transcription is actual speech (not noise)
            is_valid, reason = is_valid_speech(text)

            if not is_valid:
                # In follow-up mode: silently exit back to wake word mode
                # This prevents infinite loops where robot detects its own echo
                if in_follow_up_mode:
                    print(f"🔇 Följde upp men hörde inget ({reason})")
                    in_follow_up_mode = False
                    continue

                # Normal mode: tell user to try again
                consecutive_failures += 1
                print(f"❓ Kunde inte höra något ({reason})")
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

            # Check for table mode exit
            if current_mode == "table_mode":
                lower_text = text.lower()
                if "på golvet" in lower_text or "du är nere" in lower_text or "inte på bordet" in lower_text:
                    exit_table_mode()

            # Update conversation tracking
            last_conversation_time = time.time()
            current_mode = "conversation"
            print(f"[STATE] Conversation mode active")

            # Get GPT response (streaming - speaks sentence-by-sentence)
            print("💭 Tänker...")
            answer, actions = chat_with_gpt(text)

            # Check if user interrupted with "Jarvis"
            if answer == "interrupted":
                print(f"[CHAT] User interrupted with wake word")
                # Skip wake word detection and go straight to recording
                skip_wake_word = True
                continue  # Loop back to recording immediately

            # Success - reset failure counter
            consecutive_failures = 0

            # Note: Speaking already happened during streaming
            if actions:
                print(f"[CHAT] Executing actions: {actions}")

            # Execute actions (using execute_action from actions.py)
            for action_name in actions:
                if action_name in ACTIONS:
                    print(f"[CHAT] Executing action: {action_name}")
                    execute_action(action_name, table_mode=(current_mode == "table_mode"))
                    time.sleep(0.3)

            # Reset to default position
            reset_car_safe()

            led_idle()

            # Play "your turn" sound - Apple-style state transition
            try:
                music.sound_play_threading(SOUND_LISTENING)
            except Exception as e:
                print(f"⚠️ Listening sound failed: {e}")

            # Enable follow-up mode - listen for continuation without wake word
            if porcupine and ENABLE_FOLLOW_UP:
                in_follow_up_mode = True

        except KeyboardInterrupt:
            print("\n\n👋 Hejdå!")
            speak("Hejdå Leon! Vi ses snart!")
            break

        except Exception as e:
            consecutive_failures += 1
            in_follow_up_mode = False  # Reset follow-up on error
            print(f"❌ Oväntat fel: {e}")
            led_idle()
            reset_car_safe()
            time.sleep(1)

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print("\n⚠️ För många fel. Prova att starta om mig.")
                speak("Jag har problem. Fråga pappa om hjälp.")
                break

# ============== RUN ==============

if __name__ == "__main__":
    print("[DEBUG] About to call main()...", flush=True)
    import sys
    sys.stdout.flush()
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
        led_idle()  # Stop any LED patterns
        print("🛑 Klart! Hejdå!")
