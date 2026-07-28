# Updated app.py
# (Based on original streamlit_app.py with PPT generation moved to ppt_engine.create_gamma_style_pptx,
# improved JSON parsing/enforcement for LLM outputs, and step-by-step status updates.)
import datetime
import json
import os
import random
import re
import requests
import smtplib
import tempfile
import time
from email.mime.text import MIMEText
import extra_streamlit_components as stx
from groq import Groq
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from PIL import Image
from pptx import Presentation
import streamlit as st

# Import the new PPT engine
from ppt_engine import create_gamma_style_pptx, fetch_image_by_keyword

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

# Persistent Auth State Handling via Cookies (30-Day Persistence)
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

# NotebookLM-Style PPT Studio State
if "slides_data" not in st.session_state:
  st.session_state.slides_data = [
      {
          "title": "Introduction to Institutional AI",
          "bullets": [
              "Overview of Apollo Omni platform",
              "Secure @somaiya.edu integration",
          ],
      },
      {
          "title": "Core Architecture & Workflow",
          "bullets": [
              "Retrieval-Augmented Generation (RAG)",
              "Multi-model micro-agent routing",
          ],
      },
  ]

# 6. Multi-Provider Model Matrix
MODEL_OPTIONS = {
    "Qwen 3.6 27B (Groq LPU)": {
        "provider": "groq",
        "model_id": "qwen/qwen3.6-27b",
        "desc": (
            "Alibaba Qwen 3.6 running at blazingly fast inference speed via Groq"
            " LPUs."
        ),
    },
    "Meta Llama 3.3 70B (Groq)": {
        "provider": "groq",
        "model_id": "llama-3.3-70b-versatile",
        "desc": "Massive 70B model running with exceptional speed on Groq.",
    },
    "Google Gemma 4 26B (OpenRouter)": {
        "provider": "openrouter",
        "model_id": "google/gemma-4-26b-a4b-it:free",
        "desc": "Google's efficient 26B model via OpenRouter gateway.",
    },
}


# 7. Unified LLM Streamer (Using Groq SDK)
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
          max_tokens=1024,
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
    url = "https://openrouter.ai/api/v1/chat/completions"
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
        "max_tokens": 1024,
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


# 8. Qwen 3.6 PPT Generator Function using Groq SDK (STRICT JSON MODE)
def generate_slides_with_qwen(topic, groq_key=""):
  groq_key = groq_key.strip() if groq_key else ""

  if not groq_key or not groq_key.startswith("gsk_"):
    return (
        None,
        "Missing active GROQ_API_KEY starting with 'gsk_' in Streamlit Secrets.",
    )

  # Strong prompt enforcement to avoid topic bleed or injecting system/app context
  prompt = f"""Create a presentation outline about the single topic: '{topic}'.
Return ONLY a JSON object containing a single "slides" array with 4-6 slide objects.
Each slide object must have:
  - "title": short string (no mentions of 'Apollo' or 'Somaiya' or any system/RAG/service names)
  - "bullets": array of 2-6 short strings
Optional:
  - "image_keyword": a short keyword phrase to fetch an illustrative image

STRICT REQUIREMENTS:
- Output valid JSON exclusively, no markdown, no commentary, no explanation.
- Do NOT mention 'Apollo', 'Somaiya', 'RAG', or any internal service names anywhere in titles or bullets.
- Keep titles <= 60 chars and bullets <= 160 chars.
Example output:
{{ "slides": [ {{ "title": "Slide 1", "bullets": ["a","b"] }}, ... ] }}"""

  def robust_json_extract(raw_text: str):
    if not raw_text:
      return None
    text = raw_text

    # Strip <think>...</think> tags
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Remove markdown json fences
    text = text.replace("```json", "").replace("```", "")

    # Remove trailing commas in objects/arrays (best-effort)
    # remove ",]" or ",}" patterns
    text = re.sub(r',\s*([\]\}])', r'\1', text)

    # Find the first JSON object or array
    m = re.search(r'(\{.*\}|\[.*\])', text, flags=re.DOTALL)
    if m:
      candidate = m.group(0)
    else:
      candidate = text.strip()

    try:
      parsed = json.loads(candidate)
      # if it's an object with "slides", extract that
      if isinstance(parsed, dict) and "slides" in parsed and isinstance(parsed["slides"], list):
        # Filter out any slides that mention forbidden tokens
        filtered = []
        for s in parsed["slides"]:
          t = s.get("title", "")
          b = " ".join(s.get("bullets", [])) if isinstance(s.get("bullets", []), list) else ""
          if any(tok.lower() in (t + " " + b).lower() for tok in ["apollo", "somaiya", "rag"]):
            # strip forbidden mentions; best effort: reject slide
            continue
          filtered.append(s)
        return filtered
      # if parsed is list, return it as list of slides
      if isinstance(parsed, list):
        return parsed
    except Exception:
      # last attempt: try to balance braces by truncation heuristics
      try:
        # try to find the JSON substring by searching for first { and last }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
          substr = text[start:end + 1]
          substr = re.sub(r',\s*([\]\}])', r'\1', substr)
          parsed = json.loads(substr)
          return parsed.get("slides", parsed if isinstance(parsed, list) else None)
      except Exception:
        pass
    return None

  try:
    client = Groq(api_key=groq_key)
    try:
      completion = client.chat.completions.create(
          model="qwen/qwen3.6-27b",
          messages=[
              {"role": "system", "content": "You are a JSON only generator. Output valid JSON only."},
              {"role": "user", "content": prompt},
          ],
          response_format={"type": "json_object"},
          temperature=0.2,
      )
    except Exception:
      completion = client.chat.completions.create(
          model="qwen/qwen3.6-27b",
          messages=[
              {"role": "system", "content": "You are a JSON only generator. Output valid JSON only."},
              {"role": "user", "content": prompt},
          ],
          temperature=0.2,
      )

    raw_text = ""
    try:
      raw_text = completion.choices[0].message.content
    except Exception:
      raw_text = str(completion)

    parsed_slides = robust_json_extract(raw_text)
    if parsed_slides:
      return parsed_slides, "Success (Qwen 3.6 via Groq SDK)"
    else:
      snippet = raw_text[:240].replace("\n", " ") if raw_text else "Empty"
      return None, f"Could not parse response into slides. Model output start: '{snippet}'"
  except Exception as e:
    return None, f"Qwen Generation Error: {str(e)}"


# 9. Legacy Gemini PPT Generator Function (improved JSON extraction & isolation)
def get_best_active_gemini_model(gemini_key):
  try:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key.strip()}"
    response = requests.get(url, timeout=10)
    if response.status_code == 200:
      data = response.json()
      models_list = data.get("models", [])
      valid_models = []
      for m in models_list:
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" in methods:
          clean_name = m.get("name", "").replace("models/", "")
          if not any(
              deprecated in clean_name.lower()
              for deprecated in ["2.5-flash", "1.5-flash", "1.0"]
          ):
            valid_models.append(clean_name)
      for m in valid_models:
        if "flash" in m.lower():
          return m
      if valid_models:
        return valid_models[0]
  except Exception:
    pass
  return "gemini-2.0-flash"


def generate_slides_with_gemini(topic, gemini_key):
  if not gemini_key:
    return None, "Missing GEMINI_API_KEY in Streamlit Secrets."
  active_model = get_best_active_gemini_model(gemini_key)

  prompt = f"""Create a presentation outline purely about '{topic}'.
Return a single valid JSON array or object containing slides as in:
[{{"title":"...","bullets":["a","b"], "image_keyword":"..."}}, ...]
Requirements:
- Output only JSON, no markdown/code fences/no commentary.
- Avoid mentioning 'Apollo', 'Somaiya', 'RAG' or other platform or contexts.
- Titles <= 60 chars; bullets <= 160 chars.
"""

  url = f"https://generativelanguage.googleapis.com/v1beta/models/{active_model}:generateContent?key={gemini_key.strip()}"
  headers = {"Content-Type": "application/json"}

  payload = {
      "contents": [{"parts": [{"text": prompt}]}],
      "generationConfig": {
          "temperature": 0.4,
          "responseMimeType": "application/json",
      },
  }

  def _robust_parse(text: str):
    if not text:
      return None
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = text.replace("```json", "").replace("```", "")
    text = re.sub(r',\s*([\]\}])', r'\1', text)
    m = re.search(r'(\{.*\}|\[.*\])', text, flags=re.DOTALL)
    if not m:
      return None
    try:
      parsed = json.loads(m.group(0))
      if isinstance(parsed, dict) and "slides" in parsed:
        return parsed["slides"]
      if isinstance(parsed, list):
        return parsed
    except Exception:
      try:
        # try fallback bracket-balancing
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1 and end > start:
          substr = text[start:end+1]
          parsed = json.loads(substr)
          return parsed
      except Exception:
        pass
    return None

  try:
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code == 200:
      data = response.json()
      try:
        text_output = data["candidates"][0]["content"]["parts"][0]["text"]
      except Exception:
        text_output = json.dumps(data)
      parsed = _robust_parse(text_output)
      if parsed:
        return parsed, "Success"
      else:
        return None, f"Could not parse Gemini response start: '{text_output[:240]}'"
    else:
      return None, f"Gemini API Error ({response.status_code}): {response.text}"
  except Exception as e:
    return None, str(e)


# 10. Email Dispatcher Function
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


# 11. CSS Styling & Custom UI Layer
st.markdown(
    """
<style>
    @import url('[https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap](https://fonts.googleapis.com/css2?family=Inter:wght@400;500;6[...]
    
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
    .header-left { display: flex; align-items: center; gap: 15px; }
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

# Custom Brand Header Matrix
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

# ================= PERSISTENT DOMAIN OTP GATEKEEPER =================
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

# ================= LEFT COLUMN: INGESTION & QWEN PPT STUDIO =================
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

  # --- QWEN 3.6 & GEMINI POWERED PPT STUDIO ---
  st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
  st.markdown(
      "<div class='panel-header'>📊 Qwen 3.6 PPT Studio (Groq)</div>",
      unsafe_allow_html=True,
  )

  status_msg = []
  if GROQ_API_KEY:
    status_msg.append("⚡ Groq (Qwen 3.6)")
  if GEMINI_API_KEY:
    status_msg.append("✨ Gemini")

  if status_msg:
    st.markdown(
        f"<span style='font-size:0.8rem; color:#4ade80;'>Active Keys:"
        f" {', '.join(status_msg)}</span>",
        unsafe_allow_html=True,
    )
  else:
    st.markdown(
        "<span style='font-size:0.8rem; color:#f87171;'>❌ No API Keys"
        " Configured in Secrets</span>",
        unsafe_allow_html=True,
    )

  ppt_topic_input = st.text_input(
      "Presentation Topic:", placeholder="e.g. Quantum Cryptography"
  )

  btn_qwen, btn_gemini = st.columns(2)
  with btn_qwen:
    if st.button("🚀 Qwen 3.6 PPT", use_container_width=True):
      if not GROQ_API_KEY:
        st.error("Please add GROQ_API_KEY to your Streamlit secrets.")
      elif ppt_topic_input:
        with st.spinner("Generating slide structure via Qwen 3.6 (Groq)..."):
          new_slides, err = generate_slides_with_qwen(
              ppt_topic_input, GROQ_API_KEY
          )
          if new_slides and isinstance(new_slides, list):
            st.session_state.slides_data = new_slides
            st.success("Successfully generated slides via Qwen 3.6!")
            st.rerun()
          else:
            st.error(f"Qwen Generation Failed: {err}")

  with btn_gemini:
    if st.button("✨ Gemini PPT", use_container_width=True):
      if not GEMINI_API_KEY:
        st.error("Please add GEMINI_API_KEY to your Streamlit secrets.")
      elif ppt_topic_input:
        with st.spinner("Generating slide structure via Gemini..."):
          new_slides, err = generate_slides_with_gemini(
              ppt_topic_input, GEMINI_API_KEY
          )
          if new_slides and isinstance(new_slides, list):
            st.session_state.slides_data = new_slides
            st.success("Successfully generated slides via Gemini!")
            st.rerun()
          else:
            st.error(f"Gemini Generation Failed: {err}")

  with st.expander("✨ Open NotebookLM Slide Editor", expanded=False):
    st.markdown("Live-edit your generated slides before downloading.")

    if not st.session_state.slides_data or not isinstance(
        st.session_state.slides_data, list
    ):
      st.session_state.slides_data = [{
          "title": "Slide 1",
          "bullets": [
              "Add a bullet point or generate slides via Qwen/Gemini"
          ],
      }]

    tabs = st.tabs(
        [f"Slide {i+1}" for i in range(len(st.session_state.slides_data))]
    )

    for i, tab in enumerate(tabs):
      with tab:
        slide_info = st.session_state.slides_data[i]

        if isinstance(slide_info, str):
          slide_info = {"title": slide_info, "bullets": []}
          st.session_state.slides_data[i] = slide_info
        elif not isinstance(slide_info, dict):
          slide_info = {"title": f"Slide {i+1}", "bullets": []}
          st.session_state.slides_data[i] = slide_info

        new_title = st.text_input(
            f"Title {i+1}", slide_info.get("title", ""), key=f"title_{i}"
        )
        st.session_state.slides_data[i]["title"] = new_title

        updated_bullets = []
        bullets_list = slide_info.get("bullets", [])
        if not isinstance(bullets_list, list):
          bullets_list = [str(bullets_list)]

        for j, bullet in enumerate(bullets_list):
          b_val = st.text_input(
              f"Bullet {j+1}", bullet, key=f"bullet_{i}_{j}"
          )
          updated_bullets.append(b_val)
        st.session_state.slides_data[i]["bullets"] = updated_bullets

    # New: Use create_gamma_style_pptx from ppt_engine.py
    def _generate_and_download_pptx():
      # Use st.status() if available, otherwise fallback to st.empty
      status_func = getattr(st, "status", None)
      status_ctx = status_func("Starting...") if status_func else st.empty()
      temp_output = None
      temp_images_to_cleanup = []
      try:
        # Stage 1
        if hasattr(status_ctx, "text") and callable(getattr(status_ctx, "text")):
          status_ctx.text("1/4 — Generating slide content outline...")
        else:
          status_ctx.markdown("**1/4 — Generating slide content outline...**")

        slides_payload = st.session_state.slides_data

        # Stage 2
        if hasattr(status_ctx, "text") and callable(getattr(status_ctx, "text")):
          status_ctx.text("2/4 — Fetching visual assets per slide...")
        else:
          status_ctx.markdown("**2/4 — Fetching visual assets per slide...**")

        # Pre-fetch a few images per slide to speed up layout (non blocking)
        # We'll try to fetch at most 1 image per slide keyword (best-effort)
        for s in slides_payload:
          kw = s.get("image_keyword") or (s.get("bullets") and s.get("bullets")[0]) or s.get("title")
          if kw:
            try:
              img_path = fetch_image_by_keyword(str(kw))
              if img_path:
                # attach local image path to slide for engine to pick up
                s["_fetched_image"] = img_path
                temp_images_to_cleanup.append(img_path)
            except Exception:
              # skip failing images
              pass

        # Stage 3
        if hasattr(status_ctx, "text") and callable(getattr(status_ctx, "text")):
          status_ctx.text("3/4 — Constructing widescreen 16:9 layout containers...")
        else:
          status_ctx.markdown("**3/4 — Constructing widescreen 16:9 layout containers...**")

        # Call the engine
        # The engine expects 'image_keyword' fields or will attempt to fetch by bullets/title.
        out_path = f"apollo_presentation_{int(time.time())}.pptx"
        saved_path, temp_images = create_gamma_style_pptx(slides_payload, out_path)

        # Stage 4
        if hasattr(status_ctx, "text") and callable(getattr(status_ctx, "text")):
          status_ctx.text("4/4 — Presentation ready!")
        else:
          status_ctx.markdown("**4/4 — Presentation ready!**")

        # Return saved path and images to cleanup
        return saved_path, temp_images
      finally:
        # no immediate cleanup here; caller will delete after download
        try:
          if hasattr(status_ctx, "empty"):
            status_ctx.empty()
        except Exception:
          pass

    if st.button("📥 Generate & Download .pptx File", use_container_width=True):
      try:
        saved_path, temp_images = _generate_and_download_pptx()
        if saved_path and os.path.exists(saved_path):
          with open(saved_path, "rb") as f:
            st.download_button(
                label="Click here to download",
                data=f,
                file_name=os.path.basename(saved_path),
                mime=(
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                ),
                use_container_width=True,
            )
          # cleanup temp images and saved file after providing a moment
          for p in temp_images:
            try:
              os.unlink(p)
            except Exception:
              pass
          try:
            os.unlink(saved_path)
          except Exception:
            pass
        else:
          st.error("Failed to produce presentation.")
      except Exception as e:
        st.error(f"Presentation generation failed: {e}")

  st.markdown("</div>", unsafe_allow_html=True)

  # --- SECURED WEB SEARCH INDEXER (TAVILY REST API) ---
  st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
  st.markdown(
      "<div class='panel-header'>🌐 AI Web Search (Tavily)</div>",
      unsafe_allow_html=True,
  )

  if TAVILY_API_KEY:
    st.markdown(
        "<span style='font-size:0.8rem; color:#4ade80;'>✅ Tavily API Key Linked"
        " Safely</span>",
        unsafe_allow_html=True,
    )
  else:
    st.markdown(
        "<span style='font-size:0.8rem; color:#f87171;'>❌ Missing"
        " TAVILY_API_KEY in Secrets</span>",
        unsafe_allow_html=True,
    )

  web_query = st.text_input(
      "Enter topic to scrape & index...",
      placeholder="e.g. Current AI news",
      label_visibility="collapsed",
  )

  RESTRICTED_TERMS = [
      "porn",
      "nsfw",
      "xxx",
      "sex",
      "nude",
      "kill",
      "suicide",
      "murder",
      "gore",
      "weapon",
      "bomb",
      "drugs",
  ]

  if st.button("SEARCH & INDEX", use_container_width=True):
    if not TAVILY_API_KEY or not TAVILY_API_KEY.startswith("tvly-"):
      st.error("No active Tavily API Key found in Streamlit Secrets.")
    elif web_query:
      query_lower = web_query.lower()
      violation_found = any(term in query_lower for term in RESTRICTED_TERMS)

      if violation_found:
        st.error(
            "🚨 **SECURITY ALERT:** Your search query violates safety policy."
        )
      else:
        with st.spinner("Executing secure web retrieval..."):
          try:
            api_url = "[https://api.tavily.com/search](https://api.tavily.com/search)"
            payload = {
                "api_key": TAVILY_API_KEY.strip(),
                "query": web_query,
                "search_depth": "advanced",
                "include_answer": False,
                "include_images": False,
                "include_raw_content": False,
                "max_results": 10,
            }

            response = requests.post(api_url, json=payload, timeout=25)

            if response.status_code == 200:
              data = response.json()
              results = data.get("results", [])
              unique_docs = {}

              for r in results:
                source_url = r.get("url", "")
                content = r.get("content", "")
                title = r.get("title", "Verified Source")

                if source_url and content and (source_url not in unique_docs):
                  unique_docs[source_url] = {"content": content, "title": title}

              web_docs = []
              for url, info in unique_docs.items():
                web_docs.append(
                    Document(
                        page_content=(
                            f"Title: {info['title']}\nSource:"
                            f" {url}\nContext: {info['content']}"
                        ),
                        metadata={"source": url, "title": info["title"]},
                    )
                )

              if web_docs:
                chunks = text_splitter.split_documents(web_docs)
                valid_chunks = [c for c in chunks if c.page_content.strip()]

                if valid_chunks:
                  if st.session_state.vector_db is None:
                    st.session_state.vector_db = FAISS.from_documents(
                        valid_chunks, embedder
                    )
                  else:
                    st.session_state.vector_db.add_documents(valid_chunks)

                  st.session_state.node_count += len(valid_chunks)
                  st.success(
                      f"Indexed {len(valid_chunks)} verified blocks via"
                      " Tavily!"
                  )
            else:
              st.error(f"Tavily API Error: {response.text}")
          except Exception as e:
            st.error(f"Tavily connection failed: {str(e)}")
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
          valid_chunks = [c for c in chunks if c.page_content.strip()]

          if valid_chunks:
            if st.session_state.vector_db is None:
              st.session_state.vector_db = FAISS.from_documents(
                  valid_chunks, embedder
              )
            else:
              st.session_state.vector_db.add_documents(valid_chunks)
            st.session_state.node_count += len(valid_chunks)
            st.success(
                f"Successfully Indexed {len(valid_chunks)} document blocks."
            )
  st.markdown("</div>", unsafe_allow_html=True)

# ================= MIDDLE COLUMN: MAIN STUDY CONSOLE =================
with col_mid:
  if not st.session_state.chat_history:
    st.markdown(
        """
        <div style='margin-top: 50px; margin-bottom: 30px; text-align: center;'>
            <h2 style='color: #f97316; font-family: "Inter", sans-serif; font-weight: 700;'>Study Console Initialized</h2>
            <p style='color: #a1a1aa; font-family: "JetBrains Mono", monospace; font-size: 0.85rem;'>Use the left panel to index Web Data or Local Files, then chat here.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

  chat_scroll_pane = st.container()

  with chat_scroll_pane:
    for msg in st.session_state.chat_history:
      with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

  user_query = st.chat_input("Enter your query...")

  if user_query:
    st.session_state.chat_history.append({"role": "user", "content": user_query})

    start_time = time.time()
    context_payload = ""

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
          "You are APOLLO OMNI AI, an advanced AI study buddy. Formulate a"
          " crisp response using ONLY the provided context below. DO NOT"
          " include raw URLs or brackets."
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
          "You are APOLLO OMNI AI, an advanced AI study buddy. Answer based on"
          " general knowledge. Be crisp and concise."
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
      st.session_state.slides_data = [
          {
              "title": "Introduction to Institutional AI",
              "bullets": [
                  "Overview of Apollo Omni platform",
                  "Secure @somaiya.edu integration",
              ],
          }
      ]
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
