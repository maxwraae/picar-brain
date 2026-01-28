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

# Wake word detection (Picovoice Porcupine)
import pvporcupine
from pvrecorder import PvRecorder

# PiCar imports
from picarx import Picarx
from robot_hat import Music, Pin

# ============== CONSTANTS ==============

MAX_RETRIES = 3
SUBPROCESS_TIMEOUT = 10  # seconds
AUDIO_DEVICE_RETRY_DELAY = 0.5  # seconds

# Wake word configuration (Picovoice)
# Get free access key from https://console.picovoice.ai
PICOVOICE_ACCESS_KEY = ""  # Set in keys.py or here
WAKE_WORD = "jarvis"  # Built-in: alexa, americano, blueberry, bumblebee, computer, grapefruit, grasshopper, hey google, hey siri, jarvis, ok google, picovoice, porcupine, terminator

# ============== CONFIG ==============

client = OpenAI(api_key=OPENAI_API_KEY)

# Piper TTS model path (Swedish)
PIPER_MODEL = "/home/pi/.local/share/piper/sv_SE-nst-medium.onnx"

# Microphone configuration
MIC_DEVICE = "plughw:2,0"

# Speaker configuration - use robothat device which is configured in system
SPEAKER_DEVICE = "robothat"

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

            for chunk in response:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                if not delta.content:
                    continue

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

# ============== MAIN LOOP ==============

def record_audio(duration=4):
    """
    Record audio using arecord with retry logic for device busy
    """
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


def listen_for_wake_word(timeout=None):
    """
    Listen for wake word using Picovoice Porcupine.
    Returns True when wake word detected, False on error/timeout.
    """
    if porcupine is None:
        return True  # Fallback to push-to-talk

    print("👂 Lyssnar efter 'Jarvis'...")

    try:
        rec = PvRecorder(device_index=15, frame_length=porcupine.frame_length)
        rec.start()
        start_time = time.time()

        while True:
            if timeout and (time.time() - start_time) > timeout:
                rec.stop()
                rec.delete()
                return False

            pcm = rec.read()
            result = porcupine.process(pcm)

            if result >= 0:
                print("✨ Jarvis!")
                rec.stop()
                rec.delete()
                return True

    except Exception as e:
        print(f"⚠️ Wake word error: {e}")
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

    while True:
        try:
            # LED off = listening for wake word
            try:
                led.off()
            except:
                pass

            # Wait for wake word or Enter key (fallback)
            if porcupine:
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
                # Quick beep for immediate feedback
                try:
                    music.sound_play_threading('/home/pi/picar-brain/sounds/car-double-horn.wav')
                except:
                    pass
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

            # Record 4 seconds
            wav_file = record_audio(duration=4)
            if not wav_file:
                consecutive_failures += 1
                print("❌ Inspelning misslyckades")
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
                print("❓ Kunde inte höra något")
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

        except KeyboardInterrupt:
            print("\n\n👋 Hejdå!")
            speak("Hejdå Leon! Vi ses snart!")
            break

        except Exception as e:
            consecutive_failures += 1
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
