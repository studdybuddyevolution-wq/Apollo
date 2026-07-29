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

# Import the interactive Plotly chart engine
from charts import render_dynamic_chart_from_text

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
  GEMINI_API_KEY = st.secrets.get(
      "GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", "")
  )
except Exception:
  GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


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
  st.session_state.response_time = "0.00s"
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

# Gamma AI Style Initial Slides State
if "slides_data" not in st.session_state:
  st.session_state.slides_data = [
      {
          "title": "Artificial Intelligence: Foundational Overview",
          "subtitle": (
              "Understanding Cognitive Architecture and Modern Computing"
          ),
          "image_keyword": (
              "futuristic artificial intelligence neural network dark blue glow"
          ),
          "cards": [
              {
                  "heading": "Core Definition",
                  "text": (
                      "Artificial Intelligence (AI) refers to the simulation of"
                      " human intelligence in machines programmed to think,"
                      " learn, reason, and make autonomous decisions."
                  ),
              },
              {
                  "heading": "Historical Evolution",
                  "text": (
                      "Evolved from symbolic logic and rule-based expert systems"
                      " in the 1950s to modern statistical learning, deep"
                      " neural networks, and generative models."
                  ),
              },
              {
                  "heading": "Primary Paradigm Shift",
                  "text": (
                      "Shifting from explicit hard-coded software engineering to"
                      " data-driven pattern recognition and self-improving"
                      " cognitive algorithms."
                  ),
              },
          ],
      },
      {
          "title": "Types of AI by Capability",
          "subtitle": (
              "Classification Based on Performance & Autonomy Levels"
          ),
          "image_keyword": (
              "futuristic robot brain technology cybernetic interface"
          ),
          "cards": [
              {
                  "heading": "Narrow AI (ANI)",
                  "text": (
                      "Specialized AI designed to perform dedicated tasks with"
                      " high proficiency (e.g., Siri, facial recognition, search"
                      " engines). Cannot operate outside its domain."
                  ),
              },
              {
                  "heading": "General AI (AGI)",
                  "text": (
                      "Hypothetical AI possessing human-level intelligence across"
                      " diverse domains, capable of transfer learning, abstract"
                      " reasoning, and adaptability."
                  ),
              },
              {
                  "heading": "Super AI (ASI)",
                  "text": (
                      "Theoretical future state where artificial systems"
                      " surpass human intelligence in all creative,"
                      " scientific, emotional, and strategic domains."
                  ),
              },
          ],
      },
      {
          "title": "Primary Domains of Artificial Intelligence",
          "subtitle": "Core Technical Branches and Specialized Fields",
          "image_keyword": (
              "machine learning deep learning data visual science concept"
          ),
          "cards": [
              {
                  "heading": "Machine & Deep Learning",
                  "text": (
                      "Statistical foundation allowing algorithms to parse"
                      " massive datasets, optimize parameters, and construct"
                      " predictive neural models."
                  ),
              },
              {
                  "heading": "Natural Language Processing (NLP)",
                  "text": (
                      "Enables machines to comprehend, interpret, generate, and"
                      " translate human languages via transformer architectures"
                      " and semantic analysis."
                  ),
              },
              {
                  "heading": "Computer Vision & Visual AI",
                  "text": (
                      "Enables software to extract structured context from"
                      " digital images and video streams for object tracking and"
                      " visual diagnostics."
                  ),
              },
              {
                  "heading": "Robotics & Autonomous Systems",
                  "text": (
                      "Integrates physical actuators, sensor fusion, and spatial"
                      " navigation algorithms for hardware operational autonomy."
                  ),
              },
          ],
      },
  ]

# 6. Multi-Provider Model Matrix
MODEL_OPTIONS = {
    "Qwen 3.6 27B (Groq LPU)": {
        "provider": "groq",
        "model_id": "qwen/qwen3.6-27b",
        "desc": "Alibaba Qwen 3.6 running at ultra-fast inference speed via Groq.",
    },
    "Meta Llama 3.3 70B (Groq)": {
        "provider": "groq",
        "model_id": "llama-3.3-70b-versatile",
        "desc": "Massive 70B model running with exceptional speed on Groq.",
    },
    "Google Gemma 4 26B (OpenRouter)": {
        "provider": "openrouter",
        "model_id": "google/gemma-4-26b-a4b-it:free",
        "desc": "Google's efficient model via OpenRouter gateway.",
    },
}


# 7. Image Engine
def fetch_image_by_keyword(keyword):
  if not keyword:
    keyword = "artificial intelligence neural technology"

  clean_kw = re.sub(r"[^\w\s]", "", keyword).strip()
  prompt_encoded = urllib.parse.quote(
      f"sleek modern technological visual representation of {clean_kw}, high"
      " resolution, 8k, dark aesthetic, minimalist design"
  )

  pollinations_url = f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){prompt_encoded}?width=800&height=600&seed={abs(hash(clean_kw)) % 100000}&nologo=true"

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


# 8. Gamma AI PPTX Builder Engine
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


# 9. Unified LLM Streamer
def generate_llm_stream(messages, groq_key, or_token, selected_model_name):
  model_cfg = MODEL_OPTIONS.get(selected_model_name, {})
  provider = model_cfg.get("provider", "groq")
  model_id = model_cfg.get("model_id", "")

  if provider == "groq":
    if not groq_key or not groq_key.startswith("gsk_"):
      yield (
          "❌ MISSING CONFIGURATION: Please set a valid 'GROQ_API_KEY' starting"
          " with 'gsk_' in Streamlit Secrets."
      )
      return
    try:
      client = Groq(api_key=groq_key.strip())
      stream = client.chat.completions.create(
          model=model_id,
          messages=messages,
          temperature=0.3,
          max_tokens=2048,
          stream=True,
      )
      for chunk in stream:
        token_text = chunk.choices[0].delta.content or ""
        if token_text:
          yield token_text
    except Exception as e:
      yield f"❌ Groq SDK Failure: {str(e)}"
      return
  else:
    if not or_token or not or_token.startswith("sk-or-"):
      yield (
          "❌ MISSING CONFIGURATION: Please set a valid 'OPENROUTER_API_KEY'"
          " starting with 'sk-or-' in Streamlit Secrets."
      )
      return
    url = "[https://openrouter.ai/api/v1/chat/completions](https://openrouter.ai/api/v1/chat/completions)"
    headers = {
        "Authorization": f"Bearer {or_token.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8501",
        "X-Title": "APOLLO OMNI",
    }
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2048,
        "stream": True,
    }
    try:
      response = requests.post(
          url, headers=headers, json=payload, stream=True, timeout=30
      )
      if response.status_code != 200:
        yield f"❌ API Error ({response.status_code}): {response.text}"
        return
      for line in response.iter_lines():
        if line:
          decoded = line.decode("utf-8").strip()
          if decoded.startswith("data: "):
            data_str = decoded[6:]
            if data_str == "[DONE]":
              break
            try:
              data_json = json.loads(data_str)
              token_text = (
                  data_json.get("choices", [{}])[0]
                  .get("delta", {})
                  .get("content", "")
              )
              if token_text:
                yield token_text
            except Exception:
              pass
    except Exception as e:
      yield f"❌ Network Failure: {str(e)}"


# 10. ROBUST SLIDE GENERATOR (COT SUPPRESSION + STRICT PARSER)
def parse_robust_json(raw_text):
  if not raw_text:
    return None

  # Clean out thinking blocks if present
  clean_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)
  if "</think>" in clean_text:
    clean_text = clean_text.split("</think>")[-1]

  # Slice directly from first '{' to last '}'
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


def generate_slides_with_qwen(topic, groq_key=""):
  groq_key = groq_key.strip() if groq_key else ""

  if not groq_key or not groq_key.startswith("gsk_"):
    return (
        None,
        "Missing active GROQ_API_KEY starting with 'gsk_' in Streamlit Secrets.",
    )

  prompt = f"""Create a detailed presentation on: '{topic}'.

DO NOT output <think> tags, chain of thought reasoning, or introductory conversational filler.
OUTPUT raw JSON ONLY. Start directly with '{{' and end with '}}'.

SCHEMA REQUIRED:
{{
  "slides": [
    {{
      "title": "Slide Title",
      "subtitle": "Informative Subtitle",
      "image_keyword": "descriptive technology topic image prompt",
      "cards": [
        {{
          "heading": "Core Subtopic Heading",
          "text": "Detailed, multi-sentence contextual explanation with deep insights."
        }},
        {{
          "heading": "Technical Mechanics",
          "text": "Detailed multi-sentence explanation of principles, applications, or mechanisms."
        }},
        {{
          "heading": "Domain Relevance",
          "text": "Detailed multi-sentence explanation of real-world implementation."
        }}
      ]
    }}
  ]
}}"""

  client = Groq(api_key=groq_key)

  # Model attempt priority: Qwen 3.6 -> Fallback to Llama 3.3 70B
  models_to_try = ["qwen/qwen3.6-27b", "llama-3.3-70b-versatile"]

  for model_id in models_to_try:
    try:
      completion = client.chat.completions.create(
          model=model_id,
          messages=[
              {
                  "role": "system",
                  "content": (
                      "You are a presentation JSON generator. You output ONLY"
                      " raw JSON without thinking tags or commentary."
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
      "Failed to parse JSON across available models. Please try clicking Gemini"
      " Gamma or retry.",
  )


# 11. Legacy Gemini Slide Generator
def generate_slides_with_gemini(topic, gemini_key):
  if not gemini_key:
    return None, "Missing GEMINI_API_KEY in Streamlit Secrets."
  url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=){gemini_key.strip()}"
  headers = {"Content-Type": "application/json"}

  prompt = f"""Create an in-depth academic presentation outline about '{topic}'.
Return ONLY a valid JSON object with key 'slides' containing 5-6 detailed slide objects.
Do NOT include commentary outside JSON.
Schema:
{{
  "slides": [
    {{
      "title": "Title",
      "subtitle": "Subtitle",
      "image_keyword": "descriptive technology prompt",
      "cards": [
        {{"heading": "Heading", "text": "Comprehensive multi-sentence explanation text."}}
      ]
    }}
  ]
}}"""

  payload = {
      "contents": [{"parts": [{"text": prompt}]}],
      "generationConfig": {
          "temperature": 0.3,
          "responseMimeType": "application/json",
      },
  }

  try:
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code == 200:
      data = response.json()
      text_output = data["candidates"][0]["content"]["parts"][0]["text"]
      parsed_json = json.loads(text_output)
      return parsed_json.get("slides", parsed_json), "Success"
    else:
      return None, f"Gemini API Error ({response.status_code}): {response.text}"
  except Exception as e:
    return None, str(e)


# 12. Email Dispatcher Function
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
    @import url('[https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap](https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap)');
    
    :root {
        --background-color: #0f0f11 !important;
        --secondary-background-color: rgba(24, 24, 27, 0.8) !important;
        --text-color: #e5e7eb !important;
        --primary-color: #f97316 !important;
    }

    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { 
        background-color: #0f0f11 !important; 
        background-image: linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px) !important;
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
        background: rgba(24, 24, 27, 0.8);
        backdrop-filter: blur(12px);
        padding: 10px 24px;
        margin-top: -60px;
        margin-bottom: 30px;
        border-radius: 0 0 12px 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .status-badge {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        background: rgba(34, 197, 94, 0.1);
        color: #4ade80 !important;
        border: 1px solid rgba(34, 197, 94, 0.2);
        padding: 4px 10px;
        border-radius: 4px;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    
    .cyber-card { 
        background: rgba(24, 24, 27, 0.8) !important; 
        backdrop-filter: blur(8px); 
        border: 1px solid rgba(255, 255, 255, 0.1) !important; 
        border-radius: 8px; 
        padding: 16px; 
        margin-bottom: 20px; 
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .panel-header {
        font-size: 0.875rem;
        font-weight: 600;
        letter-spacing: 0.05em;
        color: #d4d4d8 !important;
        text-transform: uppercase;
        margin-bottom: 16px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        padding-bottom: 8px;
    }

    .metric-value { font-size: 1.875rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: #fff !important; text-shadow: 0 0 10px rgba(249, 115, 22, 0.5); }
    .metric-title { font-size: 0.75rem; color: #71717a !important; text-transform: uppercase; font-family: 'JetBrains Mono', monospace; margin-bottom: 4px; }

    div[data-testid="stChatMessage"]:has(div[aria-label="Chat message from user"]) { 
        background: rgba(56, 189, 248, 0.05) !important; 
        border-left: 2px solid #38bdf8 !important; 
        border-radius: 4px 12px 12px 4px !important; 
    }
    div[data-testid="stChatMessage"]:has(div[aria-label="Chat message from assistant"]) { 
        background: rgba(249, 115, 22, 0.05) !important; 
        border-left: 2px solid #f97316 !important; 
        border-radius: 4px 12px 12px 4px !important; 
        box-shadow: inset 4px 0 0 rgba(249, 115, 22, 0.2);
    }
    
    div[data-testid="stChatInput"] textarea,
    div[data-testid="stChatInput"] { 
        background-color: #0a0a0c !important; 
        border-color: rgba(255, 255, 255, 0.1) !important; 
        color: white !important; 
        font-family: 'JetBrains Mono', monospace !important;
    }
    
    div[data-baseweb="input"] > div {
        background-color: #0a0a0c !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
    }
    div[data-baseweb="input"] input {
        color: white !important;
        background-color: transparent !important;
    }

    .stButton button {
        background: linear-gradient(180deg, #f97316 0%, #ea580c 100%) !important;
        color: #fff !important;
        border: none !important;
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
</style>
""",
    unsafe_allow_html=True,
)

# Custom Header
logo_loaded = False
if os.path.exists("logo.png"):
  try:
    with Image.open("logo.png") as img:
      img.verify()
    col_logo, col_badge = st.columns([8, 2])
    with col_logo:
      st.image("logo.png", width=220)
    with col_badge:
      st.markdown(
          "<div style='text-align: right; margin-top: 15px;'><span"
          " class='status-badge'>● PERSISTENT SESSION ACTIVE</span></div>",
          unsafe_allow_html=True,
      )
    st.markdown(
        "<hr style='border-color: rgba(255,255,255,0.1); margin-top: -10px;"
        " margin-bottom: 30px;'>",
        unsafe_allow_html=True,
    )
    logo_loaded = True
  except Exception:
    pass

if not logo_loaded:
  st.markdown(
      """
    <div class='header-bar'>
        <div class='header-left'>
            <div style='font-size: 1.25rem; font-weight: 700; letter-spacing: 0.05em; color: white;'>APOLLO <span style='color: #f97316;'>OMNI AI</span></div>
        </div>
        <div class='status-badge'>● PERSISTENT SESSION ACTIVE</div>
    </div>
    """,
      unsafe_allow_html=True,
  )

# ================= AUTHENTICATION GATEKEEPER =================
if not st.session_state.authenticated:
  st.markdown(
      "<div style='text-align: center; margin-top: 80px;'><h2"
      " style='color: #f97316;'>🔒 Restricted Access</h2><p"
      " style='color: #a1a1aa;'>Verify your Somaiya university email to"
      " receive a secure access code.</p></div>",
      unsafe_allow_html=True,
  )

  col_space1, col_login, col_space3 = st.columns([3, 4, 3])
  with col_login:
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    if not st.session_state.otp_sent:
      email_input = st.text_input(
          "University Email", placeholder="your.name@somaiya.edu"
      )
      if st.button("SEND ACCESS CODE", use_container_width=True):
        if email_input.strip().lower().endswith("@somaiya.edu"):
          with st.spinner("Dispatching secure code..."):
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
              st.error(f"❌ Failed to send email: {error_msg}")
        else:
          st.error(
              "❌ Access Denied. Only @somaiya.edu accounts are permitted."
          )
    else:
      st.success(f"Secure code sent to {st.session_state.user_email}")
      otp_input = st.text_input("Enter 6-Digit Code", type="password")

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
          st.error("❌ Incorrect code. Please check your email and try again.")

      st.markdown("<br>", unsafe_allow_html=True)
      if st.button("Use a different email", type="secondary"):
        st.session_state.otp_sent = False
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
  st.stop()
# ==============================================================

col_left, col_mid, col_right = st.columns([3, 6, 3], gap="large")

# ================= LEFT COLUMN: GAMMA AI PPT STUDIO & INGESTION =================
with col_left:
  st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
  st.markdown(
      "<div class='panel-header'>⚙️ Multi-Model Engine</div>",
      unsafe_allow_html=True,
  )
  selected_model = st.selectbox(
      "API Gateway Endpoint:", options=list(MODEL_OPTIONS.keys()), index=0
  )
  st.caption(f"**Desc:** {MODEL_OPTIONS[selected_model]['desc']}")
  st.markdown("</div>", unsafe_allow_html=True)

  # --- GAMMA AI PPT STUDIO ---
  st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
  st.markdown(
      "<div class='panel-header'>🎨 Gamma AI PPT Studio</div>",
      unsafe_allow_html=True,
  )

  ppt_topic_input = st.text_input(
      "Presentation Topic:",
      placeholder="e.g. Domains and Types of Artificial Intelligence",
  )

  btn_qwen, btn_gemini = st.columns(2)
  with btn_qwen:
    if st.button("🚀 Qwen Gamma", use_container_width=True):
      if not GROQ_API_KEY:
        st.error("Please add GROQ_API_KEY to your Streamlit secrets.")
      elif ppt_topic_input:
        with st.spinner("Generating deep slide structure via Qwen 3.6..."):
          new_slides, status_msg = generate_slides_with_qwen(
              ppt_topic_input, GROQ_API_KEY
          )
          if new_slides and isinstance(new_slides, list):
            st.session_state.slides_data = new_slides
            st.success(f"Deck generated! ({status_msg})")
            st.rerun()
          else:
            st.error(f"Generation Failed: {status_msg}")

  with btn_gemini:
    if st.button("✨ Gemini Gamma", use_container_width=True):
      if not GEMINI_API_KEY:
        st.error("Please add GEMINI_API_KEY to your Streamlit secrets.")
      elif ppt_topic_input:
        with st.spinner("Generating deep slide structure via Gemini..."):
          new_slides, err = generate_slides_with_gemini(
              ppt_topic_input, GEMINI_API_KEY
          )
          if new_slides and isinstance(new_slides, list):
            st.session_state.slides_data = new_slides
            st.success("Generated comprehensive deck with Gemini!")
            st.rerun()
          else:
            st.error(f"Generation Failed: {err}")

  with st.expander("✏️ Live Slide Layout & Cards Editor", expanded=False):
    if not st.session_state.slides_data or not isinstance(
        st.session_state.slides_data, list
    ):
      st.session_state.slides_data = [{
          "title": "Slide 1",
          "subtitle": "Overview",
          "image_keyword": "technology",
          "cards": [{"heading": "Card 1", "text": "Details"}],
      }]

    tabs = st.tabs(
        [f"Slide {i+1}" for i in range(len(st.session_state.slides_data))]
    )

    for i, tab in enumerate(tabs):
      with tab:
        slide_info = st.session_state.slides_data[i]
        if not isinstance(slide_info, dict):
          slide_info = {
              "title": f"Slide {i+1}",
              "subtitle": "",
              "image_keyword": "ai",
              "cards": [],
          }
          st.session_state.slides_data[i] = slide_info

        st.session_state.slides_data[i]["title"] = st.text_input(
            f"Title {i+1}", slide_info.get("title", ""), key=f"t_{i}"
        )
        st.session_state.slides_data[i]["subtitle"] = st.text_input(
            f"Subtitle {i+1}", slide_info.get("subtitle", ""), key=f"sub_{i}"
        )
        st.session_state.slides_data[i]["image_keyword"] = st.text_input(
            f"Image Keyword {i+1}",
            slide_info.get("image_keyword", ""),
            key=f"img_{i}",
        )

        cards = slide_info.get("cards", [])
        if not isinstance(cards, list):
          cards = [{"heading": "Detail", "text": str(cards)}]

        for j, card in enumerate(cards):
          st.markdown(f"**Card Box {j+1}**")
          if isinstance(card, dict):
            h_val = st.text_input(
                f"Card {j+1} Heading",
                card.get("heading", ""),
                key=f"ch_{i}_{j}",
            )
            b_val = st.text_area(
                f"Card {j+1} Text", card.get("text", ""), key=f"ct_{i}_{j}"
            )
            cards[j] = {"heading": h_val, "text": b_val}
          else:
            b_val = st.text_input(f"Card {j+1}", str(card), key=f"ct_{i}_{j}")
            cards[j] = {"heading": "Note", "text": b_val}
        st.session_state.slides_data[i]["cards"] = cards

  if st.button("📥 Export Gamma .pptx File", use_container_width=True):
    with st.spinner("Building modern widescreen slide deck with pictures..."):
      file_path = create_gamma_style_pptx(st.session_state.slides_data)
      with open(file_path, "rb") as f:
        st.download_button(
            label="Click here to download deck",
            data=f,
            file_name="Gamma_Style_Presentation.pptx",
            mime=(
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ),
            use_container_width=True,
        )
  st.markdown("</div>", unsafe_allow_html=True)

  # --- SECURED WEB SEARCH INDEXER ---
  st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
  st.markdown(
      "<div class='panel-header'>🌐 AI Web Search (Tavily)</div>",
      unsafe_allow_html=True,
  )

  web_query = st.text_input(
      "Enter topic to scrape & index...",
      placeholder="e.g. Current AI news",
      label_visibility="collapsed",
  )

  if st.button("SEARCH & INDEX", use_container_width=True):
    if not TAVILY_API_KEY or not TAVILY_API_KEY.startswith("tvly-"):
      st.error("No active Tavily API Key found in Streamlit Secrets.")
    elif web_query:
      with st.spinner("Executing secure web retrieval..."):
        try:
          api_url = "[https://api.tavily.com/search](https://api.tavily.com/search)"
          payload = {
              "api_key": TAVILY_API_KEY.strip(),
              "query": web_query,
              "search_depth": "advanced",
              "max_results": 8,
          }
          response = requests.post(api_url, json=payload, timeout=25)
          if response.status_code == 200:
            results = response.json().get("results", [])
            web_docs = [
                Document(
                    page_content=(
                        f"Title: {r.get('title')}\nSource:"
                        f" {r.get('url')}\nContext: {r.get('content')}"
                    ),
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
              st.success(f"Indexed {len(chunks)} verified blocks!")
        except Exception as e:
          st.error(f"Search failed: {str(e)}")
  st.markdown("</div>", unsafe_allow_html=True)

  # --- LOCAL DOCUMENTS INDEXER ---
  st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
  st.markdown(
      "<div class='panel-header'>📚 Local Documents</div>",
      unsafe_allow_html=True,
  )
  uploaded_files = st.file_uploader(
      "Upload course materials...",
      type=["pdf", "txt"],
      accept_multiple_files=True,
      label_visibility="collapsed",
      key="file_in",
  )
  if st.button("SYNC KNOWLEDGE BASE", use_container_width=True):
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
            st.success(f"Indexed {len(chunks)} document blocks.")
  st.markdown("</div>", unsafe_allow_html=True)

# ================= MIDDLE COLUMN: MAIN STUDY CONSOLE =================
with col_mid:
  if not st.session_state.chat_history:
    st.markdown(
        """
        <div style='margin-top: 50px; margin-bottom: 30px; text-align: center;'>
            <h2 style='color: #f97316; font-family: "Inter", sans-serif; font-weight: 700;'>Study Console Initialized</h2>
            <p style='color: #a1a1aa; font-family: "JetBrains Mono", monospace; font-size: 0.85rem;'>Use the left panel to generate Gamma AI presentations, index Web Data, or chat here.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

  chat_scroll_pane = st.container(height=650, border=False)

  # Render existing chat history using charts.py for assistant messages
  with chat_scroll_pane:
    for msg in st.session_state.chat_history:
      with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
          render_dynamic_chart_from_text(msg["content"])
        else:
          st.markdown(msg["content"])

  user_query = st.chat_input("Enter your query...")

  if user_query:
    st.session_state.chat_history.append({"role": "user", "content": user_query})
    start_time = time.time()
    context_payload = ""

    # Prompt extension to instruct LLM on chart output format
    chart_instruction = (
        "\n\nIf the user asks for a chart, graph, data visualization, or numerical comparison, "
        "append a JSON code block at the very end of your response following this exact structure:\n"
        "```json\n"
        "{\n"
        '  "type": "bar",  // options: "bar", "line", or "pie"\n'
        '  "title": "Chart Title",\n'
        '  "x_label": "X Axis Label",\n'
        '  "y_label": "Y Axis Label",\n'
        '  "x": ["Category A", "Category B"],\n'
        '  "y": [10, 20]\n'
        "}\n"
        "```"
    )

    if st.session_state.vector_db is not None:
      retriever = st.session_state.vector_db.as_retriever(
          search_kwargs={"k": 5}
      )
      matched_nodes = retriever.invoke(user_query)
      context_payload = "\n\n".join([
          f"[{node.metadata.get('source', 'Unknown')}]\n{node.page_content}"
          for node in matched_nodes
      ])
      sys_instruction = (
          "You are APOLLO OMNI AI, an advanced study buddy. Answer using ONLY"
          f" context below.{chart_instruction}"
      )
      clean_ctx = (
          context_payload.replace("<", "&lt;")
          .replace(">", "&gt;")
          .replace("\n", "<br>")
      )
      st.session_state.source_reference = (
          f"<div class='source-box'><strong>Active Context"
          f" (RAG):</strong><br><br>{clean_ctx}</div>"
      )
    else:
      sys_instruction = (
          "You are APOLLO OMNI AI, an advanced study buddy. Answer based on"
          f" general knowledge.{chart_instruction}"
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
        "content": (
            f"Context Matrix:\n{context_payload}\n\nQuery: {user_query}"
        ),
    })

    with chat_scroll_pane:
      with st.chat_message("assistant"):
        try:
          stream = generate_llm_stream(
              message_stream, GROQ_API_KEY, OPENROUTER_API_KEY, selected_model
          )
          collected_tokens = st.write_stream(stream)
          if not collected_tokens or not str(collected_tokens).strip():
            collected_tokens = "⚠️ EMPTY RESPONSE."
            st.markdown(collected_tokens)
        except Exception as ex:
          collected_tokens = f"❌ FRAMEWORK API FAILURE: {ex}"
          st.markdown(collected_tokens)

    st.session_state.chat_history.append(
        {"role": "assistant", "content": collected_tokens}
    )
    st.session_state.response_time = f"{time.time() - start_time:.2f}s"
    st.rerun()

# ================= RIGHT COLUMN: PERFORMANCE & TELEMETRY MATRIX =================
with col_right:
  st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
  st.markdown(
      "<div class='panel-header'>📊 Analytics Dashboard</div>",
      unsafe_allow_html=True,
  )
  st.markdown(
      f"<div><div class='metric-title'>Inference Latency</div><div"
      f" class='metric-value'>{st.session_state.response_time}</div></div>",
      unsafe_allow_html=True,
  )
  st.markdown(
      "<hr style='border-color: rgba(255,255,255,0.1); margin: 15px 0;'>",
      unsafe_allow_html=True,
  )
  st.markdown(
      f"<div><div class='metric-title'>Indexed Documents</div><div"
      f" class='metric-value'>{st.session_state.node_count}</div></div>",
      unsafe_allow_html=True,
  )
  st.markdown("</div>", unsafe_allow_html=True)

  st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
  st.markdown(
      "<div class='panel-header'>📑 Verified Retrieval Matrix</div>",
      unsafe_allow_html=True,
  )
  st.markdown(st.session_state.source_reference, unsafe_allow_html=True)
  st.markdown("</div>", unsafe_allow_html=True)

  st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
  st.markdown(
      "<div class='panel-header'>🛠️ Session Actions</div>",
      unsafe_allow_html=True,
  )
  c1, c2 = st.columns(2)
  with c1:
    if st.button("PURGE", use_container_width=True):
      st.session_state.chat_history = []
      st.session_state.vector_db = None
      st.session_state.node_count = 0
      st.session_state.response_time = "0.00s"
      st.session_state.source_reference = (
          "<div class='source-box font-mono'>Awaiting vector alignment...</div>"
      )
      st.rerun()
  with c2:
    chat_log = "\n".join([
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in st.session_state.chat_history
    ])
    st.download_button(
        "EXPORT",
        data=chat_log,
        file_name="apollo_log.txt",
        mime="text/plain",
        use_container_width=True,
    )

  st.markdown("<br>", unsafe_allow_html=True)
  if st.button("LOG OUT", use_container_width=True, type="secondary"):
    st.session_state.authenticated = False
    cookie_manager.delete("apollo_somaiya_session")
    st.rerun()

  st.markdown("</div>", unsafe_allow_html=True)
