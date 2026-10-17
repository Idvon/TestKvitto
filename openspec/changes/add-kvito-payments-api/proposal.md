# Proposal

## Why

The online school needs a small service to accept course payments through Kvito. The codebase is tiny, but money handling demands precision — kopecks without loss, idempotent retries, and correct status transitions — so the service must be exact by design, not by convention.

## What Changes

- New FastAPI service exposing a payments API for an online school: tariff catalog, payment creation, payment queries, and a bank webhook.
- Money is handled exclusively as **integer kopecks** (no floats) across the API and the database.
- Tariff catalog seeded at startup: `basic` (990000), `standard` (1990000), `premium` (2990000) kopecks.
- Promo code `KVITTO10` (case-insensitive) applies −10% of the tariff price; unknown codes are rejected with `422`.
- Payment methods `card` / `sbp` / `installment`; `installment` requires `installment_months` ∈ {3, 6, 12} and produces a kopeck-exact schedule whose parts sum exactly to the amount (remainder placed in the first payments).
- **Idempotent** payment creation via the `Idempotency-Key` header: a repeat with the same key returns the existing payment (`200`) and never creates a second.
- Payment status lifecycle: `pending → succeeded`, `pending → failed`, `succeeded → refunded`; every other transition is rejected with `409` and the status left unchanged.
- Bank webhook `POST /webhooks/bank` verifies an `X-Signature` header (HMAC-SHA256 over the raw request body keyed by `WEBHOOK_SECRET`); an invalid signature returns `401`.
- Payment queries: `GET /payments/{id}` (`404` if absent) and `GET /payments` with optional `email` and `status` filters.
- Persistence on PostgreSQL via SQLAlchemy + Alembic migrations; `Dockerfile` + `docker-compose`; GitHub Actions running ruff, pytest, and a Docker build on each push.

## Capabilities

### New Capabilities
- `payments`: The online-school payment lifecycle — tariff catalog, idempotent payment creation, promo-code discounting, installment scheduling, status transitions, bank-webhook intake, and payment queries.

### Modified Capabilities
<!-- None: this is a greenfield repo with no existing specs. -->

## Impact

- **New service** — the repo is greenfield, so no existing code is affected.
- **New API surface**: `GET /tariffs`, `POST /payments`, `GET /payments/{id}`, `GET /payments`, `POST /webhooks/bank`.
- **New dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, PostgreSQL, pytest, httpx, ruff; Docker + docker-compose; a GitHub Actions workflow.
- **Security**: `WEBHOOK_SECRET` and DB credentials are supplied via environment variables; no secrets are committed; `.env.example` documents placeholders. Access to data and keys is limited to the app process and the compose network.
