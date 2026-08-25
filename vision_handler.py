"""
vision_handler.py — Apollo Omni AI: Ask With a Photo

Students don't always have a question in text form — a handwritten
equation, a diagram from a textbook, a photo of a professor's whiteboard.
This renders a camera/upload widget, sends the image (plus any typed
context) to a Groq vision-capable model, and drops the exchange straight
into the main chat history so it reads like any other turn.
"""

import base64

import streamlit as st
from groq import Groq

# Groq vision-capable chat models, tried in order. All are on Groq's free,
# no-credit-card tier (rate-limited, not model-gated) -- confirmed Aug 2026.
# Groq deprecates model IDs periodically (same caveat as the text
# MODEL_OPTIONS matrix in Apollo_omni.py); as of this writing,
# llama-4-maverick-17b-128e-instruct and the llama-3.2-*-vision-preview IDs
# have already been deprecated, so they're intentionally left out below.
# Check https://console.groq.com/docs/models if this list starts failing.
VISION_MODEL_FALLBACKS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-vl-32b-instruct",  # enterprise-gated as of Aug 2026; harmless to try, just falls through if unavailable on your account
]

DEFAULT_VISION_PROMPT = (
    "Look at this image carefully — it may be a handwritten question, a"
    " textbook page, a diagram, or class notes. Identify what's being asked"
    " and answer it like a patient tutor, explaining your reasoning step by"
    " step rather than just stating a final answer."
)

DEFAULT_GRADING_RUBRIC = (
    "Grade the student's handwritten solution as a teacher. Identify the"
    " likely question, check each step, assign a score out of 10, explain"
    " what earned credit, point out mistakes, and give a short corrected"
    " solution or improvement plan. Be fair and specific."
)


def _image_to_data_url(image_bytes: bytes, mime_type: str) -> str:
  b64 = base64.b64encode(image_bytes).decode("utf-8")
  return f"data:{mime_type};base64,{b64}"


def ask_vision_model(image_bytes: bytes, mime_type: str, question: str, groq_key: str) -> tuple[str | None, str]:
  """Sends one image (+ optional question) to a Groq vision model with
  automatic fallback across model IDs. Returns (answer, status)."""
  if not groq_key or not groq_key.startswith("gsk_"):
    return None, "Missing or invalid GROQ_API_KEY (must start with 'gsk_')."

  client = Groq(api_key=groq_key.strip())
  data_url = _image_to_data_url(image_bytes, mime_type)
  prompt_text = question.strip() if question and question.strip() else DEFAULT_VISION_PROMPT

  last_exception = None
  for model_id in VISION_MODEL_FALLBACKS:
    try:
      completion = client.chat.completions.create(
          model=model_id,
          messages=[{
              "role": "user",
              "content": [
                  {"type": "text", "text": prompt_text},
                  {"type": "image_url", "image_url": {"url": data_url}},
              ],
          }],
          temperature=0.3,
          max_tokens=1200,
      )
      answer = completion.choices[0].message.content
      if answer:
        return answer, f"OK ({model_id})"
    except Exception as e:
      last_exception = e
      continue

  return None, f"All vision models failed: {last_exception}"


def render_image_question_widget(groq_key: str, key_suffix: str = "main", on_answered=None):
  """Renders the camera/upload + optional context box. On submit, calls the
  vision model and appends the exchange to st.session_state.chat_history,
  then reruns so it shows up in the main chat feed immediately.

  on_answered: optional zero-arg callback fired right before the rerun
  (e.g. to persist the notebook's chat history to disk).
  """
  with st.expander("📷 Ask With a Photo (handwriting, diagrams, textbook pages)", expanded=False):
    st.caption("No need to type it out — snap or upload a photo of the question instead.")

    tab_upload, tab_camera = st.tabs(["📁 Upload", "📸 Camera"])
    image_file = None
    with tab_upload:
      uploaded = st.file_uploader(
          "Upload an image", type=["png", "jpg", "jpeg", "webp"],
          key=f"vision_upload_{key_suffix}", label_visibility="collapsed",
      )
      if uploaded is not None:
        image_file = uploaded
    with tab_camera:
      cam_shot = st.camera_input(
          "Take a photo", key=f"vision_camera_{key_suffix}", label_visibility="collapsed"
      )
      if cam_shot is not None:
        image_file = cam_shot

    if image_file is not None:
      st.image(image_file, caption="Preview", width=280)

    question_text = st.text_input(
        "Add context (optional):",
        placeholder="e.g., What's the answer to question 3?",
        key=f"vision_question_{key_suffix}",
    )

    if st.button("🔍 Ask Apollo About This Image", use_container_width=True, key=f"vision_submit_{key_suffix}"):
      if image_file is None:
        st.warning("Please upload or capture an image first.")
      else:
        image_bytes = image_file.getvalue()
        mime_type = getattr(image_file, "type", None) or "image/jpeg"
        with st.spinner("👀 Reading the image & thinking..."):
          answer, status = ask_vision_model(image_bytes, mime_type, question_text, groq_key)

        user_note = f"🖼️ *[Image question]* {question_text}".strip() if question_text else "🖼️ *[Image question]*"
        st.session_state.chat_history.append({"role": "user", "content": user_note})
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": answer if answer else f"❌ Couldn't read that image: {status}",
        })

        if on_answered:
          try:
            on_answered()
          except Exception:
            pass
        st.rerun()


def render_homework_grading_widget(groq_key: str, key_suffix: str = "main", on_answered=None):
  """Sibling of Ask With a Photo for solved homework. It sends the image to
  the same vision pipeline, but asks Apollo to grade against a rubric."""
  with st.expander("🧾 Grade Homework From a Photo", expanded=False):
    st.caption("Upload a solved handwritten answer and Apollo will grade it against a rubric.")

    tab_upload, tab_camera = st.tabs(["📁 Upload", "📸 Camera"])
    image_file = None
    with tab_upload:
      uploaded = st.file_uploader(
          "Upload solved homework", type=["png", "jpg", "jpeg", "webp"],
          key=f"grading_upload_{key_suffix}", label_visibility="collapsed",
      )
      if uploaded is not None:
        image_file = uploaded
    with tab_camera:
      cam_shot = st.camera_input(
          "Take a photo", key=f"grading_camera_{key_suffix}", label_visibility="collapsed"
      )
      if cam_shot is not None:
        image_file = cam_shot

    if image_file is not None:
      st.image(image_file, caption="Submission preview", width=280)

    rubric_text = st.text_area(
        "Rubric / expected answer (optional):",
        placeholder="e.g., 5 marks for formula, 3 for substitution, 2 for final answer with units.",
        key=f"grading_rubric_{key_suffix}",
        height=90,
    )

    if st.button("✅ Grade This Submission", use_container_width=True, key=f"grading_submit_{key_suffix}"):
      if image_file is None:
        st.warning("Please upload or capture the solved answer first.")
      else:
        image_bytes = image_file.getvalue()
        mime_type = getattr(image_file, "type", None) or "image/jpeg"
        prompt = DEFAULT_GRADING_RUBRIC
        if rubric_text.strip():
          prompt += f"\n\nUse this rubric / expected answer:\n{rubric_text.strip()}"
        with st.spinner("🧾 Reading and grading the submission..."):
          answer, status = ask_vision_model(image_bytes, mime_type, prompt, groq_key)

        user_note = "🧾 *[Homework photo grading request]*"
        if rubric_text.strip():
          user_note += f"\n\nRubric: {rubric_text.strip()}"
        st.session_state.chat_history.append({"role": "user", "content": user_note})
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": answer if answer else f"❌ Couldn't grade that image: {status}",
        })

        if on_answered:
          try:
            on_answered()
          except Exception:
            pass
        st.rerun()
