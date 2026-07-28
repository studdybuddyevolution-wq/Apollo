import json
import time
from pathlib import Path

import extra_streamlit_components as stx
import streamlit as st
from PIL import Image

from auth import AUTH_COOKIE_NAME, get_secret, require_authentication
from llm_service import (
    MODEL_OPTIONS,
    generate_llm_stream,
    generate_slides_with_gemini,
    generate_slides_with_qwen,
)
from ppt_engine import THEMES, build_presentation, normalize_slides
from rag_engine import process_and_index_files


st.set_page_config(layout="wide", page_title="APOLLO OMNI AI", page_icon="⚡")

GROQ_API_KEY = get_secret("GROQ_API_KEY")
OPENROUTER_API_KEY = get_secret("OPENROUTER_API_KEY")
GEMINI_API_KEY = get_secret("GEMINI_API_KEY")


DEFAULT_SLIDES = [
    {
        "title": "Commercial AI Strategy Snapshot",
        "subtitle": "A polished starter deck structure you can replace with any topic.",
        "topic_tag": "Example",
        "image_keyword": "enterprise AI strategy",
        "cards": [
            {
                "heading": "Audience problem",
                "body": "Frame the business pressure, user need, or technical challenge that makes the topic urgent.",
            },
            {
                "heading": "Strategic response",
                "body": "Explain the core idea in direct language and show how it changes decisions or workflows.",
            },
            {
                "heading": "Measurable outcome",
                "body": "Close with the most important metric, operating signal, or next step.",
            },
        ],
        "speaker_notes": "Use this opener to establish the audience problem, then preview how the deck will move from context to action.",
    }
]


def init_session_state() -> None:
    defaults = {
        "vector_db": None,
        "chat_history": [],
        "response_time": "0.00s",
        "source_reference": "<div class='source-box font-mono'>Awaiting local context...</div>",
        "node_count": 0,
        "otp_sent": False,
        "generated_otp": None,
        "user_email": "",
        "slides_data": DEFAULT_SLIDES.copy(),
        "generated_pptx_path": "",
        "last_pptx_name": "Gamma_Style_Presentation.pptx",
    }
    # Safely set default session state variables
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def safe_filename(topic: str) -> str:
    stem = "".join(ch if ch.isalnum() else "_" for ch in topic.strip())[:54].strip("_")
    return f"{stem or 'Gamma_Style_Presentation'}.pptx"


def build_deck_with_status(topic: str, theme_name: str, provider: str):
    content_label = (
        "🧠 Generating slide content & speaker notes with Qwen..."
        if provider == "qwen"
        else "🧠 Generating slide content & speaker notes with Gemini..."
    )
    with st.status(content_label, expanded=True) as status:
        generator = generate_slides_with_qwen if provider == "qwen" else generate_slides_with_gemini
        api_key = GROQ_API_KEY if provider == "qwen" else GEMINI_API_KEY
        slides, message = generator(topic, api_key)
        if not slides:
            status.update(label="Slide generation failed.", state="error")
            st.error(message)
            return

        st.session_state.slides_data = slides
        st.write(f"Generated {len(slides)} slides with speaker notes.")

        def deck_progress(stage: str, detail: str) -> None:
            if stage == "visuals":
                status.update(label="🎨 Rendering Pollinations AI visuals & photo assets...", state="running")
            elif stage == "layout":
                status.update(label="📐 Applying widescreen layouts & dynamic text auto-scaling...", state="running")
            st.write(detail)

        pptx_path = build_presentation(
            slides,
            theme_name=theme_name,
            topic=topic,
            progress_callback=deck_progress,
        )
        st.session_state.generated_pptx_path = pptx_path
        st.session_state.last_pptx_name = safe_filename(topic)
        status.update(label="✅ Presentation ready for download!", state="complete")


def build_edited_deck_with_status(topic: str, theme_name: str) -> None:
    with st.status("🎨 Rendering Pollinations AI visuals & photo assets...", expanded=True) as status:
        def deck_progress(stage: str, detail: str) -> None:
            if stage == "layout":
                status.update(label="📐 Applying widescreen layouts & dynamic text auto-scaling...", state="running")
            elif stage == "visuals":
                status.update(label="🎨 Rendering Pollinations AI visuals & photo assets...", state="running")
            st.write(detail)

        pptx_path = build_presentation(
            st.session_state.slides_data,
            theme_name=theme_name,
            topic=topic or "Edited presentation",
            progress_callback=deck_progress,
        )
        st.session_state.generated_pptx_path = pptx_path
        st.session_state.last_pptx_name = safe_filename(topic or "Edited presentation")
        status.update(label="✅ Presentation ready for download!", state="complete")


def render_download_button() -> None:
    pptx_path = st.session_state.get("generated_pptx_path")
    if not pptx_path or not Path(pptx_path).exists():
        return
    with open(pptx_path, "rb") as file:
        st.download_button(
            "Download presentation",
            data=file.read(),
            file_name=st.session_state.get("last_pptx_name", "Gamma_Style_Presentation.pptx"),
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            use_container_width=True,
        )


def render_slide_editor() -> None:
    slides = normalize_slides(st.session_state.slides_data)
    st.session_state.slides_data = slides or DEFAULT_SLIDES.copy()
    tabs = st.tabs([f"Slide {i + 1}" for i in range(len(st.session_state.slides_data))])

    for i, tab in enumerate(tabs):
        with tab:
            slide = st.session_state.slides_data[i]
            slide["title"] = st.text_input("Title", slide.get("title", ""), key=f"title_{i}")
            slide["subtitle"] = st.text_area("Subtitle", slide.get("subtitle", ""), key=f"subtitle_{i}", height=70)
            cols = st.columns(2)
            with cols[0]:
                slide["topic_tag"] = st.text_input("Topic tag", slide.get("topic_tag", ""), key=f"tag_{i}")
            with cols[1]:
                slide["image_keyword"] = st.text_input("Image keyword", slide.get("image_keyword", ""), key=f"image_{i}")

            cards = slide.get("cards") or []
            for j, card in enumerate(cards):
                st.markdown(f"**Card {j + 1}**")
                card["heading"] = st.text_input("Heading", card.get("heading", ""), key=f"heading_{i}_{j}")
                card["body"] = st.text_area("Body", card.get("body", ""), key=f"body_{i}_{j}", height=80)

            chart_text = json.dumps(slide.get("chart") or {}, indent=2)
            chart_json = st.text_area("Optional chart JSON", chart_text, key=f"chart_{i}", height=140)
            try:
                parsed_chart = json.loads(chart_json) if chart_json.strip() else {}
                slide["chart"] = parsed_chart or None
            except Exception:
                st.caption("Chart JSON is invalid, so the previous chart data will be kept.")

            slide["speaker_notes"] = st.text_area(
                "Speaker notes",
                slide.get("speaker_notes", ""),
                key=f"notes_{i}",
                height=120,
            )


def render_css() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

:root {
    --background-color: #0f0f11 !important;
    --secondary-background-color: rgba(24, 24, 27, 0.82) !important;
    --text-color: #e5e7eb !important;
    --primary-color: #f97316 !important;
}

.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background-color: #0f0f11 !important;
    background-image:
        linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px) !important;
    background-size: 20px 20px !important;
    color: #e5e7eb !important;
    font-family: 'Inter', sans-serif !important;
}

h1, h2, h3, h4, h5, h6, p, span, label, li, small, div {
    color: #e5e7eb !important;
}

.font-mono { font-family: 'JetBrains Mono', monospace !important; }

.header-bar {
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    background: rgba(24, 24, 27, 0.82);
    backdrop-filter: blur(12px);
    padding: 10px 24px;
    margin-top: -56px;
    margin-bottom: 26px;
    border-radius: 0 0 10px 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.status-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    background: rgba(34, 197, 94, 0.1);
    color: #4ade80 !important;
    border: 1px solid rgba(34, 197, 94, 0.22);
    padding: 5px 10px;
    border-radius: 5px;
}

.cyber-card {
    background: rgba(24, 24, 27, 0.82) !important;
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255, 255, 255, 0.11) !important;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 20px;
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.18);
}

.panel-header {
    font-size: 0.82rem;
    font-weight: 700;
    letter-spacing: 0.055em;
    color: #d4d4d8 !important;
    text-transform: uppercase;
    margin-bottom: 14px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    padding-bottom: 8px;
}

.metric-value {
    font-size: 1.85rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    color: #fff !important;
}

.metric-title {
    font-size: 0.72rem;
    color: #a1a1aa !important;
    text-transform: uppercase;
    font-family: 'JetBrains Mono', monospace;
    margin-bottom: 4px;
}

.source-box {
    background: #060608 !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    padding: 12px !important;
    border-radius: 6px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.8rem !important;
    color: #a1a1aa !important;
    overflow-x: auto;
    max-height: 350px;
}

.stButton button {
    background: linear-gradient(180deg, #f97316 0%, #ea580c 100%) !important;
    color: #fff !important;
    border: none !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


def render_header() -> None:
    if Path("logo.png").exists():
        try:
            with Image.open("logo.png") as image:
                image.verify()
            col_logo, col_badge = st.columns([8, 2])
            with col_logo:
                st.image("logo.png", width=220)
            with col_badge:
                st.markdown(
                    "<div style='text-align:right;margin-top:15px;'><span class='status-badge'>● SESSION ACTIVE</span></div>",
                    unsafe_allow_html=True,
                )
            st.markdown(
                "<hr style='border-color:rgba(255,255,255,0.1);margin-top:-10px;margin-bottom:30px;'>",
                unsafe_allow_html=True,
            )
            return
        except Exception:
            pass

    st.markdown(
        """
<div class='header-bar'>
  <div style='font-size:1.25rem;font-weight:700;letter-spacing:0.05em;color:white;'>
    APOLLO <span style='color:#f97316;'>OMNI AI</span>
  </div>
  <div class='status-badge'>● SESSION ACTIVE</div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_ppt_studio() -> None:
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>Gamma-Style PPT Engine</div>", unsafe_allow_html=True)

    ppt_topic = st.text_input("Presentation topic", placeholder="e.g. Quantum-safe banking infrastructure")
    theme_name = st.selectbox("Slide theme", options=list(THEMES.keys()), index=0)
    provider_label = st.radio(
        "Content model",
        ["Qwen 3.6 (Groq free tier)", "Gemini (free tier key)"],
        horizontal=True,
    )
    provider = "qwen" if provider_label.startswith("Qwen") else "gemini"

    active_keys = []
    if GROQ_API_KEY:
        active_keys.append("Groq")
    if GEMINI_API_KEY:
        active_keys.append("Gemini")
    if OPENROUTER_API_KEY:
        active_keys.append("OpenRouter")
    st.caption(f"Free services active: {', '.join(active_keys) if active_keys else 'none configured yet'}")

    if st.button("Generate Gamma-style PPTX", use_container_width=True):
        if not ppt_topic.strip():
            st.error("Enter a presentation topic first.")
        elif provider == "qwen" and not GROQ_API_KEY:
            st.error("Add GROQ_API_KEY to Streamlit secrets for Qwen generation.")
        elif provider == "gemini" and not GEMINI_API_KEY:
            st.error("Add GEMINI_API_KEY to Streamlit secrets for Gemini generation.")
        else:
            build_deck_with_status(ppt_topic.strip(), theme_name, provider)

    render_download_button()

    with st.expander("Open slide editor", expanded=False):
        render_slide_editor()
        if st.button("Rebuild PPTX from edited slides", use_container_width=True):
            build_edited_deck_with_status(ppt_topic.strip(), theme_name)
            render_download_button()

    st.markdown("</div>", unsafe_allow_html=True)


def render_document_ingestion() -> None:
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>Local RAG Documents</div>", unsafe_allow_html=True)
    uploaded_files = st.file_uploader(
        "Upload PDF or TXT course materials",
        type=["pdf", "txt"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="file_in",
    )
    if st.button("Sync knowledge base", use_container_width=True):
        if not uploaded_files:
            st.warning("Upload at least one PDF or TXT file first.")
        else:
            with st.status("Indexing local documents...", expanded=True) as status:
                updated_vector_db, added_count = process_and_index_files(
                    uploaded_files,
                    st.session_state.vector_db,
                )
                if added_count:
                    st.session_state.vector_db = updated_vector_db
                    st.session_state.node_count += added_count
                    status.update(label=f"Indexed {added_count} local context blocks.", state="complete")
                else:
                    status.update(label="No readable text found.", state="error")
    st.caption("RAG indexing uses local uploads only. No paid search API is required.")
    st.markdown("</div>", unsafe_allow_html=True)


def render_model_selector() -> str:
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>Multi-Model Chat</div>", unsafe_allow_html=True)
    selected_model = st.selectbox("API gateway endpoint", options=list(MODEL_OPTIONS.keys()), index=0)
    st.caption(MODEL_OPTIONS[selected_model]["desc"])
    st.markdown("</div>", unsafe_allow_html=True)
    return selected_model


def render_chat(selected_model: str) -> None:
    if not st.session_state.chat_history:
        st.markdown(
            """
<div style='margin-top:50px;margin-bottom:30px;text-align:center;'>
  <h2 style='color:#f97316;font-weight:700;'>Study Console Initialized</h2>
  <p style='color:#a1a1aa;font-family:"JetBrains Mono",monospace;font-size:0.85rem;'>
    Upload local files on the left, then ask focused questions here.
  </p>
</div>
""",
            unsafe_allow_html=True,
        )

    chat_scroll_pane = st.container(height=650, border=False)
    with chat_scroll_pane:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    user_query = st.chat_input("Enter your query...")
    if not user_query:
        return

    st.session_state.chat_history.append({"role": "user", "content": user_query})
    start_time = time.time()
    context_payload = ""

    if st.session_state.vector_db is not None:
        retriever = st.session_state.vector_db.as_retriever(search_kwargs={"k": 5})
        matched_nodes = retriever.invoke(user_query)
        context_payload = "\n\n".join(
            f"[{node.metadata.get('source', 'Local document')}]\n{node.page_content}"
            for node in matched_nodes
        )
        sys_instruction = (
            "You are APOLLO OMNI AI, an advanced study assistant. Answer using only the provided local context. "
            "Do not include raw URLs, source brackets, or internal retrieval metadata. "
            "Structure your response logically: provide a brief 1-sentence overview, break down the main points cleanly with bullet points, "
            "and finish with a concise, actionable takeaway."
        )
        clean_ctx = context_payload.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        st.session_state.source_reference = f"<div class='source-box'><strong>Active local context:</strong><br><br>{clean_ctx}</div>"
    else:
        sys_instruction = (
            "You are APOLLO OMNI AI, an advanced study assistant. Answer from general knowledge with a clear, "
            "structured overview, organized bullet points, and a crisp final takeaway."
        )
        st.session_state.source_reference = "<div class='source-box font-mono'>No local context indexed. General model response used.</div>"

    message_stream = [{"role": "system", "content": sys_instruction}]
    message_stream.extend(st.session_state.chat_history[-4:])
    message_stream.append({"role": "user", "content": f"Context:\n{context_payload}\n\nQuestion: {user_query}"})

    with chat_scroll_pane:
        with st.chat_message("assistant"):
            try:
                stream = generate_llm_stream(message_stream, GROQ_API_KEY, OPENROUTER_API_KEY, selected_model)
                collected_tokens = st.write_stream(stream)
                if not str(collected_tokens).strip():
                    collected_tokens = "Empty response."
                    st.markdown(collected_tokens)
            except Exception as exc:
                collected_tokens = f"Framework API failure: {exc}"
                st.markdown(collected_tokens)

    st.session_state.chat_history.append({"role": "assistant", "content": collected_tokens})
    st.session_state.response_time = f"{time.time() - start_time:.2f}s"
    st.rerun()


def render_sidebar_metrics(cookie_manager: stx.CookieManager) -> None:
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>Analytics Dashboard</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div><div class='metric-title'>Inference Latency</div><div class='metric-value'>{st.session_state.response_time}</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("<hr style='border-color:rgba(255,255,255,0.1);margin:15px 0;'>", unsafe_allow_html=True)
    st.markdown(
        f"<div><div class='metric-title'>Indexed Chunks</div><div class='metric-value'>{st.session_state.node_count}</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>Retrieval Matrix</div>", unsafe_allow_html=True)
    st.markdown(st.session_state.source_reference, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>Session Actions</div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Purge", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.vector_db = None
            st.session_state.node_count = 0
            st.session_state.response_time = "0.00s"
            st.session_state.source_reference = "<div class='source-box font-mono'>Awaiting local context...</div>"
            st.session_state.slides_data = DEFAULT_SLIDES.copy()
            st.session_state.generated_pptx_path = ""
            st.rerun()
    with c2:
        chat_log = "\n".join(f"{msg['role'].upper()}: {msg['content']}" for msg in st.session_state.chat_history)
        st.download_button("Export", data=chat_log, file_name="apollo_log.txt", mime="text/plain", use_container_width=True)

    if st.button("Log out", use_container_width=True, type="secondary"):
        st.session_state.authenticated = False
        cookie_manager.delete(AUTH_COOKIE_NAME)
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    init_session_state()
    render_css()
    cookie_manager = stx.CookieManager()

    # Wait for stx.CookieManager JS component to initialize completely
    cookies = cookie_manager.get_all(key="main_app_cookie_manager")
    if cookies is None:
        st.stop()

    render_header()
    require_authentication(cookie_manager)

    col_left, col_mid, col_right = st.columns([3, 6, 3], gap="large")
    with col_left:
        selected_model = render_model_selector()
        render_ppt_studio()
        render_document_ingestion()
    with col_mid:
        render_chat(selected_model)
    with col_right:
        render_sidebar_metrics(cookie_manager)


if __name__ == "__main__":
    main()
