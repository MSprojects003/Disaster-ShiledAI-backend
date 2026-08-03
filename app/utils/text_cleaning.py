import re
import unicodedata


def clean_text_for_speech(text: str) -> str:
    """Strip markdown, control chars, and other non-speech artifacts before TTS."""
    if not text:
        return ""

    # Normalize unicode (fixes many "garbled character" issues)
    text = unicodedata.normalize("NFC", text)

    # Remove zero-width and control characters
    text = re.sub(r'[\u200B-\u200F\u202A-\u202E\uFEFF]', '', text)
    text = ''.join(ch for ch in text if ch == '\n' or unicodedata.category(ch)[0] != 'C')

    # Strip markdown formatting
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)   # **bold**
    text = re.sub(r'\*([^*]+)\*', r'\1', text)        # *italic*
    text = re.sub(r'`([^`]+)`', r'\1', text)           # `code`
    text = re.sub(r'#{1,6}\s*', '', text)              # # headers
    text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)   # bullet markers
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)  # numbered lists

    # Strip [Simulated] prefix, like the frontend already does
    text = re.sub(r'^\[Simulated\]\s*', '', text, flags=re.IGNORECASE)

    # Strip URLs (TTS reading out full URLs is bad UX anyway)
    text = re.sub(r'https?://\S+', '', text)

    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()