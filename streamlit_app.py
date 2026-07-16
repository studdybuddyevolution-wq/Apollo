import os
import time
import tempfile
import json
import requests
import streamlit as st
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from duckduckgo_search import DDGS

# 1. Page Configuration & Title
st.set_page_config(layout="wide", page_title="APOLLO OMNI", page_icon="⚡")

# 2. Key/Token Initialization
HF_TOKEN = os.getenv("HF_TOKEN")

# 3. Resource Caching Pipelines
@st.cache_resource
def get_embedding_model():
    return HuggingFaceEmbeddings(
        model_name="BAAI/bge-large-en-v1.5",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )

@st.cache_resource
def get_text_splitter():
    return RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

embedder = get_embedding_model()
text_splitter = get_text_splitter()

# 4. State Management Matrix
if "vector_db" not in st.session_state: st.session_state.vector_db = None
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "response_time" not in st.session_state: st.session_state.response_time = "0.00s"
if "source_reference" not in st.session_state: st.session_state.source_reference = "<div class='source-box font-mono'>Awaiting vector alignment...</div>"
if "node_count" not in st.session_state: st.session_state.node_count = 0

MODEL_OPTIONS = {
    "Auto-Free Router (Recommended)": {
        "or_id": "openrouter/free",
        "hf_id": "Qwen/Qwen2.5-72B-Instruct",
        "desc": "Highly stable. Dynamically load-balances across zero-cost models."
    },
    "Google Gemma 4 31B (Free)": {
        "or_id": "google/gemma-4-31b-it:free",
        "hf_id": "google/gemma-4-31b-it",
        "desc": "Exceptional reasoning. Prone to individual upstream rate-limiting."
    },
    "Meta Llama 3.3 70B (Free)": {
        "or_id": "meta-llama/llama-3.3-70b-instruct:free",
        "hf_id": "meta-llama/Llama-3.3-70B-Instruct",
        "desc": "Meta's flagship 70B. Reliable, subject to occasional provider limits."
    }
}

# 5. Intelligent Hybrid LLM Streamer
def generate_llm_stream(messages, token, selected_model_name):
    if not token:
        yield "❌ MISSING CONFIGURATION: Please set your 'HF_TOKEN' secret or environment variable."
        return

    model_config = MODEL_OPTIONS[selected_model_name]
    model_id = model_config["or_id"]

    if token.strip().startswith("sk-or-"):
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {token.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/streamlit/streamlit",
            "X-Title": "APOLLO OMNI"
        }
        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1024,
            "stream": True
        }
        
        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=30)
        
        if response.status_code == 429 and selected_model_name != "Auto-Free Router (Recommended)":
            yield "⚠️ *Engine rate-limited. Activating emergency pivot to Auto-Free Router...*\n\n"
            time.sleep(1)
            payload["model"] = "openrouter/free"
            response = requests.post(url, headers=headers, json=payload, stream=True, timeout=30)
            
        if response.status_code != 200:
            yield f"❌ OpenRouter API Error ({response.status_code}): {response.text}"
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
    else:
        from huggingface_hub import InferenceClient
        hf_model = model_config["hf_id"]
        try:
            client = InferenceClient(hf_model, token=token.strip())
            stream = client.chat_completion(messages=messages, max_tokens=1024, stream=True, temperature=0.2)
            for chunk in stream:
                token_text = chunk.choices[0].delta.content
                if token_text:
                    yield token_text
        except Exception as e:
            yield f"❌ Hugging Face API Error: {str(e)}"

# 6. Advanced CSS Injection
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');
    
    .stApp { 
        background-color: #0f0f11 !important; 
        background-image: linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px) !important;
        background-size: 20px 20px !important;
        color: #e5e7eb !important; 
        font-family: 'Inter', sans-serif !important; 
    }
    
    .font-mono { font-family: 'JetBrains Mono', monospace !important; }
    
    .header-bar {
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        background: rgba(24, 24, 27, 0.8);
        backdrop-filter: blur(12px);
        padding: 15px 24px;
        margin-top: -60px;
        margin-bottom: 30px;
        border-radius: 0 0 12px 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .header-title { font-size: 1.25rem; font-weight: 700; letter-spacing: 0.05em; color: white; }
    .header-title span { color: #f97316; }
    .status-badge {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        background: rgba(34, 197, 94, 0.1);
        color: #4ade80;
        border: 1px solid rgba(34, 197, 94, 0.2);
        padding: 2px 8px;
        border-radius: 4px;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    
    .cyber-card { 
        background: rgba(24, 24, 27, 0.8) !important; 
        backdrop-filter: blur(8px); 
        border: 1px solid rgba(255, 255, 255, 0.1); 
        border-radius: 8px; 
        padding: 16px; 
        margin-bottom: 20px; 
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .panel-header {
        font-size: 0.875rem;
        font-weight: 600;
        letter-spacing: 0.05em;
        color: #d4d4d8;
        text-transform: uppercase;
        margin-bottom: 16px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        padding-bottom: 8px;
    }

    .metric-value { font-size: 1.875rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: #fff; text-shadow: 0 0 10px rgba(249, 115, 22, 0.5); }
    .metric-title { font-size: 0.75rem; color: #71717a; text-transform: uppercase; font-family: 'JetBrains Mono', monospace; margin-bottom: 4px; }

    div[data-testid="stChatMessage"]:has(div[aria-label="Chat message from user"]) { 
        background: rgba(56, 189, 248, 0.05) !important; 
        border-left: 2px solid #38bdf8 !important; 
        border-radius: 4px 12px 12px 4px !important; 
        color: #e5e7eb !important; 
    }
    div[data-testid="stChatMessage"]:has(div[aria-label="Chat message from assistant"]) { 
        background: rgba(249, 115, 22, 0.05) !important; 
        border-left: 2px solid #f97316 !important; 
        border-radius: 4px 12px 12px 4px !important; 
        color: #e5e7eb !important; 
        box-shadow: inset 4px 0 0 rgba(249, 115, 22, 0.2);
    }
    
    div[data-testid="stChatInput"] textarea { 
        background-color: #0a0a0c !important; 
        border: 1px solid rgba(255, 255, 255, 0.1) !important; 
        color: white !important; 
        font-family: 'JetBrains Mono', monospace !important;
    }
    div[data-testid="stChatInput"] textarea:focus {
        border-color: #f97316 !important;
        box-shadow: 0 0 0 1px #f97316 !important;
    }
    .stButton button {
        background: linear-gradient(180deg, #f97316 0%, #ea580c 100%) !important;
        color: #fff !important;
        border: none !important;
        box-shadow: 0 0 15px rgba(249, 115, 22, 0.2) !important;
        transition: all 0.2s ease !important;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.05em;
    }
    .stButton button:hover {
        box-shadow: 0 0 25px rgba(249, 115, 22, 0.4) !important;
        transform: translateY(-1px) !important;
    }
    section[data-testid="stFileUploadDropzone"] { 
        background-color: rgba(24, 24, 27, 0.5) !important; 
        border: 1px dashed rgba(255, 255, 255, 0.2) !important; 
    }
    
    .source-box { 
        background: #0a0a0c !important; 
        border: 1px solid rgba(255, 255, 255, 0.1); 
        padding: 12px; 
        border-radius: 6px; 
        font-size: 0.75rem; 
        color: #94a3b8; 
        max-height: 300px; 
        overflow-y: auto; 
    }
    .source-box strong { color: #f97316; }
</style>
""", unsafe_allow_html=True)

# Custom Header
st.markdown("""
<div class='header-bar'>
    <div class='header-title'>APOLLO <span>OMNI</span></div>
    <div class='status-badge'>● SYSTEM NOMINAL</div>
</div>
""", unsafe_allow_html=True)

col_left, col_mid, col_right = st.columns([3, 6, 3], gap="large")

# ================= LEFT COLUMN: INGESTION ENGINE =================
with col_left:
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>⚙️ RAG Engine Settings</div>", unsafe_allow_html=True)
    selected_model = st.selectbox("AI Engine Core:", options=list(MODEL_OPTIONS.keys()), index=0)
    st.caption(f"**Desc:** {MODEL_OPTIONS[selected_model]['desc']}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>📚 Local Documents</div>", unsafe_allow_html=True)
    uploaded_files = st.file_uploader("Upload course materials...", type=["pdf", "txt"], accept_multiple_files=True, label_visibility="collapsed", key="file_in")
    if st.button("SYNC KNOWLEDGE BASE", use_container_width=True):
        if uploaded_files:
            with st.spinner("Indexing materials..."):
                docs = []
                for f in uploaded_files:
                    suffix = os.path.splitext(f.name)[1].lower()
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(f.read())
                        path = tmp.name
                    try:
                        if suffix == ".pdf": docs.extend(PyPDFLoader(path).load())
                        elif suffix == ".txt": docs.extend(TextLoader(path, encoding="utf-8").load())
                    except Exception: pass
                    finally:
                        if os.path.exists(path): os.unlink(path)
                if docs:
                    chunks = text_splitter.split_documents(docs)
                    if st.session_state.vector_db is None: 
                        st.session_state.vector_db = FAISS.from_documents(chunks, embedder)
                    else: 
                        st.session_state.vector_db.add_documents(chunks)
                    st.session_state.node_count += len(chunks)
                    st.success(f"Indexed {len(chunks)} blocks.")
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>🌐 Tip: Autonomous RAG</div>", unsafe_allow_html=True)
    st.info("To perform a zero-cost live web search, type `/search [query]` into the chat box. Apollo Omni will scrape the live internet to answer your question.")
    st.markdown("</div>", unsafe_allow_html=True)

# ================= MIDDLE COLUMN: MAIN STUDY CONSOLE =================
with col_mid:
    if not st.session_state.chat_history:
        st.markdown("""
        <div style='margin-top: 50px; margin-bottom: 30px; text-align: center;'>
            <h2 style='color: #f97316; font-family: "Inter", sans-serif; font-weight: 700;'>Study Console Initialized</h2>
            <p style='color: #a1a1aa; font-family: "JetBrains Mono", monospace; font-size: 0.85rem;'>Awaiting document ingestion or queries...</p>
        </div>
        """, unsafe_allow_html=True)
    
    chat_scroll_pane = st.container(height=650, border=False)
    
    with chat_scroll_pane:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
            
    user_query = st.chat_input("Enter query or /search [topic]...")
    
    if user_query:
        st.session_state.chat_history.append({"role": "user", "content": user_query})
        
        start_time = time.time()
        context_payload = ""
        sys_instruction = "You are APOLLO OMNI, an advanced AI study buddy."
        
        # ZERO-COST AUTONOMOUS RAG LOGIC
        if user_query.lower().startswith("/search "):
            search_query = user_query[8:].strip()
            with chat_scroll_pane:
                with st.chat_message("assistant"):
                    st.markdown(f"🌐 *Scraping live internet for:* `{search_query}`...")
            try:
                # DuckDuckGo Zero-Cost Search
                results = DDGS().text(search_query, max_results=4)
                if results:
                    scraped_data = "\n\n".join([f"Source: {r['title']} ({r['href']})\nExcerpt: {r['body']}" for r in results])
                    context_payload = f"LIVE WEB SEARCH RESULTS FOR '{search_query}':\n\n{scraped_data}"
                    sys_instruction = "You are APOLLO OMNI. You have just performed a live web search. Use ONLY the following real-time web context to answer the user's query comprehensively and cite the URL sources provided."
                    st.session_state.source_reference = f"<div class='source-box'><strong>Live Web Data Extracted:</strong><br><br>{context_payload.replace(chr(10), '<br>')}</div>"
                else:
                    context_payload = "No web results found."
            except Exception as e:
                context_payload = f"Web search failed: {str(e)}"
        
        # STANDARD LOCAL RAG LOGIC
        elif st.session_state.vector_db is not None:
            retriever = st.session_state.vector_db.as_retriever(search_kwargs={"k": 5})
            matched_nodes = retriever.invoke(user_query)
            context_payload = "\n\n".join([f"[{node.metadata.get('source', 'Unknown')}]\n{node.page_content}" for node in matched_nodes])
            sys_instruction = "You are APOLLO OMNI, an advanced AI study buddy. Formulate a flawless response using ONLY the provided context below. CITE YOUR SOURCES in your answer."
            clean_ctx = context_payload.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            st.session_state.source_reference = f"<div class='source-box'><strong>Active Context (RAG):</strong><br><br>{clean_ctx}</div>"
            
        else:
            sys_instruction = "You are APOLLO OMNI, an advanced AI study buddy. (No documents uploaded yet, answer based on general knowledge)."
            st.session_state.source_reference = "<div class='source-box font-mono'>No active context. General weights used.</div>"

        # GENERATE RESPONSE
        message_stream = [{"role": "system", "content": sys_instruction}]
        for msg in st.session_state.chat_history[-4:]:
            message_stream.append({"role": msg["role"], "content": msg["content"]})
        message_stream.append({"role": "user", "content": f"Context Matrix:\n{context_payload}\n\nQuery: {user_query}"})
        
        with chat_scroll_pane:
            with st.chat_message("assistant"):
                response_container = st.empty()
                collected_tokens = ""
                try:
                    stream = generate_llm_stream(message_stream, HF_TOKEN, selected_model)
                    for chunk in stream:
                        collected_tokens += chunk
                        response_container.markdown(collected_tokens + " █")
                    if not collected_tokens.strip(): 
                        collected_tokens = "⚠️ EMPTY RESPONSE."
                    response_container.markdown(collected_tokens)
                except Exception as ex:
                    collected_tokens = f"❌ FRAMEWORK API FAILURE: {ex}"
                    response_container.markdown(collected_tokens)
        
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
    st.markdown("</div>", unsafe_allow_html=True)
