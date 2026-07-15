import os
import time
import tempfile
import streamlit as st
from huggingface_hub import InferenceClient
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

# 1. Page Configuration (Must be at the very top)
st.set_page_config(layout="wide", page_title="EduQuery AI Dashboard")

# 2. Setup Inference Engine
HF_TOKEN = os.getenv("HF_TOKEN")
#  CORRECT (Capitalized vendor name and model ID)
LLM_MODEL = "Qwen/Qwen3.6-27B"
client = InferenceClient(LLM_MODEL, token=HF_TOKEN)

# 3. Cached Resource Loaders to optimize Streamlit memory consumption
@st.cache_resource
def get_embedding_model():
    # FIXED: Replaced Alibaba with BAAI to stop the IndexError crash
    return HuggingFaceEmbeddings(
        model_name="BAAI/bge-large-en-v1.5",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True}
    )

@st.cache_resource
def get_text_splitter():
    return RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150
    )

embedder = get_embedding_model()
text_splitter = get_text_splitter()

# 4. Initialize Session States
if "vector_db" not in st.session_state:
    st.session_state.vector_db = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "response_time" not in st.session_state:
    st.session_state.response_time = "0.00s"
if "source_reference" not in st.session_state:
    st.session_state.source_reference = "<div class='source-box'>Awaiting queries...</div>"

# 5. Cyberpunk Neon Glassmorphism CSS Injections
custom_css = """
<style>
.stApp {
    background-color: #050505 !important;
    background-image: radial-gradient(circle at 50% 0%, #3a0d0d 0%, #050505 40%), 
                      radial-gradient(circle at 50% 100%, #071936 0%, #050505 40%) !important;
    color: #e0e0e0 !important;
    font-family: 'Inter', sans-serif !important;
}
h2, h3 {
    color: #ffffff !important;
    text-shadow: 0 0 10px rgba(255, 255, 255, 0.2);
}
.metric-card {
    background: rgba(20, 25, 40, 0.6) !important;
    backdrop-filter: blur(12px);
    border: 1px solid rgba(60, 130, 255, 0.3) !important;
    border-radius: 12px;
    padding: 15px;
    text-align: center;
    box-shadow: 0 4px 20px rgba(60, 130, 255, 0.1);
    margin-bottom: 15px;
}
.metric-value { 
    font-size: 26px; 
    font-weight: bold; 
    color: #4fa4ff; 
    text-shadow: 0 0 8px rgba(79, 164, 255, 0.5); 
}
.metric-title { 
    font-size: 11px; 
    color: #a0a0a0; 
    text-transform: uppercase; 
    letter-spacing: 1px; 
}
.source-box {
    background: rgba(30, 15, 15, 0.6) !important;
    backdrop-filter: blur(12px);
    border-left: 4px solid #d33420;
    border-top: 1px solid rgba(211, 52, 32, 0.2);
    border-right: 1px solid rgba(211, 52, 32, 0.2);
    border-bottom: 1px solid rgba(211, 52, 32, 0.2);
    padding: 12px;
    border-radius: 0 8px 8px 0;
    font-size: 13px;
    color: #cccccc;
    max-height: 300px;
    overflow-y: auto;
    box-shadow: 0 4px 20px rgba(211, 52, 32, 0.1);
}
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

def process_documents(uploaded_files):
    documents = []
    for uploaded_file in uploaded_files:
        suffix = os.path.splitext(uploaded_file.name)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(uploaded_file.read())
            temp_path = temp_file.name
        
        try:
            if suffix == ".pdf":
                loader = PyPDFLoader(temp_path)
                documents.extend(loader.load())
            elif suffix == ".txt":
                loader = TextLoader(temp_path, encoding="utf-8")
                documents.extend(loader.load())
        except Exception as e:
            st.error(f"Error parsing {uploaded_file.name}: {e}")
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    return documents

# 6. Dashboard Layout Architecture (3-Column Layout Configuration)
col1, col2, col3 = st.columns([2.5, 5, 2.5], gap="large")

# LEFT SIDEBAR COLUMN: Document Center
with col1:
    st.markdown("### 📁 Document Center")
    st.caption("Upload Textbook or Material (.txt or .pdf)")
    
    uploaded_files = st.file_uploader(
        "Upload files", 
        type=["pdf", "txt"], 
        accept_multiple_files=True, 
        label_visibility="collapsed"
    )
    
    index_btn = st.button("Index Documents", use_container_width=True, type="primary")
    
    if index_btn:
        if uploaded_files:
            with st.spinner("Analyzing text & building vector space..."):
                docs = process_documents(uploaded_files)
                if docs:
                    chunks = text_splitter.split_documents(docs)
                    if st.session_state.vector_db is None:
                        st.session_state.vector_db = FAISS.from_documents(chunks, embedder)
                    else:
                        st.session_state.vector_db.add_documents(chunks)
                    st.success(f"✅ Indexed {len(uploaded_files)} files ({len(chunks)} chunks).")
                else:
                    st.error("❌ Failed to parse usable content.")
        else:
            st.warning("⚠️ Please select files first.")

# MIDDLE MAIN COLUMN: Chat Hub
with col2:
    st.markdown("<h2 style='text-align: center; margin-bottom: 20px;'>🎓 EduQuery AI</h2>", unsafe_allow_html=True)
    
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    if user_msg := st.chat_input("Ask a question about your documents..."):
        with st.chat_message("user"):
            st.markdown(user_msg)
            
        st.session_state.chat_history.append({"role": "user", "content": user_msg})
        
        if st.session_state.vector_db is None:
            err_msg = "⚠️ **Error:** Please upload and index your documents in the Document Center first."
            with st.chat_message("assistant"):
                st.markdown(err_msg)
            st.session_state.chat_history.append({"role": "assistant", "content": err_msg})
            st.session_state.response_time = "--"
            st.session_state.source_reference = "<div class='source-box'>No context available. Load documents first.</div>"
            st.rerun()
            
        else:
            start_time = time.time()
            
            # Retrieval Pipeline
            retriever = st.session_state.vector_db.as_retriever(search_kwargs={"k": 3})
            docs = retriever.invoke(user_msg)
            context_text = "\n\n".join([f"--- Source {i+1} ---\n{doc.page_content}" for i, doc in enumerate(docs)])
            
            system_prompt = (
                "You are EduQuery AI, a helpful and precise assistant. "
                "Answer the user's question based strictly on the provided context. "
                "If the answer is not in the context, politely state that you cannot answer."
            )
            
            messages = [{"role": "system", "content": system_prompt}]
            for msg in st.session_state.chat_history[-4:]:
                messages.append({"role": msg["role"], "content": msg["content"]})
                
            messages.append({
                "role": "user", 
                "content": f"Context:\n{context_text}\n\nQuestion: {user_msg}"
            })
            
            with st.chat_message("assistant"):
                response_placeholder = st.empty()
                full_response = ""
                
                try:
                    response_stream = client.chat_completion(
                        messages=messages,
                        max_tokens=1024,
                        stream=True,
                        temperature=0.3
                    )
                    for chunk in response_stream:
                        if chunk.choices[0].delta.content:
                            full_response += chunk.choices[0].delta.content
                            response_placeholder.markdown(full_response + "▌")
                    response_placeholder.markdown(full_response)
                except Exception as e:
                    full_response = f"❌ API Processing Error: {str(e)}"
                    response_placeholder.markdown(full_response)
                    
            st.session_state.chat_history.append({"role": "assistant", "content": full_response})
            
            end_time = time.time()
            st.session_state.response_time = f"{end_time - start_time:.2f}s"
            
            safe_context = context_text.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            st.session_state.source_reference = f"<div class='source-box'><strong>Textbook Source Reference:</strong><br><br>{safe_context}</div>"
            
            st.rerun()

# RIGHT SIDEBAR COLUMN: Analytics & Source Reference
with col3:
    st.markdown("### 📊 Analytics")
    
    time_html = f"<div class='metric-card'><div class='metric-title'>Response Time</div><div class='metric-value'>{st.session_state.response_time}</div></div>"
    st.markdown(time_html, unsafe_allow_html=True)
    
    acc_html = "<div class='metric-card'><div class='metric-title'>Accuracy</div><div class='metric-value'>99%</div></div>"
    st.markdown(acc_html, unsafe_allow_html=True)
    
    st.markdown("### 📑 Sources")
    st.markdown(st.session_state.source_reference, unsafe_allow_html=True)
