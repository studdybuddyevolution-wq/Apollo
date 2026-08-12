"""
voice_handler.py — Apollo Omni AI
Handles:
  • Speech-to-Text  : Groq Whisper via audio_recorder_streamlit
  • Text-to-Speech  : Microsoft Edge TTS (edge-tts) — free neural voices
"""

import asyncio
import io
import tempfile
import os
import streamlit as st
from audio_recorder_streamlit import audio_recorder
from groq import Groq


# ---------------------------------------------------------------------------
# SPEECH-TO-TEXT
# ---------------------------------------------------------------------------

def render_voice_input(api_key: str, key_suffix: str = "default") -> str | None:
    """
    Renders a mic recorder button.  When audio is captured it is sent to the
    Groq Whisper API for transcription.

    Bug-fix over original:
      The dedup key is written to session_state BEFORE the API call so that
      even if st.rerun() fires inside a downstream widget, the same audio
      bytes are never submitted twice (eliminates ghost-transcription loops).

    Returns the transcribed string, or None.
    """
    st.markdown("<div style='margin-bottom: 8px;'>", unsafe_allow_html=True)

    audio_bytes = audio_recorder(
        text="Click to Speak",
        recording_color="#ff8c00",
        neutral_color="#a1a1aa",
        icon_name="microphone",
        icon_size="1x",
        key=f"audio_recorder_{key_suffix}",
    )

    st.markdown("</div>", unsafe_allow_html=True)

    if not audio_bytes:
        return None

    if not api_key or not api_key.startswith("gsk_"):
        st.error("Invalid or missing GROQ_API_KEY for Speech-to-Text.")
        return None

    # --- DEDUP GUARD (key saved BEFORE API call to prevent rerun loops) ---
    dedup_key = f"last_processed_audio_{key_suffix}"
    if st.session_state.get(dedup_key) == audio_bytes:
        # Exact same bytes already processed — skip silently
        return None

    # Mark as "in-flight" immediately so reruns are blocked
    st.session_state[dedup_key] = audio_bytes

    with st.spinner("Transcribing voice command..."):
        try:
            client = Groq(api_key=api_key.strip())
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "speech_input.wav"

            transcription = client.audio.transcriptions.create(
                file=(audio_file.name, audio_file.read()),
                model="whisper-large-v3",
                response_format="text",
            )

            result = str(transcription).strip() if transcription else ""
            if result:
                return result

        except Exception as e:
            st.error(f"Voice Transcription Error: {e}")
            # On failure reset dedup so the user can retry
            st.session_state[dedup_key] = None

    return None


# ---------------------------------------------------------------------------
# TEXT-TO-SPEECH  (edge-tts — free Microsoft neural voices)
# ---------------------------------------------------------------------------

async def _synthesize_async(text: str, voice: str) -> bytes:
    """
    Internal async coroutine that streams edge-tts audio into memory.
    Returns raw MP3 bytes.
    """
    import edge_tts  # imported lazily so the app still loads if pkg missing

    communicate = edge_tts.Communicate(text=text, voice=voice)
    audio_chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
    return b"".join(audio_chunks)


def run_tts_synthesis(text: str, voice: str = "en-US-AriaNeural") -> bytes | None:
    """
    Synchronous public wrapper around the async edge-tts pipeline.

    Safe to call from Streamlit's main thread — creates its own event loop
    so it never conflicts with any existing loop.

    Args:
        text  : The string to synthesize.
        voice : Any valid edge-tts voice name.
                Defaults to en-US-AriaNeural (natural female voice).

    Returns:
        Raw MP3 bytes, or None on failure.
    """
    if not text or not text.strip():
        return None

    # Truncate extremely long texts to avoid hitting edge-tts size limits
    text = text.strip()[:4000]

    try:
        # Always spin a fresh loop — avoids "event loop already running" errors
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            mp3_bytes = loop.run_until_complete(_synthesize_async(text, voice))
        finally:
            loop.close()

        return mp3_bytes if mp3_bytes else None

    except Exception as e:
        # Non-fatal — TTS is a progressive enhancement, not a hard requirement
        st.warning(f"⚠️ TTS synthesis failed: {e}")
        return None
