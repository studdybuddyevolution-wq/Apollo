"""FastAPI helpers for Apollo Socratic mastery and Quick Checks.

Core Socratic conversation turns remain on the existing workspace chat route.
These endpoints cover explicit Quick Check interactions and mastery inspection.
Placement generation is intentionally deferred until the core loop is stable.
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from main import _check_rate_limit
from rag_service import get_notebook
from socratic_engine import (
    get_mastery,
    generate_quick_check,
    grade_quick_check,
    list_mastery,
    source_context,
    tier_for_score,
    upsert_mastery,
)
from workspace_service import get_socratic_state, save_socratic_state


class SocraticQuickCheckRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=240)
    tier: str = Field(min_length=1, max_length=40)
    score: float = Field(ge=0, le=100)
    notebook_id: str | None = None
    active_sources: list[str] = Field(default_factory=list, max_length=40)
    source_modes: dict[str, str] = Field(default_factory=dict, max_length=40)
    user_id: str | None = None
    model: str | None = None


class SocraticGradeRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=240)
    question: str = Field(min_length=1, max_length=2000)
    expected_answer: str = Field(min_length=1, max_length=4000)
    student_answer: str = Field(min_length=1, max_length=4000)
    current_score: float = Field(ge=0, le=100)
    notebook_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    model: str | None = None


_REGISTERED_APPS: set[int] = set()


def _rate_limit(request: Request, user_id: str | None) -> None:
    key = user_id or (request.client.host if request.client else "anonymous")
    allowed, retry_after = _check_rate_limit(key)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )


def register(app: FastAPI) -> None:
    marker = id(app)
    if marker in _REGISTERED_APPS:
        return

    @app.get("/api/socratic/mastery")
    def mastery(user_id: str = "default"):
        return {"mastery": list_mastery(user_id)}

    @app.get("/api/socratic/mastery/{topic:path}")
    def mastery_topic(topic: str, user_id: str = "default"):
        record = get_mastery(user_id, topic)
        if record is None:
            raise HTTPException(status_code=404, detail="No mastery record for this topic")
        return {"mastery": record, "tier": tier_for_score(record["score"])}

    @app.post("/api/socratic/quick-check")
    async def quick_check(request: SocraticQuickCheckRequest, http_request: Request):
        _rate_limit(http_request, request.user_id)
        if request.notebook_id and get_notebook(request.user_id, request.notebook_id) is None:
            raise HTTPException(status_code=404, detail="Notebook not found")
        try:
            context = await asyncio.to_thread(
                source_context,
                request.user_id,
                request.notebook_id,
                request.active_sources,
                request.topic,
                request.source_modes,
                top_k=4,
                token_budget=3000,
            )
            question, model = await asyncio.to_thread(
                generate_quick_check,
                request.topic,
                request.tier,
                context,
                preferred_model=request.model,
            )
            return {"question": question, "model_used": model}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Apollo could not prepare the quick check. Please try again.") from exc

    @app.post("/api/socratic/quick-check/grade")
    async def quick_check_grade(request: SocraticGradeRequest, http_request: Request):
        _rate_limit(http_request, request.user_id)
        try:
            correct, feedback, model = await asyncio.to_thread(
                grade_quick_check,
                request.question,
                request.expected_answer,
                request.student_answer,
                preferred_model=request.model,
            )
            if correct is True:
                delta = 8 if tier_for_score(request.current_score) in {"Beginner", "Developing"} else 6
                new_score = min(100.0, request.current_score + delta)
                correct_delta = 1
                verdict = f"Correct! Mastery +{delta}"
            elif correct is False:
                delta = -6
                new_score = max(0.0, request.current_score + delta)
                correct_delta = 0
                verdict = f"Not quite. Mastery {delta}"
            else:
                new_score = request.current_score
                correct_delta = 0
                verdict = "Could not confidently grade that response; mastery unchanged."

            record = upsert_mastery(
                request.user_id,
                request.topic,
                new_score,
                correct_delta=correct_delta,
                attempt_delta=1,
            )

            if request.notebook_id and request.session_id:
                persisted = get_socratic_state(request.user_id, request.notebook_id, request.session_id)
                if persisted is not None:
                    persisted = dict(persisted)
                    persisted["mastery_score"] = record["score"]
                    persisted["mastery_tier"] = record["tier"]
                    save_socratic_state(request.user_id, request.notebook_id, request.session_id, persisted)

            return {
                "correct": correct,
                "feedback": feedback,
                "verdict": verdict,
                "mastery": record,
                "score": record["score"],
                "tier": record["tier"],
                "model_used": model,
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Apollo could not grade that response. Please try again.") from exc

    @app.get("/api/socratic/config")
    def config():
        from phase3_common import gemini_model_chain
        from socratic_engine import _TIERS, MAIEUTICS_MAX_CONSECUTIVE

        return {
            "models": gemini_model_chain(max_models=8),
            "maieutics_max_consecutive": MAIEUTICS_MAX_CONSECUTIVE,
            "tiers": [{"name": name, "min": lo, "max": hi - 1, "style": note} for lo, hi, name, note in _TIERS],
        }

    _REGISTERED_APPS.add(marker)
