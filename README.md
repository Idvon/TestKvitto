# Kvitto Payments API

FastAPI service for an online English school: list course tariffs, create
payments (card / SBP / installment) with promo discounts, expose a bank webhook
to move payments through their status lifecycle, and query payments.

All money is handled as **integer kopecks** — no floats, no rounding surprises.

## Tech stack

- Python 3.13, FastAPI, Pydantic v2
- SQLAlchemy 2.0 + Alembic (migrations), PostgreSQL 16 (psycopg v3)
- pytest + httpx (tests run on in-memory SQLite)
- ruff (lint/format)
- Docker + docker-compose, GitHub Actions (CI)

## Project structure

```
app/
  main.py        # create_app factory, lifespan (create_all + seed), app instance
  db.py          # engine, SessionLocal, Base, get_db dependency
  models.py      # Tariff, PromoCode, Payment
  schemas.py     # Pydantic request/response models
  money.py       # apply_discount, build_schedule (pure)
  status.py      # PaymentStatus enum + ALLOWED transitions (pure)
  seed.py        # idempotent startup seed
  services/
    payments.py  # create_payment (idempotent), apply_webhook_status
  routers/
    tariffs.py   # GET /tariffs
    payments.py  # POST /payments, GET /payments, GET /payments/{id}
    webhooks.py  # POST /webhooks/bank
alembic/         # migration environment + versions
tests/           # unit + integration tests
```

## Getting started

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows  (Linux/mac: .venv/bin/activate)
pip install -r requirements.txt
```

### Configuration

Copy the example env file and adjust:

```bash
copy .env.example .env        # Windows  (Linux/mac: cp .env.example .env)
```

`.env.example`:

```dotenv
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/kvitto
WEBHOOK_SECRET=change-me
```

`WEBHOOK_SECRET` signs incoming bank webhooks (HMAC-SHA256).

### Run locally (PostgreSQL)

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

The app also runs `create_all` + seed on startup, so a fresh database is
populated with the three tariffs and the `KVITTO10` promo code automatically.

Interactive docs: http://127.0.0.1:8000/docs

### Run with Docker Compose

```bash
docker compose up --build
```

This starts `postgres:16` and the API. The API entrypoint runs
`alembic upgrade head` before booting uvicorn. Override `DATABASE_URL` and
`WEBHOOK_SECRET` by exporting them before `docker compose up`.

## Tests

```bash
pytest
```

Tests run against an in-memory SQLite database (no PostgreSQL required) and
cover the money math, the status machine, payment creation, idempotency,
querying, and the webhook (signature + transitions).

## Lint

```bash
ruff check .
```

## API

### `GET /tariffs`

Returns the seeded tariffs with integer-kopeck prices.

```bash
curl http://127.0.0.1:8000/tariffs
# [{"id":1,"title":"basic","price":990000},
#  {"id":2,"title":"standard","price":1990000},
#  {"id":3,"title":"premium","price":2990000}]
```

### `POST /payments`

Create a payment. `method` is `card`, `sbp`, or `installment`; for
`installment`, `installment_months` must be one of `3`, `6`, `12`.
`promo_code` is optional and case-insensitive.

```bash
curl -X POST http://127.0.0.1:8000/payments \
  -H "Content-Type: application/json" \
  -d '{"tariff_id":2,"email":"me@example.com","method":"card","promo_code":"KVITTO10"}'
# {"id":"...","amount":1791000,"discount":199000,"schedule":null,
#  "status":"pending", ...}
```

Installment:

```bash
curl -X POST http://127.0.0.1:8000/payments \
  -H "Content-Type: application/json" \
  -d '{"tariff_id":2,"email":"me@example.com","method":"installment","installment_months":3}'
# schedule sums to the (discounted) amount, e.g. [663334,663333,663333]
```

**Idempotency.** Send an `Idempotency-Key` header (a UUID). A repeat with the
same key returns `200` and the *same* payment (no duplicate). Without the
header the server generates a key. A malformed UUID is rejected with `422`.

```bash
curl -X POST http://127.0.0.1:8000/payments \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 11111111-2222-3333-4444-555555555555" \
  -d '{"tariff_id":2,"email":"me@example.com","method":"card"}'
```

### `GET /payments/{id}`

Returns one payment, or `404` if it does not exist.

```bash
curl http://127.0.0.1:8000/payments/<id>
```

### `GET /payments`

List payments, optionally filtered by `email` and/or `status`.

```bash
curl "http://127.0.0.1:8000/payments?email=me@example.com&status=pending"
```

### `POST /webhooks/bank`

Bank → service notification. The request body must be signed:

`X-Signature = HMAC-SHA256(raw_body, WEBHOOK_SECRET)` (hex). A missing or
wrong signature returns `401`.

```bash
BODY='{"payment_id":"<payment_id>","status":"succeeded"}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "change-me" | awk '{print $2}')
curl -X POST http://127.0.0.1:8000/webhooks/bank \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIG" \
  -d "$BODY"
# {"result":"ok"}
```

Allowed transitions: `pending → succeeded`, `pending → failed`,
`succeeded → refunded`. A forbidden transition returns
`409 {"error":"invalid_transition"}` and leaves the status unchanged. An
unknown `payment_id` returns `404`.

## Statuses

| from        | to         |
|-------------|------------|
| `pending`   | `succeeded`|
| `pending`   | `failed`   |
| `succeeded` | `refunded` |
