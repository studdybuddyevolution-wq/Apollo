"""
video_generator.py — Apollo Omni AI
────────────────────────────────────
Standalone RAG-powered Educational Video Generator module.

Script Engine : Groq LPU (llama-3.3-70b-versatile) — fast & free
Video Engines : 
  1. MoviePy Narrated Video (Scene-by-scene script + Pollinations visuals + edge-tts narration)
  2. Kling AI Video Generation (Direct Kling AI text-to-video via KLING_API_KEY)

Dependencies:
    moviepy>=1.0.3   edge-tts>=6.1.9   groq   requests
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import urllib.parse
from typing import Optional

import requests
import streamlit as st
from groq import Groq

# Re-export TTS from voice_handler
from voice_handler import run_tts_synthesis  # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# 1. GROQ SCRIPT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def _build_video_prompt(
    topic: str,
    instructions: str,
    context: str,
    user_prefs: Optional[dict],
) -> str:
    """Builds the structured JSON prompt for video script generation."""
    prefs_ctx = ""
    if user_prefs:
        prefs_ctx = (
            f"Adapt content for a student with:\n"
            f"  • Learning Style : {user_prefs.get('learning_style', 'General')}\n"
            f"  • Expertise Level: {user_prefs.get('detail_level', 'Intermediate')}\n\n"
        )

    return f"""{prefs_ctx}Create an educational video script about: "{topic}"

SPECIFIC INSTRUCTIONS:
{instructions if instructions else "None provided."}

KNOWLEDGE BASE CONTEXT:
{context if context else "No extra context. Use general knowledge."}

OUTPUT RULES:
- Return ONLY a valid raw JSON object. No markdown, no backticks, no explanation.
- Start with {{ and end with }}.
- Include 4-6 scenes. Each duration must be an integer (4-10 seconds).
- image_keyword must be a short (5-8 word) descriptive visual prompt.
- narrative_script must be cohesive 120-200 word prose narrating all scenes.

EXACT SCHEMA:
{{
  "narrative_script": "Full engaging voiceover narration here.",
  "scenes": [
    {{"duration": 6, "image_keyword": "concise visual description"}},
    {{"duration": 5, "image_keyword": "another scene visual"}},
    {{"duration": 6, "image_keyword": "another scene visual"}},
    {{"duration": 5, "image_keyword": "final scene visual"}}
  ]
}}"""


def _parse_script_json(raw: str) -> tuple[dict | None, str]:
    """Strips markdown fences and parses the JSON safely."""
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw)

    start = raw.find("{")
    end   = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None, "No JSON object found in model response."

    candidate = raw[start : end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as je:
        return None, f"JSON parse error: {je}"

    if "narrative_script" not in data or "scenes" not in data:
        return None, "JSON missing 'narrative_script' or 'scenes' keys."
    if not isinstance(data["scenes"], list) or len(data["scenes"]) == 0:
        return None, "JSON 'scenes' array is empty."

    return data, "OK"


def generate_video_script_groq(
    topic: str,
    instructions: str = "",
    context: str = "",
    groq_key: str = "",
    user_prefs: Optional[dict] = None,
) -> tuple[dict | None, str]:
    """
    Uses Groq LPU (llama-3.3-70b-versatile) to generate a structured video script JSON.
    """
    if not groq_key or not groq_key.strip().startswith("gsk_"):
        return None, "Missing or invalid GROQ_API_KEY in Streamlit secrets."

    prompt = _build_video_prompt(topic, instructions, context, user_prefs)
    client = Groq(api_key=groq_key.strip())
    models_to_try = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

    for model_id in models_to_try:
        try:
            completion = client.chat.completions.create(
                model=model_id,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert educational video scriptwriter. "
                            "Output ONLY valid raw JSON — no markdown, no explanations."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=1500,
            )
            raw = completion.choices[0].message.content or ""
            data, status = _parse_script_json(raw)
            if data:
                return data, f"OK (Groq / {model_id})"
        except Exception as ex:
            last_err = str(ex)
            continue

    return None, f"Groq script generation error: {locals().get('last_err', 'unknown')}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. KLING AI DIRECT VIDEO GENERATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def generate_kling_video(
    prompt: str,
    kling_key: str,
    duration: int = 5,
) -> tuple[str | None, str]:
    """
    Dispatches a video generation task to Kling AI API using KLING_API_KEY.
    
    Supports official Kling AI API / Aggregator standard endpoints:
      • Endpoint: https://api.klingai.com/v1/videos/text2video
      • Fallback: https://api.aimlapi.com/v2/video/generations

    Returns (video_url_or_file_path, status_message)
    """
    if not kling_key or not kling_key.strip():
        return None, "Missing KLING_API_KEY in Streamlit Secrets."

    clean_prompt = prompt.strip()[:1000]

    # Try Primary Kling AI API endpoint
    headers = {
        "Authorization": f"Bearer {kling_key.strip()}",
        "X-API-Key": kling_key.strip(),
        "Content-Type": "application/json",
    }

    endpoints = [
        {
            "url": "https://api.klingai.com/v1/videos/text2video",
            "payload": {
                "model_name": "kling-v1",
                "prompt": clean_prompt,
                "duration": str(duration),
                "aspect_ratio": "16:9",
            },
        },
        {
            "url": "https://api.aimlapi.com/v2/video/generations",
            "payload": {
                "model": "kling-video/v1/standard/text-to-video",
                "prompt": clean_prompt,
                "duration": duration,
            },
        },
    ]

    last_error = ""
    for ep in endpoints:
        try:
            resp = requests.post(ep["url"], headers=headers, json=ep["payload"], timeout=30)
            if resp.status_code in (200, 201, 202):
                res_data = resp.json()
                # Check for direct video url in response
                video_url = (
                    res_data.get("video_url")
                    or res_data.get("data", {}).get("video_url")
                    or res_data.get("output", {}).get("video_url")
                )
                if video_url:
                    return video_url, "Success (Kling AI Direct)"
                
                # Check for task_id (asynchronous workflow)
                task_id = res_data.get("task_id") or res_data.get("id") or res_data.get("data", {}).get("task_id")
                if task_id:
                    # Poll status endpoint for up to 60 seconds
                    poll_url = f"{ep['url']}/{task_id}"
                    for _ in range(12):
                        time.sleep(5)
                        poll_resp = requests.get(poll_url, headers=headers, timeout=15)
                        if poll_resp.status_code == 200:
                            p_data = poll_resp.json()
                            status = p_data.get("status") or p_data.get("task_status")
                            if status in ("succeeded", "completed", "SUCCESS"):
                                out_url = (
                                    p_data.get("video_url")
                                    or p_data.get("data", {}).get("video_url")
                                    or p_data.get("output", {}).get("video_url")
                                )
                                if out_url:
                                    return out_url, "Success (Kling AI Async)"
                            elif status in ("failed", "ERROR"):
                                break
            else:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            last_error = str(e)
            continue

    return None, f"Kling AI API call failed: {last_error}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. IMAGE FETCHER & MOVIEPY VIDEO ASSEMBLER
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_image_for_scene(keyword: str) -> str | None:
    """Fetches a scene image from Pollinations AI."""
    if not keyword:
        keyword = "abstract digital technology education"

    clean   = re.sub(r"[^\w\s]", "", keyword).strip()
    encoded = urllib.parse.quote(
        f"high resolution modern educational illustration of {clean}, detailed, 8k wallpaper"
    )
    seed = abs(hash(clean)) % 100000
    url  = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&seed={seed}&nologo=true"

    try:
        resp = requests.get(
            url,
            timeout=20,
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


def assemble_video_moviepy(
    scene_image_paths: list[str],
    durations: list[int],
    audio_bytes: bytes,
    output_path: str | None = None,
) -> str | None:
    """Assembles images + audio track into an MP4 file using MoviePy."""
    try:
        from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
    except ImportError:
        st.error("❌ `moviepy` is not installed.")
        return None

    audio_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    audio_tmp.write(audio_bytes)
    audio_tmp.close()

    if output_path is None:
        out_tmp     = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        output_path = out_tmp.name
        out_tmp.close()

    clips = []
    try:
        for img_path, dur in zip(scene_image_paths, durations):
            if img_path and os.path.exists(img_path):
                clip = ImageClip(img_path, duration=float(max(dur, 2))).set_fps(24)
                clips.append(clip)

        if not clips:
            return None

        video = concatenate_videoclips(clips, method="compose")
        audio = AudioFileClip(audio_tmp.name)
        total_dur = video.duration

        audio = audio.subclip(0, min(audio.duration, total_dur))
        if audio.duration < total_dur:
            audio = audio.set_duration(total_dur)

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
    groq_key: str = "",
    kling_key: str = "",
    vector_db=None,
    embedder=None,
    user_prefs: dict | None = None,
) -> None:
    """
    Renders the 🎥 One-Shot Video Generator expander inside col_tools.
    """
    with st.expander("🎥 One-Shot Video Generator", expanded=False):

        st.markdown(
            "<p style='font-size:11px; color:#a1a1aa; font-family:\"JetBrains Mono\",monospace; margin-bottom:8px;'>"
            "Generate narrated educational videos with Groq LPU + MoviePy or direct Kling AI video creation."
            "</p>",
            unsafe_allow_html=True,
        )

        has_groq  = bool(groq_key and groq_key.strip().startswith("gsk_"))
        has_kling = bool(kling_key and kling_key.strip())

        b_groq = (
            "<span style='font-size:9px; font-family:\"JetBrains Mono\"; background:rgba(34,197,94,0.12); color:#4ade80; border:1px solid rgba(34,197,94,0.3); padding:2px 7px; border-radius:2px;'>"
            "✔ GROQ SCRIPT ACTIVE</span>" if has_groq else
            "<span style='font-size:9px; font-family:\"JetBrains Mono\"; background:rgba(239,68,68,0.12); color:#f87171; border:1px solid rgba(239,68,68,0.3); padding:2px 7px; border-radius:2px;'>"
            "✘ GROQ MISSING</span>"
        )
        b_kling = (
            "<span style='font-size:9px; font-family:\"JetBrains Mono\"; background:rgba(34,197,94,0.12); color:#4ade80; border:1px solid rgba(34,197,94,0.3); padding:2px 7px; border-radius:2px; margin-left:6px;'>"
            "✔ KLING AI READY</span>" if has_kling else
            "<span style='font-size:9px; font-family:\"JetBrains Mono\"; background:rgba(161,161,170,0.1); color:#71717a; border:1px solid rgba(161,161,170,0.2); padding:2px 7px; border-radius:2px; margin-left:6px;'>"
            "○ KLING AI KEY OPTIONAL</span>"
        )

        st.markdown(f"<div style='margin-bottom:10px;'>{b_groq}{b_kling}</div>", unsafe_allow_html=True)

        vid_mode = st.radio(
            "Video Mode:",
            options=["🎬 Narrated Scene Video (MoviePy + Groq + TTS)", "✨ Direct Kling AI Video (KLING_API_KEY)"],
            key="vid_mode_radio",
        )

        vid_topic = st.text_input(
            "Video Topic / Prompt:",
            placeholder="e.g. The Krebs Cycle, Quantum Physics",
            key="vid_topic_input",
        )

        if "Narrated" in vid_mode:
            vid_instructions = st.text_area(
                "Additional Focus Points (optional):",
                placeholder="e.g. Focus on practical applications",
                key="vid_instructions_input",
                height=60,
            )

            voice_options = {
                "Aria (US Female)": "en-US-AriaNeural",
                "Guy (US Male)": "en-US-GuyNeural",
                "Jenny (US Female)": "en-US-JennyNeural",
                "Ryan (UK Male)": "en-GB-RyanNeural",
            }
            chosen_voice_label = st.selectbox("Narrator Voice:", list(voice_options.keys()), key="vid_voice_select")
            chosen_voice = voice_options[chosen_voice_label]

            if st.button("🎬 GENERATE NARRATED VIDEO", use_container_width=True, key="vid_gen_narrated"):
                if not vid_topic.strip():
                    st.warning("Please enter a video topic first.")
                    return

                rag_context = ""
                if vector_db is not None and embedder is not None:
                    try:
                        retriever = vector_db.as_retriever(search_kwargs={"k": 5})
                        nodes = retriever.invoke(vid_topic)
                        rag_context = "\n\n".join(f"[{n.metadata.get('source', 'Source')}]\n{n.page_content}" for n in nodes)
                    except Exception:
                        pass

                with st.status("✍️ Assembling video pipeline...", expanded=True) as status_box:
                    script_data, script_status = generate_video_script_groq(
                        topic=vid_topic,
                        instructions=vid_instructions,
                        context=rag_context,
                        groq_key=groq_key,
                        user_prefs=user_prefs,
                    )
                    if not script_data:
                        status_box.update(label="❌ Script generation failed.", state="error")
                        st.error(f"Reason: {script_status}")
                        return

                    narrative = script_data["narrative_script"]
                    scenes    = script_data["scenes"]
                    status_box.write(f"✅ Script generated via Groq — {len(scenes)} scenes.")

                    image_paths, durations = [], []
                    for i, scene in enumerate(scenes):
                        kw  = scene.get("image_keyword", vid_topic)
                        dur = int(scene.get("duration", 6))
                        durations.append(dur)
                        img_path = _fetch_image_for_scene(kw)
                        image_paths.append(img_path)
                        status_box.write(f"  ✔ Scene {i+1}: {kw[:50]}")

                    valid_pairs = [(p, d) for p, d in zip(image_paths, durations) if p]
                    if not valid_pairs:
                        status_box.update(label="❌ Scene images failed.", state="error")
                        return

                    valid_paths = [x[0] for x in valid_pairs]
                    valid_durs  = [x[1] for x in valid_pairs]

                    status_box.write("🎙️ Synthesizing voice narration...")
                    audio_bytes = run_tts_synthesis(narrative, voice=chosen_voice)
                    if not audio_bytes:
                        status_box.update(label="❌ TTS synthesis failed.", state="error")
                        return

                    status_box.write("🎬 Compiling MP4 video...")
                    mp4_path = assemble_video_moviepy(valid_paths, valid_durs, audio_bytes)
                    
                    for p in valid_paths:
                        try:
                            if os.path.exists(p):
                                os.unlink(p)
                        except Exception:
                            pass

                    if not mp4_path:
                        status_box.update(label="❌ Assembly failed.", state="error")
                        return

                    status_box.update(label="✅ Video compilation complete!", state="complete", expanded=False)

                st.video(mp4_path)
                with open(mp4_path, "rb") as vf:
                    st.download_button("📥 DOWNLOAD MP4", vf, file_name=f"apollo_{vid_topic[:20]}.mp4", mime="video/mp4", use_container_width=True)

        else:
            # Kling AI Mode
            if st.button("✨ GENERATE KLING AI VIDEO", use_container_width=True, key="vid_gen_kling"):
                if not kling_key:
                    st.error("❌ KLING_API_KEY is not set in Streamlit Secrets.")
                    return
                if not vid_topic.strip():
                    st.warning("Please enter a video prompt first.")
                    return

                with st.spinner("✨ Requesting video from Kling AI API..."):
                    video_res, status_msg = generate_kling_video(vid_topic, kling_key)
                    if video_res:
                        st.success(f"✅ Kling AI Video Generated! ({status_msg})")
                        if video_res.startswith("http"):
                            st.video(video_res)
                        else:
                            st.video(video_res)
                    else:
                        st.error(f"❌ Kling AI Error: {status_msg}")
