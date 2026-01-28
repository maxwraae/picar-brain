#!/usr/bin/env python3
"""
Leon's Interactive Modes for PiCar

Fun stuff for a 9-year-old with an AI robot car.
Run: python3 leon_modes.py
"""
import subprocess
import time
import os
import sys

# Enable speaker on startup
os.system('pinctrl set 20 op dh')

# ============== SPEECH ==============

def speak(text, lang='sv'):
    """
    Make the car talk using Piper TTS.

    Examples:
        speak("Hej Leon!")           # Swedish (default)
        speak("Hello Leon!", 'en')   # English
    """
    models = {
        'sv': '/home/pi/.local/share/piper/sv_SE-nst-medium.onnx',
        'en': '/home/pi/.local/share/piper/en_US-lessac-medium.onnx'
    }
    model = models.get(lang, models['sv'])

    # Check if model exists
    if not os.path.exists(model):
        model = models['sv']  # Fallback to Swedish

    # Generate and play
    subprocess.run(
        f'echo "{text}" | piper --model {model} --output_file /tmp/speech.wav 2>/dev/null',
        shell=True
    )
    subprocess.run('aplay -D plughw:1,0 /tmp/speech.wav 2>/dev/null', shell=True)


# ============== MOVEMENT ==============

def get_car():
    """Get the PiCar-X controller."""
    sys.path.insert(0, '/home/pi/picar-brain')
    from picarx import Picarx
    return Picarx()


def spin(direction='right', speed=50):
    """
    Do a 360 degree spin!

    Examples:
        spin()              # Spin right
        spin('left')        # Spin left
        spin('right', 70)   # Faster spin
    """
    px = get_car()

    speak("Jag snurrar!")  # "I'm spinning!"

    # Turn wheels fully in direction
    angle = 30 if direction == 'right' else -30
    px.set_dir_servo_angle(angle)
    time.sleep(0.1)

    # Drive forward while turned to create spin
    px.forward(speed)
    time.sleep(2.0)  # Adjust for full 360

    px.stop()
    px.set_dir_servo_angle(0)

    speak("Woohoo!")


def dance():
    """
    Do a little dance!
    The car wiggles back and forth.
    """
    px = get_car()

    speak("Nu dansar jag!")  # "Now I'm dancing!"

    # Wiggle sequence
    for _ in range(3):
        # Wiggle left
        px.set_dir_servo_angle(-25)
        px.forward(30)
        time.sleep(0.3)
        px.stop()

        # Wiggle right
        px.set_dir_servo_angle(25)
        px.forward(30)
        time.sleep(0.3)
        px.stop()

    # Back to center
    px.set_dir_servo_angle(0)
    speak("Tack tack!")  # "Thank you thank you!"


def nod():
    """
    Nod the camera up and down (like saying yes).
    """
    px = get_car()

    for _ in range(2):
        px.cam_tilt.angle(20)
        time.sleep(0.3)
        px.cam_tilt.angle(-10)
        time.sleep(0.3)

    px.cam_tilt.angle(0)


def shake():
    """
    Shake the camera side to side (like saying no).
    """
    px = get_car()

    for _ in range(2):
        px.cam_pan.angle(30)
        time.sleep(0.3)
        px.cam_pan.angle(-30)
        time.sleep(0.3)

    px.cam_pan.angle(0)


# ============== MESSENGER MODE ==============

def messenger_mode(message, target="Mamma"):
    """
    Leon sends the car to deliver a message!

    The car will:
    1. Announce it has a message
    2. Drive forward
    3. Deliver the message

    Examples:
        messenger_mode("Jag vill ha glass", "Pappa")
        messenger_mode("Middag ar klar", "Leon")
    """
    px = get_car()

    # Announce the mission
    speak(f"Leon har skickat mig med ett meddelande till {target}.")
    time.sleep(0.5)

    # Drive forward toward target
    px.forward(30)
    time.sleep(3)
    px.stop()

    # Nod to get attention
    nod()

    # Deliver the message
    time.sleep(0.3)
    speak(message)
    time.sleep(0.5)
    speak(f"Leon vantar pa ditt svar.")

    return "Message delivered!"


# ============== PERSONALITIES ==============

PERSONALITIES = {
    "robot": {
        "intro": "Jag ar en robot. Pip pip boop.",
        "prefix": "Robot sager: ",
    },
    "pirat": {
        "intro": "Arrr! Jag ar kapten Robotbil!",
        "prefix": "Arrr, ",
    },
    "spion": {
        "intro": "Psst... Jag ar hemlig agent noll noll bil.",
        "prefix": "Hemligt meddelande: ",
    },
    "sportkommentator": {
        "intro": "HALLAA! Och VALKOMNA till ROBOTBIL ARENAN!",
        "prefix": "OCH HAN SAGER: ",
    },
    "prinsessa": {
        "intro": "Hej alla! Jag ar prinsessan Bilinda!",
        "prefix": "Min kara van, ",
    },
}

current_personality = "robot"


def set_personality(name):
    """
    Change how the car talks!

    Options: robot, pirat, spion, sportkommentator, prinsessa

    Example:
        set_personality("pirat")
    """
    global current_personality

    if name not in PERSONALITIES:
        speak(f"Jag kanner inte till {name}. Prova: robot, pirat, spion, sportkommentator, prinsessa")
        return

    current_personality = name
    speak(PERSONALITIES[name]["intro"])


def say_as_personality(text):
    """
    Say something in the current personality's style.
    """
    p = PERSONALITIES[current_personality]
    speak(p["prefix"] + text)


# ============== COMMANDS ==============

def tell_joke():
    """Tell a random joke in Swedish."""
    import random
    jokes = [
        "Vad sager en snoskoter? Skutt skutt skutt!",
        "Vad ar gront och rullar pa golvet? En aggressiv mopp!",
        "Varfor kan inte cyklar sta for sig sjalva? For att de ar tva trotta!",
        "Vad sager en robot nar den ar hungrig? Jag ar lite rostig!",
        "Vad heter en bil som kan sjunga? En Volvo-cal!",
    ]
    speak(random.choice(jokes))


def patrol():
    """
    Drive around in a square pattern.
    """
    px = get_car()
    speak("Jag patrullerar omradet!")

    for i in range(4):
        px.forward(30)
        time.sleep(1.5)
        px.stop()

        # Turn 90 degrees
        px.set_dir_servo_angle(30)
        px.forward(30)
        time.sleep(0.6)
        px.stop()
        px.set_dir_servo_angle(0)

    speak("Patrullering klar! Omradet ar sakert.")


# ============== INTERACTIVE MODE ==============

def show_menu():
    """Show available commands."""
    print("""
    ===== LEONS ROBOTBIL =====

    Kommandon:
      saga [text]     - Bilen sager nagot
      snurra          - Snurra runt
      dansa           - Dansa!
      skamt           - Beratta ett skamt
      patrullera      - Kor runt i en fyrkant

      personlighet [namn] - Byt personlighet
        (robot, pirat, spion, sportkommentator, prinsessa)

      meddelande [text] [till] - Skicka meddelande
        Exempel: meddelande "Jag vill ha glass" Pappa

      avsluta         - Stang programmet

    ===========================
    """)


def interactive_mode():
    """
    Interactive mode for Leon to control the car from terminal.
    Type commands and the car responds!
    """
    speak("Hej Leon! Jag ar redo!")
    show_menu()

    while True:
        try:
            cmd = input("\nLeon > ").strip().lower()

            if not cmd:
                continue

            if cmd == "avsluta" or cmd == "quit" or cmd == "exit":
                speak("Hej da Leon!")
                break

            elif cmd == "hjalp" or cmd == "help":
                show_menu()

            elif cmd.startswith("saga ") or cmd.startswith("say "):
                text = cmd.split(" ", 1)[1]
                say_as_personality(text)

            elif cmd == "snurra" or cmd == "spin":
                spin()

            elif cmd == "dansa" or cmd == "dance":
                dance()

            elif cmd == "skamt" or cmd == "joke":
                tell_joke()

            elif cmd == "patrullera" or cmd == "patrol":
                patrol()

            elif cmd.startswith("personlighet ") or cmd.startswith("personality "):
                name = cmd.split(" ", 1)[1]
                set_personality(name)

            elif cmd.startswith("meddelande "):
                # Parse: meddelande "text" target
                parts = cmd.split('"')
                if len(parts) >= 2:
                    text = parts[1]
                    target = parts[2].strip() if len(parts) > 2 else "Mamma"
                    messenger_mode(text, target)
                else:
                    print("  Anvand: meddelande \"text\" namn")

            elif cmd == "nicka" or cmd == "nod":
                nod()

            elif cmd == "skaka" or cmd == "shake":
                shake()

            else:
                speak("Jag forstod inte. Skriv hjalp for att se kommandon.")

        except KeyboardInterrupt:
            speak("Hej da!")
            break
        except Exception as e:
            print(f"  Fel: {e}")


# ============== MAIN ==============

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Command line mode
        cmd = sys.argv[1].lower()

        if cmd == "spin" or cmd == "snurra":
            spin()
        elif cmd == "dance" or cmd == "dansa":
            dance()
        elif cmd == "joke" or cmd == "skamt":
            tell_joke()
        elif cmd == "patrol" or cmd == "patrullera":
            patrol()
        elif cmd == "say" or cmd == "saga":
            text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Hej!"
            speak(text)
        elif cmd == "nod" or cmd == "nicka":
            nod()
        elif cmd == "shake" or cmd == "skaka":
            shake()
        else:
            print(f"Unknown command: {cmd}")
            print("Try: spin, dance, joke, patrol, say [text], nod, shake")
    else:
        # Interactive mode
        interactive_mode()
