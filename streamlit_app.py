import datetime
import io
import json
import os
import random
import re
import requests
import smtplib
import tempfile
import time
from email.mime.text import MIMEText
import urllib.parse

import extra_streamlit_components as stx
from groq import Groq
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from PIL import Image

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
import streamlit as st

# Import Modular Voice Handler
from voice_handler import render_voice_input, run_tts_synthesis

# Import RAG & Kling AI Video Generator module
from video_generator import render_video_generator_ui

# Import User Settings Page
from settings_app import render_settings_page

# Import interactive Plotly chart engine
try:
  from charts import render_dynamic_chart_from_text
except ImportError:

  def render_dynamic_chart_from_text(text):
    pass


# 1. Page Configuration & Title
st.set_page_config(layout="wide", page_title="APOLLO OMNI AI", page_icon="⚡")

# 2. Initialize Cookie Manager for Persistent Auth
cookie_manager = stx.CookieManager()
cookies = cookie_manager.get_all()
if cookies is None:
  cookies = {}

# 3. Explicit Key/Token Initialization
try:
  GROQ_API_KEY = st.secrets.get("GROQ_API_KEY", os.getenv("GROQ_API_KEY", ""))
except Exception:
  GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

try:
  OPENROUTER_API_KEY = st.secrets.get(
      "OPENROUTER_API_KEY", os.getenv("OPENROUTER_API_KEY", "")
  )
except Exception:
  OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

try:
  TAVILY_API_KEY = st.secrets.get(
      "TAVILY_API_KEY", os.getenv("TAVILY_API_KEY", "")
  )
except Exception:
  TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

try:
  KLING_API_KEY = st.secrets.get(
      "KLING_API_KEY", os.getenv("KLING_API_KEY", "")
  )
except Exception:
  KLING_API_KEY = os.getenv("KLING_API_KEY", "")


# 4. Resource Caching Pipelines
@st.cache_resource
def get_embedding_model():
  return HuggingFaceEmbeddings(
      model_name="sentence-transformers/all-MiniLM-L6-v2",
      model_kwargs={"device": "cpu"},
      encode_kwargs={"normalize_embeddings": True},
  )


@st.cache_resource
def get_text_splitter():
  return RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)


embedder = get_embedding_model()
text_splitter = get_text_splitter()

# 5. State Management Matrix
if "vector_db" not in st.session_state:
  st.session_state.vector_db = None
if "chat_history" not in st.session_state:
  st.session_state.chat_history = []
if "response_time" not in st.session_state:
  st.session_state.response_time = "0.00"
if "source_reference" not in st.session_state:
  st.session_state.source_reference = (
      "<div class='source-box font-mono'>Awaiting vector alignment...</div>"
  )
if "node_count" not in st.session_state:
  st.session_state.node_count = 0

# Persistent Auth State Handling
auth_cookie = cookies.get("apollo_somaiya_session")
if "authenticated" not in st.session_state:
  if auth_cookie == "verified_student":
    st.session_state.authenticated = True
  else:
    st.session_state.authenticated = False

if "otp_sent" not in st.session_state:
  st.session_state.otp_sent = False
if "generated_otp" not in st.session_state:
  st.session_state.generated_otp = None
if "user_email" not in st.session_state:
  st.session_state.user_email = ""

# ── Auto-load persisted user profile ──────────────────────────────────────
_PROFILE_DEFAULTS = {
    "full_name": "",
    "university": "Somaiya University",
    "major": "",
    "learning_style": "Visual & Interactive",
    "detail_level": "Intermediate",
    "default_model": "Meta Llama 3.1 8B (Groq)",
}
if "user_prefs" not in st.session_state:
  _profile_path = "apollo_user_profile.json"
  if os.path.exists(_profile_path):
    try:
      with open(_profile_path, "r", encoding="utf-8") as _pf:
        _loaded_prefs = json.load(_pf)
      st.session_state.user_prefs = {**_PROFILE_DEFAULTS, **_loaded_prefs}
    except Exception:
      st.session_state.user_prefs = dict(_PROFILE_DEFAULTS)
  else:
    st.session_state.user_prefs = dict(_PROFILE_DEFAULTS)

# Voice TTS output toggle (persisted across reruns)
if "voice_output_enabled" not in st.session_state:
  st.session_state.voice_output_enabled = False

# INITIAL SLIDES DEFAULT STATE (UNIVERSAL WELCOME PAGE)
if "slides_data" not in st.session_state:
  st.session_state.slides_data = [{
      "title": "Welcome to Apollo Omni AI",
      "subtitle": "Cognitive Presentation & RAG Studio",
      "image_keyword": (
          "abstract futuristic orange technology grid network minimalist"
      ),
      "cards": [
          {
              "heading": "Step 1: Index Knowledge",
              "text": (
                  "Use the sidebar to crawl the web with Tavily or upload"
                  " PDFs/TXT files into the vector database."
              ),
          },
          {
              "heading": "Step 2: Define Presentation",
              "text": (
                  "Type any topic and specific instructions into the"
                  " Presentation Studio controls on the right."
              ),
          },
          {
              "heading": "Step 3: Export & Present",
              "text": (
                  "Generate slides backed by real-time RAG context and export"
                  " directly to a Gamma-style .pptx deck."
              ),
          },
      ],
  }]

# 6. Groq LPU Model Matrix (100% Active Groq API Models)
MODEL_OPTIONS = {
    "Meta Llama 3.3 70B (Groq)": {
        "provider": "groq",
        "model_id": "llama-3.3-70b-versatile",
        "desc": "Flagship 70B model running at ultra speed on Groq LPUs.",
    },
    "Meta Llama 3.1 8B (Groq)": {
        "provider": "groq",
        "model_id": "llama-3.1-8b-instant",
        "desc": "Ultra-fast instant inference speed on Groq LPU.",
    },
    "Google Gemma 2 9B (Groq)": {
        "provider": "groq",
        "model_id": "gemma2-9b-it",
        "desc": "Google's 9B instruction-tuned model running natively on Groq.",
    },
    "Mixtral 8x7B (Groq)": {
        "provider": "groq",
        "model_id": "mixtral-8x7b-32768",
        "desc": "Mistral AI's high quality MoE model on Groq.",
    },
    "Qwen 2.5 Coder 32B (Groq)": {
        "provider": "groq",
        "model_id": "qwen-2.5-coder-32b",
        "desc": "Alibaba Qwen 2.5 specialized 32B coding model on Groq.",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# TAVILY CACHED SEARCH  (ttl=1 hour — avoids repeated API calls for same query)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_tavily_search(query: str, api_key: str) -> dict:
    """
    Calls Tavily Search API via the official SDK.
    Results are cached per (query, api_key) pair for 1 hour.
    include_answer=True requests Tavily's native synthesized quick answer.
    """
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        return client.search(
            query=query,
            search_depth="advanced",
            max_results=4,
            include_answer=True,
        )
    except ImportError:
        # Fallback to raw HTTP if SDK not installed yet
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": 4,
                "include_answer": True,
            },
            timeout=25,
        )
        if response.status_code == 200:
            return response.json()
        return {}
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# AGENTIC AUTO-SEARCH INTENT DETECTION
# ─────────────────────────────────────────────────────────────────────────────

# Keywords/phrases that suggest the user wants real-time or current information
_SEARCH_TRIGGERS = {
    "latest", "news", "current", "today", "who is", "what is",
    "2024", "2025", "2026", "recent", "now", "live", "real-time",
    "realtime", "breaking", "update", "trending", "happening",
    "this week", "this month", "this year",
}


def _needs_web_search(query: str) -> bool:
    """Returns True if the query contains temporal or intent keywords."""
    q = query.lower()
    return any(kw in q for kw in _SEARCH_TRIGGERS)


# 7. Image Engine via Pollinations
def fetch_image_by_keyword(keyword):
  if not keyword:
    keyword = "abstract orange dark digital technology background"

  clean_kw = re.sub(r"[^\w\s]", "", keyword).strip()
  prompt_encoded = urllib.parse.quote(
      f"high resolution modern photograph of {clean_kw}, detailed,"
      " 8k wallpaper"
  )

  pollinations_url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=800&height=600&seed={abs(hash(clean_kw)) % 100000}&nologo=true"

  try:
    resp = requests.get(
        pollinations_url,
        timeout=10,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
            )
        },
    )
    if resp.status_code == 200 and len(resp.content) > 5000:
      tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
      tmp.write(resp.content)
      tmp.close()
      return tmp.name
  except Exception:
    pass

  return None


# 8. PPTX Builder Engine (Gamma AI Style)
def create_gamma_style_pptx(slides_data):
  prs = Presentation()
  prs.slide_width = Inches(13.333)
  prs.slide_height = Inches(7.5)

  BG_COLOR = RGBColor(15, 23, 42)
  CARD_BG = RGBColor(30, 41, 59)
  CARD_BORDER = RGBColor(51, 65, 85)
  ACCENT_COLOR = RGBColor(249, 115, 22)
  TEXT_PRIMARY = RGBColor(248, 250, 252)
  TEXT_MUTED = RGBColor(148, 163, 184)

  blank_layout = prs.slide_layouts[6]

  for index, slide_info in enumerate(slides_data):
    if not isinstance(slide_info, dict):
      continue

    slide = prs.slides.add_slide(blank_layout)

    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = BG_COLOR

    title_text = slide_info.get("title", f"Slide {index+1}")
    subtitle_text = slide_info.get("subtitle", "")
    keyword = slide_info.get("image_keyword", title_text)
    cards = slide_info.get("cards", [])

    title_box = slide.shapes.add_textbox(
        Inches(0.8), Inches(0.5), Inches(11.7), Inches(1.2)
    )
    tf = title_box.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = title_text
    p.font.size = Pt(26)
    p.font.bold = True
    p.font.color.rgb = ACCENT_COLOR
    p.font.name = "Arial"

    if subtitle_text:
      p2 = tf.add_paragraph()
      p2.text = subtitle_text
      p2.font.size = Pt(14)
      p2.font.color.rgb = TEXT_MUTED
      p2.font.name = "Arial"

    img_path = fetch_image_by_keyword(keyword)
    has_image = img_path is not None
    content_width = Inches(7.6) if has_image else Inches(11.7)

    if has_image:
      try:
        img_card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(8.8),
            Inches(1.8),
            Inches(3.8),
            Inches(5.0),
        )
        img_card.fill.solid()
        img_card.fill.fore_color.rgb = CARD_BG
        img_card.line.color.rgb = CARD_BORDER

        slide.shapes.add_picture(
            img_path,
            Inches(8.95),
            Inches(1.95),
            width=Inches(3.5),
            height=Inches(4.7),
        )
      except Exception:
        pass
      finally:
        if img_path and os.path.exists(img_path):
          os.unlink(img_path)

    if isinstance(cards, list) and len(cards) > 0:
      num_cards = min(len(cards), 4)
      card_height = Inches(4.8 / max(num_cards, 1) - 0.15)
      start_top = Inches(1.8)

      for i in range(num_cards):
        card_item = cards[i]
        top_pos = start_top + i * (card_height + Inches(0.15))

        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(0.8),
            top_pos,
            content_width,
            card_height,
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = CARD_BG
        shape.line.color.rgb = CARD_BORDER

        tf_card = shape.text_frame
        tf_card.word_wrap = True
        tf_card.margin_left = Inches(0.25)
        tf_card.margin_right = Inches(0.25)
        tf_card.margin_top = Inches(0.12)
        tf_card.margin_bottom = Inches(0.12)

        heading = (
            card_item.get("heading", "") if isinstance(card_item, dict) else ""
        )
        text = (
            card_item.get("text", str(card_item))
            if isinstance(card_item, dict)
            else str(card_item)
        )

        p_head = tf_card.paragraphs[0]
        if heading:
          p_head.text = f"▪ {heading}"
          p_head.font.bold = True
          p_head.font.size = Pt(15)
          p_head.font.color.rgb = ACCENT_COLOR
          p_head.font.name = "Arial"

          p_body = tf_card.add_paragraph()
          p_body.text = text
          p_body.font.size = Pt(12)
          p_body.font.color.rgb = TEXT_PRIMARY
          p_body.font.name = "Arial"
        else:
          p_head.text = f"▪ {text}"
          p_head.font.size = Pt(13)
          p_head.font.color.rgb = TEXT_PRIMARY
          p_head.font.name = "Arial"

  path = "apollo_gamma_presentation.pptx"
  prs.save(path)
  return path


# 9. Pure Groq LLM Streamer with Automatic Model Fallback
def generate_llm_stream(messages, groq_key, selected_model_name):
  model_cfg = MODEL_OPTIONS.get(selected_model_name, {})
  primary_model = model_cfg.get("model_id", "llama-3.3-70b-versatile")

  if not groq_key or not groq_key.startswith("gsk_"):
    yield (
        "❌ MISSING CONFIGURATION: Please set a valid 'GROQ_API_KEY' starting"
        " with 'gsk_' in Streamlit Secrets."
    )
    return

  client = Groq(api_key=groq_key.strip())

  # Fallback models in priority order
  fallback_list = [
      primary_model,
      "llama-3.3-70b-versatile",
      "llama-3.1-8b-instant",
      "gemma2-9b-it",
      "mixtral-8x7b-32768",
  ]
  models_to_try = list(dict.fromkeys(fallback_list))

  last_exception = None
  for model_id in models_to_try:
    try:
      stream = client.chat.completions.create(
          model=model_id,
          messages=messages,
          temperature=0.3,
          max_tokens=2048,
          stream=True,
      )
      token_count = 0
      for chunk in stream:
        token_text = chunk.choices[0].delta.content or ""
        if token_text:
          token_count += 1
          yield token_text
      if token_count > 0:
        return
    except Exception as e:
      last_exception = e
      continue

  yield f"❌ Groq SDK Failure: {str(last_exception)}"


# 10. Robust JSON Parser & Slide Generator for Groq (RAG-Enabled)
def parse_robust_json(raw_text):
  if not raw_text:
    return None

  clean_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)
  if "</think>" in clean_text:
    clean_text = clean_text.split("</think>")[-1]

  start = clean_text.find("{")
  end = clean_text.rfind("}")

  if start != -1 and end != -1 and end > start:
    json_candidate = clean_text[start : end + 1]
    try:
      parsed = json.loads(json_candidate)
      if isinstance(parsed, dict):
        if "slides" in parsed and isinstance(parsed["slides"], list):
          return parsed["slides"]
        for val in parsed.values():
          if isinstance(val, list):
            return val
      elif isinstance(parsed, list):
        return parsed
    except json.JSONDecodeError:
      pass

  return None


def generate_slides_with_groq(
    topic, custom_instructions="", context="", groq_key="", user_prefs=None
):
  groq_key = groq_key.strip() if groq_key else ""
  if not groq_key or not groq_key.startswith("gsk_"):
    return (
        None,
        "Missing active GROQ_API_KEY starting with 'gsk_' in Streamlit Secrets.",
    )

  _prefs = user_prefs or {}
  prefs_line = (
      f"Adapt slides for: learning style = '{_prefs.get('learning_style','General')}', "
      f"depth = '{_prefs.get('detail_level','Intermediate')}'.\n\n"
  )

  prompt = f"""{prefs_line}Create an in-depth 4 to 5 slide presentation outline on the topic: '{topic}'.

SPECIFIC USER INSTRUCTIONS / FOCUS POINTS:
{custom_instructions if custom_instructions else "None provided."}

INDEXED KNOWLEDGE BASE CONTEXT:
{context if context else "No extra context provided. Use general knowledge."}

OUTPUT RAW JSON ONLY. Do NOT use markdown backticks or explanations. Start with '{{' and end with '}}'.

SCHEMA REQUIRED:
{{
  "slides": [
    {{
      "title": "Slide Title",
      "subtitle": "Informative Subtitle",
      "image_keyword": "descriptive picture keyword",
      "cards": [
        {{
          "heading": "Subtopic Heading",
          "text": "Detailed multi-sentence content accurately based on the topic and context provided."
        }},
        {{
          "heading": "Key Insight / Mechanic",
          "text": "Comprehensive analysis of facts or concepts mentioned in the context."
        }}
      ]
    }}
  ]
}}"""

  client = Groq(api_key=groq_key)
  models_to_try = [
      "llama-3.3-70b-versatile",
      "llama-3.1-8b-instant",
      "gemma2-9b-it",
  ]

  for model_id in models_to_try:
    try:
      completion = client.chat.completions.create(
          model=model_id,
          messages=[
              {
                  "role": "system",
                  "content": (
                      "You are an expert slide deck generator. You output ONLY"
                      " valid raw JSON strictly derived from the given context"
                      " and user instructions."
                  ),
              },
              {"role": "user", "content": prompt},
          ],
          temperature=0.2,
          max_tokens=4096,
      )

      raw_text = completion.choices[0].message.content or ""
      parsed_slides = parse_robust_json(raw_text)

      if parsed_slides:
        return parsed_slides, f"Success ({model_id})"

    except Exception:
      continue

  return (
      None,
      "Failed to parse slides JSON. Try clicking 'Gemini Gen' as a backup.",
  )


# Gemini slide generator removed per user request — Groq LPU is the primary engine.


# 12. Email Dispatcher Function for Auth
def send_otp_email(target_email, otp_code):
  try:
    sender_email = st.secrets.get("EMAIL_SENDER", "")
    sender_pass = st.secrets.get("EMAIL_PASSWORD", "")
    if not sender_email or not sender_pass:
      return False, "Email credentials missing in Streamlit secrets."

    msg = MIMEText(
        f"Your Apollo Omni AI secure access code is: {otp_code}\n\nIf you did"
        " not request this, please ignore this email."
    )
    msg["Subject"] = "APOLLO OMNI - Access Code"
    msg["From"] = sender_email
    msg["To"] = target_email

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(sender_email, sender_pass)
    server.send_message(msg)
    server.quit()
    return True, "Success"
  except Exception as e:
    return False, str(e)


# 13. CSS Styling & Custom UI Layer
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

    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: var(--surface-black) !important;
        color: var(--text-color) !important;
        font-family: 'Inter', sans-serif !important;
    }
    [data-testid="stHeader"] { background: transparent !important; border-bottom: none !important; }
    
    h1, h2, h3, h4, h5, h6, p, span, label, li, small, div { color: var(--text-color); }
    .font-mono { font-family: 'JetBrains Mono', monospace !important; }

    .glass-panel {
      background: var(--glass-bg) !important;
      backdrop-filter: blur(12px) !important;
      border: 1px solid var(--glass-border) !important;
      box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37) !important;
      transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.3s ease !important;
      border-radius: 4px !important;
      padding: 16px !important;
      margin-bottom: 20px !important;
    }
    .glass-panel:hover {
      border-color: rgba(255, 140, 0, 0.4) !important;
    }
    
    .panel-header {
      font-size: 11px !important;
      font-weight: 700 !important;
      letter-spacing: 0.2em !important;
      color: #a1a1aa !important;
      text-transform: uppercase !important;
      margin-bottom: 16px !important;
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
      height: 12px;
      background-color: var(--primary-orange);
    }

    div[data-testid="stChatInput"] textarea, div[data-testid="stChatInput"] { 
        background-color: rgba(0,0,0,0.8) !important; 
        border-color: rgba(255, 255, 255, 0.1) !important; 
        color: white !important; 
        font-family: 'JetBrains Mono', monospace !important;
    }
    div[data-baseweb="input"] > div, div[data-baseweb="select"] > div, div[data-baseweb="textarea"] > div {
        background-color: rgba(0,0,0,0.8) !important;
        border: 1px solid var(--glass-border) !important;
    }
    div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea {
        color: white !important;
        background-color: transparent !important;
    }

    .stButton button {
        background: var(--primary-orange) !important;
        color: #000 !important;
        font-size: 12px !important;
        font-weight: 900 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.2em !important;
        border: none !important;
        border-radius: 2px !important;
        transition: transform 0.2s, background 0.2s !important;
    }
    .stButton button:hover {
        background: #ff9d2e !important;
        transform: scale(1.02);
    }
    
    .stButton button[kind="secondary"] {
        background: transparent !important;
        color: #a1a1aa !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
    }

    div[data-testid="stChatMessage"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 13px !important;
        line-height: 1.6 !important;
        background: transparent !important;
        border: none !important;
        border-radius: 0 !important;
        padding: 16px !important;
        margin-bottom: 12px !important;
    }
    div[data-testid="stChatMessage"]:has(div[aria-label="Chat message from user"]) {
        border-left: 2px solid #a1a1aa !important;
        background: rgba(255, 255, 255, 0.02) !important;
    }
    div[data-testid="stChatMessage"]:has(div[aria-label="Chat message from assistant"]) {
        border-left: 2px solid var(--primary-orange) !important;
        background: rgba(255, 140, 0, 0.05) !important;
    }

    .source-box {
        background: rgba(0,0,0,0.6) !important;
        border: 1px solid rgba(255,255,255,0.05) !important;
        padding: 12px !important;
        border-radius: 2px !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 10px !important;
        color: #a1a1aa !important;
        overflow-x: auto;
        max-height: 350px;
    }

    @keyframes pulse-ring {
      0% { transform: scale(.33); opacity: 1; }
      80%, 100% { opacity: 0; }
    }
    .status-pulse { position: relative; display: inline-block; width: 8px; height: 8px; margin-right: 8px; }
    .status-pulse::before {
      content: '';
      position: absolute;
      left: -4px; top: -4px; width: 16px; height: 16px;
      background-color: #22c55e;
      border-radius: 100%;
      animation: pulse-ring 2s cubic-bezier(0.215, 0.61, 0.355, 1) infinite;
    }
    .status-dot { width: 8px; height: 8px; background-color: #22c55e; border-radius: 100%; display: inline-block; }

    .omni-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 32px;
        background: rgba(0, 0, 0, 0.8);
        backdrop-filter: blur(12px);
        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        margin-top: -60px;
        margin-bottom: 30px;
        position: sticky;
        top: 0;
        z-index: 50;
    }
    .omni-brand { font-size: 20px; font-weight: 700; letter-spacing: 0.2em; color: white; margin:0; line-height: 1.2;}
    .omni-brand span { color: var(--primary-orange); }
    .omni-subtitle { font-size: 10px; color: #71717a; font-family: 'JetBrains Mono', monospace; letter-spacing: 0.1em; text-transform: uppercase; margin:0;}
    .omni-badge {
        font-size: 10px; font-family: 'JetBrains Mono', monospace;
        background: rgba(34, 197, 94, 0.1); color: #4ade80;
        border: 1px solid rgba(34, 197, 94, 0.2); padding: 4px 12px; border-radius: 2px;
        display: flex; align-items: center;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Custom Header
st.markdown(
    """
    <div class="omni-header">
        <div style="display: flex; align-items: center; gap: 24px;">
            <div>
                <h1 class="omni-brand">APOLLO <span>OMNI</span></h1>
                <p class="omni-subtitle">Cognitive Study Environment</p>
            </div>
            <div class="omni-badge">
                <span class="status-pulse"><span class="status-dot"></span></span>
                SYSTEM_STABLE_V2.1
            </div>
        </div>
        <div style="display: flex; gap: 40px; align-items: center; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #a1a1aa;">
            <span style="color: #ff8c00; border-bottom: 1px solid #ff8c00; padding-bottom: 4px;">Console</span>
            <span>Archive</span>
            <span>Cognition</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Spacing Adjustments
st.markdown(
    """
<style>
    .block-container {
        padding-top: 2rem !important;
        padding-bottom: 1rem !important;
        max-width: 96% !important;
    }
    .omni-header { margin-top: -10px !important; margin-bottom: 20px !important; }
    [data-testid="stSidebar"] {
        background-color: #0a0a0c !important;
        border-right: 1px solid rgba(255, 140, 0, 0.15) !important;
    }
</style>
""",
    unsafe_allow_html=True,
)


# ================= AUTHENTICATION GATEKEEPER =================
if not st.session_state.authenticated:
  st.markdown(
      "<div style='text-align: center; margin-top: 80px;'><h2"
      " style='color: #ff8c00; font-family: \"Inter\"; letter-spacing: 0.1em;'>🔒 SECURE ACCESS REQUIRED</h2><p"
      " style='color: #a1a1aa; font-family: \"JetBrains Mono\"; font-size: 12px;'>Verify your Somaiya university email to"
      " receive an access token.</p></div>",
      unsafe_allow_html=True,
  )

  col_space1, col_login, col_space3 = st.columns([3, 4, 3])
  with col_login:
    st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
    if not st.session_state.otp_sent:
      email_input = st.text_input(
          "University Email", placeholder="your.name@somaiya.edu"
      )
      if st.button("DISPATCH ACCESS CODE", use_container_width=True):
        if email_input.strip().lower().endswith("@somaiya.edu"):
          with st.spinner("Dispatching secure token..."):
            otp = str(random.randint(100000, 999999))
            st.session_state.generated_otp = otp
            st.session_state.user_email = email_input.strip().lower()

            success, error_msg = send_otp_email(
                st.session_state.user_email, otp
            )

            if success:
              st.session_state.otp_sent = True
              st.rerun()
            else:
              st.error(f"❌ Failed to dispatch email: {error_msg}")
        else:
          st.error(
              "❌ Access Denied. Only @somaiya.edu accounts are permitted."
          )
    else:
      st.success(f"Secure token dispatched to {st.session_state.user_email}")
      otp_input = st.text_input("Enter 6-Digit Token", type="password")

      if st.button("VERIFY & ENTER", use_container_width=True):
        if otp_input.strip() == st.session_state.generated_otp:
          st.session_state.authenticated = True
          cookie_manager.set(
              "apollo_somaiya_session",
              "verified_student",
              expires_at=datetime.datetime.now()
              + datetime.timedelta(days=30),
          )
          st.rerun()
        else:
          st.error("❌ Invalid token. Please check your inbox and retry.")

      st.markdown("<br>", unsafe_allow_html=True)
      if st.button("Use a different identity", type="secondary"):
        st.session_state.otp_sent = False
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
  st.stop()
# ==============================================================


# ================= SIDEBAR: SETTINGS & TOOLS =================
with st.sidebar:
  st.markdown(
      "<h2 class='omni-brand' style='font-size: 16px; margin-bottom: 12px;'>APOLLO <span>OMNI</span><br><span style='font-size: 9px; color: #71717a; font-family: \"JetBrains Mono\";'>SYSTEM CONTROL PANEL</span></h2>",
      unsafe_allow_html=True,
  )

  # Interactive App Navigation Switcher
  app_mode = st.radio(
      "NAVIGATION:",
      options=["⚡ Console & Tools", "⚙️ User Settings & Profile"],
      key="main_app_navigation",
  )
  st.markdown("<hr style='border-color: rgba(255,140,0,0.2); margin: 12px 0;'>", unsafe_allow_html=True)

  # Telemetry Row
  st.markdown(
      "<div class='glass-panel' style='padding: 12px; margin-bottom: 16px;'>",
      unsafe_allow_html=True,
  )
  c_lat, c_vec = st.columns(2)
  with c_lat:
    st.markdown(
        f"<div style='text-align:center;'><div style='font-size:20px; font-weight:900; color:white; font-family: \"JetBrains Mono\";'>{st.session_state.response_time}<span style='font-size:12px;color:#ff8c00;'>s</span></div><div style='font-size:9px; color:#a1a1aa; text-transform:uppercase;'>Latency</div></div>",
        unsafe_allow_html=True,
    )
  with c_vec:
    st.markdown(
        f"<div style='text-align:center;'><div style='font-size:20px; font-weight:900; color:white; font-family: \"JetBrains Mono\";'>{st.session_state.node_count}</div><div style='font-size:9px; color:#a1a1aa; text-transform:uppercase;'>Vectors</div></div>",
        unsafe_allow_html=True,
    )
  st.markdown("</div>", unsafe_allow_html=True)

  # RAG Visual
  st.markdown(
      """
  <div class='glass-panel' style='padding: 0; overflow: hidden; margin-bottom: 16px;'>
      <div style='padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.05); display: flex; justify-content: space-between; align-items: center;'>
          <h2 style='font-size: 9px; font-weight: 700; letter-spacing: 0.1em; color: #a1a1aa; text-transform: uppercase; margin: 0;'>RAG_ENGINE_VISUAL</h2>
          <span style='font-size: 8px; font-family: "JetBrains Mono"; color: #ff8c00; background: rgba(255,140,0,0.1); padding: 2px 6px; border: 1px solid rgba(255,140,0,0.2);'>LIVE</span>
      </div>
      <div style='height: 100px; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; position: relative;'>
          <div style='position: relative; width: 60px; height: 60px; display: flex; align-items: center; justify-content: center;'>
              <div style='width: 16px; height: 16px; background: #ff8c00; border-radius: 50%; box-shadow: 0 0 15px rgba(255,140,0,0.6); z-index: 10; animation: float 4s ease-in-out infinite;'></div>
              <div style='position: absolute; width: 40px; height: 40px; border: 1px solid rgba(255,255,255,0.1); border-radius: 50%;'></div>
              <div style='position: absolute; width: 56px; height: 56px; border: 1px dashed rgba(255,140,0,0.3); border-radius: 50%;'></div>
          </div>
      </div>
  </div>
  <style>@keyframes float { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-8px); } }</style>
  """,
      unsafe_allow_html=True,
  )

  # Inference Engine Selection
  st.markdown(
      "<div class='glass-panel' style='padding: 12px; margin-bottom: 16px;'>",
      unsafe_allow_html=True,
  )
  st.markdown(
      "<div class='panel-header' style='margin-bottom: 8px; padding-bottom:"
      " 8px;'>⚙️ Inference Engine</div>",
      unsafe_allow_html=True,
  )

  # user_prefs already loaded at startup — no re-init needed here

  model_list = list(MODEL_OPTIONS.keys())
  saved_model = st.session_state.user_prefs.get(
      "default_model", "Meta Llama 3.3 70B (Groq)"
  )
  default_index = (
      model_list.index(saved_model) if saved_model in model_list else 0
  )

  selected_model = st.selectbox(
      "API Gateway Endpoint:",
      options=model_list,
      index=default_index,
      label_visibility="collapsed",
  )
  st.markdown(
      f"<div style='font-size: 9px; color: #a1a1aa; font-family: \"JetBrains"
      f" Mono\"; margin-top: 4px;'>{MODEL_OPTIONS[selected_model]['desc']}</div>",
      unsafe_allow_html=True,
  )
  st.markdown("</div>", unsafe_allow_html=True)

  # Web Crawler (Tavily) — now using cached SDK call + direct AI answer banner
  st.markdown(
      "<div class='glass-panel' style='padding: 12px; margin-bottom: 16px;'>",
      unsafe_allow_html=True,
  )
  st.markdown(
      "<div class='panel-header' style='margin-bottom: 8px; padding-bottom:"
      " 8px;'>🌐 Web Crawler (Tavily)</div>",
      unsafe_allow_html=True,
  )
  web_query = st.text_input(
      "Query:",
      placeholder="e.g. Artificial Intelligence trends 2026",
      label_visibility="collapsed",
  )
  if st.button("FETCH & INDEX", use_container_width=True):
    if not TAVILY_API_KEY or not TAVILY_API_KEY.startswith("tvly-"):
      st.error("No active Tavily API Key found in Streamlit Secrets.")
    elif web_query:
      with st.spinner("Executing secure web retrieval..."):
        try:
          result = _cached_tavily_search(web_query, TAVILY_API_KEY.strip())

          # ── Display Tavily's native quick-answer banner if available ──
          if tavily_answer := result.get("answer"):
            st.info(f"💡 **Tavily Quick Answer:** {tavily_answer}")

          results = result.get("results", [])
          web_docs = [
              Document(
                  page_content=f"Title: {r.get('title')}\nSource: {r.get('url')}\nContext: {r.get('content')}",
                  metadata={
                      "source": r.get("url", ""),
                      "title": r.get("title", ""),
                  },
              )
              for r in results
          ]
          chunks = text_splitter.split_documents(web_docs)
          if chunks:
            if st.session_state.vector_db is None:
              st.session_state.vector_db = FAISS.from_documents(
                  chunks, embedder
              )
            else:
              st.session_state.vector_db.add_documents(chunks)
            st.session_state.node_count += len(chunks)
            st.success(f"Indexed {len(chunks)} blocks!")
          elif not results:
            st.warning("⚠️ No results returned. Try a different query.")
        except Exception as e:
          st.error(f"Search failed: {str(e)}")
  st.markdown("</div>", unsafe_allow_html=True)

  # Local Documents Upload
  st.markdown(
      "<div class='glass-panel' style='padding: 12px; margin-bottom: 16px;'>",
      unsafe_allow_html=True,
  )
  st.markdown(
      "<div class='panel-header' style='margin-bottom: 8px; padding-bottom:"
      " 8px;'>📚 Material Append</div>",
      unsafe_allow_html=True,
  )
  uploaded_files = st.file_uploader(
      "Upload course materials...",
      type=["pdf", "txt"],
      accept_multiple_files=True,
      label_visibility="collapsed",
      key="file_in",
  )
  if st.button("+ ADD TO KNOWLEDGE", use_container_width=True):
    if uploaded_files:
      with st.spinner("Structuring uploaded data nodes..."):
        docs = []
        for f in uploaded_files:
          suffix = os.path.splitext(f.name)[1].lower()
          file_bytes = f.read()
          with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            path = tmp.name
          try:
            if suffix == ".pdf":
              docs.extend(PyPDFLoader(path).load())
            elif suffix == ".txt":
              docs.extend(TextLoader(path, encoding="utf-8").load())
          except Exception:
            pass
          finally:
            if os.path.exists(path):
              os.unlink(path)

        if docs:
          chunks = text_splitter.split_documents(docs)
          if chunks:
            if st.session_state.vector_db is None:
              st.session_state.vector_db = FAISS.from_documents(
                  chunks, embedder
              )
            else:
              st.session_state.vector_db.add_documents(chunks)
            st.session_state.node_count += len(chunks)
            st.success(f"Indexed {len(chunks)} blocks.")
  st.markdown("</div>", unsafe_allow_html=True)

  # Session Control
  st.markdown(
      "<div class='glass-panel' style='padding: 12px;'>", unsafe_allow_html=True
  )
  st.markdown(
      "<div class='panel-header' style='margin-bottom: 8px; padding-bottom:"
      " 8px;'>🛠️ Session Control</div>",
      unsafe_allow_html=True,
  )
  if st.button("FLUSH MEMORY", use_container_width=True):
    st.session_state.chat_history = []
    st.session_state.vector_db = None
    st.session_state.node_count = 0
    st.session_state.response_time = "0.00"
    st.session_state.source_reference = (
        "<div class='source-box font-mono'>Awaiting vector alignment...</div>"
    )
    st.rerun()

  # ── Voice TTS output toggle ──────────────────────────────────────
  st.session_state.voice_output_enabled = st.checkbox(
      "🔊 Voice Output (TTS)",
      value=st.session_state.get("voice_output_enabled", False),
      help="Speak assistant responses aloud using Microsoft Edge TTS.",
  )

  if st.button("TERMINATE SESSION", use_container_width=True, type="secondary"):
    st.session_state.authenticated = False
    cookie_manager.delete("apollo_somaiya_session")
    st.rerun()
  st.markdown("</div>", unsafe_allow_html=True)


# ================= MAIN AREA: CONSOLE & TOOLS =================
if app_mode == "⚙️ User Settings & Profile":
  render_settings_page()
else:
  col_chat, col_tools = st.columns([6, 4], gap="large")

# ----------------- MAIN LEFT: CHAT CONSOLE -----------------
with col_chat:

  # ── Chat console header with Export button ─────────────────────────────
  _hdr_left, _hdr_right = st.columns([5, 1])
  with _hdr_left:
    st.markdown(
        """
    <div style='background: rgba(0,0,0,0.6); padding: 12px 20px; border-bottom: 1px solid rgba(255,255,255,0.05); border-radius: 4px 4px 0 0; display: flex; justify-content: space-between; align-items: center;'>
        <div style='display: flex; gap: 8px; align-items: center;'>
            <div style='width: 8px; height: 8px; background: #ef4444; border-radius: 50%; opacity: 0.8;'></div>
            <div style='width: 8px; height: 8px; background: #ff8c00; border-radius: 50%; opacity: 0.8;'></div>
            <div style='width: 8px; height: 8px; background: #22c55e; border-radius: 50%; opacity: 0.8;'></div>
            <span style='font-size: 11px; font-weight: 700; letter-spacing: 0.2em; color: #a1a1aa; text-transform: uppercase; margin-left: 12px;'>STUDY_CONSOLE</span>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

  with _hdr_right:
    # ── Chat history export ──────────────────────────────────────────────
    if st.session_state.chat_history:
      _md_lines = []
      for _m in st.session_state.chat_history:
        _role_label = "**You**" if _m["role"] == "user" else "**Apollo**"
        _md_lines.append(f"{_role_label}:\n{_m['content']}\n")
      _md_export = "\n---\n".join(_md_lines)
      st.download_button(
          label="⬇ Export",
          data=_md_export,
          file_name="apollo_chat_transcript.md",
          mime="text/markdown",
          use_container_width=True,
          help="Download this conversation as a Markdown transcript",
      )

  if not st.session_state.chat_history:
    st.markdown(
        """
        <div style='margin-top: 50px; margin-bottom: 20px; text-align: center;'>
            <h2 style='color: #ff8c00; font-family: "Inter", sans-serif; font-weight: 700; font-size: 24px; letter-spacing: 0.1em;'>CONSOLE INITIALIZED</h2>
            <p style='color: #a1a1aa; font-family: "JetBrains Mono", monospace; font-size: 12px; margin-top: 10px;'>Awaiting input parameters in the command line below.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

  chat_scroll_pane = st.container(height=440, border=False)

  with chat_scroll_pane:
    for msg in st.session_state.chat_history:
      with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
          render_dynamic_chart_from_text(msg["content"])
        else:
          st.markdown(msg["content"])

  # --- VOICE & TEXT INPUT MATRIX ---
  voice_prompt = render_voice_input(GROQ_API_KEY, key_suffix="chat_main")
  user_query = st.chat_input("AWAITING COMMAND...")

  # Consolidate voice transcription or text input
  final_query = voice_prompt if voice_prompt else user_query

  if final_query:
    st.session_state.chat_history.append(
        {"role": "user", "content": final_query}
    )
    start_time = time.time()
    context_payload = ""

    chart_instruction = (
        "\n\nIf the user asks for a chart, graph, data visualization, or"
        " numerical comparison, append a JSON code block at the very end of"
        ' your response following this exact structure:\n```json\n{\n  "type":'
        ' "bar",  // options: "bar", "line", or "pie"\n  "title": "Chart'
        ' Title",\n  "x_label": "X Axis Label",\n  "y_label": "Y Axis'
        ' Label",\n  "x": ["Category A", "Category B"],\n  "y": [10, 20]\n}\n```'
    )

    # ── Build user-preference context preamble ───────────────────────────
    _prefs = st.session_state.get("user_prefs", {})
    _style = _prefs.get("learning_style", "General")
    _depth = _prefs.get("detail_level", "Intermediate")
    _name  = _prefs.get("full_name", "").strip()
    prefs_preamble = (
        f"Student profile: learning style = '{_style}', "
        f"detail level = '{_depth}'."
        + (f" Address the student as {_name}." if _name else "")
        + " Tailor all responses accordingly.\n\n"
    )

    # ── AGENTIC AUTO-SEARCH: fire Tavily when no vector DB & query needs web ──
    _auto_search_fired = False
    if st.session_state.vector_db is None and _needs_web_search(final_query):
      if TAVILY_API_KEY and TAVILY_API_KEY.startswith("tvly-"):
        try:
          with st.spinner("🌐 Fetching real-time context via Tavily..."):
            _auto_result = _cached_tavily_search(final_query, TAVILY_API_KEY.strip())

          # Show Tavily's native synthesized answer as a banner
          if _ta := _auto_result.get("answer"):
            st.info(f"💡 **Tavily Quick Answer:** {_ta}")

          # Build context payload from top web results
          _web_ctx_parts = [
              f"[{r.get('title', 'Web Result')}]\nSource: {r.get('url', '')}\n{r.get('content', '')}"
              for r in _auto_result.get("results", [])[:3]
          ]
          if _web_ctx_parts:
            context_payload = "\n\n".join(_web_ctx_parts)
            _auto_search_fired = True

            # Update source reference panel with web sources
            _clean_web_ctx = (
                context_payload.replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>")
            )
            st.session_state.source_reference = (
                "<div class='source-box'><strong>Active Context"
                " (Tavily Web Search):</strong><br><br>"
                f"{_clean_web_ctx}</div>"
            )
        except Exception as _ae:
          st.warning(f"⚠️ Auto-search failed gracefully: {_ae}")

    if st.session_state.vector_db is not None:
      retriever = st.session_state.vector_db.as_retriever(
          search_kwargs={"k": 5}
      )
      matched_nodes = retriever.invoke(final_query)
      context_payload = "\n\n".join([
          f"[{node.metadata.get('source', 'Unknown')}]\n{node.page_content}"
          for node in matched_nodes
      ])
      sys_instruction = (
          f"{prefs_preamble}You are APOLLO OMNI AI, an advanced study assistant powered by"
          f" Llama 3.3 70B. Answer using ONLY context below.{chart_instruction}"
      )
      clean_ctx = (
          context_payload.replace("<", "&lt;")
          .replace(">", "&gt;")
          .replace("\n", "<br>")
      )
      st.session_state.source_reference = (
          "<div class='source-box'><strong>Active Context"
          f" (RAG):</strong><br><br>{clean_ctx}</div>"
      )
    elif _auto_search_fired:
      sys_instruction = (
          f"{prefs_preamble}You are APOLLO OMNI AI, an advanced study assistant powered by"
          f" Llama 3.3 70B. Use the real-time web context below to answer accurately.{chart_instruction}"
      )
    else:
      sys_instruction = (
          f"{prefs_preamble}You are APOLLO OMNI AI, an advanced study assistant powered by"
          f" Llama 3.3 70B. Answer based on general knowledge.{chart_instruction}"
      )
      st.session_state.source_reference = (
          "<div class='source-box font-mono'>No active context. General weights"
          " used.</div>"
      )

    message_stream = [{"role": "system", "content": sys_instruction}]
    for msg in st.session_state.chat_history[-4:]:
      message_stream.append({"role": msg["role"], "content": msg["content"]})
    message_stream.append({
        "role": "user",
        "content": f"Context Matrix:\n{context_payload}\n\nQuery: {final_query}",
    })

    with chat_scroll_pane:
      with st.chat_message("assistant"):
        try:
          stream = generate_llm_stream(
              message_stream,
              GROQ_API_KEY,
              selected_model,
          )
          collected_tokens = st.write_stream(stream)
          if not collected_tokens or not str(collected_tokens).strip():
            collected_tokens = "⚠️ EMPTY RESPONSE."
            st.markdown(collected_tokens)
        except Exception as ex:
          collected_tokens = f"❌ FRAMEWORK API FAILURE: {ex}"
          st.markdown(collected_tokens)

        # ── TTS audio player (renders only when toggle is ON) ──────────────
        if st.session_state.get("voice_output_enabled", False):
          _tts_text = str(collected_tokens).strip()
          if _tts_text and not _tts_text.startswith("❌"):
            with st.spinner("🎶 Synthesizing voice..."):
              _audio_bytes = run_tts_synthesis(_tts_text)
            if _audio_bytes:
              st.audio(_audio_bytes, format="audio/mp3")

    st.session_state.chat_history.append(
        {"role": "assistant", "content": collected_tokens}
    )
    st.session_state.response_time = f"{time.time() - start_time:.2f}"
    st.rerun()


# ----------------- MAIN RIGHT: PPT STUDIO & CONTEXT -----------------
with col_tools:

  # --- PRESENTATION STUDIO ---
  st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
  st.markdown(
      "<div class='panel-header'>🎨 Presentation Studio</div>",
      unsafe_allow_html=True,
  )

  ppt_topic_input = st.text_input(
      "Presentation Topic:",
      placeholder="e.g. Quantum Computing or Boeing Planes",
      key="ppt_topic_in",
  )

  custom_prompt_input = st.text_area(
      "Custom Prompt / Specific Points (Optional):",
      placeholder=(
          "e.g. Focus on financial metrics, key breakthroughs, or specific"
          " architectural comparisons."
      ),
      key="ppt_custom_prompt_in",
      height=80,
  )

  # Check if indexed vector DB context is available
  has_rag = st.session_state.vector_db is not None
  if has_rag:
    st.markdown(
        f"<div style='font-size: 10px; color: #22c55e; font-family: \"JetBrains Mono\"; margin-bottom: 10px;'>"
        f"⚡ KNOWLEDGE BASE CONNECTED: Using {st.session_state.node_count} indexed vector blocks</div>",
        unsafe_allow_html=True,
    )
  else:
    st.markdown(
        "<div style='font-size: 10px; color: #a1a1aa; font-family: \"JetBrains Mono\"; margin-bottom: 10px;'>"
        "ℹ️ No indexed blocks found. Crawl the web or upload documents to anchor slides in specific context.</div>",
        unsafe_allow_html=True,
    )
  if st.button("🚀 GENERATE SLIDE DECK (GROQ LPU)", use_container_width=True):
    if not GROQ_API_KEY:
      st.error("Missing GROQ_API_KEY in Streamlit secrets.")
    elif ppt_topic_input:
      with st.spinner("Retrieving indexed blocks & generating presentation via Groq..."):
        ppt_context = ""
        if st.session_state.vector_db is not None:
          query = f"{ppt_topic_input} {custom_prompt_input}".strip()
          retriever = st.session_state.vector_db.as_retriever(search_kwargs={"k": 6})
          matched_nodes = retriever.invoke(query)
          ppt_context = "\n\n".join([
              f"[{node.metadata.get('source', 'Unknown')}]\n{node.page_content}"
              for node in matched_nodes
          ])

        new_slides, status = generate_slides_with_groq(
            topic=ppt_topic_input,
            custom_instructions=custom_prompt_input,
            context=ppt_context,
            groq_key=GROQ_API_KEY,
            user_prefs=st.session_state.get("user_prefs"),
        )
        if new_slides:
          st.session_state.slides_data = new_slides
          st.success("New slide deck generated using indexed blocks!")
          st.rerun()
        else:
          st.error(f"Generation Error: {status}")

  with st.expander("✏️ Live Slide Editor", expanded=True):
    if not st.session_state.slides_data or not isinstance(
        st.session_state.slides_data, list
    ):
      st.session_state.slides_data = [{
          "title": "Welcome to Apollo Omni AI",
          "subtitle": "Awaiting Presentation Prompt",
          "image_keyword": "abstract technology minimalist",
          "cards": [{
              "heading": "Getting Started",
              "text": (
                  "Enter a topic above to generate a new presentation deck"
                  " using your indexed knowledge base."
              ),
          }],
      }]

    tabs = st.tabs(
        [f"S{i+1}" for i in range(len(st.session_state.slides_data))]
    )

    for i, tab in enumerate(tabs):
      with tab:
        slide_info = st.session_state.slides_data[i]
        st.session_state.slides_data[i]["title"] = st.text_input(
            f"Title {i+1}", slide_info.get("title", ""), key=f"t_{i}"
        )
        st.session_state.slides_data[i]["subtitle"] = st.text_input(
            f"Subtitle {i+1}", slide_info.get("subtitle", ""), key=f"sub_{i}"
        )
        st.session_state.slides_data[i]["image_keyword"] = st.text_input(
            f"Image {i+1}", slide_info.get("image_keyword", ""), key=f"img_{i}"
        )

        cards = slide_info.get("cards", [])
        if not isinstance(cards, list):
          cards = [{"heading": "Detail", "text": str(cards)}]

        for j, card in enumerate(cards):
          st.markdown(
              f"<div style='font-size: 11px; font-weight: bold; margin-top:"
              f" 10px; color: #a1a1aa;'>Card {j+1}</div>",
              unsafe_allow_html=True,
          )
          if isinstance(card, dict):
            cards[j]["heading"] = st.text_input(
                f"Heading",
                card.get("heading", ""),
                key=f"ch_{i}_{j}",
                label_visibility="collapsed",
            )
            cards[j]["text"] = st.text_area(
                f"Text",
                card.get("text", ""),
                key=f"ct_{i}_{j}",
                label_visibility="collapsed",
            )
          else:
            cards[j] = {
                "heading": "Note",
                "text": st.text_input(
                    f"Card {j+1}",
                    str(card),
                    key=f"ct_{i}_{j}",
                    label_visibility="collapsed",
                ),
            }
        st.session_state.slides_data[i]["cards"] = cards

  if st.button("📥 EXPORT .PPTX", use_container_width=True):
    with st.spinner("Building PowerPoint file..."):
      file_path = create_gamma_style_pptx(st.session_state.slides_data)
      with open(file_path, "rb") as f:
        st.download_button(
            label="DOWNLOAD FILE",
            data=f,
            file_name="Apollo_Presentation.pptx",
            mime=(
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ),
            use_container_width=True,
        )
  st.markdown("</div>", unsafe_allow_html=True)

  # --- VIDEO GENERATOR (standalone module) ---
  render_video_generator_ui(
      groq_key=GROQ_API_KEY,
      kling_key=KLING_API_KEY,
      vector_db=st.session_state.vector_db,
      embedder=embedder,
      user_prefs=st.session_state.get("user_prefs"),
  )

  # --- ACTIVE CONTEXT VIEWER ---
  st.markdown("<div class='glass-panel'>", unsafe_allow_html=True)
  st.markdown(
      "<div class='panel-header'>📑 Active Context View</div>",
      unsafe_allow_html=True,
  )
  st.markdown(st.session_state.source_reference, unsafe_allow_html=True)
  st.markdown("</div>", unsafe_allow_html=True)
