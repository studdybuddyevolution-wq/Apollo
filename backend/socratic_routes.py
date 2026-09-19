"""FastAPI routes for Apollo Socratic Study."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from main import _check_rate_limit
from rag_service import get_notebook
from socratic_service import (
    build_socratic_system_prompt,
    generate_placement,
    generate_quick_check,
    get_mastery,
    grade_quick_check,
    list_mastery,
    score_placement,
    tier_for_score,
    upsert_mastery,
    source_context,
)


class SocraticPlacementRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=240)
    notebook_id: str | None = None
    active_sources: list[str] = Field(default_factory=list, max_length=40)
    user_id: str | None = None
    model: str | None = None


class SocraticQuickCheckRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=240)
    tier: str = Field(min_length=1, max_length=40)
    score: float = Field(ge=0, le=100)
    notebook_id: str | None = None
    active_sources: list[str] = Field(default_factory=list, max_length=40)
    user_id: str | None = None
    model: str | None = None


class SocraticGradeRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=240)
    question: str = Field(min_length=1, max_length=2000)
    expected_answer: str = Field(min_length=1, max_length=4000)
    student_answer: str = Field(min_length=1, max_length=4000)
    current_score: float = Field(ge=0, le=100)
    user_id: str | None = None
    model: str | None = None


class SocraticPlacementSubmitRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=240)
    questions: list[dict[str, Any]] = Field(min_length=5, max_length=5)
    answers: dict[str, int] = Field(default_factory=dict)
    user_id: str | None = None


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

    @app.post("/api/socratic/placement")
    async def placement(request: SocraticPlacementRequest, http_request: Request):
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
            )
            questions, model = await asyncio.to_thread(
                generate_placement,
                request.topic,
                context,
                preferred_model=request.model,
            )
            return {"topic": request.topic.strip(), "questions": questions, "model_used": model}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Apollo could not prepare the placement check. Please try again.") from exc

    @app.post("/api/socratic/placement/submit")
    def placement_submit(request: SocraticPlacementSubmitRequest, http_request: Request):
        _rate_limit(http_request, request.user_id)
        try:
            score, correct, total = score_placement(request.questions, request.answers)
            record = upsert_mastery(
                request.user_id,
                request.topic,
                score,
                correct_delta=correct,
                attempt_delta=1,
            )
            return {
                "mastery": record,
                "score": score,
                "correct": correct,
                "total": total,
                "tier": tier_for_score(score),
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
                verdict = f"Correct! Mastery +{delta}"
                correct_delta = 1
            elif correct is False:
                delta = -6
                new_score = max(0.0, request.current_score + delta)
                verdict = f"Not quite. Mastery {delta}"
                correct_delta = 0
            else:
                new_score = request.current_score
                verdict = "Could not confidently grade that response; mastery unchanged."
                correct_delta = 0
            record = upsert_mastery(
                request.user_id,
                request.topic,
                new_score,
                correct_delta=correct_delta,
                attempt_delta=1,
            )
            return {
                "correct": correct,
                "feedback": feedback,
                "verdict": verdict,
                "mastery": record,
                "score": record["score"],
                "tier": tier_for_score(record["score"]),
                "model_used": model,
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Apollo could not grade that response. Please try again.") from exc

    @app.get("/api/socratic/config")
    def config():
        from phase3_common import gemini_model_chain

        return {
            "models": gemini_model_chain(max_models=8),
            "tiers": [{"name": name, "min": lo, "max": hi - 1, "style": note} for lo, hi, name, note in __import__("socratic_service")._Tiers],
        }

    _REGISTERED_APPS.add(marker)
