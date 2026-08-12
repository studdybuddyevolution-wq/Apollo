"""
video_generator.py — Apollo Omni AI
────────────────────────────────────
Standalone RAG-powered Educational Video Generator module supporting:
  1. Veo 3 Lite Video Generation (Google Gemini API via GEMINI_API_KEY)
  2. MoviePy Narrated Video (Scene-by-scene script + Pollinations visuals + edge-tts narration)
  3. Kling AI Video Generation (Direct Kling AI text-to-video via KLING_API_KEY)
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

try:
    import jwt
except ImportError:
    jwt = None

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
    """Uses Groq LPU (llama-3.3-70b-versatile) to generate structured video script JSON."""
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
                        "content": "You are an expert educational video scriptwriter. Output ONLY valid raw JSON.",
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
# 2. GEMINI VEO 3 LITE VIDEO GENERATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def generate_veo_video(
    prompt: str,
    gemini_key: str,
    model_name: str = "veo-3-lite",
    duration: int = 5,
) -> tuple[str | None, str]:
    """
    Generates video using Google Gemini API Key and Veo 3 Lite model.
    """
    if not gemini_key or not gemini_key.strip():
        return None, "Missing GEMINI_API_KEY in Streamlit secrets."

    clean_key = gemini_key.strip()
    clean_prompt = prompt.strip()[:1000]

    # Try Google GenAI SDK first
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=clean_key)
        operation = client.models.generate_videos(
            model=model_name,
            prompt=clean_prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio="16:9",
                duration_seconds=duration,
            ),
        )

        while not operation.done:
            time.sleep(5)
            operation = client.operations.get(operation)

        if hasattr(operation, "result") and operation.result and operation.result.generated_videos:
            gen_video = operation.result.generated_videos[0]
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            
            if hasattr(gen_video, "video_bytes"):
                tmp.write(gen_video.video_bytes)
            elif hasattr(gen_video, "video") and hasattr(gen_video.video, "video_bytes"):
                tmp.write(gen_video.video.video_bytes)
            else:
                downloaded_bytes = client.files.download(file=getattr(gen_video, "video", gen_video))
                tmp.write(downloaded_bytes)

            tmp.close()
            return tmp.name, f"Success ({model_name} via GenAI SDK)"
    except Exception as sdk_ex:
        sdk_err = str(sdk_ex)

    # Fallback to Google Generative Language REST API endpoint
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:predict?key={clean_key}"
        payload = {
            "instances": [{"prompt": clean_prompt}],
            "parameters": {
                "aspectRatio": "16:9",
                "sampleCount": 1,
                "durationSeconds": duration,
            },
        }
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            res_data = resp.json()
            if "name" in res_data:
                op_url = f"https://generativelanguage.googleapis.com/v1beta/{res_data['name']}?key={clean_key}"
                for _ in range(30):
                    time.sleep(5)
                    poll_resp = requests.get(op_url, timeout=15)
                    if poll_resp.status_code == 200:
                        p_data = poll_resp.json()
                        if p_data.get("done"):
                            response_obj = p_data.get("response", {})
                            videos = response_obj.get("generatedVideos", [])
                            if videos:
                                video_uri = videos[0].get("video", {}).get("uri")
                                if video_uri:
                                    v_bytes = requests.get(f"{video_uri}?key={clean_key}", timeout=30).content
                                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
                                    tmp.write(v_bytes)
                                    tmp.close()
                                    return tmp.name, f"Success ({model_name} REST API)"
                            break
        else:
            rest_err = resp.text[:150]
    except Exception as rest_ex:
        rest_err = str(rest_ex)

    return None, f"Veo 3 Lite video generation failed. SDK Error: {locals().get('sdk_err', 'N/A')}. REST Error: {locals().get('rest_err', 'N/A')}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. KLING AI DIRECT VIDEO GENERATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def _parse_kling_credentials(kling_key: str) -> tuple[str | None, str | None, str]:
    s = kling_key.strip()
    if s.lower().startswith("bearer "):
        s = s[7:].strip()

    ak_match = re.search(r"(?:access_?key|ak)\s*[:=]\s*([^\s,;]+)", s, re.I)
    sk_match = re.search(r"(?:secret_?key|sk)\s*[:=]\s*([^\s,;]+)", s, re.I)
    if ak_match and sk_match:
        return ak_match.group(1).strip(), sk_match.group(1).strip(), s

    for delim in [":", "|", ","]:
        if delim in s and not s.startswith("http"):
            parts = s.split(delim, 1)
            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                return parts[0].strip(), parts[1].strip(), s

    parts = s.split()
    if len(parts) == 2 and not s.startswith("eyJ"):
        return parts[0].strip(), parts[1].strip(), s

    return None, None, s


def _get_kling_auth_token(kling_key: str) -> str:
    ak, sk, raw_token = _parse_kling_credentials(kling_key)
    if ak and sk and jwt:
        now = int(time.time())
        headers = {"alg": "HS256", "typ": "JWT"}
        payload = {"iss": ak, "exp": now + 1800, "nbf": now - 5}
        try:
            return jwt.encode(payload, sk, algorithm="HS256", headers=headers)
        except Exception:
            pass
    return raw_token


def generate_kling_video(prompt: str, kling_key: str, duration: int = 5) -> tuple[str | None, str]:
    if not kling_key or not kling_key.strip():
        return None, "Missing KLING_API_KEY in Streamlit Secrets."

    clean_prompt = prompt.strip()[:1000]
    raw_key = kling_key.strip()
    ak, sk, _ = _parse_kling_credentials(raw_key)
    jwt_token = _get_kling_auth_token(raw_key)

    endpoints = []
    if ak and sk:
        endpoints.append({
            "name": "Kling Open Platform (Signed JWT)",
            "url": "https://api.klingai.com/v1/videos/text2video",
            "headers": {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"},
            "payload": {"model_name": "kling-v1", "prompt": clean_prompt, "duration": str(duration), "aspect_ratio": "16:9"},
        })
    elif raw_key.startswith("fal-") or raw_key.startswith("fal_"):
        endpoints.append({
            "name": "Fal.ai Kling Gateway",
            "url": "https://queue.fal.run/fal-ai/kling-video/v1.5/standard/text-to-video",
            "headers": {"Authorization": f"Key {raw_key}", "Content-Type": "application/json"},
            "payload": {"prompt": clean_prompt, "duration": str(duration)},
        })

    for ep in endpoints:
        try:
            resp = requests.post(ep["url"], headers=ep["headers"], json=ep["payload"], timeout=30)
            if resp.status_code in (200, 201, 202):
                res_data = resp.json()
                video_url = res_data.get("video_url") or res_data.get("data", {}).get("video_url")
                if video_url:
                    return video_url, f"Success ({ep['name']})"
        except Exception as e:
            continue

    return None, "Kling AI generation request failed."


# ─────────────────────────────────────────────────────────────────────────────
# 4. IMAGE FETCHER & MOVIEPY ASSEMBLY
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_image_for_scene(keyword: str) -> str | None:
    if not keyword:
        keyword = "abstract digital technology education"

    clean = re.sub(r"[^\w\s]", "", keyword).strip()
    encoded = urllib.parse.quote(f"high resolution modern educational illustration of {clean}, detailed, 8k wallpaper")
    seed = abs(hash(clean)) % 100000
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&seed={seed}&nologo=true"

    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
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
    try:
        from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
    except ImportError:
        st.error("❌ `moviepy` is not installed.")
        return None

    audio_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    audio_tmp.write(audio_bytes)
    audio_tmp.close()

    if output_path is None:
        out_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        output_path = out_tmp.name
        out_tmp.close()

    clips = []
    try:
        for img_path, dur in zip(scene_image_paths, durations):
            if img_path and os.path.exists(img_path):
                clips.append(ImageClip(img_path, duration=float(max(dur, 2))).set_fps(24))

        if not clips:
            return None

        video = concatenate_videoclips(clips, method="compose")
        audio = AudioFileClip(audio_tmp.name)
        total_dur = video.duration

        audio = audio.subclip(0, min(audio.duration, total_dur))
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
# 5. STREAMLIT UI PANEL
# ─────────────────────────────────────────────────────────────────────────────

def render_video_generator_ui(
    groq_key: str = "",
    kling_key: str = "",
    gemini_key: str = "",
    vector_db=None,
    embedder=None,
    user_prefs: dict | None = None,
) -> None:
    """Renders the Video Generator UI panel."""
    with st.expander("🎥 One-Shot Video Generator", expanded=False):

        st.markdown(
            "<p style='font-size:11px; color:#a1a1aa; font-family:\"JetBrains Mono\",monospace; margin-bottom:8px;'>"
            "Generate AI videos using Google Gemini Veo 3 Lite, Groq + MoviePy narration, or Kling AI."
            "</p>",
            unsafe_allow_html=True,
        )

        has_gemini = bool(gemini_key and gemini_key.strip())
        has_groq = bool(groq_key and groq_key.strip().startswith("gsk_"))
        has_kling = bool(kling_key and kling_key.strip())

        b_gemini = (
            "<span style='font-size:9px; font-family:\"JetBrains Mono\"; background:rgba(34,197,94,0.12); color:#4ade80; border:1px solid rgba(34,197,94,0.3); padding:2px 7px; border-radius:2px;'>"
            "✔ GEMINI VEO READY</span>" if has_gemini else
            "<span style='font-size:9px; font-family:\"JetBrains Mono\"; background:rgba(239,68,68,0.12); color:#f87171; border:1px solid rgba(239,68,68,0.3); padding:2px 7px; border-radius:2px;'>"
            "✘ GEMINI KEY MISSING</span>"
        )
        b_groq = (
            "<span style='font-size:9px; font-family:\"JetBrains Mono\"; background:rgba(34,197,94,0.12); color:#4ade80; border:1px solid rgba(34,197,94,0.3); padding:2px 7px; border-radius:2px; margin-left:6px;'>"
            "✔ GROQ READY</span>" if has_groq else ""
        )

        st.markdown(f"<div style='margin-bottom:10px;'>{b_gemini}{b_groq}</div>", unsafe_allow_html=True)

        vid_mode = st.radio(
            "Video Mode:",
            options=[
                "✨ Veo 3 Lite Video (Gemini API)",
                "🎬 Narrated Scene Video (MoviePy + Groq + TTS)",
                "🎥 Direct Kling AI Video",
            ],
            key="vid_mode_radio",
        )

        vid_topic = st.text_input(
            "Video Topic / Prompt:",
            placeholder="e.g. A futuristic quantum computer core glowing in cyan",
            key="vid_topic_input",
        )

        if "Veo 3 Lite" in vid_mode:
            if st.button("🚀 GENERATE VEO 3 LITE VIDEO", use_container_width=True, key="vid_gen_veo"):
                if not gemini_key:
                    st.error("❌ GEMINI_API_KEY is missing from Streamlit secrets.")
                    return
                if not vid_topic.strip():
                    st.warning("Please enter a video prompt first.")
                    return

                with st.spinner("⚡ Rendering video with Gemini Veo 3 Lite..."):
                    vid_path, status_msg = generate_veo_video(vid_topic, gemini_key, model_name="veo-3-lite")
                    if vid_path and os.path.exists(vid_path):
                        st.success(f"✅ Video generated! ({status_msg})")
                        st.video(vid_path)
                        with open(vid_path, "rb") as vf:
                            st.download_button("📥 DOWNLOAD MP4", vf, file_name="apollo_veo3_lite.mp4", mime="video/mp4", use_container_width=True)
                    else:
                        st.error(status_msg)

        elif "Narrated" in vid_mode:
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
                    scenes = script_data["scenes"]

                    image_paths, durations = [], []
                    for scene in scenes:
                        kw = scene.get("image_keyword", vid_topic)
                        durations.append(int(scene.get("duration", 6)))
                        image_paths.append(_fetch_image_for_scene(kw))

                    valid_pairs = [(p, d) for p, d in zip(image_paths, durations) if p]
                    if not valid_pairs:
                        status_box.update(label="❌ Scene images failed.", state="error")
                        return

                    audio_bytes = run_tts_synthesis(narrative, voice=chosen_voice)
                    mp4_path = assemble_video_moviepy([x[0] for x in valid_pairs], [x[1] for x in valid_pairs], audio_bytes)

                    status_box.update(label="✅ Video compilation complete!", state="complete", expanded=False)

                if mp4_path:
                    st.video(mp4_path)
                    with open(mp4_path, "rb") as vf:
                        st.download_button("📥 DOWNLOAD MP4", vf, file_name=f"apollo_{vid_topic[:20]}.mp4", mime="video/mp4", use_container_width=True)

        else:
            if st.button("✨ GENERATE KLING AI VIDEO", use_container_width=True, key="vid_gen_kling"):
                if not kling_key:
                    st.error("❌ KLING_API_KEY is not set in Streamlit Secrets.")
                    return
                with st.spinner("✨ Requesting video from Kling AI API..."):
                    video_res, status_msg = generate_kling_video(vid_topic, kling_key)
                    if video_res:
                        st.success(f"✅ Kling AI Video Generated! ({status_msg})")
                        st.video(video_res)
                    else:
                        st.error(status_msg)
