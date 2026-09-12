"""Runtime patch loaded by Python before Uvicorn imports the Apollo app.

Gemini can sometimes emit useful text and then terminate a streaming request with
503 UNAVAILABLE. The original handler treated any post-output exception as fatal.
This patch replaces that handler so Apollo keeps the partial answer and continues
with the next Gemini model instead of surfacing an error to the user.
"""

from __future__ import annotations

import os
from typing import Any


def _patch() -> None:
    try:
        import main
        from google import genai
        from google.genai import types
    except Exception:
        return

    def resilient(*, prompt: str, system_instruction: str, output_tokens: int, primary_model: str, event_meta: dict[str, Any]):
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        client = genai.Client(api_key=key)
        models = main._gemini_model_chain(primary_model)
        last_error: Exception | None = None

        for index, model in enumerate(models):
            generated = ""
            try:
                stream = client.models.generate_content_stream(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        max_output_tokens=output_tokens,
                        system_instruction=system_instruction,
                    ),
                )
                yield main._event({"type": "start", "model": model, **event_meta})
                for chunk in stream:
                    text = getattr(chunk, "text", None) or ""
                    if text:
                        generated += text
                        yield main._event({"type": "token", "text": text})
                yield main._event({"type": "done", "model": model, **event_meta})
                return
            except Exception as exc:
                last_error = exc
                next_index = index + 1
                if generated and next_index < len(models):
                    next_model = models[next_index]
                    yield main._event({
                        "type": "fallback",
                        "from_model": model,
                        "to_model": next_model,
                        "reason": str(exc),
                        "after_output": True,
                    })
                    continuation_prompt = (
                        f"{prompt}\n\n"
                        "PREVIOUS PARTIAL ANSWER:\n"
                        f"{generated}\n\n"
                        "CONTINUE TASK:\n"
                        "The previous model stopped unexpectedly after producing the partial answer above. "
                        "Continue exactly where it stopped. Do not restart, repeat earlier material, or mention the failure. "
                        "Preserve the same topic, structure, tone, and level of detail. Complete the answer naturally. "
                        "Return only the continuation."
                    )
                    try:
                        continuation = client.models.generate_content_stream(
                            model=next_model,
                            contents=continuation_prompt,
                            config=types.GenerateContentConfig(
                                max_output_tokens=output_tokens,
                                system_instruction=system_instruction,
                            ),
                        )
                        for chunk in continuation:
                            text = getattr(chunk, "text", None) or ""
                            if text:
                                yield main._event({"type": "token", "text": text})
                        yield main._event({
                            "type": "done",
                            "model": next_model,
                            **event_meta,
                            "continued_after_fallback": True,
                        })
                        return
                    except Exception as continuation_exc:
                        last_error = continuation_exc
                        if next_index + 1 < len(models):
                            final_model = models[next_index + 1]
                            yield main._event({
                                "type": "fallback",
                                "from_model": next_model,
                                "to_model": final_model,
                                "reason": str(continuation_exc),
                                "after_output": True,
                            })
                            try:
                                continuation = client.models.generate_content_stream(
                                    model=final_model,
                                    contents=continuation_prompt,
                                    config=types.GenerateContentConfig(
                                        max_output_tokens=output_tokens,
                                        system_instruction=system_instruction,
                                    ),
                                )
                                for chunk in continuation:
                                    text = getattr(chunk, "text", None) or ""
                                    if text:
                                        yield main._event({"type": "token", "text": text})
                                yield main._event({
                                    "type": "done",
                                    "model": final_model,
                                    **event_meta,
                                    "continued_after_fallback": True,
                                })
                                return
                            except Exception as final_exc:
                                last_error = final_exc
                        yield main._event({"type": "done", "model": model, **event_meta, "partial": True})
                        return

                if next_index < len(models):
                    yield main._event({
                        "type": "fallback",
                        "from_model": model,
                        "to_model": models[next_index],
                        "reason": str(exc),
                    })
                    continue
                break

        raise RuntimeError(f"All Gemini synthesis models failed: {last_error}")

    main._stream_gemini_resilient = resilient


_patch()
