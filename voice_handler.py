import os
import tempfile
import streamlit as st
from groq import Groq

def transcribe_audio_bytes(audio_bytes: bytes, groq_api_key: str) -> tuple[str | None, str | None]:
    """
    Sends raw audio bytes to Groq Whisper API for transcription.
    Returns (transcribed_text, error_message).
    """
    if not groq_api_key or not groq_api_key.startswith("gsk_"):
        return None, "Invalid or missing GROQ_API_KEY."

    try:
        client = Groq(api_key=groq_api_key)
        
        # Write bytes to a temporary file required by the Groq SDK
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(audio_bytes)
            tmp_path = tmp_file.name

        with open(tmp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=(tmp_path, audio_file.read()),
                model="whisper-large-v3-turbo",
                response_format="json",
                temperature=0.0
            )

        # Cleanup temporary audio file
        os.unlink(tmp_path)
        return transcription.text, None

    except Exception as e:
        return None, str(e)


def render_voice_input(groq_api_key: str, key_suffix: str = "main") -> str | None:
    """
    Renders the UI microphone component and returns the transcribed text string
    if new audio was recorded, otherwise returns None.
    """
    st.markdown("##### 🎙️ Voice Command")
    audio_data = st.audio_input("Record voice input", key=f"mic_{key_suffix}")

    if "last_processed_audio_hash" not in st.session_state:
        st.session_state.last_processed_audio_hash = None

    if audio_data:
        audio_bytes = audio_data.getvalue()
        current_hash = hash(audio_bytes)

        # Avoid re-processing the same recording on Streamlit re-renders
        if st.session_state.last_processed_audio_hash != current_hash:
            with st.spinner("Transcribing voice via Groq Whisper..."):
                text, err = transcribe_audio_bytes(audio_bytes, groq_api_key)
                if text:
                    st.session_state.last_processed_audio_hash = current_hash
                    st.success(f"Transcribed: \"{text}\"")
                    return text
                else:
                    st.error(f"Voice Transcription Error: {err}")

    return None
