# Design

## Context

Greenfield repo — there is no existing code. We are building a small FastAPI service that lets an online school accept course payments through Kvitto. See `proposal.md` for motivation. Hard constraints that shape the approach: money is integer kopecks everywhere (no floats), payment creation must be idempotent, the status lifecycle is a strict 3-transition machine, and the bank webhook must be signature-verified. The service runs on PostgreSQL (SQLAlchemy + Alembic), is containerized, and is linted/tested in CI.

## Goals / Non-Goals

**Goals:**
- Exact, lossless money handling (integer kopecks) from API to DB.
- Idempotent payment creation keyed by `Idempotency-Key`.
- An enforced, race-safe status transition machine.
- Signature-verified bank webhook.
- Runnable with `docker compose up --build`; linted (ruff) and tested (pytest) in GitHub Actions.
- Pure, unit-testable money/status logic separated from I/O.

**Non-Goals:**
- Real Kvitto/bank integration (no real external API calls; the bank is modeled by the webhook).
- End-user authentication or authorization.
- Frontend, deployment/scaling, and payment date scheduling (only amounts, no dates).

## Decisions

### 1. Money is Python `int` kopecks end-to-end
All amounts are `int` in Pydantic schemas, service logic, and DB columns (`Integer`/`BigInteger`). No `float`, no `Decimal`.
- **Why:** Kopecks are whole units; integer arithmetic is exact. `price * PCT // 100` is exact for integer prices.
- **Alternative considered:** `Decimal` — rejected; adds no precision benefit for integer kopecks and invites confusion.

### 2. Three tables; explicit primary keys; methods and statuses are enums
- `tariffs(id, title, price)`: `id` is a **unique integer primary key**; `title` is unique.
- `promo_codes(code, discount_pct)`: **no `id`** — `code` is the **unique primary key**.
- `payments(id, tariff_id, email, method, installment_months, amount, discount, schedule, status, idempotency_key, created_at)`: `id` is a **unique UUID primary key** (referenced by the bank webhook, so non-enumerable); `idempotency_key` is a **UUID, `UNIQUE`, `NOT NULL`**.

`method` (`card`/`sbp`/`installment`) and `status` (`pending`/`succeeded`/`failed`/`refunded`) are Python `enum.Enum` stored as short strings. `schedule` is a JSON list of ints or `NULL`.
- **Why:** `method`/`status` are fixed closed sets — enums keep queries simple and the DB self-documenting. `payments.id` is a UUID because the bank references it; `tariffs`/`promo_codes` are tiny internal catalogs, so an integer `id` (tariffs) and the natural `code` (promo_codes) are simplest.
- **Alternative considered:** lookup tables for methods — rejected (no expected growth, extra joins for nothing); a separate `id` on `promo_codes` — rejected (the `code` is already a natural unique key).

### 3. Idempotency via a unique, always-present UUID key + find-or-create
`payments.idempotency_key` is a **UUID, `UNIQUE`, `NOT NULL`** — every payment has one. On `POST /payments`: if the `Idempotency-Key` header is present it must be a **valid UUID** (otherwise `422`); if it is absent the server **generates a UUID**. Then `SELECT` by key → if found, return it with `200`; otherwise `INSERT` with `201`. Under concurrency the `UNIQUE` constraint lets exactly one insert win; the loser catches `IntegrityError`, re-fetches, and returns the existing row. No duplicate is possible.
- **Why:** One column on `payments` is the simplest correct model; the key is also the conceptual "stable idempotency key at the bank", so a retry after a network timeout reuses it and cannot double-charge. Making it `NOT NULL` means every payment is idempotency-addressable even when the client supplies no key.
- **Alternative considered:** a nullable key (header-less requests stored `NULL`) — rejected per the `NOT NULL` requirement; a separate `idempotency_keys` table — rejected; the mapping to a payment is 1:1, so the column is simpler.

### 4. Short DB transaction; the "bank call" happens after commit
The pending payment is inserted and committed in its own short transaction. A real bank call would be made **after** commit, using the idempotency key — never while a transaction is open. With no real bank, the webhook is the external actor that advances status, and the commit-then-act ordering is what makes a timeout-retry safe.
- **Why:** Holding a DB transaction across a network call risks long locks and inconsistent state; committing first and acting on a stable key is the standard safe pattern.

### 5. Status machine as an explicit allowed-set
```
ALLOWED = {("pending","succeeded"), ("pending","failed"), ("succeeded","refunded")}
```
On webhook: if `(current, new)` is not in `ALLOWED` → `409 {"error":"invalid_transition"}`, status untouched; otherwise update. The update is guarded by `WHERE status = current` so a concurrent webhook cannot double-apply.
- **Why:** Three transitions do not justify a state-machine library (KISS); an explicit set is obvious and trivially testable.
- **Alternative considered:** a state-machine framework — rejected as over-engineering for 3 edges.

### 6. Webhook signature from the raw body
Read `body = await request.body()` **once** (raw bytes), compute `hmac.new(WEBHOOK_SECRET, body, sha256).hexdigest()`, and compare to `X-Signature` with `hmac.compare_digest` (constant-time). Mismatch → `401`. The JSON payload is parsed from the same cached `body` via `json.loads`, so the stream is never consumed twice.
- **Why:** The signature is over the exact bytes the bank sent; re-serializing JSON would change byte order and break verification. Constant-time compare avoids a timing side-channel.
- `WEBHOOK_SECRET` comes from the environment and is never committed.

### 7. Pure functions for money math
`apply_discount(price, pct) -> (amount, discount)` where `discount = price * pct // 100`, `amount = price - discount`. `build_schedule(amount, n) -> list[int]` where `base, rem = divmod(amount, n)` and the result is `[base+1]*rem + [base]*(n-rem)` (remainder in the first payments). Both are pure and unit-testable without HTTP; `sum(schedule) == amount` holds by construction.
- **Why:** Isolating the money rules in pure functions is where correctness is proven, and it keeps them independent of FastAPI/SQLAlchemy.

### 8. Persistence, seeding, and migrations
Alembic owns the schema (initial revision creates the three tables). Tariffs and the promo code are seeded by an **idempotent upsert** on application startup (keyed by `title`/`code`), so `docker compose up` needs no manual data step and repeated starts do not duplicate rows.
- **Alternative considered:** a data migration for seeds — viable, but a startup upsert is simpler and self-healing.

### 9. Application layout (KISS with clean seams)
```
app/
  main.py            # app factory, router wiring, startup seed
  db.py              # engine, session, Base
  models.py          # SQLAlchemy models
  schemas.py         # Pydantic request/response schemas
  money.py           # apply_discount, build_schedule (pure)
  status.py          # status enum + ALLOWED transitions (pure)
  services/payments.py  # create/idempotency + webhook status update
  routers/           # tariffs, payments, webhooks
tests/
alembic/
Dockerfile
docker-compose.yml
.env.example
README.md
.github/workflows/ci.yml
```
- **Why:** Pure logic (`money.py`, `status.py`) is separated from I/O so the money rules are testable in isolation; routers stay thin.

### 10. Testing: unit tests for pure logic; integration tests dropped
The correctness-critical logic — kopeck arithmetic (`money.py`) and the 3-transition status machine (`status.py`) — is pure and unit-tested without I/O (`tests/test_money.py`, `tests/test_status.py`). The originally planned integration tests (DB-session stubbed over the PostgreSQL dialect) were **dropped**: there was no mandatory requirement for them, and the environment has intermittent Postgres connectivity. API/service behavior is exercised against the running service rather than by an automated integration suite.
- **Why:** The money/status rules are where correctness lives and they are pure, so unit tests prove them without a database; HTTP-level integration tests added little beyond that and depended on a live or stubbed Postgres.
- **Alternative considered:** DB-session-stubbed integration tests (original plan) — dropped per decision; a live-Postgres integration suite — rejected (environment instability, external dependency).

### 11. CI and Docker
GitHub Actions on each push: setup Python 3.13, install deps, `ruff check .`, `pytest`, then `docker build` (proves the image compiles). `Dockerfile` is `python:3.13-slim` running uvicorn; `docker-compose.yml` defines `db` (postgres:16) and `api`, with `DATABASE_URL` and `WEBHOOK_SECRET` injected from the environment and an entrypoint that runs `alembic upgrade head` before starting the app.
- **Why:** Lint + tests + image build on every push gives a fast correctness net; compose gives a one-command local run.

### 12. Configuration: DSN and secrets via pydantic-settings
The Postgres DSN and `WEBHOOK_SECRET` are declared in a single `pydantic_settings.BaseSettings` class that reads the process environment and the local `.env` file. The DSN field is typed as pydantic's `PostgresDsn`, so a malformed connection string fails fast at startup with a clear validation error. There is **no static/hardcoded fallback URL** — the DSN always comes from the environment/`.env`.
- **Why:** `BaseSettings` gives typed, validated configuration from `.env` in one place; `PostgresDsn` validates the connection string's shape. Removing any hardcoded default means a missing or typo'd DSN is an immediate, obvious error rather than a silent connection to the wrong database.
- **Alternative considered:** reading `os.getenv("DATABASE_URL")` with a hardcoded default (the previous `_url()` pattern) — rejected; the default masked misconfiguration and duplicated the config source.

## Risks / Trade-offs

- **[No integration tests]** → API/service behavior is not covered by automated tests; the pure money/status logic is unit-tested, and `alembic upgrade head` against a real Postgres validates dialect-specific SQL.
- **[Concurrent same-key race]** → the `UNIQUE` constraint is the source of truth; the code path catches `IntegrityError` and re-fetches. Happy path is tested; the constraint covers the rare race.
- **[Reading the raw body twice]** → read `request.body()` once, verify the signature, then `json.loads` the same bytes; never re-serialize.
- **[Float creep]** → money only enters/leaves through `money.py`; ruff + review forbid `float` amounts.
- **[Startup seeding duplicates]** → upsert by unique `title`/`code` makes repeated starts idempotent.

## Migration Plan

Greenfield, so there is nothing to migrate:
1. `alembic init` + an initial revision creating `tariffs`, `promo_codes`, `payments`.
2. Compose entrypoint runs `alembic upgrade head`, then the startup seed upserts tariffs + promo code, then uvicorn starts.
3. **Rollback:** `alembic downgrade -1`; the data is new, so dropping the schema is safe.
4. **Deploy:** `docker compose up --build`.

## Open Questions

None that would change the specs, the approach, or the task breakdown. Chosen defaults (recorded, not blocking): Postgres 16, Python 3.13, DSN via pydantic-settings, integration tests dropped (unit tests only).
