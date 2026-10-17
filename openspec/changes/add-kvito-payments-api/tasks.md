# Tasks

## 1. Project scaffolding

- [x] 1.1 Create the `app/` package layout (`main.py`, `db.py`, `models.py`, `schemas.py`, `money.py`, `status.py`, `services/`, `routers/`) and verify `python -c "import app.main"` succeeds
- [x] 1.2 Add dependencies (FastAPI, uvicorn, Pydantic v2, SQLAlchemy 2.0, Alembic, psycopg, pytest, httpx, ruff) to the dependency file and verify `pip install -r requirements.txt` succeeds in a clean venv
- [x] 1.3 Add ruff configuration and verify `ruff check .` passes on the scaffold
- [x] 1.4 Add `.env.example` with `DATABASE_URL` and `WEBHOOK_SECRET` placeholders plus a `.gitignore`, and verify no real secret appears in the repo

## 2. Data model and migrations

- [x] 2.1 Define SQLAlchemy models for `tariffs` (integer `id` PK), `promo_codes` (`code` PK, no `id`), and `payments` (UUID `id` PK, `idempotency_key` UUID `UNIQUE NOT NULL`; integer-kopeck columns, `method`/`status` enums, JSON `schedule`) and verify `Base.metadata` contains all three tables with the specified primary keys and a non-null unique `idempotency_key`
- [x] 2.2 Create the Alembic config and an initial revision for the three tables, and verify `alembic upgrade head` creates them
- [x] 2.3 Implement an idempotent startup seed (upsert `basic`/`standard`/`premium` and `KVITTO10`) and verify running startup twice does not create duplicate rows

## 3. Money and status logic (pure, unit-tested)

- [x] 3.1 Implement `apply_discount(price, pct) -> (amount, discount)` in `money.py` and verify unit tests assert `standard`+`KVITTO10` → `(1791000, 199000)` and no-promo → `(1990000, 0)`
- [x] 3.2 Implement `build_schedule(amount, n)` in `money.py` and verify unit tests assert `sum(schedule) == amount` for `n` in {3, 6, 12} and that 3-month `standard` equals `[663334, 663333, 663333]`
- [x] 3.3 Implement the status enum and the `ALLOWED` transition set in `status.py` and verify unit tests assert exactly `pending→succeeded`, `pending→failed`, `succeeded→refunded` are allowed and all other pairs are rejected

## 4. Payment creation and query API

- [x] 4.1 Implement `POST /payments` creation (resolve tariff, case-insensitive promo with unknown code → 422, `installment_months` required for installment, build schedule, insert `pending`) and verify a `card` payment returns `201` with correct `amount`/`discount`/`schedule`
- [x] 4.2 Implement `Idempotency-Key` find-or-create (with `IntegrityError` re-fetch) and verify a repeat with the same key returns `200` with exactly one payment, while distinct keys create distinct payments
- [x] 4.3 Implement `GET /tariffs` and verify it returns the three seeded tariffs with integer-kopeck prices
- [x] 4.4 Implement `GET /payments/{id}` (404 when absent) and `GET /payments` with optional `email` and `status` filters, and verify each returns the expected rows and `404` for a missing id

## 5. Bank webhook

- [x] 5.1 Implement `X-Signature` verification (HMAC-SHA256 of the raw body vs `WEBHOOK_SECRET`, constant-time compare → 401 on mismatch) and verify a valid signature is accepted while an invalid or missing one returns `401`
- [x] 5.2 Implement `POST /webhooks/bank` status update (unknown payment → 404, forbidden transition → `409 {"error":"invalid_transition"}` with status unchanged, allowed transition → `200 {"result":"ok"}`) and verify each case with a correctly signed request

## 6. Containerization and CI

- [x] 6.1 Add a `Dockerfile` (python:3.13-slim, uvicorn) and `docker-compose.yml` (postgres:16 `db` + `api`, env-injected `DATABASE_URL`/`WEBHOOK_SECRET`, entrypoint runs `alembic upgrade head`) and verify `docker compose up --build` boots and `GET /tariffs` responds
- [x] 6.2 Add a GitHub Actions workflow on push (setup Python 3.13, `ruff check .`, `pytest`, `docker build`) and verify the workflow is valid YAML and its steps match the local commands
- [x] 6.3 Write the README (how to run, how to test, curl examples) and verify each documented command runs as written

## 7. Integration verification

- [x] 7.1 Run the full pytest suite and verify all five required scenarios pass (amount with/without promo incl. lowercase; schedule sums to amount for 3/6/12; idempotent repeat creates no duplicate; forbidden transition → 409 with status unchanged; missing payment → 404), plus webhook bad-signature → 401
- [x] 7.2 Run `ruff check .` and verify it reports no findings

## Workflow follow-up

- Archive the change once the implementation is complete and reviewed.
- Verify the archived main spec reflects the `payments` capability.
