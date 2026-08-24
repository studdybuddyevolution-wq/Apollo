"""
notebook_manager.py — Apollo Omni AI: Multi-Notebook Workspaces

Gives each signed-in student (identified by their verified @somaiya.edu email,
via the existing OTP auth flow) a NotebookLM-style picker: multiple named
notebooks, each holding its own indexed sources, FAISS vector index, and
chat history. Switching notebooks swaps the entire RAG workspace in/out.

Storage is local disk (same lightweight pattern as settings_app.py /
tutor_engine.py's JSON profiles) — one manifest file plus one folder per
notebook containing a saved FAISS index and a small metadata JSON.
"""

import datetime
import json
import os
import shutil
import uuid

import streamlit as st
from langchain_community.vectorstores import FAISS

NOTEBOOKS_DIR = "apollo_notebooks"
MANIFEST_PATH = os.path.join(NOTEBOOKS_DIR, "manifest.json")


# ---------------------------------------------------------------------------
# LOW-LEVEL STORAGE
# ---------------------------------------------------------------------------

def _load_manifest() -> dict:
  if os.path.exists(MANIFEST_PATH):
    try:
      with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      return {}
  return {}


def _save_manifest(manifest: dict):
  os.makedirs(NOTEBOOKS_DIR, exist_ok=True)
  try:
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
      json.dump(manifest, f, indent=2)
  except Exception:
    pass


def _notebook_dir(notebook_id: str) -> str:
  return os.path.join(NOTEBOOKS_DIR, notebook_id)


def _reset_session_workspace():
  """Clears every piece of session state tied to a single notebook's contents."""
  st.session_state.vector_db = None
  st.session_state.indexed_sources = []
  st.session_state.node_count = 0
  st.session_state.chat_history = []
  st.session_state.studio_results = {}
  st.session_state.active_studio_tool = "Slide Deck"
  st.session_state.source_reference = (
      "<div class='source-box font-mono'>Awaiting vector alignment...</div>"
  )


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def init_notebook_state(user_email: str):
  if "notebook_manifest" not in st.session_state:
    st.session_state.notebook_manifest = _load_manifest()
  if "active_notebook_id" not in st.session_state:
    st.session_state.active_notebook_id = None
  st.session_state.notebook_manifest.setdefault(user_email, [])


def list_notebooks(user_email: str) -> list[dict]:
  return st.session_state.notebook_manifest.get(user_email, [])


def get_active_notebook(user_email: str):
  nid = st.session_state.get("active_notebook_id")
  for nb in list_notebooks(user_email):
    if nb["id"] == nid:
      return nb
  return None


def save_active_notebook(user_email: str):
  """Persists the CURRENT session's vector_db / sources / chat to disk under
  the active notebook's folder. Call this after indexing new sources, after
  chat turns you want kept, and before switching away."""
  nid = st.session_state.get("active_notebook_id")
  if not nid:
    return
  nb_dir = _notebook_dir(nid)
  os.makedirs(nb_dir, exist_ok=True)

  try:
    if st.session_state.get("vector_db") is not None:
      st.session_state.vector_db.save_local(os.path.join(nb_dir, "index"))
  except Exception:
    pass  # best-effort; the in-memory session state is still authoritative this run

  meta = {
      "indexed_sources": st.session_state.get("indexed_sources", []),
      "node_count": st.session_state.get("node_count", 0),
      "chat_history": st.session_state.get("chat_history", []),
  }
  try:
    with open(os.path.join(nb_dir, "meta.json"), "w", encoding="utf-8") as f:
      json.dump(meta, f, indent=2)
  except Exception:
    pass

  for nb in st.session_state.notebook_manifest.get(user_email, []):
    if nb["id"] == nid:
      nb["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
      nb["source_count"] = len(meta["indexed_sources"])
      break
  _save_manifest(st.session_state.notebook_manifest)


def create_notebook(user_email: str, title: str) -> dict:
  if st.session_state.get("active_notebook_id"):
    save_active_notebook(user_email)  # don't lose whatever was open

  nid = "nb_" + uuid.uuid4().hex[:10]
  now = datetime.datetime.now().isoformat(timespec="seconds")
  record = {
      "id": nid,
      "title": title.strip() or "Untitled Notebook",
      "created": now,
      "updated": now,
      "source_count": 0,
  }
  st.session_state.notebook_manifest.setdefault(user_email, []).append(record)
  _save_manifest(st.session_state.notebook_manifest)

  _reset_session_workspace()
  st.session_state.active_notebook_id = nid
  return record


def load_notebook(user_email: str, notebook_id: str, embedder):
  if notebook_id == st.session_state.get("active_notebook_id"):
    return
  if st.session_state.get("active_notebook_id"):
    save_active_notebook(user_email)

  _reset_session_workspace()
  nb_dir = _notebook_dir(notebook_id)
  index_dir = os.path.join(nb_dir, "index")
  meta_path = os.path.join(nb_dir, "meta.json")

  if os.path.exists(index_dir):
    try:
      st.session_state.vector_db = FAISS.load_local(
          index_dir, embedder, allow_dangerous_deserialization=True
      )
    except Exception:
      st.session_state.vector_db = None

  if os.path.exists(meta_path):
    try:
      with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
      st.session_state.indexed_sources = meta.get("indexed_sources", [])
      st.session_state.node_count = meta.get("node_count", 0)
      st.session_state.chat_history = meta.get("chat_history", [])
    except Exception:
      pass

  st.session_state.active_notebook_id = notebook_id


def delete_notebook(user_email: str, notebook_id: str):
  shutil.rmtree(_notebook_dir(notebook_id), ignore_errors=True)
  st.session_state.notebook_manifest[user_email] = [
      nb for nb in st.session_state.notebook_manifest.get(user_email, [])
      if nb["id"] != notebook_id
  ]
  _save_manifest(st.session_state.notebook_manifest)
  if st.session_state.get("active_notebook_id") == notebook_id:
    st.session_state.active_notebook_id = None
    _reset_session_workspace()


def rename_notebook(user_email: str, notebook_id: str, new_title: str):
  for nb in st.session_state.notebook_manifest.get(user_email, []):
    if nb["id"] == notebook_id:
      nb["title"] = new_title.strip() or nb["title"]
      nb["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
      break
  _save_manifest(st.session_state.notebook_manifest)


# ---------------------------------------------------------------------------
# SIDEBAR UI
# ---------------------------------------------------------------------------

def render_notebook_switcher(user_email: str, embedder):
  """Renders the notebook picker + create/rename/delete controls. Call this
  once, near the top of the sidebar, before any source-indexing UI."""
  init_notebook_state(user_email)
  notebooks = list_notebooks(user_email)

  # First-ever login: give them a default notebook so upload/chat still
  # works immediately, same as before this feature existed.
  if not notebooks and not st.session_state.get("active_notebook_id"):
    create_notebook(user_email, "My Notebook")
    notebooks = list_notebooks(user_email)

  active = get_active_notebook(user_email)

  st.markdown(
      "<div style='font-size:10px; color:#71717a; text-transform:uppercase;"
      " letter-spacing:0.1em; margin-bottom:4px;'>📚 Notebook</div>",
      unsafe_allow_html=True,
  )

  if notebooks:
    options = [nb["id"] for nb in notebooks]
    labels = {nb["id"]: f"{nb['title']}  ·  {nb['source_count']} src" for nb in notebooks}
    default_idx = options.index(active["id"]) if active else 0
    chosen = st.selectbox(
        "Switch notebook",
        options=options,
        format_func=lambda nid: labels.get(nid, nid),
        index=default_idx,
        key="notebook_selector",
        label_visibility="collapsed",
    )
    if chosen != (active["id"] if active else None):
      with st.spinner("Loading notebook..."):
        load_notebook(user_email, chosen, embedder)
      st.rerun()

  with st.expander("➕ New / Manage Notebooks", expanded=False):
    new_title = st.text_input(
        "New notebook name", key="new_notebook_title",
        placeholder="e.g., Semester 5 — DBMS",
    )
    if st.button("Create Notebook", use_container_width=True, key="create_notebook_btn"):
      if new_title.strip():
        create_notebook(user_email, new_title)
        st.rerun()
      else:
        st.warning("Give it a name first.")

    if notebooks:
      st.markdown("<hr style='border-color: rgba(255,140,0,0.15); margin: 8px 0;'>", unsafe_allow_html=True)
      for nb in notebooks:
        is_active = active is not None and nb["id"] == active["id"]
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
          st.caption(f"{'📖' if is_active else '📓'} {nb['title']} ({nb['source_count']} src)")
        with c2:
          if st.button("✏️", key=f"rename_btn_{nb['id']}", help="Rename"):
            st.session_state[f"renaming_{nb['id']}"] = True
        with c3:
          if st.button("🗑️", key=f"delete_btn_{nb['id']}", help="Delete"):
            delete_notebook(user_email, nb["id"])
            st.rerun()

        if st.session_state.get(f"renaming_{nb['id']}"):
          new_name = st.text_input(
              "Rename to:", value=nb["title"], key=f"rename_input_{nb['id']}",
              label_visibility="collapsed",
          )
          if st.button("Save name", key=f"save_rename_{nb['id']}", use_container_width=True):
            rename_notebook(user_email, nb["id"], new_name)
            st.session_state[f"renaming_{nb['id']}"] = False
            st.rerun()

  st.markdown("<hr style='border-color: rgba(255,140,0,0.2); margin: 10px 0 14px 0;'>", unsafe_allow_html=True)
