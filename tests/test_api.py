"""Integration tests: real FastAPI app + real SQL against the dedicated test DB."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from app.settings import get_settings


def _tariff_id(client, title: str) -> int:
    resp = client.get("/tariffs")
    assert resp.status_code == 200
    for tariff in resp.json():
        if tariff["title"] == title:
            return tariff["id"]
    raise AssertionError(f"tariff '{title}' not seeded")


def _sign(body: bytes) -> str:
    secret = get_settings().webhook_secret.encode()
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def _create_payment(client, tariff_id: int, **fields):
    idem = fields.pop("idempotency_key", None)
    payload = {"tariff_id": tariff_id, "email": "buyer@example.com", "method": "card", **fields}
    headers = {"Idempotency-Key": idem} if idem is not None else {}
    return client.post("/payments", json=payload, headers=headers)


def _webhook(client, payment_id, status: str, signature: str | None = None):
    body = json.dumps({"payment_id": str(payment_id), "status": status}).encode()
    sig = signature if signature is not None else _sign(body)
    return client.post(
        "/webhooks/bank",
        content=body,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )


def test_create_card_payment_no_promo(client):
    tid = _tariff_id(client, "standard")
    resp = _create_payment(client, tid)
    assert resp.status_code == 201
    body = resp.json()
    assert body["amount"] == 1_990_000
    assert body["discount"] == 0
    assert body["schedule"] is None
    assert body["installment_months"] is None
    assert body["status"] == "pending"


def test_create_payment_with_promo_lowercase(client):
    tid = _tariff_id(client, "standard")
    resp = _create_payment(client, tid, promo_code="kvitto10")
    assert resp.status_code == 201
    body = resp.json()
    assert body["discount"] == 199_000
    assert body["amount"] == 1_791_000


def test_installment_schedule_sums_to_amount(client):
    tid = _tariff_id(client, "standard")
    for n in (3, 6, 12):
        resp = _create_payment(client, tid, method="installment", installment_months=n)
        assert resp.status_code == 201
        schedule = resp.json()["schedule"]
        assert len(schedule) == n
        assert sum(schedule) == 1_990_000


def test_idempotency_new_then_repeat(client):
    tid = _tariff_id(client, "standard")
    key = str(uuid.uuid4())
    first = _create_payment(client, tid, idempotency_key=key)
    assert first.status_code == 201
    payment_id = first.json()["id"]

    second = _create_payment(client, tid, idempotency_key=key)
    assert second.status_code == 200
    assert second.json()["id"] == payment_id

    listing = client.get("/payments", params={"email": "buyer@example.com"}).json()
    matches = [p for p in listing if p["id"] == payment_id]
    assert len(matches) == 1


def test_webhook_valid_transition(client):
    tid = _tariff_id(client, "standard")
    payment_id = _create_payment(client, tid).json()["id"]
    resp = _webhook(client, payment_id, "succeeded")
    assert resp.status_code == 200
    assert resp.json() == {"result": "ok"}
    assert client.get(f"/payments/{payment_id}").json()["status"] == "succeeded"


def test_webhook_forbidden_transition_unchanged(client):
    tid = _tariff_id(client, "standard")
    payment_id = _create_payment(client, tid).json()["id"]
    resp = _webhook(client, payment_id, "refunded")
    assert resp.status_code == 409
    assert resp.json() == {"error": "invalid_transition"}
    assert client.get(f"/payments/{payment_id}").json()["status"] == "pending"


def test_get_payment_missing_404(client):
    resp = client.get(f"/payments/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_webhook_bad_signature_401(client):
    tid = _tariff_id(client, "standard")
    payment_id = _create_payment(client, tid).json()["id"]
    resp = _webhook(client, payment_id, "succeeded", signature="0" * 64)
    assert resp.status_code == 401
    assert client.get(f"/payments/{payment_id}").json()["status"] == "pending"
