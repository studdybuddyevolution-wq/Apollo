import os
import json
import streamlit as st

PROFILE_PATH = "apollo_user_profile.json"

_DEFAULTS = {
    "full_name": "",
    "university": "Somaiya University",
    "major": "",
    "learning_style": "Visual & Interactive",
    "detail_level": "Intermediate",
    "default_model": "Qwen 3.6 27B (Groq)"
}

def generate_profile_json(config):
    return json.dumps(config, indent=4)

def init_user_prefs():
    if "user_prefs" not in st.session_state:
        if os.path.exists(PROFILE_PATH):
            try:
                with open(PROFILE_PATH, "r", encoding="utf-8") as _f:
                    _loaded = json.load(_f)
                st.session_state.user_prefs = {**_DEFAULTS, **_loaded}
            except Exception:
                st.session_state.user_prefs = dict(_DEFAULTS)
        else:
            st.session_state.user_prefs = dict(_DEFAULTS)

def render_settings_page():
    init_user_prefs()

    st.markdown(
        """
        <div style="background: rgba(20, 20, 20, 0.8); border: 1px solid rgba(255, 140, 0, 0.2); padding: 16px 24px; border-radius: 4px; margin-bottom: 24px; display: flex; justify-content: space-between; align-align: center;">
            <div>
                <h2 style="font-size: 20px; font-weight: 700; letter-spacing: 0.15em; color: white; margin: 0;">APOLLO <span style="color: #ff8c00;">OMNI</span> — USER PREFERENCES</h2>
                <p style="font-size: 11px; color: #a1a1aa; font-family: 'JetBrains Mono', monospace; margin: 4px 0 0 0;">Tailor your AI cognitive engine, learning style, and student profile.</p>
            </div>
            <div style="font-size: 11px; font-weight: 700; color: #ff8c00; letter-spacing: 0.1em; align-self: center;">
                USER_PROFILE_ACTIVE
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
        st.markdown("<div class='panel-header'>👤 Student Profile</div>", unsafe_allow_html=True)

        st.session_state.user_prefs["full_name"] = st.text_input(
            "Full Name",
            value=st.session_state.user_prefs.get("full_name", ""),
            placeholder="Enter your name"
        )

        st.session_state.user_prefs["university"] = st.text_input(
            "Institution",
            value=st.session_state.user_prefs.get("university", "Somaiya University"),
            disabled=True,
            help="Linked to your secure access token."
        )

        st.session_state.user_prefs["major"] = st.text_input(
            "Major / Field of Study",
            value=st.session_state.user_prefs.get("major", ""),
            placeholder="e.g., Computer Science, Biology"
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
        st.markdown("<div class='panel-header'>🧠 AI Learning Preferences</div>", unsafe_allow_html=True)

        styles = ["Visual & Interactive", "Text-Heavy & Detailed", "Concise & Bulleted", "Socratic (Questioning)"]
        curr_style = st.session_state.user_prefs.get("learning_style", "Visual & Interactive")
        idx_style = styles.index(curr_style) if curr_style in styles else 0

        st.session_state.user_prefs["learning_style"] = st.selectbox(
            "Primary Learning Style",
            options=styles,
            index=idx_style
        )

        st.session_state.user_prefs["detail_level"] = st.select_slider(
            "Explanation Depth",
            options=["Beginner", "Intermediate", "Advanced", "Expert"],
            value=st.session_state.user_prefs.get("detail_level", "Intermediate")
        )

        models = [
            "Qwen 3.6 27B (Groq)",
            "GPT-OSS 120B (Groq)",
            "GPT-OSS 20B (Groq)",
            "Llama 3.3 70B (Groq)",
            "Groq Compound Mini",
            "Gemini 3.6 Flash (Google)",
            "Gemini 2.5 Flash (Google)",
            "Gemini 2.5 Flash-Lite (Google)",
        ]
        curr_model = st.session_state.user_prefs.get("default_model", "Qwen 3.6 27B (Groq)")
        idx_model = models.index(curr_model) if curr_model in models else 0

        st.session_state.user_prefs["default_model"] = st.selectbox(
            "Default Cognitive Engine",
            options=models,
            index=idx_model
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='glass-panel' style='text-align: center;'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header' style='justify-content: center;'>💾 Save & Export Profile</div>", unsafe_allow_html=True)
    st.markdown("<p class='font-mono' style='font-size: 12px; color: #a1a1aa;'>Save your personalized learning preferences to apply them globally across APOLLO.</p>", unsafe_allow_html=True)

    col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
    with col_btn2:
        if st.button("SAVE PREFERENCES", use_container_width=True):
            json_content = generate_profile_json(st.session_state.user_prefs)
            try:
                with open(PROFILE_PATH, "w", encoding="utf-8") as _wf:
                    _wf.write(json_content)
                st.success("✅ Profile saved locally & applied globally!")
            except Exception as _we:
                st.warning(f"Local save failed ({_we}). Use download button.")
            st.download_button(
                label="DOWNLOAD PROFILE (JSON)",
                data=json_content,
                file_name="apollo_user_profile.json",
                mime="application/json",
                use_container_width=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="APOLLO OMNI - Settings", page_icon="⚙️")
    render_settings_page()
