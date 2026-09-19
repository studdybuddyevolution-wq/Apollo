"""Planner API for Apollo's Progress Dashboard and Study Planner."""

from __future__ import annotations

import weakref

from fastapi import FastAPI, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field

from auth import request_user_id
from planner_service import (
    create_course,
    create_topic,
    dashboard,
    get_fall_behind,
    list_courses,
    list_topics,
    set_daily_hours,
    set_topic_status,
)

oauth2_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)
_REGISTERED: weakref.WeakSet[FastAPI] = weakref.WeakSet()


class CourseCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    title: str = Field(min_length=1, max_length=160)
    deadline_at: str | None = None
    priority: int = Field(default=3, ge=1, le=5)
    user_id: str | None = None


class TopicCreateRequest(BaseModel):
    course_id: str
    title: str = Field(min_length=1, max_length=240)
    estimated_hours: float = Field(default=1.0, ge=0.1, le=40)
    lecture_at: str | None = None
    user_id: str | None = None


class TopicStatusRequest(BaseModel):
    status: str
    user_id: str | None = None


class PlannerPreferencesRequest(BaseModel):
    daily_hours: float = Field(ge=0.25, le=16)
    user_id: str | None = None


def _resolve_user(http_request: Request, legacy_user_id: str | None) -> str:
    authorization = http_request.headers.get("authorization", "")
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else None
    return request_user_id(token, legacy_user_id, allow_legacy=True)


def register(app: FastAPI) -> None:
    if app in _REGISTERED:
        return

    @app.get("/api/planner/dashboard")
    def planner_dashboard(http_request: Request, user_id: str | None = None):
        return dashboard(_resolve_user(http_request, user_id))

    @app.get("/api/planner/fall-behind")
    def planner_fall_behind(http_request: Request, user_id: str | None = None):
        return {"fall_behind": get_fall_behind(_resolve_user(http_request, user_id))}

    @app.get("/api/planner/courses")
    def planner_courses(http_request: Request, user_id: str | None = None):
        return {"courses": list_courses(_resolve_user(http_request, user_id))}

    @app.post("/api/planner/courses")
    def planner_course_create(http_request: Request, request: CourseCreateRequest):
        try:
            return create_course(
                _resolve_user(http_request, request.user_id),
                code=request.code,
                title=request.title,
                deadline_at=request.deadline_at,
                priority=request.priority,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/planner/topics")
    def planner_topics(http_request: Request, course_id: str | None = None, user_id: str | None = None):
        return {"topics": list_topics(_resolve_user(http_request, user_id), course_id=course_id)}

    @app.post("/api/planner/topics")
    def planner_topic_create(http_request: Request, request: TopicCreateRequest):
        try:
            return create_topic(
                _resolve_user(http_request, request.user_id),
                course_id=request.course_id,
                title=request.title,
                estimated_hours=request.estimated_hours,
                lecture_at=request.lecture_at,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.patch("/api/planner/topics/{topic_id}")
    def planner_topic_status(http_request: Request, topic_id: str, request: TopicStatusRequest):
        try:
            return set_topic_status(_resolve_user(http_request, request.user_id), topic_id, request.status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.put("/api/planner/preferences")
    def planner_preferences(http_request: Request, request: PlannerPreferencesRequest):
        try:
            return set_daily_hours(_resolve_user(http_request, request.user_id), request.daily_hours)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    _REGISTERED.add(app)
