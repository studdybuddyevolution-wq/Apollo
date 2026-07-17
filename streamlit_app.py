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
st.set_page_config(layout="wide", page_title="APOLLO OMNI AI", page_icon="⚡")

# 2. Key/Token Initialization (Exclusively OpenRouter)
OR_TOKEN = os.getenv("OPENROUTER_API_KEY")

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

# 5. Stable 100% Free OpenRouter Model Matrix
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

# 6. OpenRouter Exclusive LLM Streamer
def generate_llm_stream(messages, token, selected_model_name):
    if not token or not token.startswith("sk-or-"):
        yield "❌ MISSING CONFIGURATION: Please set a valid 'OPENROUTER_API_KEY' starting with 'sk-or-v1-'."
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

# 7. Advanced CSS Injection
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
        color: #4ade80;
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
    .stButton button {
        background: linear-gradient(180deg, #f97316 0%, #ea580c 100%) !important;
        color: #fff !important;
        border: none !important;
    }
</style>
""", unsafe_allow_html=True)

# Custom Brand Header Matrix (Renders logo if present, else drops back to pristine font layout)
if os.path.exists("logo.png"):
    col_logo, col_badge = st.columns([8, 2])
    with col_logo:
        st.image("logo.png", width=220)
    with col_badge:
        st.markdown("<div style='text-align: right; margin-top: 15px;'><span class='status-badge'>● OPENROUTER LINKED</span></div>", unsafe_allow_html=True)
    st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin-top: -10px; margin-bottom: 30px;'>", unsafe_allow_html=True)
else:
    st.markdown("""
    <div class='header-bar'>
        <div class='header-left'>
            <div style='font-size: 1.25rem; font-weight: 700; letter-spacing: 0.05em; color: white;'>APOLLO <span style='color: #f97316;'>OMNI AI</span></div>
        </div>
        <div class='status-badge'>● OPENROUTER LINKED</div>
    </div>
    """, unsafe_allow_html=True)

col_left, col_mid, col_right = st.columns([3, 6, 3], gap="large")

# ================= LEFT COLUMN: INGESTION ENGINE =================
with col_left:
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>⚙️ Zero-Cost Engine</div>", unsafe_allow_html=True)
    selected_model = st.selectbox("API Gateway Endpoint:", options=list(MODEL_OPTIONS.keys()), index=0)
    st.caption(f"**Desc:** {MODEL_OPTIONS[selected_model]['desc']}")
    st.markdown("</div>", unsafe_allow_html=True)

    # --- WEB SEARCH INDEXER WITH BOT BYPASS FIX ---
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-header'>🌐 Web Search Indexer</div>", unsafe_allow_html=True)
    web_query = st.text_input("Enter topic to scrape & index...", placeholder="e.g. Current AI news", label_visibility="collapsed")
    if st.button("SEARCH & INDEX", use_container_width=True):
        if web_query:
            with st.spinner("Scraping and chunking web data..."):
                try:
                    # Bypass DuckDuckGo bot-protection by forcing the HTML backend
                    results = DDGS().text(web_query, max_results=4, backend="html")
                    
                    # If HTML fails, fallback to the Lite backend
                    if not results:
                        results = DDGS().text(web_query, max_results=4, backend="lite")
                        
                    if results:
                        web_docs = []
                        for r in results:
                            doc = Document(
                                page_content=r['body'], 
                                metadata={"source": r['href'], "title": r['title']}
                            )
                            web_docs.append(doc)
                            
                        chunks = text_splitter.split_documents(web_docs)
                        if st.session_state.vector_db is None: 
                            st.session_state.vector_db = FAISS.from_documents(chunks, embedder)
                        else: 
                            st.session_state.vector_db.add_documents(chunks)
                            
                        st.session_state.node_count += len(chunks)
                        st.success(f"Indexed {len(chunks)} blocks from web!")
                    else:
                        st.warning("No web results found.")
                except Exception as e:
                    st.error(f"Search failed: {str(e)}")
    st.markdown("</div>", unsafe_allow_html=True)

    # --- LOCAL DOCUMENTS INDEXER ---
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
        
        # STANDARD LOCAL RAG LOGIC ONLY
        if st.session_state.vector_db is not None:
            retriever = st.session_state.vector_db.as_retriever(search_kwargs={"k": 5})
            matched_nodes = retriever.invoke(user_query)
            context_payload = "\n\n".join([f"[{node.metadata.get('source', 'Unknown')}]\n{node.page_content}" for node in matched_nodes])
            sys_instruction = "You are APOLLO OMNI AI, an advanced AI study buddy. Formulate a response using ONLY the provided context below. CITE YOUR SOURCES in your answer."
            clean_ctx = context_payload.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            st.session_state.source_reference = f"<div class='source-box'><strong>Active Context (RAG):</strong><br><br>{clean_ctx}</div>"
            
        else:
            sys_instruction = "You are APOLLO OMNI AI, an advanced AI study buddy. (Answering based on general knowledge)."
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
                    stream = generate_llm_stream(message_stream, OR_TOKEN, selected_model)
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
