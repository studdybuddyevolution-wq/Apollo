import os
import json
import streamlit as st
import apollo_theme as theme

PROFILE_PATH = "apollo_user_profile.json"

_DEFAULTS = {
    "full_name": "",
    "university": "Somaiya University",
    "major": "",
    "learning_style": "Visual & Interactive",
    "detail_level": "Intermediate",
    "default_model": "Qwen 3.6 27B (Groq)",
}

_STYLE_CARDS = [
    ("Visual & Interactive", "schema", "Mental models, generated visualizers, and step-by-step intuition before formulas."),
    ("Text-Heavy & Detailed", "menu_book", "Full written explanations with complete context and worked examples."),
    ("Concise & Bulleted", "format_list_bulleted", "High-density bullet summaries and rapid conceptual takeaways."),
    ("Socratic (Questioning)", "forum", "Guided inquiry and questions that test your assumptions as you go."),
]

_DEPTH_PREVIEWS = {
    "Beginner": "Apollo keeps things high-level: plain-language summaries, minimal jargon, no assumed background.",
    "Intermediate": "Apollo balances clarity with substance: core formulas and reasoning, explained plainly.",
    "Advanced": "Apollo goes deeper: full derivations, edge cases, and more rigorous notation.",
    "Expert": "Apollo assumes strong background: dense, technical, research-adjacent explanations.",
}

_MODEL_CARDS = [
    ("Qwen 3.6 27B (Groq)", "bolt", "Fast, general-purpose reasoning and coding. Good default for most questions."),
    ("GPT-OSS 120B (Groq)", "psychology", "Larger open model for tougher multi-step problems and longer context."),
    ("GPT-OSS 20B (Groq)", "speed", "Lighter and quicker — good for short factual questions."),
    ("Groq Compound Mini", "auto_awesome", "Tool-using variant, better when a question benefits from a quick lookup."),
]


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


def _card_container_css():
    c = theme.COLORS
    st.markdown(
        f"""
        <style>
        .apollo-settings-card {{
            background: {c['surface-container-low']};
            border-radius: 14px;
            padding: 18px 20px;
            margin-bottom: 16px;
        }}
        .apollo-settings-header {{
            font-size: 15px; font-weight: 600; color: {c['on-surface']};
            display: flex; align-items: center; gap: 8px; margin-bottom: 2px;
        }}
        .apollo-settings-sub {{
            font-size: 12px; color: {c['on-surface-variant']}; margin-bottom: 14px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_settings_page():
    init_user_prefs()
    theme.inject_theme()
    _card_container_css()

    st.markdown(
        f"""
        <div style="margin-bottom:20px;">
            <div style="font-size:11px;font-weight:600;letter-spacing:0.08em;
                        text-transform:uppercase;color:{theme.COLORS['primary-fixed-dim']};
                        display:flex;align-items:center;gap:6px;margin-bottom:4px;">
                {theme.icon('tune', 15)} Cognitive Configuration
            </div>
            <div style="font-size:22px;font-weight:600;color:{theme.COLORS['on-surface']};">
                Student preferences &amp; AI companion tuning
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Academic identity ---
    st.markdown('<div class="apollo-settings-card">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="apollo-settings-header">{theme.icon("badge")} Academic identity</div>'
        f'<div class="apollo-settings-sub">Determines baseline context and vocabulary tier.</div>',
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.session_state.user_prefs["full_name"] = st.text_input(
            "Full name",
            value=st.session_state.user_prefs.get("full_name", ""),
            placeholder="Enter your name",
        )
        st.session_state.user_prefs["university"] = st.text_input(
            "Institution",
            value=st.session_state.user_prefs.get("university", "Somaiya University"),
            disabled=True,
            help="Linked to your secure access token.",
        )
    with col2:
        st.session_state.user_prefs["major"] = st.text_input(
            "Major / field of study",
            value=st.session_state.user_prefs.get("major", ""),
            placeholder="e.g., Computer Science, Biology",
        )
    st.markdown("</div>", unsafe_allow_html=True)

    # --- Learning style: card picker ---
    st.markdown('<div class="apollo-settings-card">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="apollo-settings-header">{theme.icon("auto_stories")} Cognitive delivery style</div>'
        f'<div class="apollo-settings-sub">Chooses explanation structure and scaffolding.</div>',
        unsafe_allow_html=True,
    )
    curr_style = st.session_state.user_prefs.get("learning_style", "Visual & Interactive")
    style_cols = st.columns(len(_STYLE_CARDS))
    for col, (name, icon_name, desc) in zip(style_cols, _STYLE_CARDS):
        with col:
            is_active = curr_style == name
            st.markdown(
                f'<div style="font-size:12px;color:{theme.COLORS["on-surface-variant"]};'
                f'min-height:70px;">{theme.icon(icon_name, 20, theme.COLORS["primary-fixed-dim"] if is_active else theme.COLORS["outline"])}'
                f'<br><b style="color:{theme.COLORS["on-surface"]};">{name}</b><br>{desc}</div>',
                unsafe_allow_html=True,
            )
            if st.button(
                "Selected" if is_active else "Choose",
                key=f"style_{name}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.user_prefs["learning_style"] = name
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # --- Explanation depth ---
    st.markdown('<div class="apollo-settings-card">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="apollo-settings-header">{theme.icon("equalizer")} Explanation depth</div>'
        f'<div class="apollo-settings-sub">Calibrates how much detail Apollo includes by default.</div>',
        unsafe_allow_html=True,
    )
    st.session_state.user_prefs["detail_level"] = st.select_slider(
        "Explanation depth",
        options=["Beginner", "Intermediate", "Advanced", "Expert"],
        value=st.session_state.user_prefs.get("detail_level", "Intermediate"),
        label_visibility="collapsed",
    )
    _depth = st.session_state.user_prefs["detail_level"]
    st.markdown(
        f'<div style="margin-top:10px;padding:12px 14px;border-radius:10px;'
        f'background:{theme.COLORS["surface-container"]};border-left:3px solid {theme.COLORS["primary-container"]};'
        f'font-size:13px;color:{theme.COLORS["on-surface"]};">{_DEPTH_PREVIEWS[_depth]}</div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # --- Model picker: friendly cards, no raw API/model strings shown elsewhere ---
    st.markdown('<div class="apollo-settings-card">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="apollo-settings-header">{theme.icon("smart_toy")} Cognitive engine</div>'
        f'<div class="apollo-settings-sub">This is the only place the model choice lives — it never appears in the main chat screen.</div>',
        unsafe_allow_html=True,
    )
    curr_model = st.session_state.user_prefs.get("default_model", "Qwen 3.6 27B (Groq)")
    model_cols = st.columns(len(_MODEL_CARDS))
    for col, (name, icon_name, desc) in zip(model_cols, _MODEL_CARDS):
        with col:
            is_active = curr_model == name
            st.markdown(
                f'<div style="font-size:12px;color:{theme.COLORS["on-surface-variant"]};'
                f'min-height:70px;">{theme.icon(icon_name, 20, theme.COLORS["primary-fixed-dim"] if is_active else theme.COLORS["outline"])}'
                f'<br><b style="color:{theme.COLORS["on-surface"]};">{name}</b><br>{desc}</div>',
                unsafe_allow_html=True,
            )
            if st.button(
                "Selected" if is_active else "Choose",
                key=f"model_{name}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.user_prefs["default_model"] = name
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # --- Save ---
    st.markdown('<div class="apollo-settings-card" style="text-align:center;">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="apollo-settings-header" style="justify-content:center;">{theme.icon("save")} Save &amp; export profile</div>',
        unsafe_allow_html=True,
    )
    col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
    with col_btn2:
        if st.button("Save preferences", use_container_width=True, type="primary"):
            json_content = generate_profile_json(st.session_state.user_prefs)
            try:
                with open(PROFILE_PATH, "w", encoding="utf-8") as _wf:
                    _wf.write(json_content)
                st.success("Profile saved and applied.")
            except Exception as _we:
                st.warning(f"Local save failed ({_we}). Use the download button.")
            st.download_button(
                label="Download profile (JSON)",
                data=json_content,
                file_name="apollo_user_profile.json",
                mime="application/json",
                use_container_width=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    st.set_page_config(layout="wide", page_title="APOLLO OMNI - Settings", page_icon="⚙️")
    render_settings_page()
