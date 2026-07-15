import os
import time
import tempfile
import streamlit as st
from huggingface_hub import InferenceClient
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

# 1. Page Configuration & Title
st.set_page_config(layout="wide", page_title="APOLLO", page_icon="☀️")

# 2. Setup High-Availability Cloud Inference Engine
HF_TOKEN = os.getenv("HF_TOKEN")
LLM_MODEL = "Qwen/Qwen2.5-72B-Instruct"
client = InferenceClient(LLM_MODEL, token=HF_TOKEN)

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
if "vector_db" not in st.session_state:
    st.session_state.vector_db = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "response_time" not in st.session_state:
    st.session_state.response_time = "0.00s"
if "source_reference" not in st.session_state:
    st.session_state.source_reference = "<div class='source-box'>Awaiting data vector alignment...</div>"
if "node_count" not in st.session_state:
    st.session_state.node_count = 0

# 5. Advanced CSS Injection: Premium Crimson, Gold & Clean Minimalist UI
st.markdown("""
<style>
    /* Global System Core Layout */
    .stApp {
        background-color: #000000 !important;
        background-image: 
            radial-gradient(circle at 50% 15%, rgba(255, 60, 60, 0.12) 0%, transparent 60%),
            radial-gradient(circle at 85% 80%, rgba(0, 120, 255, 0.06) 0%, transparent 50%) !important;
        color: #ffffff !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Cyber Glass Cards */
    .cyber-card {
        background: rgba(10, 12, 18, 0.65) !important;
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 20px;
        padding: 22px;
        margin-bottom: 20px;
        box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.8);
    }
    
    .system-title {
        font-size: 2.6rem;
        font-weight: 900;
        letter-spacing: 10px;
        text-align: center;
        text-transform: uppercase;
        background: linear-gradient(135deg, #ffffff 0%, #ffaa00 50%, #ff3333 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 3px;
        text-shadow: 0 0 35px rgba(255, 170, 0, 0.15);
    }
    
    .system-subtitle {
        font-size: 0.75rem;
        color: #666666;
        text-transform: uppercase;
        letter-spacing: 4px;
        text-align: center;
        margin-bottom: 35px;
    }
    
    /* Dynamic Performance Telemetry Displays */
    .metric-card {
        background: rgba(15, 20, 32, 0.5) !important;
        backdrop-filter: blur(12px);
        border: 1px solid rgba(0, 150, 255, 0.15) !important;
        border-radius: 12px;
        padding: 14px;
        text-align: center;
        transition: all 0.3s ease;
    }
    .metric-card:hover {
        border-color: rgba(0, 150, 255, 0.4);
        box-shadow: 0 0 15px rgba(0, 150, 255, 0.15);
    }
    .metric-value { 
        font-size: 24px; 
        font-weight: 800; 
        color: #00bfff; 
        text-shadow: 0 0 10px rgba(0, 191, 255, 0.3); 
    }
    .metric-title { 
        font-size: 10px; 
        color: #888888; 
        text-transform: uppercase; 
        letter-spacing: 1px; 
    }
    
    /* Source Matrix Viewer */
    .source-box {
        background: rgba(15, 5, 5, 0.5) !important;
        backdrop-filter: blur(12px);
        border-left: 3px solid #ff3333;
        border-top: 1px solid rgba(255, 51, 51, 0.08);
        border-right: 1px solid rgba(255, 51, 51, 0.08);
        border-bottom: 1px solid rgba(255, 51, 51, 0.08);
        padding: 14px;
        border-radius: 4px 12px 12px 4px;
        font-size: 13px;
        color: #cccccc;
        max-height: 480px;
        overflow-y: auto;
    }

    /* Asymmetric Chat Injections */
    div[data-testid="stChatMessage"]:has(div[aria-label="Chat message from user"]) {
        background: linear-gradient(135deg, #cc2222 0%, #881111 100%) !important;
        border-radius: 24px 24px 4px 24px !important;
        color: white !important;
        border: none !important;
        margin-left: 15% !important;
        box-shadow: 0 4px 15px rgba(204, 34, 34, 0.15);
    }
    
    div[data-testid="stChatMessage"]:has(div[aria-label="Chat message from assistant"]) {
        background: rgba(0, 35, 70, 0.35) !important;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(0, 150, 255, 0.25) !important;
        border-radius: 24px 24px 24px 4px !important;
        color: #e2e8f0 !important;
        margin-right: 15% !important;
        box-shadow: 0 0 20px rgba(0, 150, 255, 0.1);
    }

    /* Interactive Inputs */
    div[data-testid="stChatInput"] textarea {
        background-color: #070709 !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        color: white !important;
        border-radius: 12px !important;
    }
    div[data-testid="stChatInput"] textarea:focus {
        border-color: #ffaa00 !important;
        box-shadow: 0 0 10px rgba(255, 170, 0, 0.25) !important;
    }
    section[data-testid="stFileUploadDropzone"] {
        background-color: rgba(15, 15, 20, 0.4) !important;
        border: 1px dashed rgba(255, 51, 51, 0.25) !important;
        border-radius: 14px !important;
    }
</style>
""", unsafe_allow_html=True)

# 6. File Processing Execution Path
def process_uploaded_files(files):
    docs = []
    for f in files:
        suffix = os.path.splitext(f.name)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(f.read())
            path = tmp.name
        try:
            if suffix == ".pdf":
                loader = PyPDFLoader(path)
                docs.extend(loader.load())
            elif suffix == ".txt":
                loader = TextLoader(path, encoding="utf-8")
                docs.extend(loader.load())
        except Exception as e:
            st.error(f"Execution Error Parsing {f.name}: {e}")
        finally:
            if os.path.exists(path):
                os.unlink(path)
    return docs

# 7. Layout Distribution Matrix
st.markdown("<div class='system-title'>APOLLO</div>", unsafe_allow_html=True)
st.markdown("<div class='system-subtitle'>HIGH-AVAILABILITY CORE CONTROL ENVIRONMENT // V2.0</div>", unsafe_allow_html=True)

col_left, col_mid, col_right = st.columns([2.7, 4.8, 2.5], gap="large")

# ================= LEFT COLUMN: DATA ASSITS STORAGE =================
with col_left:
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("### 💾 DATA INGESTION ENGINE")
    uploaded_files = st.file_uploader("Upload assets...", type=["pdf", "txt"], accept_multiple_files=True, label_visibility="collapsed")
    
    if st.button("SYNCHRONIZE VECTOR SPACE", use_container_width=True, type="primary"):
        if uploaded_files:
            with st.spinner("Compiling multi-dimensional spaces..."):
                parsed_docs = process_uploaded_files(uploaded_files)
                if parsed_docs:
                    chunks = text_splitter.split_documents(parsed_docs)
                    st.session_state.vector_db = FAISS.from_documents(chunks, embedder)
                    st.session_state.node_count = len(chunks)
                    st.success(f"Mapped {st.session_state.node_count} contextual blocks.")
        else:
            st.warning("Data arrays missing. Ingest structural files.")
    st.markdown("</div>", unsafe_allow_html=True)
        
    # Operations Controls Panel
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("### 🛠️ SYSTEM WORKSPACE")
    btn_c1, btn_c2 = st.columns(2)
    with btn_c1:
        if st.button("🧹 PURGE LOGS", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.response_time = "0.00s"
            st.session_state.source_reference = "<div class='source-box'>Awaiting data vector alignment...</div>"
            st.rerun()
    with btn_c2:
        chat_log = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in st.session_state.chat_history])
        st.download_button("💾 EXPORT TEXT", data=chat_log, file_name="apollo_session_export.txt", mime="text/plain", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ================= MIDDLE COLUMN: MAIN CHAT INTERACTION VIEW =================
with col_mid:
    # Display Chat Array
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    # Input Stream Listener
    user_query = st.chat_input("Pass prompt to Apollo network...")
    
    if user_query:
        with st.chat_message("user"):
            st.markdown(user_query)
        st.session_state.chat_history.append({"role": "user", "content": user_query})
        
        if st.session_state.vector_db is None:
            err_msg = "⚠️ CORE PIPELINE ERROR: Vector core uninitialized. Mount context arrays via the Left Panel."
            with st.chat_message("assistant"):
                st.markdown(err_msg)
            st.session_state.chat_history.append({"role": "assistant", "content": err_msg})
        else:
            start_time = time.time()
            
            # Context Retrieval Segment
            retriever = st.session_state.vector_db.as_retriever(search_kwargs={"k": 4})
            matched_nodes = retriever.invoke(user_query)
            context_payload = "\n\n".join([f"[Retrieved Document Chunk {i+1}]\n{node.page_content}" for i, node in enumerate(matched_nodes)])
            
            sys_instruction = (
                "You are APOLLO, a hyper-intelligent cloud AI cluster interface. "
                "Formulate a flawless, analytical response using ONLY the verified context payload provided below. "
                "Structure your execution clean using concise phrasing or bold details. If context elements don't answer the prompt, declare it directly."
            )
            
            message_stream = [{"role": "system", "content": sys_instruction}]
            for msg in st.session_state.chat_history[-4:]:
                message_stream.append({"role": msg["role"], "content": msg["content"]})
            message_stream.append({"role": "user", "content": f"Context Matrix:\n{context_payload}\n\nQuery: {user_query}"})
            
            # Response Streaming Process
            with st.chat_message("assistant"):
                response_container = st.empty()
                collected_tokens = ""
                try:
                    # Optimized, fixed configuration values hidden for a distraction-free professional UI
                    stream = client.chat_completion(
                        messages=message_stream, max_tokens=1024, stream=True, temperature=0.2
                    )
                    for chunk in stream:
                        token = chunk.choices[0].delta.content
                        if token:
                            collected_tokens += token
                            response_container.markdown(collected_tokens + " █")
                    
                    if not collected_tokens.strip():
                        collected_tokens = "⚠️ ENDPOINT TIMEOUT FALLBACK: The serverless grid returned an empty sequence. Re-submitting the query stream usually fixes this."
                        
                    response_container.markdown(collected_tokens)
                except Exception as ex:
                    collected_tokens = f"❌ FRAMEWORK API CRITICAL FAILURE: {ex}"
                    response_container.markdown(collected_tokens)
            
            st.session_state.chat_history.append({"role": "assistant", "content": collected_tokens})
            st.session_state.response_time = f"{time.time() - start_time:.2f}s"
            
            clean_ctx = context_payload.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            st.session_state.source_reference = f"<div class='source-box'><strong>Attributed Node Matrix:</strong><br><br>{clean_ctx}</div>"
            st.rerun()

# ================= RIGHT COLUMN: PERFORMANCE & DATA TELEMETRY =================
with col_right:
    st.markdown("### 📊 DASHBOARD METRICS")
    
    st.markdown(f"<div class='metric-card'><div class='metric-title'>Inference Latency</div><div class='metric-value'>{st.session_state.response_time}</div></div>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"<div class='metric-card'><div class='metric-title'>Context Nodes Injected</div><div class='metric-value'>{st.session_state.node_count}</div></div>", unsafe_allow_html=True)
    
    st.markdown("<br>### 📑 VERIFIED RETRIEVAL MATRIX", unsafe_allow_html=True)
    st.markdown(st.session_state.source_reference, unsafe_allow_html=True)
