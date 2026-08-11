"""
Voice I/O — Speech-to-Text (Whisper) and Text-to-Speech.
Supports local Whisper via API or OpenAI Whisper API.
"""

import os
import logging
from pathlib import Path

import httpx

from hive.core.config import settings

logger = logging.getLogger(__name__)


async def transcribe(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """Transcribe audio to text using OpenAI Whisper API or local Whisper.

    Set OPENAI_API_KEY for cloud Whisper, or install local whisper package.
    """
    if settings.OPENAI_API_KEY:
        return await _transcribe_openai(audio_bytes, filename)
    return await _transcribe_local(audio_bytes)


async def _transcribe_openai(audio_bytes: bytes, filename: str) -> str:
    """Transcribe using OpenAI Whisper API."""
    url = f"{settings.OPENAI_BASE_URL}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}

    # multipart form data
    files = {"file": (filename, audio_bytes, "audio/wav")}
    data = {"model": "whisper-1"}

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, files=files, data=data, headers=headers)
        resp.raise_for_status()
        return resp.json()["text"]


async def _transcribe_local(audio_bytes: bytes) -> str:
    """Transcribe using local Whisper (if installed)."""
    try:
        import whisper
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            f.flush()
            model = whisper.load_model("base")
            result = model.transcribe(f.name)
            Path(f.name).unlink()
            return result["text"]
    except ImportError:
        return "Error: Whisper not installed. Set OPENAI_API_KEY for cloud Whisper or run: pip install openai-whisper"


async def synthesize(text: str, voice: str = "alloy") -> bytes:
    """Convert text to speech audio bytes.

    Uses OpenAI TTS API. Set OPENAI_API_KEY.
    """
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY required for text-to-speech")

    url = f"{settings.OPENAI_BASE_URL}/audio/speech"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "tts-1",
        "input": text,
        "voice": voice,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.content
