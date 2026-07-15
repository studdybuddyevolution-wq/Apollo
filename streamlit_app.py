import os
import time
import tempfile
import requests
import streamlit as st
from huggingface_hub import InferenceClient
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from duckduckgo_search import DDGS

# 1. Page Configuration & Title
st.set_page_config(layout="wide", page_title="APOLLO OMNI", page_icon="☀️")

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

# 4. Data Ingestion Helper Functions
@st.cache_data(show_spinner=False)
def fetch_github_repo_files(repo_url):
    try:
        parts = repo_url.replace("https://github.com/", "").strip("/").split("/")
        if len(parts) < 2: return None, "Invalid GitHub URL format."
        owner, repo = parts[0], parts[1]
        
        api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/main?recursive=1"
        response = requests.get(api_url)
        if response.status_code != 200: 
            api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/master?recursive=1"
            response = requests.get(api_url)
            
        if response.status_code == 200:
            tree = response.json().get("tree", [])
            files_data = []
            allowed_extensions = ('.py', '.md', '.txt', '.json', '.js', '.ts', '.html', '.css', '.java', '.cpp')
            count = 0
            for item in tree:
                if item.get("type") == "blob" and item.get("path", "").endswith(allowed_extensions):
                    if count >= 30: break
                    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{item['path']}"
                    file_resp = requests.get(raw_url)
                    if file_resp.status_code != 200:
                        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/{item['path']}"
                        file_resp = requests.get(raw_url)
                    
                    if file_resp.status_code == 200:
                        files_data.append({"path": item['path'], "content": file_resp.text})
                        count += 1
            return files_data, None
        return None, "Failed to access repository."
    except Exception as e:
        return None, str(e)

def process_uploaded_files(files):
    docs = []
    for f in files:
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
    return docs

# 5. State Management Matrix
if "vector_db" not in st.session_state: st.session_state.vector_db = None
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "response_time" not in st.session_state: st.session_state.response_time = "0.00s"
if "source_reference" not in st.session_state: st.session_state.source_reference = "<div class='source-box'>Awaiting data vector alignment...</div>"
if "node_count" not in st.session_state: st.session_state.node_count = 0

# 6. Advanced CSS Injection
st.markdown("""
<style>
    .stApp { background-color: #000000 !important; background-image: radial-gradient(circle at 50% 15%, rgba(255, 60, 60, 0.12) 0%, transparent 60%), radial-gradient(circle at 85% 80%, rgba(0, 120, 255, 0.06) 0%, transparent 50%) !important; color: #ffffff !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    .cyber-card { background: rgba(10, 12, 18, 0.65) !important; backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 20px; padding: 22px; margin-bottom: 20px; box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.8); }
    .system-title { font-size: 2.6rem; font-weight: 900; letter-spacing: 10px; text-align: center; text-transform: uppercase; background: linear-gradient(135deg, #ffffff 0%, #ffaa00 50%, #ff3333 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 3px; text-shadow: 0 0 35px rgba(255, 170, 0, 0.15); }
    .system-subtitle { font-size: 0.75rem; color: #666666; text-transform: uppercase; letter-spacing: 4px; text-align: center; margin-bottom: 25px; }
    .gemini-greeting { font-size: 2.2rem; font-weight: 700; background: linear-gradient(135deg, #ffffff 30%, #ffaa00 70%, #ff4444 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-top: 100px; margin-bottom: 10px; animation: fadeIn 1.2s ease-out forwards; text-align: left; }
    .gemini-subgreeting { font-size: 1.2rem; color: #888888; margin-bottom: 40px; animation: fadeIn 1.6s ease-out forwards; text-align: left; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(15px); } to { opacity: 1; transform: translateY(0); } }
    .metric-card { background: rgba(15, 20, 32, 0.5) !important; backdrop-filter: blur(12px); border: 1px solid rgba(0, 150, 255, 0.15) !important; border-radius: 12px; padding: 14px; text-align: center; transition: all 0.3s ease; }
    .metric-card:hover { border-color: rgba(0, 150, 255, 0.4); box-shadow: 0 0 15px rgba(0, 150, 255, 0.15); }
    .metric-value { font-size: 24px; font-weight: 800; color: #00bfff; text-shadow: 0 0 10px rgba(0, 191, 255, 0.3); }
    .metric-title { font-size: 10px; color: #888888; text-transform: uppercase; letter-spacing: 1px; }
    .source-box { background: rgba(15, 5, 5, 0.5) !important; backdrop-filter: blur(12px); border-left: 3px solid #ff3333; border-top: 1px solid rgba(255, 51, 51, 0.08); border-right: 1px solid rgba(255, 51, 51, 0.08); border-bottom: 1px solid rgba(255, 51, 51, 0.08); padding: 14px; border-radius: 4px 12px 12px 4px; font-size: 13px; color: #cccccc; max-height: 480px; overflow-y: auto; }
    div[data-testid="stChatMessage"]:has(div[aria-label="Chat message from user"]) { background: linear-gradient(135deg, #cc2222 0%, #881111 100%) !important; border-radius: 24px 24px 4px 24px !important; color: white !important; border: none !important; margin-left: 10% !important; box-shadow: 0 4px 15px rgba(204, 34, 34, 0.15); }
    div[data-testid="stChatMessage"]:has(div[aria-label="Chat message from assistant"]) { background: rgba(0, 35, 70, 0.35) !important; backdrop-filter: blur(10px); border: 1px solid rgba(0, 150, 255, 0.25) !important; border-radius: 24px 24px 24px 4px !important; color: #e2e8f0 !important; margin-right: 10% !important; box-shadow: 0 0 20px rgba(0, 150, 255, 0.1); }
    div[data-testid="stChatInput"] textarea { background-color: #070709 !important; border: 1px solid rgba(255, 255, 255, 0.08) !important; color: white !important; border-radius: 14px !important; }
    div[data-testid="stChatInput"] textarea:focus { border-color: #ffaa00 !important; box-shadow: 0 0 10px rgba(255, 170, 0, 0.25) !important; }
    section[data-testid="stFileUploadDropzone"] { background-color: rgba(15, 15, 20, 0.4) !important; border: 1px dashed rgba(255, 51, 51, 0.25) !important; border-radius: 14px !important; }
</style>
""", unsafe_allow_html=True)

# 7. Layout Distribution Matrix
st.markdown("<div class='system-title'>APOLLO OMNI</div>", unsafe_allow_html=True)
st.markdown("<div class='system-subtitle'>GITHUB SYNC // WEB RESEARCH // LOCAL FILES</div>", unsafe_allow_html=True)

col_left, col_mid, col_right = st.columns([2.8, 4.7, 2.5], gap="large")

# ================= LEFT COLUMN: THE TRIFECTA INGESTION ENGINE =================
with col_left:
    # 1. GitHub Form
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("### 🐙 GITHUB REPOSITORY")
    with st.form("github_form", clear_on_submit=False):
        github_url = st.text_input("URL", placeholder="https://github.com/user/repo", label_visibility="collapsed", key="gh_in")
        submit_gh = st.form_submit_button("INDEX REPO", use_container_width=True)
        
    if submit_gh and github_url:
        with st.spinner("Cloning code to Vector DB..."):
            files, err = fetch_github_repo_files(github_url)
            if files:
                docs = [Document(page_content=f"File: {f['path']}\n\n{f['content']}", metadata={"source": f"GitHub: {f['path']}"}) for f in files]
                chunks = text_splitter.split_documents(docs)
                if st.session_state.vector_db is None: st.session_state.vector_db = FAISS.from_documents(chunks, embedder)
                else: st.session_state.vector_db.add_documents(chunks)
                st.session_state.node_count += len(chunks)
                st.success(f"Indexed {len(chunks)} code blocks.")
            else: st.error(err)
    st.markdown("</div>", unsafe_allow_html=True)

    # 2. File Upload Module
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("### 💾 LOCAL DOCUMENTS")
    uploaded_files = st.file_uploader("Upload assets...", type=["pdf", "txt"], accept_multiple_files=True, label_visibility="collapsed", key="file_in")
    if st.button("INDEX FILES", use_container_width=True):
        if uploaded_files:
            with st.spinner("Parsing documents..."):
                parsed_docs = process_uploaded_files(uploaded_files)
                if parsed_docs:
                    chunks = text_splitter.split_documents(parsed_docs)
                    if st.session_state.vector_db is None: st.session_state.vector_db = FAISS.from_documents(chunks, embedder)
                    else: st.session_state.vector_db.add_documents(chunks)
                    st.session_state.node_count += len(chunks)
                    st.success(f"Indexed {len(chunks)} document blocks.")
    st.markdown("</div>", unsafe_allow_html=True)
    
    # 3. Web Research Form (Now Context-Managed with Fallback Architecture)
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("### 🌐 WEB RESEARCH")
    with st.form("web_research_form", clear_on_submit=False):
        research_topic = st.text_input("Topic", placeholder="e.g. Next-Gen AI Models", label_visibility="collapsed", key="web_in")
        submit_web = st.form_submit_button("INDEX LIVE WEB", use_container_width=True)
        
    if submit_web and research_topic:
        with st.spinner("Scraping live internet..."):
            results = []
            error_details = None
            
            # Step A: Attempt standard API backend with context manager
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(research_topic, max_results=8))
            except Exception as e:
                error_details = f"API Engine Error: {e}"
            
            # Step B: Sequential Fallback to Scraper Backend if API returned empty/failed
            if not results:
                try:
                    with DDGS() as ddgs:
                        results = list(ddgs.text(research_topic, backend="html", max_results=8))
                except Exception as e:
                    error_details = f"{error_details} | HTML Engine Error: {e}" if error_details else f"HTML Engine Error: {e}"
            
            # Step C: Sequential Fallback to Lite Backend layout
            if not results:
                try:
                    with DDGS() as ddgs:
                        results = list(ddgs.text(research_topic, backend="lite", max_results=8))
                except Exception:
                    pass

            # Process alignment if payload verified
            if results:
                compiled_text = f"--- WEB RESEARCH: {research_topic} ---\n\n"
                for res in results: 
                    compiled_text += f"Title: {res.get('title', 'No Title')}\nURL: {res.get('href', '')}\nSummary: {res.get('body', '')}\n\n"
                
                doc = [Document(page_content=compiled_text, metadata={"source": f"Web Search: {research_topic}"})]
                chunks = text_splitter.split_documents(doc)
                
                if st.session_state.vector_db is None: 
                    st.session_state.vector_db = FAISS.from_documents(chunks, embedder)
                else: 
                    st.session_state.vector_db.add_documents(chunks)
                
                st.session_state.node_count += len(chunks)
                st.success(f"Indexed {len(chunks)} live web blocks.")
            else:
                st.error(
                    f"❌ WEB SEARCH BLOCKED BY DUCKDUGKO\n\n"
                    f"The search returned 0 entries. Because this app is hosted on cloud infra, DuckDuckGo "
                    f"is rate-limiting or blocking the shared server IP address.\n\n"
                    f"**Internal Engine Diagnostics:** {error_details if error_details else 'No explicit crash code. Anti-scraping firewall silently returned an empty page.'}\n\n"
                    f"💡 *Bypass Tip: To search live web cleanly without IP blocks, run your streamlit app locally on your machine (using your home residential IP) or drop a raw text/PDF download into the local workspace box above!*"
                )
    st.markdown("</div>", unsafe_allow_html=True)

    # 4. System Workspace
    st.markdown("<div class='cyber-card'>", unsafe_allow_html=True)
    st.markdown("### 🛠️ SYSTEM WORKSPACE")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🧹 PURGE DB", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.vector_db = None
            st.session_state.node_count = 0
            st.session_state.response_time = "0.00s"
            st.session_state.source_reference = "<div class='source-box'>Awaiting data vector alignment...</div>"
            st.rerun()
    with c2:
        chat_log = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in st.session_state.chat_history])
        st.download_button("💾 EXPORT", data=chat_log, file_name="apollo_log.txt", mime="text/plain", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ================= MIDDLE COLUMN: MAIN CHAT INTERACTION VIEW =================
with col_mid:
    if not st.session_state.chat_history:
        st.markdown("<div class='gemini-greeting'>Hello, User.</div>", unsafe_allow_html=True)
        st.markdown("<div class='gemini-subgreeting'>Index a GitHub Repo, upload PDFs, or command the Web Agent. Then ask me anything.</div>", unsafe_allow_html=True)
        st.markdown("<div style='height: 120px;'></div>", unsafe_allow_html=True)
    
    chat_scroll_pane = st.container(height=520, border=False)
    
    with chat_scroll_pane:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
            
    user_query = st.chat_input("Query your Vector Database...")
    
    if user_query:
        st.session_state.chat_history.append({"role": "user", "content": user_query})
        
        if st.session_state.vector_db is None:
            err_msg = "⚠️ DATABASE EMPTY: Please index a repo, a file, or a web topic first via the Left Panel."
            st.session_state.chat_history.append({"role": "assistant", "content": err_msg})
            st.rerun()
        else:
            start_time = time.time()
            retriever = st.session_state.vector_db.as_retriever(search_kwargs={"k": 5})
            matched_nodes = retriever.invoke(user_query)
            context_payload = "\n\n".join([f"[{node.metadata.get('source', 'Unknown')}]\n{node.page_content}" for node in matched_nodes])
            
            sys_instruction = (
                "You are APOLLO. Formulate a flawless response using ONLY the provided context matrix below. "
                "CITE YOUR SOURCES in your answer (e.g., 'According to github_script.py...' or 'Based on the web search...')."
            )
            
            message_stream = [{"role": "system", "content": sys_instruction}]
            for msg in st.session_state.chat_history[-4:]:
                message_stream.append({"role": msg["role"], "content": msg["content"]})
            message_stream.append({"role": "user", "content": f"Context Matrix:\n{context_payload}\n\nQuery: {user_query}"})
            
            with chat_scroll_pane:
                with st.chat_message("assistant"):
                    response_container = st.empty()
                    collected_tokens = ""
                    try:
                        stream = client.chat_completion(messages=message_stream, max_tokens=1024, stream=True, temperature=0.2)
                        for chunk in stream:
                            token = chunk.choices[0].delta.content
                            if token:
                                collected_tokens += token
                                response_container.markdown(collected_tokens + " █")
                        if not collected_tokens.strip(): collected_tokens = "⚠️ EMPTY RESPONSE RETURNED."
                        response_container.markdown(collected_tokens)
                    except Exception as ex:
                        collected_tokens = f"❌ API FAILURE: {ex}"
                        response_container.markdown(collected_tokens)
            
            st.session_state.chat_history.append({"role": "assistant", "content": collected_tokens})
            st.session_state.response_time = f"{time.time() - start_time:.2f}s"
            
            clean_ctx = context_payload.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            st.session_state.source_reference = f"<div class='source-box'><strong>Attributed Sources:</strong><br><br>{clean_ctx}</div>"
            st.rerun()

# ================= RIGHT COLUMN: PERFORMANCE & DATA TELEMETRY =================
with col_right:
    st.markdown("### 📊 DASHBOARD METRICS")
    st.markdown(f"<div class='metric-card'><div class='metric-title'>Inference Latency</div><div class='metric-value'>{st.session_state.response_time}</div></div>", unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"<div class='metric-card'><div class='metric-title'>Total Nodes Indexed</div><div class='metric-value'>{st.session_state.node_count}</div></div>", unsafe_allow_html=True)
    st.markdown("<br>### 📑 VERIFIED RETRIEVAL MATRIX", unsafe_allow_html=True)
    st.markdown(st.session_state.source_reference, unsafe_allow_html=True)
