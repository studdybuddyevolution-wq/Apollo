"""Apollo authentication endpoints."""

from __future__ import annotations

import weakref
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from auth import authenticate_user, create_access_token, create_user, public_user
from storage import STORE

_REGISTERED: weakref.WeakSet[FastAPI] = weakref.WeakSet()


def _client_ip(request: Request) -> str:
    cf = (request.headers.get("cf-connecting-ip") or "").strip()
    if cf:
        return cf
    return (request.client.host if request.client else "unknown") or "unknown"


def _record_auth_attempt(ip: str, email: str, kind: str, ok: bool) -> None:
    if not STORE:
        return
    with STORE._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO apollo_auth_attempts(ip,email,kind,ok,at) VALUES(%s,%s,%s,%s,%s)",
                (ip, email[:254], kind, ok, datetime.now(UTC)),
            )


def _check_login_rate(ip: str, email: str) -> None:
    if not STORE:
        return
    from datetime import timedelta
    since = datetime.now(UTC) - timedelta(minutes=10)
    with STORE._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM apollo_auth_attempts
                   WHERE at >= %s AND kind='login' AND ok=false
                     AND (ip=%s OR email=%s)""",
                (since, ip, email[:254].lower()),
            )
            failures = int(cur.fetchone()[0] or 0)
    if failures >= 8:
        raise HTTPException(status_code=429, detail="Too many failed login attempts. Try again later.", headers={"Retry-After": "600"})

def _check_register_rate(ip: str) -> None:
    if not STORE:
        return
    from datetime import timedelta
    since = datetime.now(UTC) - timedelta(minutes=10)
    with STORE._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM apollo_auth_attempts
                   WHERE at >= %s AND kind='register' AND ip=%s""",
                (since, ip),
            )
            attempts = int(cur.fetchone()[0] or 0)
    if attempts >= 5:
        raise HTTPException(
            status_code=429,
            detail="Too many account creation attempts. Try again later.",
            headers={"Retry-After": "600"},
        )


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=256)


class JsonLoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=256)


def _login(request: Request, email: str, password: str) -> dict:
    normalized = email.strip().lower()
    ip = _client_ip(request)
    _check_login_rate(ip, normalized)
    user = authenticate_user(normalized, password)
    _record_auth_attempt(ip, normalized, "login", bool(user))
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password.", headers={"WWW-Authenticate": "Bearer"})
    token = create_access_token(str(user["id"]))
    return {"access_token": token, "token_type": "bearer", "user": public_user(user)}


def register(app: FastAPI) -> None:
    if app in _REGISTERED:
        return

    @app.post("/api/auth/register")
    def auth_register(request: RegisterRequest, http_request: Request):
        ip = _client_ip(http_request)
        _check_register_rate(ip)
        try:
            user = create_user(request.email, request.password)
            _record_auth_attempt(ip, request.email, "register", True)
            return {"access_token": create_access_token(str(user["id"])), "token_type": "bearer", "user": public_user(user)}
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/auth/login")
    def auth_login(request: JsonLoginRequest, http_request: Request):
        return _login(http_request, request.email, request.password)

    @app.post("/api/auth/token")
    def auth_token(http_request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
        return _login(http_request, form_data.username, form_data.password)

    @app.get("/api/auth/me")
    def auth_me(http_request: Request):
        from auth import get_current_user
        authorization = http_request.headers.get("authorization", "")
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Authentication required.", headers={"WWW-Authenticate": "Bearer"})
        user = get_current_user(authorization[7:].strip())
        return {"user": public_user(user)}

    _REGISTERED.add(app)