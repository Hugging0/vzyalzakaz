from __future__ import annotations

import asyncio
from pathlib import Path

from app.config import AppSettings


class VoiceTranscriber:
    """Lazy local speech-to-text for private Telegram onboarding messages."""

    def __init__(self, settings: AppSettings):
        self.settings = settings
        self._model = None
        self._lock = asyncio.Lock()

    async def transcribe(self, audio_path: Path) -> str:
        if not self.settings.voice_transcription_enabled:
            raise RuntimeError("Voice transcription is disabled")
        async with self._lock:
            return await asyncio.to_thread(self._transcribe_sync, audio_path)

    def _transcribe_sync(self, audio_path: Path) -> str:
        if self._model is None:
            from faster_whisper import WhisperModel

            cache_dir = self.settings.voice_transcription_cache_dir
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._model = WhisperModel(
                self.settings.voice_transcription_model,
                device="cpu",
                compute_type="int8",
                download_root=str(cache_dir),
            )
        segments, _ = self._model.transcribe(
            str(audio_path),
            beam_size=5,
            vad_filter=True,
        )
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip())[:6000]
