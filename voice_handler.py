import io
import streamlit as st
from audio_recorder_streamlit import audio_recorder
from groq import Groq

def render_voice_input(api_key: str, key_suffix: str = "default") -> str | None:
    """
    Renders a audio mic recorder button, sends recorded audio to 
    Groq Whisper API, and returns transcribed text.
    """
    st.markdown("<div style='margin-bottom: 8px;'>", unsafe_allow_html=True)
    
    # Render Audio Microphone Button
    audio_bytes = audio_recorder(
        text="Click to Speak",
        recording_color="#ff8c00",
        neutral_color="#a1a1aa",
        icon_name="microphone",
        icon_size="1x",
        key=f"audio_recorder_{key_suffix}"
    )
    st.markdown("</div>", unsafe_allow_html=True)

    if audio_bytes:
        if not api_key or not api_key.startswith("gsk_"):
            st.error("Invalid or missing GROQ_API_KEY for Speech-to-Text.")
            return None

        # Session state key to avoid duplicate processing of the same audio input
        audio_key = f"last_processed_audio_{key_suffix}"
        
        if st.session_state.get(audio_key) != audio_bytes:
            with st.spinner("Transcribing voice command..."):
                try:
                    client = Groq(api_key=api_key.strip())
                    
                    # Convert raw audio bytes into an in-memory file stream
                    audio_file = io.BytesIO(audio_bytes)
                    audio_file.name = "speech_input.wav"

                    # Request transcription using Groq's Whisper model
                    transcription = client.audio.transcriptions.create(
                        file=(audio_file.name, audio_file.read()),
                        model="whisper-large-v3",
                        response_format="text"
                    )
                    
                    # Save state to prevent infinite rerun loops
                    st.session_state[audio_key] = audio_bytes
                    
                    if transcription and str(transcription).strip():
                        return str(transcription).strip()

                except Exception as e:
                    st.error(f"Voice Transcription Error: {str(e)}")
                    return None

    return None
