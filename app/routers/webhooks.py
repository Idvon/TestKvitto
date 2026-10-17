"""Bank webhook endpoint with HMAC-SHA256 signature verification."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.payments import TransitionResult, apply_webhook_status
from app.status import PaymentStatus

router = APIRouter()


def _webhook_secret() -> bytes:
    return os.getenv("WEBHOOK_SECRET", "").encode()


def verify_signature(body: bytes, signature: str | None) -> bool:
    """Constant-time check of ``X-Signature`` = HMAC-SHA256(raw body, secret)."""
    if signature is None:
        return False
    expected = hmac.new(_webhook_secret(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhooks/bank")
async def bank_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    if not verify_signature(body, request.headers.get("X-Signature")):
        return JSONResponse(status_code=401, content={"error": "invalid_signature"})

    try:
        payload = json.loads(body)
        payment_id = uuid.UUID(str(payload["payment_id"]))
        new_status = PaymentStatus(payload["status"])
    except (KeyError, ValueError, TypeError):
        return JSONResponse(status_code=422, content={"error": "invalid_payload"})

    result = apply_webhook_status(db, payment_id, new_status)
    if result is TransitionResult.NOT_FOUND:
        return JSONResponse(status_code=404, content={"error": "not_found"})
    if result is TransitionResult.INVALID:
        return JSONResponse(status_code=409, content={"error": "invalid_transition"})
    return JSONResponse(status_code=200, content={"result": "ok"})
