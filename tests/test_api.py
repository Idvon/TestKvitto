"""Integration tests for the payment API and bank webhook."""
from __future__ import annotations

import hashlib
import hmac
import json

from tests.conftest import TEST_WEBHOOK_SECRET

STANDARD_PRICE = 1_990_000


def _standard_id(client) -> int:
    for t in client.get("/tariffs").json():
        if t["title"] == "standard":
            return t["id"]
    raise AssertionError("standard tariff not found")


def _create(client, tariff_id, method="card", promo=None, key=None,
            email="a@b.c", months=None):
    payload = {"tariff_id": tariff_id, "email": email, "method": method}
    if promo is not None:
        payload["promo_code"] = promo
    if months is not None:
        payload["installment_months"] = months
    headers = {}
    if key is not None:
        headers["Idempotency-Key"] = key
    return client.post("/payments", json=payload, headers=headers)


def _sign(body: bytes, secret: str = TEST_WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _webhook(client, payment_id, status, secret=TEST_WEBHOOK_SECRET,
             signature=None):
    body = json.dumps(
        {"payment_id": str(payment_id), "status": status}
    ).encode()
    sig = signature if signature is not None else _sign(body, secret)
    return client.post(
        "/webhooks/bank",
        content=body,
        headers={"X-Signature": sig, "Content-Type": "application/json"},
    )


# --- tariffs ---------------------------------------------------------

def test_list_tariffs(client):
    r = client.get("/tariffs")
    assert r.status_code == 200
    prices = {t["title"]: t["price"] for t in r.json()}
    assert prices == {"basic": 990_000, "standard": 1_990_000, "premium": 2_990_000}


# --- payment creation ------------------------------------------------

def test_create_card_payment(client):
    tid = _standard_id(client)
    r = _create(client, tid, method="card")
    assert r.status_code == 201
    body = r.json()
    assert body["amount"] == STANDARD_PRICE
    assert body["discount"] == 0
    assert body["schedule"] is None
    assert body["installment_months"] is None
    assert body["status"] == "pending"
    assert body["method"] == "card"
    assert "id" in body and "created_at" in body


def test_create_payment_with_promo(client):
    tid = _standard_id(client)
    r = _create(client, tid, promo="KVITTO10")
    assert r.status_code == 201
    body = r.json()
    assert body["discount"] == 199_000
    assert body["amount"] == 1_791_000


def test_promo_code_case_insensitive(client):
    tid = _standard_id(client)
    r = _create(client, tid, promo="kvitto10")
    assert r.status_code == 201
    assert r.json()["discount"] == 199_000


def test_unknown_promo_rejected(client):
    tid = _standard_id(client)
    r = _create(client, tid, promo="NOPE")
    assert r.status_code == 422


def test_unknown_tariff_rejected(client):
    r = _create(client, 99999)
    assert r.status_code == 422


# --- installment -----------------------------------------------------

def test_installment_three_month_schedule(client):
    tid = _standard_id(client)
    r = _create(client, tid, method="installment", months=3)
    assert r.status_code == 201
    body = r.json()
    assert body["schedule"] == [663_334, 663_333, 663_333]
    assert sum(body["schedule"]) == STANDARD_PRICE
    assert body["installment_months"] == 3


def test_installment_sums_for_6_and_12(client):
    tid = _standard_id(client)
    for n in (6, 12):
        r = _create(client, tid, method="installment", months=n)
        assert r.status_code == 201
        sched = r.json()["schedule"]
        assert len(sched) == n
        assert sum(sched) == STANDARD_PRICE


def test_installment_invalid_months_rejected(client):
    tid = _standard_id(client)
    r = _create(client, tid, method="installment", months=4)
    assert r.status_code == 422


def test_installment_missing_months_rejected(client):
    tid = _standard_id(client)
    r = _create(client, tid, method="installment")
    assert r.status_code == 422


# --- idempotency -----------------------------------------------------

def test_idempotent_repeat_same_key(client):
    tid = _standard_id(client)
    key = "11111111-2222-3333-4444-555555555555"
    r1 = _create(client, tid, key=key)
    r2 = _create(client, tid, key=key)
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


def test_distinct_keys_create_distinct_payments(client):
    tid = _standard_id(client)
    r1 = _create(client, tid, key="11111111-2222-3333-4444-555555555555")
    r2 = _create(client, tid, key="99999999-8888-7777-6666-555555555555")
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


def test_malformed_idempotency_key_rejected(client):
    tid = _standard_id(client)
    r = _create(client, tid, key="not-a-uuid")
    assert r.status_code == 422


# --- get / list ------------------------------------------------------

def test_get_payment_by_id(client):
    tid = _standard_id(client)
    created = _create(client, tid).json()
    r = client.get(f"/payments/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_missing_payment_404(client):
    r = client.get("/payments/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_list_payments_filter_by_email(client):
    tid = _standard_id(client)
    _create(client, tid, email="x@y.z")
    _create(client, tid, email="p@q.r")
    r = client.get("/payments", params={"email": "x@y.z"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["email"] == "x@y.z"


def test_list_payments_filter_by_status(client):
    tid = _standard_id(client)
    p = _create(client, tid).json()
    _webhook(client, p["id"], "succeeded")
    r = client.get("/payments", params={"status": "succeeded"})
    assert r.status_code == 200
    data = r.json()
    assert all(x["status"] == "succeeded" for x in data)
    assert any(x["id"] == p["id"] for x in data)


# --- webhook signature -----------------------------------------------

def test_webhook_valid_signature_accepted(client):
    tid = _standard_id(client)
    p = _create(client, tid).json()
    r = _webhook(client, p["id"], "succeeded")
    assert r.status_code == 200
    assert client.get(f"/payments/{p['id']}").json()["status"] == "succeeded"


def test_webhook_invalid_signature_401(client):
    tid = _standard_id(client)
    p = _create(client, tid).json()
    body = json.dumps(
        {"payment_id": str(p["id"]), "status": "succeeded"}
    ).encode()
    r = client.post(
        "/webhooks/bank",
        content=body,
        headers={"X-Signature": "deadbeef", "Content-Type": "application/json"},
    )
    assert r.status_code == 401
    assert client.get(f"/payments/{p['id']}").json()["status"] == "pending"


def test_webhook_missing_signature_401(client):
    tid = _standard_id(client)
    p = _create(client, tid).json()
    body = json.dumps(
        {"payment_id": str(p["id"]), "status": "succeeded"}
    ).encode()
    r = client.post(
        "/webhooks/bank", content=body,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 401


# --- webhook status transitions ---------------------------------------

def test_webhook_unknown_payment_404(client):
    r = _webhook(client, "00000000-0000-0000-0000-000000000000", "succeeded")
    assert r.status_code == 404


def test_webhook_forbidden_transition_409(client):
    tid = _standard_id(client)
    p = _create(client, tid).json()
    _webhook(client, p["id"], "succeeded")
    r = _webhook(client, p["id"], "failed")
    assert r.status_code == 409


def test_webhook_allowed_transition_succeeded(client):
    tid = _standard_id(client)
    p = _create(client, tid).json()
    r = _webhook(client, p["id"], "succeeded")
    assert r.status_code == 200
    assert client.get(f"/payments/{p['id']}").json()["status"] == "succeeded"


def test_webhook_refund_after_success(client):
    tid = _standard_id(client)
    p = _create(client, tid).json()
    _webhook(client, p["id"], "succeeded")
    r = _webhook(client, p["id"], "refunded")
    assert r.status_code == 200
    assert client.get(f"/payments/{p['id']}").json()["status"] == "refunded"
