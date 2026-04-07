from jarvis.ui.display import Display
from jarvis.core.voice import VoiceIO


def run_voice_query() -> str:
    Display.status("Listening...")

    voice = VoiceIO()

    if not voice.is_available():
        Display.warning("Voice not available. Please type your request.")
        return ""

    user_input = voice.listen(timeout=5)

    if not user_input:
        Display.warning("No speech detected. Try again or type your request.")
        return ""

    Display.status("Processing...")

    return user_input
