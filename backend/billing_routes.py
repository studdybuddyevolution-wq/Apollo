"""Stripe billing and webhook synchronization for Apollo."""

from __future__ import annotations

import os
import time
import weakref
from typing import Any

import stripe
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from auth import get_current_user
from storage import STORE

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
_REGISTERED: weakref.WeakSet[FastAPI] = weakref.WeakSet()


class CheckoutRequest(BaseModel):
    price_id: str = Field(min_length=1, max_length=200)
    success_url: str = Field(default="https://apollo.studdybuddyevolution.workers.dev/?billing=success", max_length=2000)
    cancel_url: str = Field(default="https://apollo.studdybuddyevolution.workers.dev/?billing=cancelled", max_length=2000)


def _require_billing() -> None:
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe billing is not configured.")
    if not STORE:
        raise HTTPException(status_code=503, detail="Stripe billing requires DATABASE_URL.")


def _persist_customer(user_id: str, customer_id: str) -> None:
    with STORE._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE apollo_users SET stripe_customer_id=%s,updated=NOW()::text WHERE id=%s",
                (customer_id, user_id),
            )


def _customer_for_user(user: dict[str, Any]) -> str:
    customer_id = user.get("stripe_customer_id")
    if customer_id:
        return str(customer_id)
    customer = stripe.Customer.create(email=user["email"], metadata={"apollo_user_id": user["id"]})
    _persist_customer(str(user["id"]), str(customer.id))
    return str(customer.id)


def _sync_subscription_from_stripe(user_id: str, subscription: Any) -> None:
    status = str(subscription.get("status") or "unknown")
    updated = int(subscription.get("created") or time.time())
    customer_id = str(subscription.get("customer") or "")
    with STORE._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE apollo_users
                   SET stripe_customer_id=COALESCE(%s,stripe_customer_id),
                       subscription_status=%s,
                       subscription_updated_at=%s,
                       updated=NOW()::text
                   WHERE id=%s""",
                (customer_id or None, status, updated, user_id),
            )


def _user_for_customer(customer_id: str) -> dict[str, Any] | None:
    with STORE._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id,email,password_hash,is_active,is_superuser,stripe_customer_id,subscription_status,subscription_updated_at,created,updated FROM apollo_users WHERE stripe_customer_id=%s",
                (customer_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    keys = ("id","email","password_hash","is_active","is_superuser","stripe_customer_id","subscription_status","subscription_updated_at","created","updated")
    return dict(zip(keys, row))


def _claim_event(event: Any) -> bool:
    """Claim a webhook exactly once, but allow Stripe retries after failed/interrupted work."""
    event_id = str(event["id"])
    event_type = str(event["type"])
    created = int(event.get("created") or 0)
    with STORE._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO apollo_stripe_webhook_events(event_id,event_type,stripe_created,status)
                   VALUES(%s,%s,%s,'received')
                   ON CONFLICT(event_id) DO NOTHING
                   RETURNING event_id""",
                (event_id, event_type, created),
            )
            if cur.fetchone() is not None:
                return True
            cur.execute(
                """SELECT status FROM apollo_stripe_webhook_events
                   WHERE event_id=%s
                   FOR UPDATE""",
                (event_id,),
            )
            row = cur.fetchone()
            if not row:
                return True
            status = str(row[0] or "")
            if status == "processed":
                return False
            cur.execute(
                """UPDATE apollo_stripe_webhook_events
                   SET status='received', error_message=NULL, processed_at=NULL
                   WHERE event_id=%s""",
                (event_id,),
            )
            return True


def _finish_event(event_id: str, *, status: str, error: str | None = None) -> None:
    with STORE._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE apollo_stripe_webhook_events SET status=%s,error_message=%s,processed_at=NOW() WHERE event_id=%s",
                (status, error, event_id),
            )


def register(app: FastAPI) -> None:
    if app in _REGISTERED:
        return

    @app.post("/api/billing/checkout")
    def billing_checkout(request: CheckoutRequest, http_request: Request):
        authorization = http_request.headers.get("authorization", "")
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Authentication required.", headers={"WWW-Authenticate": "Bearer"})
        token = authorization[7:].strip()
        user = get_current_user(token)
        _require_billing()
        try:
            customer_id = _customer_for_user(user)
            session = stripe.checkout.Session.create(
                mode="subscription",
                customer=customer_id,
                line_items=[{"price": request.price_id, "quantity": 1}],
                success_url=request.success_url,
                cancel_url=request.cancel_url,
                client_reference_id=str(user["id"]),
                metadata={"apollo_user_id": str(user["id"])},
            )
            return {"checkout_url": session.url, "session_id": session.id}
        except stripe.error.StripeError as exc:
            raise HTTPException(status_code=502, detail="Stripe could not create the checkout session.") from exc

    @app.get("/api/billing/me")
    def billing_me(http_request: Request):
        authorization = http_request.headers.get("authorization", "")
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Authentication required.", headers={"WWW-Authenticate": "Bearer"})
        user = get_current_user(authorization[7:].strip())
        return {
            "stripe_customer_id": user.get("stripe_customer_id"),
            "subscription_status": user.get("subscription_status"),
            "subscription_updated_at": user.get("subscription_updated_at"),
        }

    @app.post("/api/billing/webhook")
    async def billing_webhook(http_request: Request):
        _require_billing()
        payload = await http_request.body()
        signature = http_request.headers.get("stripe-signature")
        secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
        if not signature or not secret:
            raise HTTPException(status_code=400, detail="Stripe webhook signature is not configured.")
        try:
            event = stripe.Webhook.construct_event(payload=payload, sig_header=signature, secret=secret)
        except (ValueError, stripe.error.SignatureVerificationError) as exc:
            raise HTTPException(status_code=400, detail="Invalid Stripe webhook.") from exc

        if not _claim_event(event):
            return {"received": True, "duplicate": True}

        event_id = str(event["id"])
        try:
            event_type = str(event["type"])
            obj = event["data"]["object"]
            customer_id = str(obj.get("customer") or "")
            user = _user_for_customer(customer_id) if customer_id else None

            if user and event_type.startswith("customer.subscription"):
                current = stripe.Subscription.retrieve(obj.get("id"))
                _sync_subscription_from_stripe(str(user["id"]), current)

            elif user and event_type == "checkout.session.completed":
                subscription_id = str(obj.get("subscription") or "")
                if subscription_id:
                    current = stripe.Subscription.retrieve(subscription_id)
                    _sync_subscription_from_stripe(str(user["id"]), current)

            _finish_event(event_id, status="processed")
            return {"received": True, "processed": True}
        except Exception as exc:
            _finish_event(event_id, status="failed", error=str(exc)[:1000])
            raise HTTPException(status_code=500, detail="Stripe webhook processing failed; Stripe may retry the event.") from exc

    _REGISTERED.add(app)