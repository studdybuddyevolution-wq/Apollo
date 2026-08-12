"""
video_generator.py — Apollo Omni AI
────────────────────────────────────
Standalone RAG-powered Educational Video Generator module.

Public surface (imported by app.py):
    generate_video_script_gemini()  → asks Gemini for JSON scene plan
    run_tts_synthesis()             → edge-tts MP3 bytes (re-exported)
    assemble_video_moviepy()         → MoviePy MP4 on disk
    render_video_generator_ui()     → drop-in Streamlit UI panel
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.parse
from typing import Optional

import requests
import streamlit as st

# Re-export TTS from voice_handler
from voice_handler import run_tts_synthesis  # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# 1. GEMINI SCRIPT / SCENE PLANNER
# ─────────────────────────────────────────────────────────────────────────────

def generate_video_script_gemini(
    topic: str,
    instructions: str = "",
    context: str = "",
    gemini_key: str = "",
    user_prefs: Optional[dict] = None,
) -> tuple[dict | None, str]:
    """Calls Gemini-2.0-flash to produce a structured video script JSON."""
    if not gemini_key:
        return None, "Missing GEMINI_API_KEY in Streamlit Secrets."

    prefs_ctx = ""
    if user_prefs:
        prefs_ctx = (
            f"Adapt content for a student with:\n"
            f"  • Learning Style : {user_prefs.get('learning_style', 'General')}\n"
            f"  • Expertise Level: {user_prefs.get('detail_level', 'Intermediate')}\n\n"
        )

    prompt = f"""{prefs_ctx}Create an educational video script about: "{topic}"

SPECIFIC INSTRUCTIONS:
{instructions if instructions else "None provided."}

KNOWLEDGE BASE CONTEXT:
{context if context else "No extra context. Use general knowledge."}

Return ONLY a valid JSON object — no markdown, no backticks — exactly this schema:
{{
  "narrative_script": "Full voiceover narration text. Should be engaging, educational, 120-200 words.",
  "scenes": [
    {{"duration": 6, "image_keyword": "concise visual description for image generation"}},
    {{"duration": 5, "image_keyword": "another scene visual"}},
    {{"duration": 6, "image_keyword": "another scene visual"}},
    {{"duration": 5, "image_keyword": "final scene visual"}}
  ]
}}

Rules:
- Include 4-6 scenes. Each duration must be an integer between 4 and 10 seconds.
- image_keyword must be a short (5-8 word) descriptive visual prompt.
- narrative_script must be cohesive prose that narrates all scenes in sequence.
"""

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={gemini_key.strip()}"
    )
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json",
        },
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=45)
        if resp.status_code != 200:
            return None, f"Gemini API error ({resp.status_code}): {resp.text[:300]}"

        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]

        # Clean markdown syntax
        raw = re.sub(r"```json\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw)

        script_data = json.loads(raw.strip())

        if "narrative_script" not in script_data or "scenes" not in script_data:
            return None, "Gemini returned JSON missing required keys."
        if not isinstance(script_data["scenes"], list) or len(script_data["scenes"]) == 0:
            return None, "Gemini returned empty scenes array."

        return script_data, "OK"

    except json.JSONDecodeError as je:
        return None, f"JSON parse error: {je}"
    except Exception as ex:
        return None, f"Script generation failed: {ex}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. IMAGE FETCHER
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_image_for_scene(keyword: str) -> str | None:
    """Fetches a scene image from Pollinations AI. Returns local temp path or None."""
    if not keyword:
        keyword = "abstract digital technology education"

    clean = re.sub(r"[^\w\s]", "", keyword).strip()
    encoded = urllib.parse.quote(
        f"high resolution modern educational illustration of {clean}, detailed, 8k wallpaper"
    )
    seed = abs(hash(clean)) % 100000
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1280&height=720&seed={seed}&nologo=true"
    )

    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        if resp.status_code == 200 and len(resp.content) > 5000:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp.write(resp.content)
            tmp.close()
            return tmp.name
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. MOVIEPY VIDEO ASSEMBLER
# ─────────────────────────────────────────────────────────────────────────────

def assemble_video_moviepy(
    scene_image_paths: list[str],
    durations: list[int],
    audio_bytes: bytes,
    output_path: str | None = None,
) -> str | None:
    """Assembles images into an MP4 with speech narration, perfectly scaled to audio duration."""
    try:
        from moviepy.editor import (
            ImageClip,
            AudioFileClip,
            concatenate_videoclips,
        )
    except ImportError:
        st.error("❌ `moviepy` is not installed. Ensure `moviepy==1.0.3` is installed.")
        return None

    audio_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    audio_tmp.write(audio_bytes)
    audio_tmp.close()

    if output_path is None:
        out_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        output_path = out_tmp.name
        out_tmp.close()

    try:
        audio = AudioFileClip(audio_tmp.name)
        audio_duration = audio.duration

        # Calculate time scaling ratio so images match exact narration audio length
        total_planned_dur = sum(durations) if durations else 1.0
        scale_ratio = audio_duration / total_planned_dur if total_planned_dur > 0 else 1.0

        clips = []
        for img_path, dur in zip(scene_image_paths, durations):
            if img_path and os.path.exists(img_path):
                adjusted_dur = max(float(dur) * scale_ratio, 1.0)
                clip = ImageClip(img_path, duration=adjusted_dur).set_fps(24)
                clips.append(clip)

        if not clips:
            return None

        video = concatenate_videoclips(clips, method="compose")
        video = video.set_audio(audio)

        video.write_videofile(
            output_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            ffmpeg_params=["-crf", "28"],
            verbose=False,
            logger=None,
        )
        return output_path

    except Exception as ex:
        st.error(f"❌ Video assembly error: {ex}")
        return None

    finally:
        if os.path.exists(audio_tmp.name):
            try:
                os.unlink(audio_tmp.name)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# 4. STREAMLIT UI PANEL
# ─────────────────────────────────────────────────────────────────────────────

def render_video_generator_ui(
    gemini_key: str,
    vector_db=None,
    embedder=None,
    user_prefs: dict | None = None,
) -> None:
    """Renders the 🎥 One-Shot Video Generator expander inside col_tools."""
    
    # Initialize state keys for render persistence across UI cycles
    if "vid_mp4_path" not in st.session_state:
        st.session_state.vid_mp4_path = None
    if "vid_script_text" not in st.session_state:
        st.session_state.vid_script_text = None
    if "vid_topic_rendered" not in st.session_state:
        st.session_state.vid_topic_rendered = ""

    with st.expander("🎥 One-Shot Video Generator", expanded=False):

        st.markdown(
            "<p style='font-size:11px; color:#a1a1aa; font-family:\"JetBrains Mono\",monospace; margin-bottom:12px;'>"
            "Enter a topic → Gemini writes a script → images auto-fetched → "
            "edge-tts narrates → MoviePy renders a downloadable MP4."
            "</p>",
            unsafe_allow_html=True,
        )

        if vector_db is not None:
            st.markdown(
                "<div style='font-size:10px; color:#22c55e; font-family:\"JetBrains Mono\"; margin-bottom:10px;'>"
                "⚡ KNOWLEDGE BASE ACTIVE — RAG context will enrich the script."
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='font-size:10px; color:#a1a1aa; font-family:\"JetBrains Mono\"; margin-bottom:10px;'>"
                "ℹ️ No indexed context. Script will use general knowledge."
                "</div>",
                unsafe_allow_html=True,
            )

        vid_topic = st.text_input(
            "Video Topic:",
            placeholder="e.g. The Krebs Cycle, Quantum Entanglement",
            key="vid_topic_input",
        )
        vid_instructions = st.text_area(
            "Additional Instructions (optional):",
            placeholder="e.g. Keep it beginner-friendly, focus on real-world applications",
            key="vid_instructions_input",
            height=68,
        )

        voice_options = {
            "Aria (US Female — Natural)": "en-US-AriaNeural",
            "Guy (US Male — Natural)": "en-US-GuyNeural",
            "Jenny (US Female — Friendly)": "en-US-JennyNeural",
            "Ryan (UK Male — Professional)": "en-GB-RyanNeural",
            "Sonia (UK Female — Calm)": "en-GB-SoniaNeural",
        }
        chosen_voice_label = st.selectbox(
            "Narrator Voice:",
            options=list(voice_options.keys()),
            key="vid_voice_select",
        )
        chosen_voice = voice_options[chosen_voice_label]

        if st.button("🎬 GENERATE VIDEO", use_container_width=True, key="vid_gen_btn"):

            if not gemini_key:
                st.error("❌ GEMINI_API_KEY is missing in Streamlit Secrets.")
                return
            if not vid_topic.strip():
                st.warning("Please enter a video topic first.")
                return

            rag_context = ""
            if vector_db is not None and embedder is not None:
                try:
                    retriever = vector_db.as_retriever(search_kwargs={"k": 5})
                    nodes = retriever.invoke(vid_topic)
                    rag_context = "\n\n".join(
                        f"[{n.metadata.get('source', 'Source')}]\n{n.page_content}"
                        for n in nodes
                    )
                except Exception:
                    rag_context = ""

            with st.status("✍️ Writing educational script with Gemini…", expanded=True) as status_box:
                script_data, script_status = generate_video_script_gemini(
                    topic=vid_topic,
                    instructions=vid_instructions,
                    context=rag_context,
                    gemini_key=gemini_key,
                    user_prefs=user_prefs,
                )

                if script_data is None:
                    status_box.update(label="❌ Script generation failed.", state="error")
                    st.error(f"Reason: {script_status}")
                    return

                narrative = script_data["narrative_script"]
                scenes = script_data["scenes"]
                status_box.write(f"✅ Script ready — {len(scenes)} scenes planned.")

                status_box.write("🖼️ Fetching scene visuals from Pollinations AI…")
                image_paths: list[str] = []
                durations: list[int] = []
                for i, scene in enumerate(scenes):
                    kw = scene.get("image_keyword", vid_topic)
                    dur = int(scene.get("duration", 6))
                    durations.append(dur)
                    img_path = _fetch_image_for_scene(kw)
                    image_paths.append(img_path)
                    status_box.write(f"  ✔ Scene {i+1}: {kw[:50]}")

                valid_images = [p for p in image_paths if p]
                if not valid_images:
                    status_box.update(label="❌ All image fetches failed.", state="error")
                    st.error("Could not retrieve any scene images. Check your connection.")
                    return

                valid_pairs = [(p, d) for p, d in zip(image_paths, durations) if p]
                valid_paths = [x[0] for x in valid_pairs]
                valid_durs = [x[1] for x in valid_pairs]

                status_box.write(f"🎙️ Synthesizing narration with {chosen_voice_label}…")
                audio_bytes = run_tts_synthesis(narrative, voice=chosen_voice)
                if not audio_bytes:
                    status_box.update(label="❌ TTS narration failed.", state="error")
                    st.error("Could not synthesize audio. Ensure `edge-tts` is installed.")
                    return
                status_box.write(f"  ✔ Audio ready ({len(audio_bytes)//1024} KB)")

                status_box.write("🎬 Assembling video with MoviePy…")
                out_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
                out_path = out_tmp.name
                out_tmp.close()

                mp4_path = assemble_video_moviepy(
                    scene_image_paths=valid_paths,
                    durations=valid_durs,
                    audio_bytes=audio_bytes,
                    output_path=out_path,
                )

                for p in valid_paths:
                    try:
                        if os.path.exists(p):
                            os.unlink(p)
                    except Exception:
                        pass

                if mp4_path is None:
                    status_box.update(label="❌ Video assembly failed.", state="error")
                    return

                # Save generated path to session_state so UI elements survive reruns
                st.session_state.vid_mp4_path = mp4_path
                st.session_state.vid_script_text = narrative
                st.session_state.vid_topic_rendered = vid_topic

                status_box.update(label="✅ Video rendered successfully!", state="complete", expanded=False)

        # RENDER PERSISTENT OUTPUT SECTION (OUTSIDE OF BUTTON BLOCK)
        if st.session_state.vid_mp4_path and os.path.exists(st.session_state.vid_mp4_path):
            st.markdown(
                "<div style='margin-top:12px; font-size:11px; font-weight:700; "
                "letter-spacing:0.15em; color:#a1a1aa; text-transform:uppercase; "
                "border-bottom:1px solid rgba(255,140,0,0.2); padding-bottom:8px; "
                "margin-bottom:12px;'>🎞️ RENDERED OUTPUT</div>",
                unsafe_allow_html=True,
            )

            st.video(st.session_state.vid_mp4_path)

            with open(st.session_state.vid_mp4_path, "rb") as vf:
                st.download_button(
                    label="📥 DOWNLOAD MP4",
                    data=vf,
                    file_name=f"apollo_{re.sub(r'[^\\w]', '_', st.session_state.vid_topic_rendered[:30])}.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                    key="vid_download_btn",
                )

            if st.session_state.vid_script_text:
                with st.expander("📜 View Generated Script", expanded=False):
                    st.markdown(
                        f"<div style='font-family:\"JetBrains Mono\",monospace; "
                        f"font-size:11px; color:#e5e2e1; white-space:pre-wrap; "
                        f"background:rgba(0,0,0,0.4); padding:12px; border-radius:4px; "
                        f"border:1px solid rgba(255,140,0,0.15);'>{st.session_state.vid_script_text}</div>",
                        unsafe_allow_html=True,
                    )
