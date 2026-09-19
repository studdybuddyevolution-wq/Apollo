from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth
import planner_service
from planner_service import compute_course_risk


def test_compute_course_risk_marks_critical_when_backlog_exceeds_capacity():
    now = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    course = {
        "id": "c1",
        "code": "PHY",
        "title": "Physics",
        "deadline_at": (now + timedelta(days=2)).isoformat(),
        "priority": 3,
    }
    topics = [
        {"id": "t1", "title": "A", "status": "not_started", "estimated_hours": 3.0, "lecture_at": None},
        {"id": "t2", "title": "B", "status": "not_started", "estimated_hours": 3.0, "lecture_at": None},
    ]
    result = compute_course_risk(course=course, topics=topics, daily_hours=2, now=now)
    assert result["severity"] == "critical"
    assert result["required_hours"] == 6
    assert result["available_hours"] == 4


def test_compute_course_risk_uses_upcoming_topic_lecture_as_target():
    now = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
    lecture = (now + timedelta(days=1)).isoformat()
    course = {"id": "c1", "code": "BIO", "title": "Biology", "deadline_at": None, "priority": 3}
    topics = [
        {"id": "t1", "title": "Cells", "status": "not_started", "estimated_hours": 1.5, "lecture_at": lecture},
        {"id": "t2", "title": "DNA", "status": "completed", "estimated_hours": 2.0, "lecture_at": lecture},
    ]
    result = compute_course_risk(course=course, topics=topics, daily_hours=2, now=now)
    assert result["target_at"] == lecture
    assert result["required_hours"] == 1.5
    assert result["severity"] in {"ok", "warn"}


def test_reference_routes_are_registerable():
    import auth_routes
    import billing_routes
    import planner_routes

    app = FastAPI()
    auth_routes.register(app)
    billing_routes.register(app)
    planner_routes.register(app)
    paths = {route.path for route in app.routes}
    assert "/api/auth/register" in paths
    assert "/api/auth/login" in paths
    assert "/api/billing/webhook" in paths
    assert "/api/planner/fall-behind" in paths


def test_auth_password_hash_round_trip():
    hashed = auth.get_password_hash("correct horse battery staple")
    valid, upgraded = auth.verify_password("correct horse battery staple", hashed)
    assert valid
    assert upgraded is None or isinstance(upgraded, str)


def test_auth_token_requires_long_secret(monkeypatch):
    monkeypatch.setenv("APOLLO_AUTH_SECRET", "too-short")
    with pytest.raises(Exception):
        auth.create_access_token("usr_test")
