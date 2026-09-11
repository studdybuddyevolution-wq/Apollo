"""
apollo_theme.py — Apollo Omni AI: Shared visual design system

Ports the color tokens, typography, and component look from the approved
Stitch mockups into the real app. This module ONLY changes appearance —
it injects CSS/fonts and provides small HTML-snippet helpers. It never
touches session_state, business logic, or API calls, so it is safe to
drop into streamlit_app.py without risking existing functionality.

Usage:
    import apollo_theme
    apollo_theme.inject_theme()   # call once, right after st.set_page_config

    st.markdown(apollo_theme.icon("auto_stories") + " Notebook Suite",
                unsafe_allow_html=True)
"""

import textwrap

import streamlit as st

# ---------------------------------------------------------------------------
# COLOR TOKENS — copied verbatim from the approved Stitch dark-mode config
# so the real app matches pixel-for-pixel, not just "close enough".
# ---------------------------------------------------------------------------
COLORS = {
    "primary": "#ffb690",
    "primary-container": "#f97316",
    "on-primary": "#552100",
    "on-primary-container": "#582200",
    "primary-fixed-dim": "#ffb690",
    "secondary": "#adc6ff",
    "secondary-container": "#0566d9",
    "on-secondary-container": "#e6ecff",
    "tertiary": "#4edea3",
    "tertiary-container": "#00b07a",
    "on-tertiary-container": "#003b26",
    "error": "#ffb4ab",
    "error-container": "#93000a",
    "on-error-container": "#ffdad6",
    "surface": "#12131a",
    "surface-dim": "#12131a",
    "surface-bright": "#383941",
    "surface-container-lowest": "#0d0e15",
    "surface-container-low": "#1a1b22",
    "surface-container": "#1e1f26",
    "surface-container-high": "#292931",
    "surface-container-highest": "#33343c",
    "surface-variant": "#33343c",
    "on-surface": "#e3e1ec",
    "on-surface-variant": "#e0c0b1",
    "outline": "#a78b7d",
    "outline-variant": "#584237",
    "background": "#12131a",
    "on-background": "#e3e1ec",
}


def inject_theme():
    """Call once, right after st.set_page_config(). Injects fonts + CSS
    that re-skins Streamlit's own widgets to match the Stitch mockups —
    no existing st.button/st.chat_message/st.radio/etc. calls need to
    change for this to take effect."""
    c = COLORS
    css = f"""
    <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200"
          rel="stylesheet"/>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"/>
    <style>
    .material-symbols-outlined {{
        font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 20;
        vertical-align: -4px;
    }}

    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
    }}

    .stApp {{
        background: {c['background']};
    }}

    section[data-testid="stSidebar"] {{
        background: {c['surface-container-lowest']};
        border-right: 1px solid {c['surface-container-high']}66;
    }}

    /* ---- Buttons ---- */
    .stButton > button {{
        border-radius: 10px !important;
        border: 1px solid {c['surface-container-high']} !important;
        background: {c['surface-container']} !important;
        color: {c['on-surface']} !important;
        font-weight: 500 !important;
        transition: all 0.15s ease;
    }}
    .stButton > button:hover {{
        background: {c['surface-container-high']} !important;
        border-color: {c['primary-container']}88 !important;
    }}
    .stButton > button[kind="primary"] {{
        background: {c['primary-container']} !important;
        border-color: {c['primary-container']} !important;
        color: {c['on-primary-container']} !important;
        font-weight: 600 !important;
    }}

    /* ---- Nav radio, restyled as a vertical module list ---- */
    div[role="radiogroup"] {{
        display: flex; flex-direction: column; gap: 2px;
    }}
    div[role="radiogroup"] label {{
        border-radius: 10px !important;
        padding: 8px 10px !important;
        color: {c['on-surface-variant']} !important;
    }}
    div[role="radiogroup"] label:has(input:checked) {{
        background: {c['primary-container']}26 !important;
        color: {c['primary-fixed-dim']} !important;
        font-weight: 600 !important;
    }}

    /* ---- Chat bubbles (st.chat_message) ---- */
    div[data-testid="stChatMessage"] {{
        background: {c['surface-container']} !important;
        border: 1px solid {c['surface-container-high']}66 !important;
        border-radius: 16px !important;
        padding: 4px 6px !important;
    }}

    /* ---- Popovers (settings, photo, grading, mic, past chats) ---- */
    div[data-testid="stPopoverBody"] {{
        background: {c['surface-container']} !important;
        border: 1px solid {c['surface-container-high']} !important;
        border-radius: 14px !important;
    }}

    /* ---- Expanders ---- */
    div[data-testid="stExpander"] {{
        border: 1px solid {c['surface-container-high']}66 !important;
        border-radius: 12px !important;
        background: {c['surface-container-low']} !important;
    }}

    /* ---- Text inputs / selects ---- */
    div[data-baseweb="select"] > div, .stTextInput input, .stTextArea textarea {{
        background: {c['surface-container']} !important;
        border-color: {c['surface-container-high']} !important;
        color: {c['on-surface']} !important;
        border-radius: 10px !important;
    }}

    #MainMenu, footer {{ visibility: hidden; }}
    </style>
    """
    st.html(textwrap.dedent(css))


def icon(name: str, size: int = 18, color: str = None) -> str:
    """Returns a Material Symbols icon span for embedding inline in
    st.markdown(..., unsafe_allow_html=True) calls."""
    style = f"font-size:{size}px;"
    if color:
        style += f"color:{color};"
    return f'<span class="material-symbols-outlined" style="{style}">{name}</span>'


def citation_pill(label: str) -> str:
    c = COLORS
    return (
        f'<span style="display:inline-flex;align-items:center;gap:4px;'
        f'padding:3px 10px;border-radius:999px;font-size:11px;'
        f'background:{c["primary-container"]}1a;color:{c["primary-fixed-dim"]};'
        f'border:1px solid {c["primary-container"]}4d;margin-right:4px;">'
        f'{icon("auto_stories", 13)} {label}</span>'
    )


def notebook_pill_html(title: str, count: int, active: bool) -> str:
    c = COLORS
    if active:
        style = (
            f'background:{c["surface-container"]};border-left:3px solid {c["primary-container"]};'
        )
        text_color = c["on-surface"]
    else:
        style = "border-left:3px solid transparent;"
        text_color = c["on-surface-variant"]
    return (
        f'<div style="{style}padding:8px 10px 8px 8px;border-radius:8px;'
        f'display:flex;justify-content:space-between;align-items:center;margin-bottom:2px;">'
        f'<span style="color:{text_color};font-size:13px;">{icon("auto_stories", 15)} {title}</span>'
        f'<span style="font-size:10px;color:{c["outline"]};">{count} src</span></div>'
    )


def source_chip_html(icon_name: str, name: str, meta: str) -> str:
    c = COLORS
    return (
        f'<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;'
        f'border-radius:8px;background:{c["surface-container-low"]};margin-bottom:4px;">'
        f'{icon(icon_name, 16, c["outline"])}'
        f'<div><div style="font-size:12px;color:{c["on-surface"]};">{name}</div>'
        f'<div style="font-size:10px;color:{c["outline"]};">{meta}</div></div></div>'
    )
