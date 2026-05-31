import os
import threading
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# Optional voice dependencies
_whisper_available = False
_pyttsx3_available = False
_sounddevice_available = False
_numpy_available = False

try:
    import whisper
    _whisper_available = True
except ImportError:
    logger.info("openai-whisper not available. Voice input disabled.")

try:
    import pyttsx3
    _pyttsx3_available = True
except ImportError:
    logger.info("pyttsx3 not available. Voice output disabled.")

try:
    import sounddevice as sd
    _sounddevice_available = True
except ImportError:
    logger.info("sounddevice not available. Microphone input disabled.")

try:
    import numpy as np
    _numpy_available = True
except ImportError:
    logger.info("numpy not available. Audio processing disabled.")


class VoiceInterface:
    """Voice control for AIOS NL Shell (STT + TTS, fully offline)."""

    def __init__(self, whisper_model: str = "base", tts_rate: int = 150):
        self.whisper_model_name = whisper_model
        self.tts_rate = tts_rate
        self._whisper_model = None
        self._tts_engine = None
        self._continuous = False
        self._stop_event = threading.Event()
        self._listen_thread = None

    @property
    def is_available(self) -> bool:
        """True if both microphone and TTS are ready."""
        return _sounddevice_available and (_pyttsx3_available or _whisper_available)

    @property
    def has_microphone(self) -> bool:
        """True if we can record audio."""
        return _sounddevice_available

    def _load_whisper(self):
        """Lazy-load the Whisper model for transcription."""
        if not _whisper_available:
            raise RuntimeError("Whisper is not installed.")
        if self._whisper_model is None:
            logger.info(f"Loading Whisper model '{self.whisper_model_name}'...")
            self._whisper_model = whisper.load_model(self.whisper_model_name)
            logger.info("Whisper model loaded.")
        return self._whisper_model

    def _load_tts(self):
        """Lazy-load the TTS engine."""
        if not _pyttsx3_available:
            raise RuntimeError("pyttsx3 is not installed.")
        if self._tts_engine is None:
            self._tts_engine = pyttsx3.init()
            self._tts_engine.setProperty("rate", self.tts_rate)
        return self._tts_engine

    def listen(self, timeout: int = 10) -> Optional[str]:
        """Records from microphone, transcribes with Whisper, returns text."""
        if not _sounddevice_available:
            logger.warning("No microphone available.")
            return None

        if not _numpy_available:
            logger.warning("numpy not available for audio processing.")
            return None

        fs = 16000  # Whisper expects 16kHz
        duration = timeout

        logger.info(f"Listening for up to {timeout}s...")
        try:
            audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype="float32")
            sd.wait()
        except Exception as e:
            logger.error(f"Microphone recording failed: {e}")
            return None

        # Check if there is actual audio (not just silence)
        max_amp = float(abs(audio).max()) if audio is not None else 0
        if max_amp < 0.01:
            logger.info("No speech detected (silence).")
            return None

        # Transcribe
        try:
            model = self._load_whisper()
            result = model.transcribe(audio.squeeze(), fp16=False)
            text = result.get("text", "").strip()
            logger.info(f"Transcribed: {text}")
            return text if text else None
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            return None

    def speak(self, text: str, speed: float = 1.0) -> None:
        """Converts text to speech and plays it aloud."""
        # Strip markdown-style formatting
        clean = text.replace("**", "").replace("", "").replace("#", "").strip()

        if not clean:
            return

        if not _pyttsx3_available:
            logger.info(f"TTS unavailable, would have said: {clean[:80]}")
            return

        try:
            engine = self._load_tts()
            adjusted_rate = int(self.tts_rate * speed)
            engine.setProperty("rate", adjusted_rate)
            engine.say(clean)
            engine.runAndWait()
        except Exception as e:
            logger.error(f"TTS speak failed: {e}")

    def start_continuous(self, callback: Callable[[str], None]) -> None:
        """Background listener: listens -> transcribes -> calls callback(text)."""
        if self._continuous:
            logger.warning("Continuous listening is already active.")
            return

        self._continuous = True
        self._stop_event.clear()

        def _loop():
            while not self._stop_event.is_set():
                text = self.listen(timeout=5)
                if text:
                    callback(text)
                # Small pause between recordings
                self._stop_event.wait(0.5)

        self._listen_thread = threading.Thread(target=_loop, daemon=True)
        self._listen_thread.start()
        logger.info("Continuous voice listening started.")

    def stop_continuous(self) -> None:
        """Stops the background listening loop."""
        self._stop_event.set()
        self._continuous = False
        if self._listen_thread:
            self._listen_thread.join(timeout=3)
            self._listen_thread = None
        logger.info("Continuous voice listening stopped.")
