import logging

logger = logging.getLogger(__name__)


class VoiceIO:
    def __init__(self):
        self.recognizer = None
        self.microphone = None
        self.tts_engine = None
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return True

        try:
            import speech_recognition as sr
            import pyttsx3
        except ImportError:
            logger.warning("Voice dependencies not installed. Install with: pip install pyttsx3 SpeechRecognition")
            return False

        self.recognizer = sr.Recognizer()
        
        try:
            self.microphone = sr.Microphone()
        except AttributeError as e:
            logger.warning(f"Microphone init failed (likely missing pyaudio): {e}")
            return False
        except Exception as e:
            logger.warning(f"Microphone not available: {e}")
            return False

        try:
            self.tts_engine = pyttsx3.init()
            voices = self.tts_engine.getProperty('voices')
            for voice in voices:
                if "male" in voice.name.lower():
                    self.tts_engine.setProperty('voice', voice.id)
                    break
            self.tts_engine.setProperty('rate', 150)
        except Exception as e:
            logger.warning(f"TTS initialization failed: {e}")
            self.tts_engine = None

        self._initialized = True
        return True

    def listen(self, timeout: int = 5) -> str:
        if not self._ensure_initialized():
            logger.error("Voice I/O not available")
            return ""

        import speech_recognition as sr

        try:
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source)
                logger.info("Listening for speech...")
                audio = self.recognizer.listen(source, timeout=timeout)
                text = self.recognizer.recognize_google(audio)
                logger.info(f"Voice input: {text}")
                return text
        except sr.WaitTimeoutError:
            logger.warning("No speech detected (timeout)")
            return ""
        except sr.UnknownValueError:
            logger.warning("Could not understand audio")
            return ""
        except Exception as e:
            logger.error(f"STT error: {e}")
            return ""

    def speak(self, text: str):
        if not self._ensure_initialized():
            logger.error("Voice I/O not available")
            return

        if self.tts_engine is None:
            logger.warning("TTS not available")
            return

        logger.info(f"TTS output: {text}")
        try:
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()
        except Exception as e:
            logger.error(f"TTS error: {e}")

    def is_available(self) -> bool:
        return self._ensure_initialized()
