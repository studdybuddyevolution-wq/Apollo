import json

import requests
from groq import Groq

from ppt_engine import (
    FORBIDDEN_METADATA_TERMS,
    enforce_topic_isolation,
    normalize_slides,
    parse_slide_json_response,
)


MODEL_OPTIONS = {
    "Qwen 3.6 27B (Groq free tier)": {
        "provider": "groq",
        "model_id": "qwen/qwen3.6-27b",
        "desc": "Qwen served through Groq's free developer tier.",
    },
    "Meta Llama 3.3 70B (Groq free tier)": {
        "provider": "groq",
        "model_id": "llama-3.3-70b-versatile",
        "desc": "Large Groq-hosted chat model for general study responses.",
    },
    "Gemma Free (OpenRouter)": {
        "provider": "openrouter",
        "model_id": "google/gemma-3-27b-it:free",
        "desc": "Free OpenRouter model endpoint for fallback chat.",
    },
}


def slide_system_prompt(topic: str) -> str:
    forbidden = [
        term
        for term in FORBIDDEN_METADATA_TERMS
        if term.lower() not in topic.lower()
    ]
    forbidden_text = ", ".join(forbidden) if forbidden else "none"
    return f"""
You are a commercial presentation strategist and strict JSON generator.
Create audience-facing slide content only about the user's requested topic.
Never use hidden context, previous chat history, product names, school names, app names, or implementation details.
Forbidden application metadata for this request: {forbidden_text}.
Do not mention any forbidden term anywhere in titles, body copy, image keywords, chart labels, or speaker notes.
Do not expose chain-of-thought, planning notes, prompt instructions, model names, JSON caveats, or source metadata.
Return valid JSON only. No markdown fences. No trailing commas.
""".strip()


def slide_schema_prompt(topic: str) -> str:
    return f"""
Create a Gamma AI-style widescreen presentation about: "{topic}".

Return a JSON object with a "slides" array containing 5-7 slide objects.
Every slide must include:
- title: concise slide title
- subtitle: optional one-sentence context
- topic_tag: short topic label
- image_keyword: 3-7 word visual prompt for free image generation
- cards: 2, 3, or 4 objects with "heading" and "body"
- speaker_notes: 45-90 words of presenter notes

Add chart data to 1-2 slides when useful:
"chart": {{
  "title": "Chart title",
  "categories": ["Category A", "Category B", "Category C"],
  "series": [{{"name": "Value", "values": [25, 40, 55]}}]
}}

Use exactly 3 cards when a feature-grid slide makes sense and exactly 4 cards when a 2x2 comparison makes sense.
Return only JSON in this shape:
{{
  "slides": [
    {{
      "title": "Slide Title",
      "subtitle": "Short context sentence.",
      "topic_tag": "Topic",
      "image_keyword": "specific visual keyword",
      "cards": [
        {{"heading": "Card heading", "body": "Tight audience-facing body copy."}}
      ],
      "speaker_notes": "Presenter notes for this slide."
    }}
  ]
}}
""".strip()


def generate_slides_with_qwen(topic: str, groq_key: str = ""):
    groq_key = groq_key.strip() if groq_key else ""
    if not groq_key or not groq_key.startswith("gsk_"):
        return None, "Missing active GROQ_API_KEY starting with 'gsk_' in Streamlit Secrets."

    messages = [
        {"role": "system", "content": slide_system_prompt(topic)},
        {"role": "user", "content": slide_schema_prompt(topic)},
    ]

    try:
        client = Groq(api_key=groq_key)
        try:
            completion = client.chat.completions.create(
                model="qwen/qwen3.6-27b",
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.25,
                max_tokens=4096,
            )
        except Exception:
            completion = client.chat.completions.create(
                model="qwen/qwen3.6-27b",
                messages=messages,
                temperature=0.25,
                max_tokens=4096,
            )

        raw_text = completion.choices[0].message.content
        parsed_slides = parse_slide_json_response(raw_text)
        parsed_slides = enforce_topic_isolation(parsed_slides, topic)
        parsed_slides = normalize_slides(parsed_slides, topic=topic)
        if parsed_slides:
            return parsed_slides, "Success (Qwen via Groq free tier)"
        snippet = (raw_text or "Empty")[:180].replace("\n", " ")
        return None, f"Could not parse Qwen response into slides. Output start: {snippet}"
    except Exception as exc:
        return None, f"Qwen generation error: {exc}"


def get_best_active_gemini_model(gemini_key: str) -> str:
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key.strip()}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            valid_models = []
            for model in response.json().get("models", []):
                methods = model.get("supportedGenerationMethods", [])
                clean_name = model.get("name", "").replace("models/", "")
                if "generateContent" in methods and "vision" not in clean_name.lower():
                    valid_models.append(clean_name)
            for model_name in valid_models:
                if "flash" in model_name.lower():
                    return model_name
            if valid_models:
                return valid_models[0]
    except Exception:
        pass
    return "gemini-2.0-flash"


def generate_slides_with_gemini(topic: str, gemini_key: str = ""):
    gemini_key = gemini_key.strip() if gemini_key else ""
    if not gemini_key:
        return None, "Missing GEMINI_API_KEY in Streamlit Secrets."

    active_model = get_best_active_gemini_model(gemini_key)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{active_model}:generateContent?key={gemini_key}"
    payload = {
        "systemInstruction": {"parts": [{"text": slide_system_prompt(topic)}]},
        "contents": [{"role": "user", "parts": [{"text": slide_schema_prompt(topic)}]}],
        "generationConfig": {
            "temperature": 0.35,
            "responseMimeType": "application/json",
        },
    }

    try:
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=35,
        )
        if response.status_code != 200:
            return None, f"Gemini API error ({response.status_code}): {response.text}"
        data = response.json()
        text_output = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed_slides = parse_slide_json_response(text_output)
        parsed_slides = enforce_topic_isolation(parsed_slides, topic)
        parsed_slides = normalize_slides(parsed_slides, topic=topic)
        if parsed_slides:
            return parsed_slides, f"Success ({active_model})"
        return None, "Gemini returned JSON, but no slide array was found."
    except Exception as exc:
        return None, f"Gemini generation error: {exc}"


def generate_llm_stream(messages, groq_key: str, openrouter_key: str, selected_model_name: str):
    model_cfg = MODEL_OPTIONS.get(selected_model_name, {})
    provider = model_cfg.get("provider", "groq")
    model_id = model_cfg.get("model_id", "")

    if provider == "groq":
        if not groq_key or not groq_key.startswith("gsk_"):
            yield "Missing configuration: set a valid GROQ_API_KEY starting with 'gsk_'."
            return
        try:
            client = Groq(api_key=groq_key.strip())
            stream = client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=0.3,
                max_tokens=1024,
                stream=True,
            )
            for chunk in stream:
                token_text = chunk.choices[0].delta.content or ""
                if token_text:
                    yield token_text
        except Exception as exc:
            yield f"Groq SDK failure: {exc}"
        return

    if not openrouter_key or not openrouter_key.startswith("sk-or-"):
        yield "Missing configuration: set a valid OPENROUTER_API_KEY starting with 'sk-or-'."
        return

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openrouter_key.strip()}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8501",
                "X-Title": "APOLLO OMNI AI",
            },
            json={
                "model": model_id,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 1024,
                "stream": True,
            },
            stream=True,
            timeout=30,
        )
        if response.status_code != 200:
            yield f"OpenRouter API error ({response.status_code}): {response.text}"
            return
        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8").strip()
            if not decoded.startswith("data: "):
                continue
            data_str = decoded[6:]
            if data_str == "[DONE]":
                break
            try:
                token_text = (
                    json.loads(data_str)
                    .get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content", "")
                )
                if token_text:
                    yield token_text
            except Exception:
                continue
    except Exception as exc:
        yield f"OpenRouter network failure: {exc}"
