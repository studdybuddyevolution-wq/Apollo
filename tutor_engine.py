"""
tutor_engine.py — Apollo Omni AI: Adaptive Socratic Tutor

The one thing NotebookLM-style "Studio" tools don't do: actually teach you
and find out how much you know.

Flow:
  1. PLACEMENT CHECK — a short graded diagnostic quiz on the chosen topic
     establishes a starting mastery score (0-100) and tier.
  2. SOCRATIC SESSION — a guided chat where Apollo asks leading questions
     and gives hints calibrated to the student's tier, instead of just
     handing over answers.
  3. QUICK CHECKS — at any point the student can request a fresh graded
     question; each result nudges the mastery score up or down, which in
     turn changes how Apollo explains things for the rest of the session.

Mastery is persisted per-topic to a local JSON file so it survives across
sessions, the same lightweight pattern used by settings_app.py.
"""

import datetime
import json
import os
import re

import streamlit as st

MASTERY_PATH = "apollo_mastery_profile.json"

# (lower bound inclusive, upper bound exclusive, tier name, teaching style note)
_TIERS = [
    (0, 20, "Beginner", "Use very simple language, concrete everyday analogies, and short steps. Avoid jargon."),
    (20, 45, "Developing", "Use plain language with light technical vocabulary. Explain any term before relying on it."),
    (45, 70, "Proficient", "Use standard technical vocabulary. Assume familiarity with the basics, focus on connecting ideas."),
    (70, 90, "Advanced", "Use precise technical language. Skip basic definitions, focus on edge cases and 'why', not just 'what'."),
    (90, 101, "Master", "Treat the student as a peer. Challenge them with nuanced, exam/interview-level questions and counter-examples."),
]

_TIER_BADGE = {
    "Beginner": "🌱",
    "Developing": "📘",
    "Proficient": "⚡",
    "Advanced": "🔥",
    "Master": "🏆",
}


def tier_for_score(score: float) -> str:
  for lo, hi, name, _ in _TIERS:
    if lo <= score < hi:
      return name
  return "Master"


def tier_style_note(tier: str) -> str:
  for _, _, name, note in _TIERS:
    if name == tier:
      return note
  return ""


def badge_for_tier(tier: str) -> str:
  return _TIER_BADGE.get(tier, "📘")


# ---------------------------------------------------------------------------
# PERSISTENCE
# ---------------------------------------------------------------------------

def init_mastery_state():
  if "mastery_profile" not in st.session_state:
    if os.path.exists(MASTERY_PATH):
      try:
        with open(MASTERY_PATH, "r", encoding="utf-8") as f:
          st.session_state.mastery_profile = json.load(f)
      except Exception:
        st.session_state.mastery_profile = {}
    else:
      st.session_state.mastery_profile = {}

  for key, default in {
      "tutor_phase": "setup",       # setup -> diagnostic -> teaching
      "tutor_topic": "",
      "tutor_sources": [],
      "tutor_diag_questions": [],
      "tutor_diag_answers": {},
      "tutor_messages": [],
      "tutor_pending_check": None,  # holds the active quick-check question dict
  }.items():
    if key not in st.session_state:
      st.session_state[key] = default


def _save_mastery_profile():
  try:
    with open(MASTERY_PATH, "w", encoding="utf-8") as f:
      json.dump(st.session_state.mastery_profile, f, indent=2)
  except Exception:
    pass  # best-effort local persistence; session state still holds the truth


def get_topic_record(topic: str):
  return st.session_state.mastery_profile.get(topic.strip().lower())


def upsert_topic_record(topic: str, score: float, correct_delta: int = 0, attempt_delta: int = 0):
  key = topic.strip().lower()
  rec = st.session_state.mastery_profile.get(key, {"score": 30.0, "attempts": 0, "correct": 0})
  rec["score"] = max(0.0, min(100.0, score))
  rec["attempts"] = rec.get("attempts", 0) + attempt_delta
  rec["correct"] = rec.get("correct", 0) + correct_delta
  rec["tier"] = tier_for_score(rec["score"])
  rec["display_name"] = topic.strip()
  rec["last_updated"] = datetime.datetime.now().isoformat(timespec="seconds")
  st.session_state.mastery_profile[key] = rec
  _save_mastery_profile()
  return rec


# ---------------------------------------------------------------------------
# LLM JSON HELPERS (self-contained so this module has no circular import)
# ---------------------------------------------------------------------------

def _extract_json(raw_text: str):
  if not raw_text:
    return None
  clean = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)
  if "</think>" in clean:
    clean = clean.split("</think>")[-1]
  start, end = clean.find("{"), clean.rfind("}")
  if start != -1 and end != -1 and end > start:
    try:
      return json.loads(clean[start:end + 1])
    except json.JSONDecodeError:
      return None
  return None


def _generate_diagnostic_questions(topic, context, groq_key, model_name, generate_fn):
  """Asks the LLM for a 5-question diagnostic quiz spanning easy/medium/hard."""
  prompt = f"""Create a 5-question multiple-choice diagnostic quiz to gauge a student's
current understanding of: "{topic}".
Use exactly 2 "easy" questions, 2 "medium" questions, and 1 "hard" question.
{"Base the questions on this context where relevant:\\n" + context if context else ""}

Respond with ONLY raw JSON, no prose, no markdown fences, in this exact shape:
{{
  "questions": [
    {{"question": "...", "options": ["A", "B", "C", "D"], "answer_index": 0, "difficulty": "easy"}}
  ]
}}"""
  content, status = generate_fn([{"role": "user", "content": prompt}], groq_key, model_name, max_tokens=1400)
  parsed = _extract_json(content) if content else None
  if parsed and isinstance(parsed.get("questions"), list) and parsed["questions"]:
    return parsed["questions"], status
  return None, status


_DIFFICULTY_POINTS = {"easy": 10, "medium": 20, "hard": 40}


def _score_diagnostic(questions, answers) -> tuple[float, int, int]:
  """Returns (score_0_to_100, num_correct, num_total)."""
  total_possible = sum(_DIFFICULTY_POINTS.get(q.get("difficulty", "medium"), 20) for q in questions) or 1
  earned = 0
  correct = 0
  for i, q in enumerate(questions):
    if answers.get(i) == q.get("answer_index"):
      earned += _DIFFICULTY_POINTS.get(q.get("difficulty", "medium"), 20)
      correct += 1
  score = round((earned / total_possible) * 100, 1)
  return score, correct, len(questions)


def _generate_quick_check(topic, tier, context, groq_key, model_name, generate_fn):
  """One short-answer question calibrated to the student's current tier."""
  prompt = f"""Write ONE short quick-check question on "{topic}" calibrated for a
student at the "{tier}" level ({tier_style_note(tier)}).
{"Base it on this context where relevant:\\n" + context if context else ""}

Respond with ONLY raw JSON, no prose:
{{"question": "...", "expected_answer": "a concise correct answer or key points"}}"""
  content, status = generate_fn([{"role": "user", "content": prompt}], groq_key, model_name, max_tokens=400)
  parsed = _extract_json(content) if content else None
  if parsed and parsed.get("question"):
    return parsed, status
  return None, status


def _grade_quick_check(question, expected_answer, student_answer, groq_key, model_name, generate_fn):
  prompt = f"""You are grading a student's answer.
Question: {question}
Expected answer / key points: {expected_answer}
Student's answer: {student_answer}

Respond with ONLY raw JSON, no prose:
{{"correct": true or false, "feedback": "one short encouraging sentence explaining why, and the right idea if they were wrong"}}"""
  content, status = generate_fn([{"role": "user", "content": prompt}], groq_key, model_name, max_tokens=250)
  parsed = _extract_json(content) if content else None
  if parsed is not None and "correct" in parsed:
    return bool(parsed["correct"]), parsed.get("feedback", ""), status
  # Fallback: treat ungradeable responses as "needs review" rather than silently wrong
  return None, "Could not auto-grade that answer — try rephrasing it.", status


def _build_tutor_system_prompt(topic, tier, score, context, user_prefs=None):
  name = (user_prefs or {}).get("full_name", "").strip()
  addr = f" Address the student as {name}." if name else ""
  return f"""You are Apollo, a warm, patient Socratic tutor helping a student master: "{topic}".
The student's current mastery score is {score}/100 (tier: {tier}).
Teaching style for this tier: {tier_style_note(tier)}

Rules you must follow:
- Act like a real teacher, not a search engine: guide the student TOWARD the answer with
  leading questions, hints, and small steps, rather than stating the final answer outright.
- Only give the direct answer if the student is clearly stuck after at least two guiding
  attempts, or explicitly asks to just be told.
- Keep every message short (2-5 sentences) and end with a question or a small task
  whenever possible, to keep the student actively engaged.
- Be encouraging and never condescending, regardless of how basic the question is.
-{addr}
{("Use this indexed source context when relevant, and mention when you are drawing on it:\n" + context) if context else "No indexed source material was selected — teach from general knowledge."}"""


# ---------------------------------------------------------------------------
# MAIN RENDER FUNCTION
# ---------------------------------------------------------------------------

def render_tutor_mode(
    groq_key: str,
    selected_model: str,
    generate_llm_response_fn,
    generate_llm_stream_fn,
    get_scoped_context_fn,
    source_names: list[str],
    user_prefs: dict | None = None,
):
  init_mastery_state()

  st.markdown(
      "<h2 style='color:#ff8c00; font-family:\"Inter\",sans-serif; font-weight:700; "
      "font-size:22px; letter-spacing:0.08em; margin-bottom:2px;'>🎓 SOCRATIC TUTOR</h2>"
      "<p style='color:#a1a1aa; font-family:\"JetBrains Mono\",monospace; font-size:12px; "
      "margin-top:0;'>Apollo tests what you know, then teaches at exactly your level — "
      "and keeps re-testing as you go.</p>",
      unsafe_allow_html=True,
  )

  if not groq_key or not groq_key.startswith("gsk_"):
    st.error("❌ Missing or invalid GROQ_API_KEY (must start with 'gsk_'). Set it in Streamlit Secrets.")
    return

  # ── Skill overview across every topic ever assessed ──────────────────────
  if st.session_state.mastery_profile:
    with st.expander("📊 Your Skill Overview", expanded=False):
      for rec in sorted(st.session_state.mastery_profile.values(), key=lambda r: -r["score"]):
        badge = badge_for_tier(rec["tier"])
        st.markdown(
            f"{badge} **{rec['display_name']}** — {rec['tier']} "
            f"({rec['score']:.0f}/100, {rec.get('correct', 0)}/{rec.get('attempts', 0)} correct checks)"
        )
        st.progress(min(1.0, rec["score"] / 100))

  st.markdown("<hr style='border-color: rgba(255,140,0,0.2);'>", unsafe_allow_html=True)

  # ── PHASE 1: SETUP ────────────────────────────────────────────────────────
  if st.session_state.tutor_phase == "setup":
    topic_input = st.text_input(
        "What do you want to be taught & tested on?",
        placeholder="e.g., Binary Search Trees, Newton's Laws, Indian Constitution Article 21",
        key="tutor_topic_input",
    )

    sel_sources = source_names
    if source_names:
      with st.expander(f"📎 Sources — {len(source_names)} available", expanded=False):
        sel_sources = [n for n in source_names if st.checkbox(n, value=True, key=f"tutor_src_{n}")]

    existing = get_topic_record(topic_input) if topic_input else None
    if existing:
      st.info(
          f"{badge_for_tier(existing['tier'])} You've studied this before — "
          f"currently **{existing['tier']}** ({existing['score']:.0f}/100). "
          "Starting a new placement check will re-calibrate this score."
      )

    col_a, col_b = st.columns(2)
    with col_a:
      start_diag = st.button("🧪 Start Placement Check", use_container_width=True, type="primary")
    with col_b:
      skip_diag = st.button(
          "⏭️ Skip — Teach at Last Known Level",
          use_container_width=True,
          disabled=existing is None,
      )

    if start_diag:
      if not topic_input.strip():
        st.warning("Please enter a topic first.")
      else:
        with st.spinner("Preparing your placement check..."):
          context = get_scoped_context_fn(topic_input, sel_sources, k=6)
          questions, status = _generate_diagnostic_questions(
              topic_input, context, groq_key, selected_model, generate_llm_response_fn
          )
        if questions:
          st.session_state.tutor_topic = topic_input.strip()
          st.session_state.tutor_sources = sel_sources
          st.session_state.tutor_diag_questions = questions
          st.session_state.tutor_diag_answers = {}
          st.session_state.tutor_phase = "diagnostic"
          st.rerun()
        else:
          st.error(f"Couldn't generate the placement check: {status}")

    if skip_diag and existing:
      st.session_state.tutor_topic = topic_input.strip()
      st.session_state.tutor_sources = sel_sources
      st.session_state.tutor_messages = []
      st.session_state.tutor_phase = "teaching"
      st.rerun()

  # ── PHASE 2: DIAGNOSTIC (PLACEMENT CHECK) ────────────────────────────────
  elif st.session_state.tutor_phase == "diagnostic":
    st.markdown(f"**Placement Check: {st.session_state.tutor_topic}**")
    st.caption("Answer honestly — this decides your starting difficulty, not a grade.")

    for i, q in enumerate(st.session_state.tutor_diag_questions):
      st.markdown(f"**{i + 1}. {q['question']}**  \n<span style='font-size:10px;color:#71717a;'>({q.get('difficulty', 'medium')})</span>", unsafe_allow_html=True)
      choice = st.radio(
          f"q_{i}", options=list(range(len(q["options"]))),
          format_func=lambda idx, opts=q["options"]: opts[idx],
          key=f"tutor_diag_radio_{i}", label_visibility="collapsed",
      )
      st.session_state.tutor_diag_answers[i] = choice

    col_a, col_b = st.columns([2, 1])
    with col_a:
      submit_diag = st.button("✅ Submit Placement Check", use_container_width=True, type="primary")
    with col_b:
      if st.button("Cancel", use_container_width=True):
        st.session_state.tutor_phase = "setup"
        st.rerun()

    if submit_diag:
      score, correct, total = _score_diagnostic(
          st.session_state.tutor_diag_questions, st.session_state.tutor_diag_answers
      )
      rec = upsert_topic_record(
          st.session_state.tutor_topic, score, correct_delta=correct, attempt_delta=1
      )
      st.session_state.tutor_last_diag_result = (score, correct, total, rec["tier"])
      st.session_state.tutor_messages = []
      st.session_state.tutor_phase = "teaching"
      st.rerun()

  # ── PHASE 3: TEACHING (Socratic chat + quick checks) ─────────────────────
  elif st.session_state.tutor_phase == "teaching":
    topic = st.session_state.tutor_topic
    rec = get_topic_record(topic) or upsert_topic_record(topic, 30.0)
    tier, score = rec["tier"], rec["score"]

    if st.session_state.get("tutor_last_diag_result"):
      s, c, t, tr = st.session_state.tutor_last_diag_result
      st.success(f"Placement check done: {c}/{t} correct → **{s:.0f}/100 ({tr})**. Teaching now starts at this level.")
      st.session_state.tutor_last_diag_result = None

    top_l, top_r = st.columns([3, 1])
    with top_l:
      st.markdown(f"**{badge_for_tier(tier)} Topic: {topic}** &nbsp;•&nbsp; Tier: **{tier}** ({score:.0f}/100)")
      st.progress(min(1.0, score / 100))
    with top_r:
      if st.button("🔁 New Topic", use_container_width=True):
        st.session_state.tutor_phase = "setup"
        st.session_state.tutor_messages = []
        st.rerun()

    chat_pane = st.container(height=420, border=False)
    with chat_pane:
      if not st.session_state.tutor_messages:
        st.markdown(
            f"<div style='color:#a1a1aa; font-size:12px; font-family:\"JetBrains Mono\",monospace;'>"
            f"Ask a question about {topic}, or hit 'Quick Check' below to be tested right away.</div>",
            unsafe_allow_html=True,
        )
      for m in st.session_state.tutor_messages:
        with st.chat_message(m["role"]):
          st.markdown(m["content"])

    # ── Active quick-check, if one is pending ──
    pending = st.session_state.tutor_pending_check
    if pending:
      with st.form(key="tutor_quick_check_form"):
        st.markdown(f"🧪 **Quick Check:** {pending['question']}")
        student_answer = st.text_area("Your answer:", key="tutor_quick_check_answer", height=80)
        graded = st.form_submit_button("Submit Answer", use_container_width=True)
      if graded:
        with st.spinner("Grading..."):
          is_correct, feedback, _status = _grade_quick_check(
              pending["question"], pending["expected_answer"], student_answer,
              groq_key, selected_model, generate_llm_response_fn,
          )
        if is_correct is True:
          delta = 8 if tier in ("Beginner", "Developing") else 6
          new_score = score + delta
          verdict = f"✅ Correct! Mastery +{delta} → {new_score:.0f}/100"
        elif is_correct is False:
          delta = -6
          new_score = score + delta
          verdict = f"❌ Not quite. Mastery {delta} → {new_score:.0f}/100"
        else:
          new_score = score
          verdict = "⚠️ Couldn't auto-grade that one — mastery unchanged."
        new_rec = upsert_topic_record(
            topic, new_score,
            correct_delta=1 if is_correct else 0,
            attempt_delta=1,
        )
        st.session_state.tutor_messages.append({"role": "assistant", "content": f"{verdict}\n\n{feedback}\n\n_You're now at **{new_rec['tier']}**._"})
        st.session_state.tutor_pending_check = None
        st.rerun()

    # ── Chat input + Quick Check trigger ──
    col_chat_in, col_qc = st.columns([4, 1])
    with col_chat_in:
      user_msg = st.chat_input("Ask Apollo about this topic...")
    with col_qc:
      quick_check_clicked = st.button("🧪 Quick Check", use_container_width=True, disabled=bool(pending))

    if quick_check_clicked and not pending:
      with st.spinner("Preparing a quick check..."):
        ctx = get_scoped_context_fn(topic, st.session_state.tutor_sources, k=4)
        q, status = _generate_quick_check(topic, tier, ctx, groq_key, selected_model, generate_llm_response_fn)
      if q:
        st.session_state.tutor_pending_check = q
        st.rerun()
      else:
        st.error(f"Couldn't prepare a quick check: {status}")

    if user_msg:
      st.session_state.tutor_messages.append({"role": "user", "content": user_msg})
      ctx = get_scoped_context_fn(user_msg, st.session_state.tutor_sources, k=4)
      sys_prompt = _build_tutor_system_prompt(topic, tier, score, ctx, user_prefs)
      msg_stream = [{"role": "system", "content": sys_prompt}]
      msg_stream.extend(st.session_state.tutor_messages[-8:])

      with chat_pane:
        with st.chat_message("assistant"):
          reply = st.write_stream(generate_llm_stream_fn(msg_stream, groq_key, selected_model))
      st.session_state.tutor_messages.append({"role": "assistant", "content": reply or ""})
      st.rerun()
