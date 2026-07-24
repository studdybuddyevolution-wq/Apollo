import os
import time
import tempfile
import json
import requests
import random
import smtplib
import datetime
from email.mime.text import MIMEText
import streamlit as st
import extra_streamlit_components as stx
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
import urllib.parse
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from PIL import Image

# 1. Page Configuration & Title
st.set_page_config(layout="wide", page_title="APOLLO OMNI AI", page_icon="⚡")

# 2. Initialize Cookie Manager for Persistent Auth
cookie_manager = stx.CookieManager()
cookies = cookie_manager.get_all()
if cookies is None:
    cookies = {}

# 3. Key/Token Initialization
try:
    OR_TOKEN = st.secrets.get("OPENROUTER_API_KEY", os.getenv("OPENROUTER_API_KEY", ""))
except Exception:
    OR_TOKEN = os.getenv("OPENROUTER_API_KEY", "")

try:
    TAVILY_KEY = st.secrets.get("TAVILY_API_KEY", os.getenv("TAVILY_API_KEY", ""))
except Exception:
    TAVILY_KEY = os.getenv("TAVILY_API_KEY", "")

try:
    GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
except Exception:
    GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

# 4. Resource Caching Pipelines
@st.cache_resource
def get_embedding_model():
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )

@st.cache_resource
def get_text_splitter():
    return RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

embedder = get_embedding_model()
text_splitter = get_text_splitter()

# 5. State Management Matrix
if "vector_db" not in st.session_state: st.session_state.vector_db = None
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "response_time" not in st.session_state: st.session_state.response_time = "0.00s"
if "source_reference" not in st.session_state: st.session_state.source_reference = "<div class='source-box font-mono'>Awaiting vector alignment...</div>"
if "node_count" not in st.session_state: st.session_state.node_count = 0

# Persistent Auth State Handling via Cookies
auth_cookie = cookies.get("apollo_somaiya_session")
if auth_cookie == "verified_student":
    st.session_state.authenticated = True
elif "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "otp_sent" not in st.session_state: st.session_state.otp_sent = False
if "generated_otp" not in st.session_state: st.session_state.generated_otp = None
if "user_email" not in st.session_state: st.session_state.user_email = ""

# NotebookLM-Style Gamma PPT Studio State
if "slides_data" not in st.session_state:
    st.session_state.slides_data = [
        {
            "title": "Introduction to Institutional AI",
            "subtitle": "Modernizing Academic & Enterprise Intelligence",
            "bullets": ["Overview of Apollo Omni platform", "Secure @somaiya.edu integration", "Privacy-first zero data persistence"],
            "image_prompt": "Futuristic 3d AI neural network avatar glowing orange in dark room"
        },
        {
            "title": "Core Architecture & RAG Workflow",
            "subtitle": "Vector Storage & Multi-Model Orchestration",
            "bullets": ["Retrieval-Augmented Generation (RAG)", "Sub-second FAISS vector indexing", "Multi-model micro-agent routing"],
            "image_prompt": "3d render of database data nodes connected with glowing cyber light beams"
        }
    ]

# 6. Stable OpenRouter Model Matrix
MODEL_OPTIONS = {
    "Google Gemma 4 26B (Free)": {
        "or_id": "google/gemma-4-26b-a4b-it:free",
        "desc": "Google's highly efficient 26B model. Excellent for fast retrieval and text tasks."
    },
    "Meta Llama 3.3 70B (Free)": {
        "or_id": "meta-llama/llama-3.3-70b-instruct:free",
        "desc": "Massive 70B model. Incredible at general reasoning and completely free."
    }
}

# 7. OpenRouter Exclusive LLM Streamer
def generate_llm_stream(messages, token, selected_model_name):
    if not token or not token.startswith("sk-or-"):
        yield "❌ MISSING CONFIGURATION: Please set a valid 'OPENROUTER_API_KEY' starting with 'sk-or-v1-' in your Streamlit Secrets Dashboard."
        return

    model_id = MODEL_OPTIONS[selected_model_name]["or_id"]
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {token.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8501", 
        "X-Title": "APOLLO OMNI" 
    }
    
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.3,  
        "max_tokens": 1024,
        "stream": True
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=30)
        
        if response.status_code != 200:
            yield f"❌ API Error ({response.status_code}): {response.text}"
            return
            
        for line in response.iter_lines():
            if line:
                decoded = line.decode('utf-8').strip()
                if decoded.startswith("data: "):
                    data_str = decoded[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data_json = json.loads(data_str)
                        token_text = data_json["choices"][0]["delta"].get("content", "")
                        if token_text:
                            yield token_text
                    except Exception:
                        pass
    except Exception as e:
        yield f"❌ Network Failure: {str(e)}"

# 8. Gemini PPT Generator Function (With dynamic model discovery & fallback)
def generate_slides_with_gemini(topic, gemini_key):
    if not gemini_key:
        return None, "Missing GEMINI_API_KEY in Streamlit Secrets."
    
    clean_key = gemini_key.strip()
    headers = {"Content-Type": "application/json"}
    
    prompt = f"""Create a modern Gamma AI-style presentation outline about '{topic}'. 
    Return ONLY a valid JSON array of 4-6 slide objects. Each object MUST have:
    - 'title': Slide title (concise, impactful)
    - 'subtitle': Brief 1-line summary/tagline
    - 'bullets': Array of 3-4 detailed bullet strings
    - 'image_prompt': A specific 3D render/visual image description for this slide (e.g. 'Futuristic cybernetic neural network glowing orange')

    Do NOT include markdown formatting code blocks like ```json, just return raw JSON text.
    Example format:
    [
      {{"title": "AI Architecture", "subtitle": "Scalable Neural Processing", "bullets": ["High-performance compute clusters", "Sub-millisecond latency routing"], "image_prompt": "3d render of neural network glowing orange"}}
    ]"""
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json"
        }
    }
    
    discovered_models = []
    try:
        models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={clean_key}"
        res = requests.get(models_url, timeout=10)
        if res.status_code == 200:
            m_data = res.json().get("models", [])
            for m in m_data:
                m_name = m.get("name", "").replace("models/", "")
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods:
                    discovered_models.append(m_name)
    except Exception:
        pass
        
    flash_models = [m for m in discovered_models if "flash" in m.lower()]
    candidate_models = flash_models + [m for m in discovered_models if m not in flash_models]
    
    if not candidate_models:
        candidate_models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash", "gemini-2.0-flash-exp"]
        
    last_error = ""
    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={clean_key}"
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                text_output = data['candidates'][0]['content']['parts'][0]['text']
                parsed_json = json.loads(text_output)
                return parsed_json, "Success"
            else:
                last_error = f"Gemini API Error ({response.status_code}) [{model_name}]: {response.text}"
        except Exception as e:
            last_error = str(e)
            
    return None, last_error

# 9. Email Dispatcher Function
def send_otp_email(target_email, otp_code):
    try:
        sender_email = st.secrets.get("EMAIL_SENDER", "")
        sender_pass = st.secrets.get("EMAIL_PASSWORD", "")
        
        if not sender_email or not sender_pass:
            return False, "Email credentials missing in Streamlit secrets."
            
        msg = MIMEText(f"Your Apollo Omni AI secure access code is: {otp_code}\n\nIf you did not request this, please ignore this email.")
        msg['Subject'] = 'APOLLO OMNI - Access Code'
        msg['From'] = sender_email
        msg['To'] = target_email
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_pass)
        server.send_message(msg)
        server.quit()
        return True, "Success"
    except Exception as e:
        return False, str(e)

# 10. Advanced CSS Injection (Forcing Dark Mode)
st.markdown("""
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
    .header-left {
        display: flex;
        align-items: center;
        gap: 15px;
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

    [data-testid="stFileUploadDropzone"] {
        background-color: #18181b !important;
        border: 1px dashed rgba(255, 255, 255, 0.2) !important;
    }
    [data-testid="stFileUploadDropzone"] * {
        color: #a1a1aa !important;
    }
    [data-testid="stFileUploadDropzone"]:hover {
        border-color: #f97316 !important;
        background-color: #27272a !important;
    }

    .stButton button {
        background: linear-gradient(180deg, #f97316 0%, #ea580c 100%) !important;
        color: #fff !important;
        border: none !important;
    }

    div[data-baseweb="select"] > div {
        background-color: #18181b !important;
        border-color: rgba(255, 255, 255, 0.1) !important;
        color: white !important;
    }
    div[data-baseweb="select"] span {
        color: white !important;
    }
    ul[role="listbox"] {
        background-color: #18181b !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
    }
    li[role="option"] {
        background-color: #18181b !important;
        color: #e5e7eb !important;
    }
    li[role="option"]:hover {
        background-color: #f97316 !important;
        color: white !important;
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
""", unsafe_allow_html=True)

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
            st.markdown("<div style='text-align: right; margin-top: 15px;'><span class='status-badge'>● PERSISTENT SESSION ACTIVE</span></div>", unsafe_allow_html=True)
        st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin-top: -10px; margin-bottom: 30px;'>", unsafe_allow_html=True)
        logo_loaded = True
    except Exception:
        pass

if not logo_loaded:
    st.markdown("""
    <div class='header-bar'>
        <div class='header-left'>
            <div style='font-size: 1.25rem; font-weight: 700; letter-spacing: 0.05em; color: white;'>APOLLO <span style='color: #f97316;'>OMNI AI</span></div>
        </div>
        <div class='status-badge'>● PERSISTENT SESSION ACTIVE</div>
    </div>
    """, unsafe_allow_html=True)

# ================= PERSISTENT DOMAIN OTP GATEKEEPER =================
if not st.session_state.authenticated:
    st.markdown("<div style='text-align: center; margin-top: 80px;'><h2 style='color: #f97316;'>🔒 Restricted Access</h2><p style='color: #a1a1aa;'>Verify your Somaiya university email to receive a secure access code.</p></div>", unsafe_allow_html=True)
    
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
                            st.error(f"❌ Failed to send email. Ensure EMAIL_SENDER and EMAIL_PASSWORD are set in secrets. Error: {error_msg}")
                else:
                    st.error("❌ Access Denied. Only @somaiya.edu accounts are permitted.")
        else:
            st.success(f"Secure code sent to {st.session_state.user_email}")
            otp_input = st.text_input("Enter 6-Digit Code", type="password")
            
            if st.button("VERIFY & ENTER", use_container_width=True):
                if otp_input.strip() == st.session_state.generated_otp:
                    st.session_state.authenticated = True
                    cookie_manager.set(
                        "apollo_somaiya_session", 
                        "verified_student", 
                        expires_at=datetime.datetime.now() + datetime.timedelta(days=30)
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

# ================= LEFT COLUMN: INGESTION & GEMINI PPT STUDIO =================
with col_left:
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>⚙️ Zero-Cost Engine</div>", unsafe_allow_html=True)
    selected_model = st.selectbox("API Gateway Endpoint:", options=list(MODEL_OPTIONS.keys()), index=0)
    st.caption(f"**Desc:** {MODEL_OPTIONS[selected_model]['desc']}")
    st.markdown("</div>", unsafe_allow_html=True)

    # --- GEMINI-POWERED INTERACTIVE PPT STUDIO ---
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>📊 Gemini PPT Studio</div>", unsafe_allow_html=True)
    
    if GEMINI_KEY:
        st.markdown("<span style='font-size:0.8rem; color:#4ade80;'>✅ Gemini API Key Linked Safely</span>", unsafe_allow_html=True)
    else:
        st.markdown("<span style='font-size:0.8rem; color:#f87171;'>❌ Missing GEMINI_API_KEY in Secrets</span>", unsafe_allow_html=True)

    ppt_topic_input = st.text_input("Presentation Topic:", placeholder="e.g. Quantum Cryptography")
    if st.button("✨ Generate Slides via Gemini", use_container_width=True):
        if not GEMINI_KEY:
            st.error("Please add GEMINI_API_KEY to your Streamlit secrets.")
        elif ppt_topic_input:
            with st.spinner("Generating slide structure with Gemini..."):
                new_slides, err = generate_slides_with_gemini(ppt_topic_input, GEMINI_KEY)
                if new_slides and isinstance(new_slides, list):
                    st.session_state.slides_data = new_slides
                    st.success("Successfully generated new presentation structure!")
                    st.rerun()
                else:
                    st.error(f"Failed to generate slides: {err}")

    with st.expander("✨ Open NotebookLM Slide Editor", expanded=False):
        st.markdown("Live-edit your generated slides before downloading.")
        tabs = st.tabs([f"Slide {i+1}" for i in range(len(st.session_state.slides_data))])
        
        for i, tab in enumerate(tabs):
            with tab:
                slide_info = st.session_state.slides_data[i]
                new_title = st.text_input(f"Title {i+1}", slide_info["title"], key=f"title_{i}")
                st.session_state.slides_data[i]["title"] = new_title
                
                updated_bullets = []
                for j, bullet in enumerate(slide_info["bullets"]):
                    b_val = st.text_input(f"Bullet {j+1}", bullet, key=f"bullet_{i}_{j}")
                    updated_bullets.append(b_val)
                st.session_state.slides_data[i]["bullets"] = updated_bullets
        
# Helper to fetch dynamic AI visuals / images for slide cards
def fetch_slide_image(prompt_text, slide_index):
    try:
        clean_prompt = urllib.parse.quote(f"modern presentation visual {prompt_text} cinematic dark mode 8k")
        img_url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=800&height=600&nologo=true&seed={slide_index+42}"
        res = requests.get(img_url, timeout=12)
        if res.status_code == 200:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp.write(res.content)
            tmp.close()
            return tmp.name
    except Exception:
        pass
    
    try:
        from PIL import ImageDraw
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        img = Image.new('RGB', (800, 600), color=(24, 24, 27))
        draw = ImageDraw.Draw(img)
        for x in range(0, 800, 40):
            draw.line([(x, 0), (x, 600)], fill=(39, 39, 42), width=1)
        for y in range(0, 600, 40):
            draw.line([(0, y), (800, y)], fill=(39, 39, 42), width=1)
        draw.rounded_rectangle([80, 120, 720, 480], radius=16, fill=(30, 41, 59), outline=(249, 115, 22), width=3)
        img.save(tmp.name)
        return tmp.name
    except Exception:
        return None

def create_gamma_pptx(data):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    DARK_BG = RGBColor(15, 15, 17)        # #0F0F11
    CARD_BG = RGBColor(24, 24, 27)        # #18181B
    BORDER_COLOR = RGBColor(63, 63, 70)   # #3F3F46
    ORANGE_ACCENT = RGBColor(249, 115, 22)# #F97316
    CYAN_ACCENT = RGBColor(56, 189, 248)  # #38BDF8
    WHITE_TEXT = RGBColor(255, 255, 255)
    MUTED_TEXT = RGBColor(161, 161, 170)

    # 1. Cover Slide
    cover_slide = prs.slides.add_slide(blank_layout)
    cover_bg = cover_slide.background.fill
    cover_bg.solid()
    cover_bg.fore_color.rgb = DARK_BG

    card = cover_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(1.0), Inches(11.333), Inches(5.5))
    card.fill.solid()
    card.fill.fore_color.rgb = CARD_BG
    card.line.color.rgb = BORDER_COLOR
    card.line.width = Pt(1.5)

    badge = cover_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.5), Inches(1.5), Inches(3.5), Inches(0.4))
    badge.fill.solid()
    badge.fill.fore_color.rgb = RGBColor(30, 41, 59)
    badge.line.color.rgb = CYAN_ACCENT
    tf = badge.text_frame
    p = tf.paragraphs[0]
    p.text = "⚡ GAMMA AI DESIGN ENGINE"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = CYAN_ACCENT

    first_title = data[0]["title"] if data else "Apollo Omni AI Presentation"
    txBox = cover_slide.shapes.add_textbox(Inches(1.5), Inches(2.2), Inches(10.333), Inches(1.5))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = first_title
    p.font.size = Pt(40)
    p.font.bold = True
    p.font.color.rgb = ORANGE_ACCENT

    first_sub = data[0].get("subtitle", "AI-Generated Interactive Knowledge Studio") if data else ""
    txBox2 = cover_slide.shapes.add_textbox(Inches(1.5), Inches(3.8), Inches(10.333), Inches(1.0))
    tf2 = txBox2.text_frame
    tf2.word_wrap = True
    p2 = tf2.paragraphs[0]
    p2.text = first_sub
    p2.font.size = Pt(20)
    p2.font.color.rgb = WHITE_TEXT

    txBox3 = cover_slide.shapes.add_textbox(Inches(1.5), Inches(5.3), Inches(10.333), Inches(0.6))
    tf3 = txBox3.text_frame
    p3 = tf3.paragraphs[0]
    p3.text = "Generated by APOLLO OMNI AI • Powered by Gemini & Gamma Engine"
    p3.font.size = Pt(12)
    p3.font.color.rgb = MUTED_TEXT

    # 2. Content Slides (2-Column Gamma Layout)
    for i, item in enumerate(data):
        slide = prs.slides.add_slide(blank_layout)
        s_bg = slide.background.fill
        s_bg.solid()
        s_bg.fore_color.rgb = DARK_BG

        top_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.1))
        top_bar.fill.solid()
        top_bar.fill.fore_color.rgb = ORANGE_ACCENT if i % 2 == 0 else CYAN_ACCENT
        top_bar.line.fill.background()

        badge = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(0.5), Inches(1.8), Inches(0.35))
        badge.fill.solid()
        badge.fill.fore_color.rgb = CARD_BG
        badge.line.color.rgb = ORANGE_ACCENT if i % 2 == 0 else CYAN_ACCENT
        tf = badge.text_frame
        p = tf.paragraphs[0]
        p.text = f"SLIDE 0{i+1}"
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = ORANGE_ACCENT if i % 2 == 0 else CYAN_ACCENT

        tBox = slide.shapes.add_textbox(Inches(0.8), Inches(0.95), Inches(7.2), Inches(0.9))
        tf = tBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = item["title"]
        p.font.size = Pt(26)
        p.font.bold = True
        p.font.color.rgb = WHITE_TEXT

        if item.get("subtitle"):
            p_sub = tf.add_paragraph()
            p_sub.text = item["subtitle"]
            p_sub.font.size = Pt(13)
            p_sub.font.color.rgb = MUTED_TEXT

        bullets = item.get("bullets", [])
        start_y = 2.0
        card_h = 1.05
        spacing = 0.2

        for b_idx, bullet_text in enumerate(bullets[:4]):
            y_pos = start_y + b_idx * (card_h + spacing)
            b_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(y_pos), Inches(7.2), Inches(card_h))
            b_card.fill.solid()
            b_card.fill.fore_color.rgb = CARD_BG
            b_card.line.color.rgb = BORDER_COLOR

            strip = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(y_pos), Inches(0.12), Inches(card_h))
            strip.fill.solid()
            strip.fill.fore_color.rgb = ORANGE_ACCENT if b_idx % 2 == 0 else CYAN_ACCENT
            strip.line.fill.background()

            bt_box = slide.shapes.add_textbox(Inches(1.1), Inches(y_pos + 0.1), Inches(6.7), Inches(card_h - 0.2))
            bt_tf = bt_box.text_frame
            bt_tf.word_wrap = True
            bp = bt_tf.paragraphs[0]
            bp.text = bullet_text
            bp.font.size = Pt(14)
            bp.font.color.rgb = WHITE_TEXT

        img_path = fetch_slide_image(item.get("image_prompt", item["title"]), i)
        if img_path and os.path.exists(img_path):
            try:
                frame = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.3), Inches(1.5), Inches(4.3), Inches(5.2))
                frame.fill.solid()
                frame.fill.fore_color.rgb = CARD_BG
                frame.line.color.rgb = BORDER_COLOR
                frame.line.width = Pt(1.5)

                slide.shapes.add_picture(img_path, Inches(8.45), Inches(1.65), width=Inches(4.0), height=Inches(4.4))
                
                cap_box = slide.shapes.add_textbox(Inches(8.45), Inches(6.1), Inches(4.0), Inches(0.5))
                cap_tf = cap_box.text_frame
                cap_p = cap_tf.paragraphs[0]
                cap_p.text = f"📷 {item.get('image_prompt', 'AI Visual Card')[:35]}..."
                cap_p.font.size = Pt(10)
                cap_p.font.color.rgb = MUTED_TEXT
            except Exception:
                pass
            finally:
                if os.path.exists(img_path):
                    try:
                        os.unlink(img_path)
                    except Exception:
                        pass

    path = "apollo_gamma_presentation.pptx"
    prs.save(path)
    return path

    with st.expander("✨ Open Gamma Slide Editor & Preview", expanded=False):
        st.markdown("Live-edit your generated Gamma slides, subtitles, and image prompts before downloading.")
        tabs = st.tabs([f"Slide {i+1}" for i in range(len(st.session_state.slides_data))])
        
        for i, tab in enumerate(tabs):
            with tab:
                slide_info = st.session_state.slides_data[i]
                
                st.markdown(f"""
                <div style='background: #18181b; border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 12px; margin-bottom: 12px;'>
                    <span style='background: rgba(249,115,22,0.1); color: #f97316; border: 1px solid rgba(249,115,22,0.3); font-size: 0.7rem; padding: 2px 6px; border-radius: 4px;'>SLIDE 0{i+1} PREVIEW</span>
                    <h4 style='color: white; margin-top: 6px; margin-bottom: 2px;'>{slide_info.get("title", "")}</h4>
                    <p style='color: #a1a1aa; font-size: 0.8rem; margin-bottom: 8px;'><em>{slide_info.get("subtitle", "")}</em></p>
                    <div style='font-size: 0.75rem; color: #38bdf8;'>🎨 Image Prompt: {slide_info.get("image_prompt", "")}</div>
                </div>
                """, unsafe_allow_html=True)
                
                new_title = st.text_input(f"Title {i+1}", slide_info["title"], key=f"title_{i}")
                new_sub = st.text_input(f"Subtitle {i+1}", slide_info.get("subtitle", ""), key=f"sub_{i}")
                new_img_p = st.text_input(f"Image Prompt {i+1}", slide_info.get("image_prompt", ""), key=f"img_p_{i}")
                
                st.session_state.slides_data[i]["title"] = new_title
                st.session_state.slides_data[i]["subtitle"] = new_sub
                st.session_state.slides_data[i]["image_prompt"] = new_img_p
                
                updated_bullets = []
                for j, bullet in enumerate(slide_info.get("bullets", [])):
                    b_val = st.text_input(f"Bullet {j+1}", bullet, key=f"bullet_{i}_{j}")
                    updated_bullets.append(b_val)
                st.session_state.slides_data[i]["bullets"] = updated_bullets

        if st.button("📥 Download Gamma .pptx File", use_container_width=True):
            with st.spinner("Rendering Gamma AI Presentation with images & themes..."):
                file_path = create_gamma_pptx(st.session_state.slides_data)
                with open(file_path, "rb") as f:
                    st.download_button(
                        label="Click here to download Gamma PPTX",
                        data=f,
                        file_name="Apollo_Gamma_Presentation.pptx",
                        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        use_container_width=True
                    )
    st.markdown("</div>", unsafe_allow_html=True)

    # --- SECURED WEB SEARCH INDEXER (TAVILY REST API) ---
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>🌐 AI Web Search (Tavily)</div>", unsafe_allow_html=True)
    
    if TAVILY_KEY:
        st.markdown("<span style='font-size:0.8rem; color:#4ade80;'>✅ Tavily API Key Linked Safely</span>", unsafe_allow_html=True)
    else:
        st.markdown("<span style='font-size:0.8rem; color:#f87171;'>❌ Missing TAVILY_API_KEY in Secrets</span>", unsafe_allow_html=True)
        
    web_query = st.text_input("Enter topic to scrape & index...", placeholder="e.g. Current AI news", label_visibility="collapsed")
    
    RESTRICTED_TERMS = [
        "porn", "nsfw", "xxx", "sex", "nude", "onlyfans", "erotic",
        "kill", "suicide", "murder", "gore", "violence", "torture", "dead body",
        "weapon", "bomb", "gun", "ammunition", "firearm", "explosive", "rifle",
        "drugs", "meth", "cocaine", "heroin"
    ]
    
    if st.button("SEARCH & INDEX", use_container_width=True):
        if not TAVILY_KEY or not TAVILY_KEY.startswith("tvly-"):
            st.error("No active Tavily API Key found in Streamlit Secrets.")
        elif web_query:
            query_lower = web_query.lower()
            violation_found = any(term in query_lower for term in RESTRICTED_TERMS)
            
            if violation_found:
                st.error("🚨 **SECURITY ALERT:** Your search query violates safety policy.")
            else:
                with st.spinner("Executing secure web retrieval..."):
                    try:
                        api_url = "https://api.tavily.com/search"
                        payload = {
                            "api_key": TAVILY_KEY.strip(),
                            "query": web_query,
                            "search_depth": "advanced",
                            "include_answer": False,
                            "include_images": False,
                            "include_raw_content": False,
                            "max_results": 10
                        }
                        
                        response = requests.post(api_url, json=payload, timeout=25)
                        
                        if response.status_code == 200:
                            data = response.json()
                            results = data.get("results", [])
                            unique_docs = {}
                            
                            for r in results:
                                source_url = r.get('url', '')
                                content = r.get('content', '')
                                title = r.get('title', 'Verified Source')
                                
                                if source_url and content and (source_url not in unique_docs):
                                    unique_docs[source_url] = {"content": content, "title": title}
                                    
                            web_docs = []
                            for url, info in unique_docs.items():
                                web_docs.append(Document(
                                    page_content=f"Title: {info['title']}\nSource: {url}\nContext: {info['content']}",
                                    metadata={"source": url, "title": info['title']}
                                ))
                                
                            if web_docs:
                                chunks = text_splitter.split_documents(web_docs)
                                valid_chunks = [c for c in chunks if c.page_content.strip()]
                                
                                if valid_chunks:
                                    if st.session_state.vector_db is None: 
                                        st.session_state.vector_db = FAISS.from_documents(valid_chunks, embedder)
                                    else: 
                                        st.session_state.vector_db.add_documents(valid_chunks)
                                        
                                    st.session_state.node_count += len(valid_chunks)
                                    st.success(f"Indexed {len(valid_chunks)} verified blocks via Tavily!")
                        else:
                            st.error(f"Tavily API Error: {response.text}")
                    except Exception as e:
                        st.error(f"Tavily connection failed: {str(e)}")
    st.markdown("</div>", unsafe_allow_html=True)

    # --- LOCAL DOCUMENTS INDEXER ---
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>📚 Local Documents</div>", unsafe_allow_html=True)
    uploaded_files = st.file_uploader("Upload course materials...", type=["pdf", "txt"], accept_multiple_files=True, label_visibility="collapsed", key="file_in")
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
                        if suffix == ".pdf": docs.extend(PyPDFLoader(path).load())
                        elif suffix == ".txt": docs.extend(TextLoader(path, encoding="utf-8").load())
                    except Exception: pass
                    finally:
                        if os.path.exists(path): os.unlink(path)
                            
                if docs:
                    chunks = text_splitter.split_documents(docs)
                    valid_chunks = [c for c in chunks if c.page_content.strip()]
                    
                    if valid_chunks:
                        if st.session_state.vector_db is None: 
                            st.session_state.vector_db = FAISS.from_documents(valid_chunks, embedder)
                        else: 
                            st.session_state.vector_db.add_documents(valid_chunks)
                        st.session_state.node_count += len(valid_chunks)
                        st.success(f"Successfully Indexed {len(valid_chunks)} document blocks.")
    st.markdown("</div>", unsafe_allow_html=True)

# ================= MIDDLE COLUMN: MAIN STUDY CONSOLE =================
with col_mid:
    if not st.session_state.chat_history:
        st.markdown("""
        <div style='margin-top: 50px; margin-bottom: 30px; text-align: center;'>
            <h2 style='color: #f97316; font-family: "Inter", sans-serif; font-weight: 700;'>Study Console Initialized</h2>
            <p style='color: #a1a1aa; font-family: "JetBrains Mono", monospace; font-size: 0.85rem;'>Use the left panel to index Web Data or Local Files, then chat here.</p>
        </div>
        """, unsafe_allow_html=True)
    
    chat_scroll_pane = st.container(height=650, border=False)
    
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
            retriever = st.session_state.vector_db.as_retriever(search_kwargs={"k": 5})
            matched_nodes = retriever.invoke(user_query)
            context_payload = "\n\n".join([f"[{node.metadata.get('source', 'Unknown')}]\n{node.page_content}" for node in matched_nodes])
            sys_instruction = "You are APOLLO OMNI AI, an advanced AI study buddy. Formulate a crisp response using ONLY the provided context below. DO NOT include raw URLs or brackets."
            clean_ctx = context_payload.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            st.session_state.source_reference = f"<div class='source-box'><strong>Active Context (RAG):</strong><br><br>{clean_ctx}</div>"
        else:
            sys_instruction = "You are APOLLO OMNI AI, an advanced AI study buddy. Answer based on general knowledge. Be crisp and concise."
            st.session_state.source_reference = "<div class='source-box font-mono'>No active context. General weights used.</div>"

        message_stream = [{"role": "system", "content": sys_instruction}]
        for msg in st.session_state.chat_history[-4:]:
            message_stream.append({"role": msg["role"], "content": msg["content"]})
        message_stream.append({"role": "user", "content": f"Context Matrix:\n{context_payload}\n\nQuery: {user_query}"})
        
        with chat_scroll_pane:
            with st.chat_message("assistant"):
                try:
                    stream = generate_llm_stream(message_stream, OR_TOKEN, selected_model)
                    collected_tokens = st.write_stream(stream)
                    
                    if not collected_tokens or not str(collected_tokens).strip(): 
                        collected_tokens = "⚠️ EMPTY RESPONSE."
                        st.markdown(collected_tokens)
                        
                except Exception as ex:
                    collected_tokens = f"❌ FRAMEWORK API FAILURE: {ex}"
                    st.markdown(collected_tokens)
        
        st.session_state.chat_history.append({"role": "assistant", "content": collected_tokens})
        st.session_state.response_time = f"{time.time() - start_time:.2f}s"
        st.rerun()

# ================= RIGHT COLUMN: PERFORMANCE & TELEMETRY MATRIX =================
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
