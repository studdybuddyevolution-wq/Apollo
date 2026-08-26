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
        audio_bytes = audio_recorder(
            text="Record",
            recording_color="#ff8c00",
            neutral_color="#e5e2e1",
            icon_name="microphone",
            icon_size="2x",
            key=f"audio_recorder_{key_suffix}",
        )

    with col_status:
        st.markdown(
            "<p style='font-size: 11px; color: #a1a1aa; margin: 4px 0 0 0; font-family: \"JetBrains Mono\", monospace;'>"
            "Click mic to record your question. Click again to stop & transcribe."
            "</p>",
            unsafe_allow_html=True,
        )

    # Audio file upload fallback (useful if browser blocks mic or component fails)
    uploaded_audio = st.file_uploader(
        "Or upload audio file (.mp3, .wav, .m4a)",
        type=["wav", "mp3", "m4a", "ogg"],
        key=f"audio_upload_{key_suffix}",
        label_visibility="collapsed",
    )

    st.markdown("</div>", unsafe_allow_html=True)

    # Pick up bytes from mic or uploaded file
    target_bytes = None
    file_name = "speech_input.wav"

    if audio_bytes:
        target_bytes = audio_bytes
        dedup_key = f"last_processed_audio_{key_suffix}"
        if st.session_state.get(dedup_key) == target_bytes:
            return None
        st.session_state[dedup_key] = target_bytes

    elif uploaded_audio:
        target_bytes = uploaded_audio.read()
        file_name = uploaded_audio.name
        dedup_key = f"last_processed_file_{key_suffix}"
        if st.session_state.get(dedup_key) == uploaded_audio.name:
            return None
        st.session_state[dedup_key] = uploaded_audio.name

    # ── Process audio bytes via Groq Whisper ───────────────────────────
    if target_bytes:
        if not api_key or not api_key.startswith("gsk_"):
            st.error("❌ Invalid or missing GROQ_API_KEY for Speech-to-Text in Streamlit secrets.")
            return None

        with st.spinner("⚡ Transcribing audio via Groq Whisper..."):
            audio_file = None
            try:
                client = Groq(api_key=api_key.strip())
                audio_file = io.BytesIO(target_bytes)
                audio_file.name = file_name

                transcription = None
                for whisper_model in ["whisper-large-v3-turbo", "whisper-large-v3"]:
                    try:
                        audio_file.seek(0)
                        transcription = client.audio.transcriptions.create(
                            file=(audio_file.name, audio_file.read()),
                            model=whisper_model,
                            response_format="text",
                        )
                        if transcription:
                            break
                    except Exception:
                        continue

                result = str(transcription).strip() if transcription else ""
                if result:
                    return result

            except Exception as e:
                st.error(f"Voice Transcription Error: {e}")
            finally:
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
            loop.close()

        return mp3_bytes if mp3_bytes else None

    except Exception as e:
        st.warning(f"⚠️ TTS synthesis failed: {e}")
        return None



