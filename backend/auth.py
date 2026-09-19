"""Apollo authentication primitives adapted from the official FastAPI template.

The implementation keeps JWT verification and password hashing in one small module
so routes can depend on a validated user instead of trusting a client-supplied user_id.
Legacy user_id values remain supported by explicit migration helpers.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from storage import STORE

password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


def _secret() -> str:
    value = os.getenv("APOLLO_AUTH_SECRET", "").strip()
    if len(value) < 32:
        raise HTTPException(status_code=503, detail="Authentication is not configured on this Apollo deployment.")
    return value


def normalize_email(email: str) -> str:
    value = email.strip().lower()
    if "@" not in value or len(value) > 254:
        raise ValueError("A valid email address is required.")
    return value


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    minutes = expires_minutes or int(os.getenv("APOLLO_AUTH_TOKEN_MINUTES", "120"))
    expire = datetime.now(UTC) + timedelta(minutes=max(5, minutes))
    payload = {"exp": expire, "sub": str(subject), "typ": "access"}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
        subject = str(payload.get("sub") or "").strip()
        if not subject:
            raise ValueError("Missing token subject")
        return subject
    except (InvalidTokenError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_password_hash(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> tuple[bool, str | None]:
    return password_hash.verify_and_update(plain_password, hashed_password)


def _require_store():
    if not STORE:
        raise HTTPException(status_code=503, detail="Persistent authentication requires DATABASE_URL.")
    return STORE


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    store = _require_store()
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id,email,password_hash,is_active,is_superuser,stripe_customer_id,
                          subscription_status,subscription_updated_at,created,updated
                   FROM apollo_users WHERE id=%s""",
                (user_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    keys = (
        "id", "email", "password_hash", "is_active", "is_superuser",
        "stripe_customer_id", "subscription_status", "subscription_updated_at",
        "created", "updated",
    )
    return dict(zip(keys, row))


def get_user_by_email(email: str) -> dict[str, Any] | None:
    store = _require_store()
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id,email,password_hash,is_active,is_superuser,stripe_customer_id,
                          subscription_status,subscription_updated_at,created,updated
                   FROM apollo_users WHERE email=%s""",
                (normalize_email(email),),
            )
            row = cur.fetchone()
    if not row:
        return None
    keys = (
        "id", "email", "password_hash", "is_active", "is_superuser",
        "stripe_customer_id", "subscription_status", "subscription_updated_at",
        "created", "updated",
    )
    return dict(zip(keys, row))


def create_user(email: str, password: str) -> dict[str, Any]:
    store = _require_store()
    clean_email = normalize_email(email)
    hashed = get_password_hash(password)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    record = {
        "id": "usr_" + uuid.uuid4().hex[:16],
        "email": clean_email,
        "password_hash": hashed,
        "is_active": True,
        "is_superuser": False,
        "stripe_customer_id": None,
        "subscription_status": None,
        "subscription_updated_at": None,
        "created": now,
        "updated": now,
    }
    try:
        with store._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO apollo_users
                       (id,email,password_hash,is_active,is_superuser,created,updated)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)
                       RETURNING id,email,is_active,is_superuser,created,updated""",
                    (
                        record["id"], record["email"], record["password_hash"],
                        True, False, now, now,
                    ),
                )
                row = cur.fetchone()
        return dict(zip(("id", "email", "is_active", "is_superuser", "created", "updated"), row))
    except Exception as exc:
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            raise ValueError("An account with that email already exists.") from exc
        raise


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    user = get_user_by_email(email)
    if not user or not user.get("is_active"):
        return None
    valid, updated_hash = verify_password(password, str(user["password_hash"]))
    if not valid:
        return None
    if updated_hash:
        store = _require_store()
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with store._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE apollo_users SET password_hash=%s,updated=%s WHERE id=%s",
                    (updated_hash, now, user["id"]),
                )
    return user


def current_user_from_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    user_id = decode_access_token(token)
    user = get_user_by_id(user_id)
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="User account is inactive or no longer exists.")
    return user


def get_optional_user(token: str | None = Depends(oauth2_scheme)) -> dict[str, Any] | None:
    return current_user_from_token(token)


def get_current_user(token: str | None = Depends(oauth2_scheme)) -> dict[str, Any]:
    user = current_user_from_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def request_user_id(
    token: str | None,
    legacy_user_id: str | None,
    *,
    allow_legacy: bool = True,
) -> str:
    """Prefer verified JWT identity; fall back to legacy user_id during migration."""
    user = current_user_from_token(token) if token else None
    if user:
        return str(user["id"])
    if allow_legacy and legacy_user_id:
        return legacy_user_id.strip() or "default"
    if allow_legacy and os.getenv("APOLLO_LEGACY_USER_ID", "true").lower() == "true":
        return "default"
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "is_active": bool(user["is_active"]),
        "is_superuser": bool(user["is_superuser"]),
        "subscription_status": user.get("subscription_status"),
    }
