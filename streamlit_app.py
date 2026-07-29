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
          "subtitle": "Understanding Cognitive Architecture and Modern Computing",
          "image_keyword": "futuristic artificial intelligence neural network dark blue glow",
          "cards": [
              {
                  "heading": "Core Definition",
                  "text": "Artificial Intelligence (AI) refers to the simulation of human intelligence in machines programmed to think, learn, reason, and make autonomous decisions.",
              },
          ],
      }
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
      f"sleek modern technological visual representation of {clean_kw}, high resolution, 8k, dark aesthetic, minimalist design"
  )
  pollinations_url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=800&height=600&seed={abs(hash(clean_kw)) % 100000}&nologo=true"
  try:
    resp = requests.get(pollinations_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
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
  ACCENT_COLOR = RGBColor(249, 115, 22)
  blank_layout = prs.slide_layouts[6]

  for index, slide_info in enumerate(slides_data):
    if not isinstance(slide_info, dict):
      continue
    slide = prs.slides.add_slide(blank_layout)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = BG_COLOR
    title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.7), Inches(1.2))
    p = title_box.text_frame.paragraphs[0]
    p.text = slide_info.get("title", f"Slide {index+1}")
    p.font.size = Pt(26)
    p.font.bold = True
    p.font.color.rgb = ACCENT_COLOR

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
      yield "❌ MISSING CONFIGURATION: Please set a valid 'GROQ_API_KEY'."
      return
    try:
      client = Groq(api_key=groq_key.strip())
      stream = client.chat.completions.create(
          model=model_id, messages=messages, temperature=0.3, max_tokens=2048, stream=True
      )
      for chunk in stream:
        token_text = chunk.choices[0].delta.content or ""
        if token_text:
          yield token_text
    except Exception as e:
      yield f"❌ Groq SDK Failure: {str(e)}"
  else:
    if not or_token or not or_token.startswith("sk-or-"):
      yield "❌ MISSING CONFIGURATION: Please set a valid 'OPENROUTER_API_KEY'."
      return
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {or_token.strip()}", "Content-Type": "application/json"}
    payload = {"model": model_id, "messages": messages, "temperature": 0.3, "stream": True}
    try:
      response = requests.post(url, headers=headers, json=payload, stream=True, timeout=30)
      for line in response.iter_lines():
        if line:
          decoded = line.decode("utf-8").strip()
          if decoded.startswith("data: ") and decoded[6:] != "[DONE]":
            try:
              data_json = json.loads(decoded[6:])
              yield data_json.get("choices", [{}])[0].get("delta", {}).get("content", "")
            except Exception:
              pass
    except Exception as e:
      yield f"❌ Network Failure: {str(e)}"

# 10. Email Dispatcher Function
def send_otp_email(target_email, otp_code):
  try:
    sender_email = st.secrets.get("EMAIL_SENDER", "")
    sender_pass = st.secrets.get("EMAIL_PASSWORD", "")
    msg = MIMEText(f"Your Apollo Omni AI secure access code is: {otp_code}")
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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');
    
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

    .stButton button {
        background: linear-gradient(180deg, #f97316 0%, #ea580c 100%) !important;
        color: #fff !important;
        border: none !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ================= CUSTOM HEADER & SETTINGS =================
col_logo, col_model, col_badge = st.columns([3, 4, 3])
with col_logo:
  st.markdown("<div style='font-size: 1.5rem; font-weight: 700; color: white;'>APOLLO <span style='color: #f97316;'>OMNI AI</span></div>", unsafe_allow_html=True)
with col_model:
  selected_model = st.selectbox(
      "API Gateway Endpoint:", options=list(MODEL_OPTIONS.keys()), index=0, label_visibility="collapsed"
  )
with col_badge:
  api_status = "CONNECTED" if (OPENROUTER_API_KEY or GROQ_API_KEY) else "MISSING"
  st.markdown(
      f"<div style='text-align: right;'><span class='status-badge'>🔑 API: {api_status}</span> &nbsp; <span class='status-badge'>● SESSION ACTIVE</span></div>",
      unsafe_allow_html=True,
  )
st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin-top: 5px; margin-bottom: 25px;'>", unsafe_allow_html=True)

# ================= AUTHENTICATION GATEKEEPER =================
if not st.session_state.authenticated:
  st.markdown(
      "<div style='text-align: center; margin-top: 80px;'><h2 style='color: #f97316;'>🔒 Restricted Access</h2><p style='color: #a1a1aa;'>Verify your email to receive a secure access code.</p></div>",
      unsafe_allow_html=True,
  )

  col_space1, col_login, col_space3 = st.columns([3, 4, 3])
  with col_login:
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    if not st.session_state.otp_sent:
      email_input = st.text_input("University Email", placeholder="your.name@somaiya.edu")
      if st.button("SEND ACCESS CODE", use_container_width=True):
        if email_input.strip().lower().endswith("@somaiya.edu"):
          with st.spinner("Dispatching secure code..."):
            otp = str(random.randint(100000, 999999))
            st.session_state.generated_otp = otp
            st.session_state.user_email = email_input.strip().lower()
            success, error_msg = send_otp_email(st.session_state.user_email, otp)
            if success:
              st.session_state.otp_sent = True
              st.rerun()
            else:
              st.error(f"❌ Failed to send email: {error_msg}")
        else:
          st.error("❌ Access Denied. Only @somaiya.edu accounts are permitted.")
    else:
      st.success(f"Secure code sent to {st.session_state.user_email}")
      otp_input = st.text_input("Enter 6-Digit Code", type="password")
      if st.button("VERIFY & ENTER", use_container_width=True):
        if otp_input.strip() == st.session_state.generated_otp:
          st.session_state.authenticated = True
          cookie_manager.set("apollo_somaiya_session", "verified_student", expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
          st.rerun()
        else:
          st.error("❌ Incorrect code. Please check your email and try again.")
    st.markdown("</div>", unsafe_allow_html=True)
  st.stop()

# ================= SIDEBAR: DRAWERS & MODALS =================
with st.sidebar:
  st.markdown("<h3 style='color: #f97316; font-family: \"JetBrains Mono\", monospace;'>⚡ Workspace Tools</h3>", unsafe_allow_html=True)
  st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin-top: 0px;'>", unsafe_allow_html=True)
  
  with st.popover("➕ Append_Material", use_container_width=True):
    st.markdown("**Upload & Vectorize Material**")
    uploaded_files = st.file_uploader(
        "Drop PDF, TXT, MD or CSV files...",
        type=["pdf", "txt", "md", "csv"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="file_in",
    )
    if st.button("SYNC KNOWLEDGE BASE", use_container_width=True):
      if uploaded_files:
        with st.spinner("Chunking vectors..."):
          docs = []
          for f in uploaded_files:
            suffix = os.path.splitext(f.name)[1].lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
              tmp.write(f.read())
              path = tmp.name
            try:
              if suffix == ".pdf":
                docs.extend(PyPDFLoader(path).load())
              else:
                docs.extend(TextLoader(path, encoding="utf-8").load())
            except Exception:
              pass
          if docs:
            chunks = text_splitter.split_documents(docs)
            if st.session_state.vector_db is None:
              st.session_state.vector_db = FAISS.from_documents(chunks, embedder)
            else:
              st.session_state.vector_db.add_documents(chunks)
            st.session_state.node_count += len(chunks)
            st.success(f"Indexed {len(chunks)} document blocks.")

  with st.popover("📝 Gen_Quiz", use_container_width=True):
    st.markdown("**Interactive Knowledge Check**")
    st.progress(20, text="Question 1 / 5")
    st.markdown("*(Simulated UI)* **What is the primary characteristic of AGI?**")
    st.radio("Options:", ["Narrow Task Execution", "Human-Level Transfer Learning", "Image Rendering", "Data Storage"], label_visibility="collapsed")
    st.button("Submit Answer", use_container_width=True)


# ================= MAIN LAYOUT =================
col_left, col_mid, col_right = st.columns([3, 6, 3], gap="large")

# ================= LEFT COLUMN: GAMMA & SEARCH =================
with col_left:
  # --- GAMMA AI PPT STUDIO ---
  st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
  st.markdown("<div class='panel-header'>🎨 Gamma AI PPT Studio</div>", unsafe_allow_html=True)
  ppt_topic_input = st.text_input("Presentation Topic:", placeholder="e.g. AI Architecture")

  if st.button("🚀 Generate Framework", use_container_width=True):
    st.success("Feature ready for prompt routing!")

  if st.button("📥 Export Gamma .pptx File", use_container_width=True):
    with st.spinner("Building slide deck..."):
      file_path = create_gamma_style_pptx(st.session_state.slides_data)
      with open(file_path, "rb") as f:
        st.download_button(
            label="Click here to download deck",
            data=f,
            file_name="Gamma_Style_Presentation.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            use_container_width=True,
        )
  st.markdown("</div>", unsafe_allow_html=True)

  # --- SECURED WEB SEARCH INDEXER ---
  st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
  st.markdown("<div class='panel-header'>🌐 AI Web Search</div>", unsafe_allow_html=True)
  web_query = st.text_input("Enter topic to scrape...", placeholder="e.g. Current AI news", label_visibility="collapsed")

  if st.button("SEARCH & INDEX", use_container_width=True):
    if not TAVILY_API_KEY:
      st.error("No active Tavily API Key found.")
    elif web_query:
      with st.spinner("Executing secure web retrieval..."):
        try:
          api_url = "https://api.tavily.com/search"
          payload = {"api_key": TAVILY_API_KEY.strip(), "query": web_query, "search_depth": "advanced"}
          response = requests.post(api_url, json=payload, timeout=25)
          if response.status_code == 200:
            results = response.json().get("results", [])
            web_docs = [Document(page_content=f"{r.get('title')}\n{r.get('content')}", metadata={"source": r.get("url")}) for r in results]
            chunks = text_splitter.split_documents(web_docs)
            if chunks:
              if st.session_state.vector_db is None:
                st.session_state.vector_db = FAISS.from_documents(chunks, embedder)
              else:
                st.session_state.vector_db.add_documents(chunks)
              st.session_state.node_count += len(chunks)
              st.success(f"Indexed {len(chunks)} verified blocks!")
        except Exception as e:
          st.error(f"Search failed: {str(e)}")
  st.markdown("</div>", unsafe_allow_html=True)

# ================= MIDDLE COLUMN: MAIN STUDY CONSOLE =================
with col_mid:
  if not st.session_state.chat_history:
    st.markdown(
        """
        <div style='margin-top: 50px; margin-bottom: 30px; text-align: center;'>
            <h2 style='color: #f97316; font-family: "Inter", sans-serif; font-weight: 700;'>Study Console Initialized</h2>
            <p style='color: #a1a1aa; font-family: "JetBrains Mono", monospace; font-size: 0.85rem;'>Upload documents in the sidebar, or query models below.</p>
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

    # Prompt extensions for Math and Charts
    chart_instruction = (
        "\n\nIf the user asks for a chart or data visualization, append a JSON code block at the very end:\n"
        "```json\n{\n  \"type\": \"bar\",\n  \"title\": \"Chart Title\",\n  \"x_label\": \"X Axis\",\n  \"y_label\": \"Y Axis\",\n  \"x\": [\"A\", \"B\"],\n  \"y\": [10, 20]\n}\n```"
    )
    math_instruction = (
        "\n\nStrict LaTeX Rule: You MUST format all mathematical formulas, symbols, and equations using LaTeX syntax. "
        "Use `$` for inline equations and `$$` for standalone block equations. Place complex formulas inside markdown codeblocks labeled with `math`."
    )

    if st.session_state.vector_db is not None:
      retriever = st.session_state.vector_db.as_retriever(search_kwargs={"k": 5})
      matched_nodes = retriever.invoke(user_query)
      context_payload = "\n\n".join([f"[{n.metadata.get('source', 'Unknown')}]\n{n.page_content}" for n in matched_nodes])
      sys_instruction = f"You are APOLLO OMNI AI. Answer using ONLY context below.{chart_instruction}{math_instruction}"
      clean_ctx = context_payload.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
      st.session_state.source_reference = f"<div class='source-box'><strong>Active Context:</strong><br><br>{clean_ctx}</div>"
    else:
      sys_instruction = f"You are APOLLO OMNI AI. Answer based on general knowledge.{chart_instruction}{math_instruction}"
      st.session_state.source_reference = "<div class='source-box font-mono'>No active context. General weights used.</div>"

    message_stream = [{"role": "system", "content": sys_instruction}]
    for msg in st.session_state.chat_history[-4:]:
      message_stream.append({"role": msg["role"], "content": msg["content"]})
    message_stream.append({"role": "user", "content": f"Context Matrix:\n{context_payload}\n\nQuery: {user_query}"})

    with chat_scroll_pane:
      with st.chat_message("assistant"):
        try:
          stream = generate_llm_stream(message_stream, GROQ_API_KEY, OPENROUTER_API_KEY, selected_model)
          collected_tokens = st.write_stream(stream)
          if not collected_tokens:
            collected_tokens = "⚠️ EMPTY RESPONSE."
        except Exception as ex:
          collected_tokens = f"❌ FRAMEWORK API FAILURE: {ex}"
          st.markdown(collected_tokens)

    st.session_state.chat_history.append({"role": "assistant", "content": collected_tokens})
    st.session_state.response_time = f"{time.time() - start_time:.2f}s"
    st.rerun()

# ================= RIGHT COLUMN: TELEMETRY =================
with col_right:
  st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
  st.markdown("<div class='panel-header'>📊 Analytics Dashboard</div>", unsafe_allow_html=True)
  st.markdown(f"<div><div class='metric-title'>Inference Latency</div><div class='metric-value'>{st.session_state.response_time}</div></div>", unsafe_allow_html=True)
  st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 15px 0;'>", unsafe_allow_html=True)
  st.markdown(f"<div><div class='metric-title'>Indexed Documents</div><div class='metric-value'>{st.session_state.node_count}</div></div>", unsafe_allow_html=True)
  st.markdown("</div>", unsafe_allow_html=True)

  st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
  st.markdown("<div class='panel-header'>📑 Verified Retrieval Matrix</div>", unsafe_allow_html=True)
  st.markdown(st.session_state.source_reference, unsafe_allow_html=True)
  st.markdown("</div>", unsafe_allow_html=True)

  st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
  st.markdown("<div class='panel-header'>🛠️ Session Actions</div>", unsafe_allow_html=True)
  c1, c2 = st.columns(2)
  with c1:
    if st.button("PURGE", use_container_width=True):
      st.session_state.chat_history = []
      st.session_state.vector_db = None
      st.session_state.node_count = 0
      st.session_state.response_time = "0.00s"
      st.session_state.source_reference = "<div class='source-box font-mono'>Awaiting vector alignment...</div>"
      st.rerun()
  with c2:
    chat_log = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in st.session_state.chat_history])
    st.download_button("EXPORT", data=chat_log, file_name="apollo_log.txt", mime="text/plain", use_container_width=True)

  st.markdown("<br>", unsafe_allow_html=True)
  if st.button("LOG OUT", use_container_width=True, type="secondary"):
    st.session_state.authenticated = False
    cookie_manager.delete("apollo_somaiya_session")
    st.rerun()
  st.markdown("</div>", unsafe_allow_html=True)
