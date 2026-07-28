import os
import tempfile
from pathlib import Path
from typing import Iterable, Tuple

import streamlit as st
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter


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


def process_and_index_files(uploaded_files: Iterable, vector_db) -> Tuple[object, int]:
    docs = []

    for uploaded in uploaded_files:
        suffix = Path(uploaded.name).suffix.lower()
        if suffix not in {".pdf", ".txt"}:
            continue

        # The 'with' context automatically writes and closes the file handle 
        # before the loaders attempt to access it.
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.read())
            temp_path = tmp.name

        try:
            if suffix == ".pdf":
                docs.extend(PyPDFLoader(temp_path).load())
            elif suffix == ".txt":
                docs.extend(TextLoader(temp_path, encoding="utf-8").load())
        except Exception:
            continue
        finally:
            # Safely attempt to clean up the temporary file without crashing on Windows
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except (OSError, PermissionError):
                    pass

    if not docs:
        return vector_db, 0

    text_splitter = get_text_splitter()
    embedder = get_embedding_model()
    chunks = text_splitter.split_documents(docs)
    valid_chunks = [chunk for chunk in chunks if chunk.page_content.strip()]

    if not valid_chunks:
        return vector_db, 0

    if vector_db is None:
        vector_db = FAISS.from_documents(valid_chunks, embedder)
    else:
        vector_db.add_documents(valid_chunks)

    return vector_db, len(valid_chunks)