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
    st.stop()

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
if "authenticated" not in st.session_state:
    if auth_cookie == "verified_student":
        st.session_state.authenticated = True
    else:
        st.session_state.authenticated = False

if "otp_sent" not in st.session_state: st.session_state.otp_sent = False
if "generated_otp" not in st.session_state: st.session_state.generated_otp = None
if "user_email" not in st.session_state: st.session_state.user_email = ""

# NotebookLM-Style PPT Studio State
if "slides_data" not in st.session_state:
    st.session_state.slides_data = [
        {"title": "Introduction to Institutional AI", "bullets": ["Overview of Apollo Omni platform", "Secure @somaiya.edu integration"]},
        {"title": "Core Architecture & Workflow", "bullets": ["Retrieval-Augmented Generation (RAG)", "Multi-model micro-agent routing"]}
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

# 8. Gemini PPT Generator Function
def generate_slides_with_gemini(topic, gemini_key):
    if not gemini_key:
        return None, "Missing GEMINI_API_KEY in Streamlit Secrets."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
    headers = {"Content-Type": "application/json"}
    
    prompt = f"""Create a comprehensive presentation outline about '{topic}'. 
    Return ONLY a valid JSON array of objects, where each object has a 'title' (string) and 'bullets' (list of 3-4 structured strings). Do not include markdown formatting code blocks like ```json, just return raw JSON text.
    Example format:
    [
      {{"title": "Slide Title", "bullets": ["Bullet point 1", "Bullet point 2"]}}
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
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            text_output = data['candidates'][0]['content']['parts'][0]['text']
            parsed_json = json.loads(text_output)
            return parsed_json, "Success"
        else:
            return None, f"Gemini API Error ({response.status_code}): {response.text}"
    except Exception as e:
        return None, str(e)

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
        
        def create_pptx(data):
            prs = Presentation()
            for item in data:
                slide_layout = prs.slide_layouts[1]
                slide = prs.slides.add_slide(slide_layout)
                slide.shapes.title.text = item["title"]
                tf = slide.placeholders[1].text_frame
                for bullet in item["bullets"]:
                    p = tf.add_paragraph()
                    p.text = bullet
            path = "apollo_presentation.pptx"
            prs.save(path)
            return path

        if st.button("📥 Download .pptx File", use_container_width=True):
            file_path = create_pptx(st.session_state.slides_data)
            with open(file_path, "rb") as f:
                st.download_button(
                    label="Click here to download",
                    data=f,
                    file_name="Apollo_Presentation.pptx",
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
                        api_url = "[https://api.tavily.com/search](https://api.tavily.com/search)"
                        payload = {
                            "api_key": TAVILY_KEY,
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
    if
