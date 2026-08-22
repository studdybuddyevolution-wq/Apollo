"""
voice_handler.py — Apollo Omni AI
Handles:
  • Speech-to-Text  : Groq Whisper via audio_recorder_streamlit + Audio File Upload Fallback
  • Text-to-Speech  : Microsoft Edge TTS (edge-tts) — free neural voices
"""

import asyncio
import io
import os
import streamlit as st
from audio_recorder_streamlit import audio_recorder
from groq import Groq


# ---------------------------------------------------------------------------
# SPEECH-TO-TEXT
# ---------------------------------------------------------------------------

def render_voice_input(api_key: str, key_suffix: str = "default") -> str | None:
    """
    Renders a high-visibility microphone recorder widget & audio upload fallback.
    Transcribes spoken voice using Groq Whisper API (whisper-large-v3).

    Returns transcribed text string or None.
    """
    st.markdown(
        """
        <div style="background: rgba(14, 14, 14, 0.85); border: 1px solid rgba(255, 140, 0, 0.3); border-radius: 4px; padding: 12px; margin-bottom: 12px;">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <div style="font-size: 11px; font-weight: 700; color: #ff8c00; font-family: 'JetBrains Mono', monospace; text-transform: uppercase; letter-spacing: 0.1em; display: flex; align-items: center; gap: 6px;">
                    <span>🎙️ VOICE COMMAND RECORDER</span>
                </div>
                <span style="font-size: 9px; font-family: 'JetBrains Mono', monospace; color: #a1a1aa;">Groq Whisper v3</span>
            </div>
        """,
        unsafe_allow_html=True,
    )

    col_mic, col_status = st.columns([1, 3], gap="small")

    audio_bytes = None
    with col_mic:
        st.markdown("<div style='text-align: center; background: rgba(255, 140, 0, 0.05); padding: 6px; border-radius: 4px; border: 1px solid rgba(255,140,0,0.15);'>", unsafe_allow_html=True)
        audio_bytes = audio_recorder(
            text="Record",
            recording_color="#ff8c00",
            neutral_color="#e5e2e1",
            icon_name="microphone",
            icon_size="2x",
            key=f"audio_recorder_{key_suffix}",
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with col_status:
        st.markdown(
            "<p style='font-size: 11px; color: #a1a1aa; margin: 4px 0 0 0; font-family: \"JetBrains Mono\", monospace;'>"
            "Click mic to record your question. Click again to stop & transcribe."
            "</p>",
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)

    # ── 1. Process recorded audio bytes from mic ───────────────────────────
    if audio_bytes:
        if not api_key or not api_key.startswith("gsk_"):
            st.error("❌ Invalid or missing GROQ_API_KEY for Speech-to-Text in Streamlit secrets.")
            return None

        dedup_key = f"last_processed_audio_{key_suffix}"
        if st.session_state.get(dedup_key) == audio_bytes:
            return None

        st.session_state[dedup_key] = audio_bytes

        with st.spinner("⚡ Transcribing audio via Groq Whisper..."):
            audio_file = None
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
                st.session_state[dedup_key] = None
            finally:
                # Explicitly close the BytesIO buffer to free memory
                if audio_file is not None:
                    audio_file.close()

    return None


# ---------------------------------------------------------------------------
# TEXT-TO-SPEECH  (edge-tts — free Microsoft neural voices)
# ---------------------------------------------------------------------------

async def _synthesize_async(text: str, voice: str) -> bytes:
    """Internal async coroutine that streams edge-tts audio into memory."""
    import edge_tts

    communicate = edge_tts.Communicate(text=text, voice=voice)
    audio_chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
    return b"".join(audio_chunks)


def run_tts_synthesis(text: str, voice: str = "en-US-AriaNeural") -> bytes | None:
    """
    Synchronous public wrapper around async edge-tts pipeline.
    Creates an isolated event loop for thread safety.
    Audio is streamed fully into memory (bytes) — no temp files written to disk.
    The returned bytes object is discarded by the caller after st.audio() renders it.
    """
    if not text or not text.strip():
        return None

    text = text.strip()[:4000]

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            mp3_bytes = loop.run_until_complete(_synthesize_async(text, voice))
        finally:
            # Always close the event loop to release OS resources
            loop.close()

        return mp3_bytes if mp3_bytes else None

    except Exception as e:
        st.warning(f"⚠️ TTS synthesis failed: {e}")
        return None
