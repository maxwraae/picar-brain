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

from openai import OpenAI
import subprocess
import json
import time
import os
import sys
import signal
import numpy as np
from keys import OPENAI_API_KEY

# Wake word detection
from openwakeword.model import Model
from openwakeword import get_pretrained_model_paths

# PiCar imports
from picarx import Picarx
from robot_hat import Music, Pin

# ============== CONSTANTS ==============

MAX_RETRIES = 3
SUBPROCESS_TIMEOUT = 10  # seconds
AUDIO_DEVICE_RETRY_DELAY = 0.5  # seconds

# Wake word configuration
# Change this to your custom model path when ready (e.g., "/home/pi/albert_einstein.onnx")
WAKE_WORD_MODEL = "hey_jarvis"  # Pre-trained model name
WAKE_WORD_THRESHOLD = 0.5  # Detection threshold (0-1)
WAKE_WORD_CHUNK_SIZE = 1280  # Samples per chunk at 16kHz

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

# Initialize wake word model
try:
    # Get path to hey_jarvis model
    model_paths = [p for p in get_pretrained_model_paths() if WAKE_WORD_MODEL.replace('_', '') in p.lower().replace('_', '')]
    if not model_paths:
        raise ValueError(f"Model '{WAKE_WORD_MODEL}' not found in pretrained models")
    oww_model = Model(wakeword_model_paths=model_paths)
    # Get the actual model name (key in predictions dict)
    WAKE_WORD_NAME = list(oww_model.models.keys())[0]
    print(f"✓ Wake word model loaded: {WAKE_WORD_NAME}")
except Exception as e:
    print(f"✗ Failed to load wake word model: {e}")
    print("  Falling back to push-to-talk mode")
    oww_model = None
    WAKE_WORD_NAME = None

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
Du kan göra dessa saker:
- forward: kör framåt
- backward: kör bakåt
- spin_right: snurra åt höger
- spin_left: snurra åt vänster
- dance: dansa (vicka fram och tillbaka)
- nod: nicka med huvudet (säga ja)
- shake_head: skaka på huvudet (säga nej)
- stop: stanna

VIKTIGT:
- Svara ALLTID på svenska
- Var kortfattad (1-2 meningar) så Leon inte tröttnar
- Föreslå roliga saker att göra tillsammans
- Om Leon vill att du rör dig, inkludera actions i ditt svar

SVARSFORMAT:
Du måste svara med JSON i detta format:
{
  "answer": "Det du säger till Leon på svenska",
  "actions": ["lista", "av", "actions"]
}

Exempel:
{"answer": "Woohoo! Jag snurrar runt!", "actions": ["spin_right"]}
{"answer": "Vill du att jag dansar? Det kan jag!", "actions": ["dance"]}
{"answer": "Hej Leon! Vad kul att prata med dig!", "actions": ["nod"]}
{"answer": "Nej det vill jag inte göra!", "actions": ["shake_head"]}

Om Leon bara pratar och inte vill att du rör dig:
{"answer": "Vad intressant! Berätta mer!", "actions": []}
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

def chat_with_gpt(user_message):
    """
    Send message to GPT using Chat Completions API with retry logic
    Returns: (answer_text, actions_list)
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

            # Call OpenAI Chat Completions (gpt-5-mini is a reasoning model)
            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=conversation_history,
                reasoning_effort="low",  # Quick responses for a robot car
                verbosity="low"  # Short answers for a kid
            )

            # Extract response
            assistant_message = response.choices[0].message.content

            # Parse JSON response
            try:
                parsed = json.loads(assistant_message)
                answer = parsed.get("answer", "")
                actions = parsed.get("actions", [])
            except json.JSONDecodeError:
                # Fallback if GPT doesn't return proper JSON
                print("⚠️ GPT svarade inte med JSON, använder raw text")
                answer = assistant_message
                actions = []

            # Add assistant response to history
            conversation_history.append({
                "role": "assistant",
                "content": assistant_message
            })

            # Keep conversation history reasonable (last 10 messages)
            if len(conversation_history) > 21:  # system + 10 pairs
                conversation_history[:] = [conversation_history[0]] + conversation_history[-20:]

            return answer, actions

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
                f"arecord -D plughw:3,0 -d {duration} -f S16_LE -r 16000 -c 1 {wav_file}",
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
    Continuously listen for wake word using arecord stream.
    Returns True when wake word detected, False on error/timeout.

    Uses arecord to capture audio in small chunks and feeds to openwakeword.
    """
    if oww_model is None:
        # Fallback to push-to-talk
        return True

    print("👂 Lyssnar efter wake word...")

    try:
        # Start arecord process that outputs raw audio to stdout
        # Format: 16-bit signed LE, 16kHz, mono
        process = subprocess.Popen(
            ['arecord', '-D', MIC_DEVICE, '-f', 'S16_LE', '-r', '16000', '-c', '1', '-t', 'raw', '-q'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        start_time = time.time()
        bytes_per_chunk = WAKE_WORD_CHUNK_SIZE * 2  # 2 bytes per 16-bit sample

        while True:
            # Check timeout
            if timeout and (time.time() - start_time) > timeout:
                process.terminate()
                return False

            # Read a chunk of audio
            audio_bytes = process.stdout.read(bytes_per_chunk)
            if len(audio_bytes) < bytes_per_chunk:
                continue

            # Convert bytes to numpy array (16-bit signed int to float)
            audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
            audio_float = audio_int16.astype(np.float32) / 32768.0

            # Feed to wake word model
            prediction = oww_model.predict(audio_float)

            # Check if wake word detected
            score = prediction[WAKE_WORD_NAME]
            if score > WAKE_WORD_THRESHOLD:
                print(f"✨ Wake word detected! (score: {score:.2f})")
                process.terminate()
                return True

    except Exception as e:
        print(f"⚠️ Wake word listening error: {e}")
        try:
            process.terminate()
        except:
            pass
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

    if oww_model:
        print(f"Säg '{WAKE_WORD_MODEL}' för att prata, Ctrl+C för att avsluta")
        speak(f"Hej Leon! Jag är din robotbil. Säg Hey Jarvis så lyssnar jag!")
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
            if oww_model:
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
                # Play acknowledgment sound
                speak("Ja?")
                # Small delay so "Ja?" doesn't get picked up by the recording
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

            # Get GPT response
            print("💭 Tänker...")
            answer, actions = chat_with_gpt(text)

            # Success - reset failure counter
            consecutive_failures = 0

            print(f"🤖 Svar: {answer}")
            if actions:
                print(f"🎬 Rörelser: {actions}")

            # Speak the answer (never crash even if TTS fails)
            speak(answer)

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
