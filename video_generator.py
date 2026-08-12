"""
video_generator.py — Apollo Omni AI
────────────────────────────────────
Zero-cost cloud video generation module:
  1. Hugging Face Inference API (Cloud GPU via `huggingface_hub.InferenceClient`)
  2. Narrated Lesson Video (Groq + Pollinations + Edge-TTS + MoviePy)
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
from groq import Groq

# Import Hugging Face Hub Inference Client
try:
    from huggingface_hub import InferenceClient
except ImportError:
    InferenceClient = None

# Re-export TTS from voice_handler
try:
    from voice_handler import run_tts_synthesis
except ImportError:
    run_tts_synthesis = None


# ─────────────────────────────────────────────────────────────────────────────
# 1. HUGGING FACE CLOUD API VIDEO ENGINE (VIA INFERENCE CLIENT)
# ─────────────────────────────────────────────────────────────────────────────

def generate_hf_cloud_video(prompt: str, hf_token: str = "") -> tuple[str | None, str]:
    """Calls serverless video generation models via Hugging Face InferenceClient."""
    if InferenceClient is None:
        return None, "Missing `huggingface_hub`. Add `huggingface_hub>=0.25.0` to your `requirements.txt`."

    clean_prompt = prompt.strip()[:500]
    token_val = hf_token or os.getenv("HF_TOKEN", "") or None

    if not token_val:
        return None, "A Hugging Face token is required for Inference API video generation. Please enter your token."

    # Models known to support robust text-to-video inference pipelines
    models_to_try = [
        ("Lightricks/LTX-Video-0.9.8-13B-distilled", "fal-ai"),
        ("tencent/HunyuanVideo", "fal-ai"),
    ]

    last_error = "No available inference model responded."

    for model_id, provider in models_to_try:
        try:
            client = InferenceClient(provider=provider, api_key=token_val)
            
            # Request video generation bytes from the cloud provider
            video_bytes = client.text_to_video(
                prompt=clean_prompt,
                model=model_id,
            )

            if video_bytes and len(video_bytes) > 1000:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
                tmp.write(video_bytes)
                tmp.close()
                return tmp.name, f"Success ({model_id})"

        except Exception as ex:
            last_error = f"{model_id}: {str(ex)}"
            continue

    return None, f"Hugging Face Inference Error: {last_error}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. GROQ SCRIPT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def _build_video_prompt(
    topic: str,
    instructions: str,
    context: str,
    user_prefs: Optional[dict],
) -> str:
    prefs_ctx = ""
    if user_prefs:
        prefs_ctx = (
            f"Adapt content for a student with:\n"
            f"  • Learning Style : {user_prefs.get('learning_style', 'General')}\n"
            f"  • Detail Level   : {user_prefs.get('detail_level', 'Intermediate')}\n\n"
        )

    return f"""{prefs_ctx}Create an educational video script about: "{topic}"

SPECIFIC INSTRUCTIONS:
{instructions if instructions else "None provided."}

CONTEXT:
{context if context else "Use general knowledge."}

OUTPUT RULES:
- Return ONLY a valid raw JSON object. No markdown, no backticks.
- Include 4-6 scenes with duration integers (4-8 seconds).
- image_keyword: 5-8 descriptive words for scene visuals.
- narrative_script: 120-180 word voiceover narrative.

EXACT SCHEMA:
{{
  "narrative_script": "Full voiceover narration here.",
  "scenes": [
    {{"duration": 5, "image_keyword": "descriptive visual prompt"}},
    {{"duration": 5, "image_keyword": "another scene visual"}}
  ]
}}"""


def generate_video_script_groq(
    topic: str,
    instructions: str = "",
    context: str = "",
    groq_key: str = "",
    user_prefs: Optional[dict] = None,
) -> tuple[dict | None, str]:
    clean_key = (groq_key or os.getenv("GROQ_API_KEY", "")).strip()
    if not clean_key or not clean_key.startswith("gsk_"):
        return None, "Missing or invalid GROQ_API_KEY."

    prompt = _build_video_prompt(topic, instructions, context, user_prefs)
    client = Groq(api_key=clean_key)

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You output ONLY raw JSON objects."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=1200,
        )
        raw = completion.choices[0].message.content or ""
        raw = re.sub(r"```json\s*|```\s*", "", raw).strip()
        data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        return data, "OK"
    except Exception as ex:
        return None, f"Groq script error: {ex}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. MOVIEPY LIGHTWEIGHT ASSEMBLY ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_image_for_scene(keyword: str) -> str | None:
    clean = re.sub(r"[^\w\s]", "", keyword).strip() or "educational graphic"
    encoded = urllib.parse.quote(f"high resolution educational illustration of {clean}, 8k")
    seed = abs(hash(clean)) % 100000
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&seed={seed}&nologo=true"

    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200 and len(resp.content) > 3000:
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
) -> str | None:
    try:
        from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips
    except ImportError:
        st.error("Please install MoviePy: `pip install 'moviepy>=1.0.3,<2.0.0'`")
        return None

    audio_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    audio_tmp.write(audio_bytes)
    audio_tmp.close()

    out_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    output_path = out_tmp.name
    out_tmp.close()

    clips = []
    try:
        for img_path, dur in zip(scene_image_paths, durations):
            if img_path and os.path.exists(img_path):
                clips.append(ImageClip(img_path, duration=float(max(dur, 3))).set_fps(24))

        if not clips:
            return None

        video = concatenate_videoclips(clips, method="compose")
        audio = AudioFileClip(audio_tmp.name)
        video = video.set_audio(audio.subclip(0, min(audio.duration, video.duration)))

        video.write_videofile(
            output_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            verbose=False,
            logger=None,
        )
        return output_path
    except Exception as ex:
        st.error(f"Assembly Error: {ex}")
        return None
    finally:
        if os.path.exists(audio_tmp.name):
            os.unlink(audio_tmp.name)


# ─────────────────────────────────────────────────────────────────────────────
# 4. STREAMLIT UI PANEL
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
    with st.expander("🎥 Free AI Video Generator", expanded=True):

        groq_key = (groq_key or os.getenv("GROQ_API_KEY", "")).strip()

        st.markdown(
            "<span style='font-size:10px; font-family:monospace; background:rgba(34,197,94,0.15); color:#4ade80; border:1px solid rgba(34,197,94,0.3); padding:3px 8px; border-radius:3px;'>"
            "✔ HF INFERENCE API ENGINE READY</span>",
            unsafe_allow_html=True,
        )

        vid_mode = st.radio(
            "Select Generator Engine:",
            options=[
                "⚡ Hugging Face Inference API Video (Direct Text-to-Video)",
                "🎬 Narrated Scene Video (Groq + Pollinations + TTS)",
            ],
            index=0,
            key="vid_mode_radio",
        )

        vid_topic = st.text_input(
            "Video Topic / Prompt:",
            placeholder="e.g., A cinematic animation of DNA double helix replicating, 8k",
            key="vid_topic_input",
        )

        if "Hugging Face" in vid_mode:
            st.caption("Executes text-to-video via Hugging Face managed serverless inference.")
            hf_token = st.text_input("Hugging Face Access Token (Required):", type="password", key="hf_token_input")

            if st.button("🚀 GENERATE CLOUD VIDEO", use_container_width=True, key="vid_gen_hf"):
                if not vid_topic.strip():
                    st.warning("Please enter a video prompt first.")
                    return
                if not hf_token.strip() and not os.getenv("HF_TOKEN"):
                    st.warning("Please provide a Hugging Face Token.")
                    return

                with st.spinner("⚡ Rendering video via HF Cloud Inference... (takes ~30-60 seconds)"):
                    vid_path, status_msg = generate_hf_cloud_video(vid_topic, hf_token=hf_token)
                    if vid_path and os.path.exists(vid_path):
                        st.success(f"✅ Video generated! ({status_msg})")
                        st.video(vid_path)
                        with open(vid_path, "rb") as vf:
                            st.download_button(
                                "📥 DOWNLOAD MP4",
                                vf,
                                file_name="apollo_hf_inference_video.mp4",
                                mime="video/mp4",
                                use_container_width=True,
                            )
                    else:
                        st.error(status_msg)

        else:
            vid_instructions = st.text_area(
                "Focus Points (optional):",
                placeholder="e.g., Focus on pH scale and lab experiments",
                key="vid_instructions_input",
                height=65,
            )

            voice_options = {
                "Aria (US Female)": "en-US-AriaNeural",
                "Guy (US Male)": "en-US-GuyNeural",
                "Jenny (US Female)": "en-US-JennyNeural",
            }
            chosen_voice = voice_options[st.selectbox("Voice:", list(voice_options.keys()), key="vid_voice_select")]

            if st.button("🎬 GENERATE NARRATED VIDEO", use_container_width=True, key="vid_gen_narrated"):
                if not vid_topic.strip():
                    st.warning("Please enter a topic first.")
                    return

                rag_context = ""
                if vector_db is not None and embedder is not None:
                    try:
                        nodes = vector_db.as_retriever(search_kwargs={"k": 3}).invoke(vid_topic)
                        rag_context = "\n\n".join(n.page_content for n in nodes)
                    except Exception:
                        pass

                with st.status("🎬 Assembling narrated video...", expanded=True) as status_box:
                    script, err = generate_video_script_groq(
                        topic=vid_topic,
                        instructions=vid_instructions,
                        context=rag_context,
                        groq_key=groq_key,
                        user_prefs=user_prefs,
                    )
                    if not script:
                        status_box.update(label="❌ Script Generation Failed", state="error")
                        st.error(err)
                        return

                    images = [_fetch_image_for_scene(s.get("image_keyword", vid_topic)) for s in script["scenes"]]
                    durations = [int(s.get("duration", 5)) for s in script["scenes"]]

                    if run_tts_synthesis is None:
                        st.error("`voice_handler.py` module is missing.")
                        return

                    audio_bytes = run_tts_synthesis(script["narrative_script"], voice=chosen_voice)
                    mp4_path = assemble_video_moviepy(
                        [img for img in images if img],
                        [d for img, d in zip(images, durations) if img],
                        audio_bytes,
                    )
                    status_box.update(label="✅ Complete!", state="complete", expanded=False)

                if mp4_path:
                    st.video(mp4_path)
                    with open(mp4_path, "rb") as vf:
                        st.download_button(
                            "📥 DOWNLOAD MP4",
                            vf,
                            file_name=f"{vid_topic[:15]}.mp4",
                            mime="video/mp4",
                            use_container_width=True,
                        )
