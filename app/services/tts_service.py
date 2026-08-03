import os
import asyncio
import logging
import requests
import edge_tts

logger = logging.getLogger(__name__)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

EDGE_VOICE_MAP = {
    "si": "si-LK-ThiliniNeural",
    "ta": "ta-IN-PallaviNeural",
    "en": "en-US-AriaNeural",
}

# Languages ElevenLabs cannot speak natively — route these to edge-tts instead
FREE_TTS_LANGUAGES = {"si"}


def _synthesize_elevenlabs(text: str) -> bytes:
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not configured")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL_ID,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"ElevenLabs TTS failed: {resp.status_code} {resp.text}")
    return resp.content


async def _synthesize_edge_tts_async(text: str, language: str) -> bytes:
    voice = EDGE_VOICE_MAP.get(language, EDGE_VOICE_MAP["en"])
    communicate = edge_tts.Communicate(text, voice)
    chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


def _synthesize_edge_tts(text: str, language: str) -> bytes:
    return asyncio.run(_synthesize_edge_tts_async(text, language))


def synthesize_speech(text: str, language: str) -> bytes:
    """Route to the right TTS engine based on language, return MP3 bytes."""
    if language in FREE_TTS_LANGUAGES:
        logger.info(f"Using edge-tts for language={language}")
        return _synthesize_edge_tts(text, language)

    try:
        logger.info(f"Using ElevenLabs for language={language}")
        return _synthesize_elevenlabs(text)
    except Exception as e:
        logger.warning(f"ElevenLabs failed ({e}), falling back to edge-tts")
        return _synthesize_edge_tts(text, language)