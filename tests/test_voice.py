import pytest
from jarvis.core.voice import VoiceIO


def test_voice_io_initializes():
    voice = VoiceIO()
    assert voice.recognizer is None
    assert voice.tts_engine is None
    assert voice._initialized is False


def test_is_available_returns_bool():
    voice = VoiceIO()
    result = voice.is_available()
    assert isinstance(result, bool)


def test_listen_returns_string():
    voice = VoiceIO()
    result = voice.listen(timeout=1)
    assert isinstance(result, str)


def test_speak_does_not_raise():
    voice = VoiceIO()
    voice.speak("Test message")
