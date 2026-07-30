import os
import streamlit as st
import configparser

st.set_page_config(layout="wide", page_title="APOLLO OMNI - Settings", page_icon="⚙️")

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');
    
    :root {
      --primary-orange: #ff8c00;
      --surface-black: #0e0e0e;
      --glass-bg: rgba(20, 20, 20, 0.7);
      --glass-border: rgba(255, 140, 0, 0.15);
      --text-color: #e5e2e1;
    }

    /* Core Application Reset */
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: var(--surface-black) !important;
        color: var(--text-color) !important;
        font-family: 'Inter', sans-serif !important;
    }
    [data-testid="stHeader"] { background: transparent !important; border-bottom: none !important; }
    
    /* Typography Global Overrides */
    h1, h2, h3, h4, h5, h6, p, span, label, li, small, div { color: var(--text-color); }
    .font-mono { font-family: 'JetBrains Mono', monospace !important; }

    /* UI Glass Panels */
    .glass-panel {
      background: var(--glass-bg) !important;
      backdrop-filter: blur(12px) !important;
      border: 1px solid var(--glass-border) !important;
      box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37) !important;
      transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.3s ease !important;
      border-radius: 4px !important;
      padding: 24px !important;
      margin-bottom: 20px !important;
    }
    .glass-panel:hover { border-color: rgba(255, 140, 0, 0.4) !important; }
    
    .panel-header {
      font-size: 13px !important;
      font-weight: 700 !important;
      letter-spacing: 0.2em !important;
      color: #a1a1aa !important;
      text-transform: uppercase !important;
      margin-bottom: 20px !important;
      border-bottom: 1px solid rgba(255,255,255,0.05) !important;
      padding-bottom: 12px !important;
      display: flex !important;
      align-items: center !important;
      gap: 8px !important;
    }
    .panel-header::before {
      content: '';
      display: inline-block;
      width: 4px;
      height: 14px;
      background-color: var(--primary-orange);
    }

    /* Input Styling */
    div[data-baseweb="input"] > div {
        background-color: rgba(0,0,0,0.8) !important;
        border: 1px solid var(--glass-border) !important;
    }
    div[data-baseweb="input"] input {
        color: white !important;
        background-color: transparent !important;
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Button Styling */
    .stButton button {
        background: var(--primary-orange) !important;
        color: #000 !important;
        font-size: 13px !important;
        font-weight: 900 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.2em !important;
        border: none !important;
        border-radius: 2px !important;
        padding: 12px 24px !important;
        transition: transform 0.2s, background 0.2s !important;
    }
    .stButton button:hover {
        background: #ff9d2e !important;
        transform: scale(1.02);
    }

    /* Custom Header */
    .omni-header {
        display: flex; align-items: center; justify-content: space-between;
        padding: 16px 32px; background: rgba(0, 0, 0, 0.8);
        backdrop-filter: blur(12px); border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        margin-top: -60px; margin-bottom: 30px; position: sticky; top: 0; z-index: 50;
    }
    .omni-brand { font-size: 20px; font-weight: 700; letter-spacing: 0.2em; color: white; margin:0; line-height: 1.2;}
    .omni-brand span { color: var(--primary-orange); }
    .omni-subtitle { font-size: 10px; color: #71717a; font-family: 'JetBrains Mono', monospace; letter-spacing: 0.1em; text-transform: uppercase; margin:0;}
    .block-container { padding-top: 2rem !important; max-width: 90% !important; }
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="omni-header">
        <div style="display: flex; align-items: center; gap: 24px;">
            <div>
                <h1 class="omni-brand">APOLLO <span>OMNI</span></h1>
                <p class="omni-subtitle">User Preferences & Profile</p>
            </div>
        </div>
        <div style="font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #ff8c00;">
            USER_PROFILE_ACTIVE
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

import json

if "user_prefs" not in st.session_state:
    st.session_state.user_prefs = {
        "full_name": "",
        "university": "Somaiya University",
        "major": "",
        "learning_style": "Visual & Interactive",
        "detail_level": "Intermediate",
        "default_model": "Qwen 3.6 27B (Groq LPU)"
    }

def generate_profile_json(config):
    return json.dumps(config, indent=4)

st.markdown("<p class='font-mono' style='color: #a1a1aa; font-size: 14px; margin-bottom: 24px;'>Customize your learning experience. These settings tailor the AI's responses and generate your unique study profile.</p>", unsafe_allow_html=True)

col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>👤 Student Profile</div>", unsafe_allow_html=True)
    
    st.session_state.user_prefs["full_name"] = st.text_input(
        "Full Name", 
        value=st.session_state.user_prefs["full_name"], 
        placeholder="Enter your name"
    )
    
    st.session_state.user_prefs["university"] = st.text_input(
        "Institution", 
        value=st.session_state.user_prefs["university"],
        disabled=True,
        help="Linked to your secure access token."
    )
    
    st.session_state.user_prefs["major"] = st.text_input(
        "Major / Field of Study", 
        value=st.session_state.user_prefs["major"], 
        placeholder="e.g., Computer Science, Biology"
    )
    st.markdown("</div>", unsafe_allow_html=True)

with col2:
    st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>🧠 AI Learning Preferences</div>", unsafe_allow_html=True)
    
    st.session_state.user_prefs["learning_style"] = st.selectbox(
        "Primary Learning Style", 
        options=["Visual & Interactive", "Text-Heavy & Detailed", "Concise & Bulleted", "Socratic (Questioning)"],
        index=["Visual & Interactive", "Text-Heavy & Detailed", "Concise & Bulleted", "Socratic (Questioning)"].index(st.session_state.user_prefs["learning_style"])
    )
    
    st.session_state.user_prefs["detail_level"] = st.select_slider(
        "Explanation Depth",
        options=["Beginner", "Intermediate", "Advanced", "Expert"],
        value=st.session_state.user_prefs["detail_level"]
    )
    
    st.session_state.user_prefs["default_model"] = st.selectbox(
        "Default Cognitive Engine",
        options=["Qwen 3.6 27B (Groq LPU)", "Meta Llama 3.3 70B (Groq)", "Google Gemma 4 26B (OpenRouter)"],
        index=["Qwen 3.6 27B (Groq LPU)", "Meta Llama 3.3 70B (Groq)", "Google Gemma 4 26B (OpenRouter)"].index(st.session_state.user_prefs["default_model"])
    )
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div class='glass-panel' style='text-align: center;'>", unsafe_allow_html=True)
st.markdown("<div class='panel-header' style='justify-content: center;'>💾 Save & Export Profile</div>", unsafe_allow_html=True)
st.markdown("<p class='font-mono' style='font-size: 12px; color: #a1a1aa;'>Save your personalized learning preferences to apply them globally across APOLLO.</p>", unsafe_allow_html=True)

col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
with col_btn2:
    if st.button("SAVE PREFERENCES", use_container_width=True):
        json_content = generate_profile_json(st.session_state.user_prefs)
        st.success("Profile Updated Successfully!")
        st.download_button(
            label="DOWNLOAD PROFILE (JSON)",
            data=json_content,
            file_name="apollo_user_profile.json",
            mime="application/json",
            use_container_width=True
        )
st.markdown("</div>", unsafe_allow_html=True)
