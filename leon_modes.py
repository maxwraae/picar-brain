"""
Leon's Custom Modes for PiCar

Fun stuff for a 9-year-old with an AI robot car.
"""

# Messenger mode - Leon sends the car to deliver messages
def messenger_mode(message, target="Mom"):
    """
    Leon tells the car what to say, it drives and delivers the message.

    Example: messenger_mode("I want ice cream", "Dad")
    """
    from picarx import Picarx
    from robot_hat import TTS

    px = Picarx()
    tts = TTS()

    # Announce the mission
    tts.say(f"Leon has sent me with a message for {target}.")

    # Drive forward (toward target)
    px.forward(30)
    import time
    time.sleep(3)
    px.stop()

    # Deliver the message
    tts.say(message)
    tts.say("Leon awaits your response.")

    return "Message delivered"


# Personality modes - different ways the car talks
PERSONALITIES = {
    "butler": "You are a formal British butler. Speak with dignity and slight dry wit.",
    "spy": "You are a secret agent delivering classified intel. Be dramatic and mysterious.",
    "silly": "You are a goofy robot who makes bad puns and laughs at your own jokes.",
    "announcer": "You are a sports announcer. Everything is EXCITING and DRAMATIC!",
}


# Voice commands Leon can use
COMMANDS = {
    "spin": "Do a 360 degree spin",
    "dance": "Do a little dance",
    "find red": "Look for something red and drive toward it",
    "patrol": "Drive around and describe what you see",
    "joke": "Tell a joke",
    "question": "Answer any question using AI",
}
