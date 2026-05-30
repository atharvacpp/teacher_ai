"""
services/tts.py — Text-to-Speech audio generation via gTTS.
"""

import base64
import io


def generate_tts_audio(text: str) -> str | None:
    """
    Convert text to an MP3 audio clip using Google TTS and return it as
    a base64-encoded string.

    Returns None (and logs the error) if TTS fails for any reason, so
    the caller can still return the text response without crashing.
    """
    try:
        from gtts import gTTS

        tts = gTTS(text=text, lang="en", slow=False)

        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)

        return base64.b64encode(fp.read()).decode("utf-8")

    except Exception as exc:
        print(f"[tts] TTS generation failed: {exc}")
        return None
