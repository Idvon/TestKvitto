# AI_LOG

Журнал работы с ИИ. Формат: дата — что сделал/исследовал, решения и почему, файлы, проверки, что осталось. Записи только добавляются, старые не стираются. Секреты и токены не пишутся.

Инструменты/модели: opencode (CLI), модель llama/qwen-27b.

---

## 2026-10-17 — Разбор задания и explore-режим

**Исследовал:**
- Прочитал задание: сообщение пользователя + `Тестовое_Junior_Python_FastAPI.pdf` (3 стр.).
- Проверил OpenSpec: корень есть (schema `spec-driven`), активных изменений и спеков нет — чистое начало.
- Кодовой базы ещё нет: только PDF, конфиги, `.venv`.

**Ключевые факты задания:**
- Стек: Python 3.13, FastAPI, Pydantic v2, PostgreSQL + SQLAlchemy + Alembic, pytest + httpx, GitHub Actions (ruff/pytest/docker).
- Все бонусы из PDF (PostgreSQL/Alembic, Actions, подпись вебхука, `GET /payments` с фильтрами, docker) по сообщению пользователя входят в основной скоуп.
- Деньги — целые копейки, без float. Тарифы: basic 9900, standard 19900, premium 29900 руб.
- Промокод KVITTO10 = -10% (регистр не важен), неизвестный код → 422.
- Способы: card / sbp / installment; для installment обязателен installment_months ∈ {3,6,12}.
- График рассрочки: деление в копейках, остаток в первые платежи, сумма графика == сумме к оплате.
- Статусы: pending → succeeded / failed; succeeded → refunded; остальные переходы запрещены (409).
- Идемпотентность по Idempotency-Key обязательна; повтор возвращает существующий платёж (200), второго не создаёт.
- Вебхук: проверка X-Signature = HMAC-SHA256(тело, WEBHOOK_SECRET), неверная подпись → 401.

**Решения (предварительные, к подтверждению):**
- `payment_methods` — enum, а не таблица (YAGNI, фиксированный набор).
- `promo_codes` и `tariffs` — таблицы, сид при старте.
- Идемпотентность: уникальный `idempotency_key` в `payments`, find-or-create с обработкой гоночного состояния.
- Математика скидки целочисленная: `discount = price * PCT // 100`, `amount = price - discount`.
- График: `base = amount // N`, `rem = amount % N`; первые `rem` платежей = base+1.
- Подпись вебхука считается от сырого тела запроса.

**Открытые вопросы к пользователю:**
1. Название тарифа: `standard` (как в PDF) или `standart` (как в сообщении)?
2. Реальная интеграция с банком не требуется — только дисциплина идемпотентности и границ транзакции (статус-кво PDF)?
3. В ответе: `amount` = после скидки, `discount` = величина скидки в копейках — верно?
4. Docker: нужен ли Dockerfile + docker-compose, или только job в Actions?

**Файлы:** создан `ai_log.md`.

**Проверки:** извлёк текст PDF через pypdf (системный Python 3.13). Проверил формулу графика на примерах 3/6/12 мес.

**Осталось:** дождаться ответов на вопросы, затем зафиксировать дизайн в OpenSpec-изменении (`/opsx-propose`).

---

## 2026-10-17 — Решения подтверждены пользователем

Ответы на открытые вопросы:
1. Название тарифа — **`standard`** (как в PDF).
2. Реального банка **нет** — только дисциплина идемпотентности (устойчивый ключ) и граница транзакции (вызов банка вне открытой транзакции БД).
3. В ответе: **`amount` = сумма после скидки**, **`discount` = величина скидки в копейках**.
4. **Docker**: `Dockerfile` + запуск через `docker compose`; в GitHub Actions — генерация (сборка) docker-образа.

**Итоговый (зафиксированный) дизайн:**
- Стек: Python 3.13, FastAPI, Pydantic v2, PostgreSQL + SQLAlchemy 2.0 + Alembic, pytest + httpx, Docker, GitHub Actions (ruff/pytest/docker build на каждый push).
- Таблицы: `tariffs` (id, title, price в копейках; сид basic/standard/premium), `promo_codes` (code, discount_pct; сид KVITTO10/10), `payments` (id, tariff_id, email, method enum, installment_months, amount, discount, schedule JSON/null, status enum, idempotency_key unique nullable, created_at).
- Методы оплаты — **enum** card/sbp/installment (не таблица).
- Эндпоинты: `GET /tariffs`; `POST /payments` (идемпотентно по Idempotency-Key: есть → 200, иначе 201); `GET /payments/{id}` (404 если нет); `GET /payments` (фильтры email, status); `POST /webhooks/bank` (проверка X-Signature → 401; нет платежа → 404; запрещённый переход → 409; успех → 200 {result:"ok"}).
- Математика: `discount = price * PCT // 100`, `amount = price - discount`; график рассрочки — остаток в первые платежи, сумма графика == amount.
- Статусы: pending→succeeded, pending→failed, succeeded→refunded; остальное → 409 без смены статуса.
- Вебхук: подпись HMAC-SHA256 от **сырого тела** с WEBHOOK_SECRET, сравнение в постоянном времени.
- Тесты (мин. 5): сумма ± промокод (вкл. нижний регистр); сумма графика == amount для 3/6/12; повтор с тем же Idempotency-Key не создаёт дубль; запрещённый переход → 409 без смены статуса; 404 для несуществующего платежа (+ бонус: неверная подпись вебхука → 401).
- Безопасность: WEBHOOK_SECRET и креды БД — из env, секреты не коммитятся, `.env.example` с плейсхолдерами.

**Файлы:** обновлён `ai_log.md`.

**Осталось:** зафиксировать в OpenSpec-изменении (`/opsx-propose`), затем реализовать (`/opsx-apply`). Реализацию в explore-режиме не начинаю.

---

## 2026-10-17 — Создано OpenSpec-изменение `add-kvito-payments-api`

Собрали обсуждение в OpenSpec-изменение (только планирование, без кода).

**Созданные артефакты** (`openspec/changes/add-kvito-payments-api/`):
- `proposal.md` — зачем и что меняется; один новый capability `payments`; greenfield (нет модифицируемых спеков).
- `specs/payments/spec.md` — контракт поведения: каталог тарифов, деньги в копейках, создание платежа, форма ответа, промокод, график рассрочки, идемпотентность, статус `pending`, машина статусов, вебхук, проверка подписи, get по id, список с фильтрами. 13 требований, каждое со сценариями.
- `design.md` — как: int-копейки, 3 таблицы + enum'ы, идемпотентность через unique-ключ + find-or-create, короткая транзакция (вызов банка после commit), ALLOWED-множество переходов, HMAC от сырого тела, чистые функции `apply_discount`/`build_schedule`, Alembic + idempotent seed, SQLite в тестах / Postgres 16 в контейнере, CI (ruff/pytest/docker build), Dockerfile + compose.
- `tasks.md` — 7 групп задач со сценариями проверки; все 5 обязательных тестовых сценарием разложены по группам (не вынесены в отдельную).

**Проверки:** `openspec status` → 4/4 артефакта; `openspec validate` и `openspec validate --strict` → валидно.

**Осталось:** реализовать по `/opsx-apply` (кода пока нет). Коммиты/пуш/merge в main — пользователем вручную.

---

## 2026-10-17 — Редактирование: ключи таблиц (по решению пользователя)

Уточнили схему ключей в `design.md` (решения 2 и 3), `tasks.md` (2.1) и `specs/payments/spec.md`:
- `tariffs`: `id` — уникальный **целочисленный** PK.
- `promo_codes`: `id` не нужен, `code` — уникальный PK.
- `payments`: `id` — уникальный **UUID** PK; `idempotency_key` — **UUID, UNIQUE, NOT NULL**.

Последствие NOT NULL: у каждого платежа всегда есть UUID-ключ. Без заголовка `Idempotency-Key` сервер генерирует UUID; если заголовок передан — он обязан быть валидным UUID (иначе 422). Добавлен сценарий в спеке: невалидный `Idempotency-Key` → 422. Клиенту ключ не возвращается, поэтому наблюдаемого поведения API это не меняет.

**Проверка:** `openspec validate --strict` → валидно.

---

## 2026-10-17 — Редактирование: опечатка бренда kvito → kvitto

Заменил во всех артефактах изменения `Kvito` (один t) на `Kvitto` (два t) — 4 вхождения в `proposal.md`, `design.md` (2), `specs/payments/spec.md`. Теперь единообразно с доменом `kвитto.pro` и промокодом `KVITTO10`.

Примечание: имя самого изменения-слаг `add-kvito-payments-api` не менял (это идентификатор, не текст; переименование изменения — отдельная операция). `openspec validate --strict` → валидно.

---

## 2026-10-17 — Реализация по `/opsx-apply` (все 21 задача)

Реализовал сервис полностью. Все 21 задача в `tasks.md` отмечены `[x]`.

**Создано:**
- `app/` — `main.py` (фабрика `create_app`, lifespan: `create_all` + seed), `db.py` (engine/SessionLocal/Base/`get_db`), `models.py` (Tariff, PromoCode, Payment; enum'ы через `SAEnum(native_enum=False, values_callable=...)` → хранят канонические нижние значения `card`/`pending`), `schemas.py`, `money.py` (`apply_discount`, `build_schedule`), `status.py` (`PaymentStatus`, `ALLOWED`), `seed.py` (идемпотентный upsert), `services/payments.py` (`create_payment` find-or-create с обработкой `IntegrityError`, `apply_webhook_status`), `routers/{tariffs,payments,webhooks}.py`.
- `alembic.ini`, `alembic/env.py` (URL из env `DATABASE_URL`), `alembic/versions/..._initial_schema.py` (автогенерация: 3 таблицы, enum'ы lowercase, `idempotency_key` UUID UNIQUE NOT NULL).
- `tests/` — `conftest.py` (SQLite in-memory StaticPool, override `get_db`, seed, `TestClient` без контекстного менеджера → lifespan не гоняется), `test_money.py`, `test_status.py`, `test_api.py` (тарифы, создание, промокод вкл. нижний регистр, график 3/6/12, идемпотентность, 404, фильтры, подпись вебхука, переходы, 409).
- `requirements.txt`, `ruff.toml` (`extend-exclude=["alembic/versions"]` — генерируемые миграции не линтим), `.env.example`, `Dockerfile` (python:3.13-slim, entrypoint `alembic upgrade head && uvicorn`), `docker-compose.yml` (postgres:16 + api, env-инъект `DATABASE_URL`/`WEBHOOK_SECRET`), `.github/workflows/ci.yml` (push/PR: ruff, pytest, docker build), `README.md` (запуск/тесты/curl).

**Ключевые технические решения при реализации:**
- `psycopg[binary]` (не голый `psycopg`) — иначе на Windows падает загрузка pq-обёртки.
- `values_callable` в `SAEnum` — чтобы в БД хранились `card`/`pending` (значения), а не `CARD`/`PENDING` (имена), как в спеке.
- `sqlalchemy.Uuid` (портативный) и `SAEnum(native_enum=False)` — чтобы схема работала и на SQLite (тесты), и на Postgres (прод).
- `TestClient(app)` без `with` — иначе lifespan попытается поднять Postgres по модульному engine.
- Ruff: `extend-immutable-calls` для `fastapi.Depends/Query/...` (B008), `alembic/versions` исключён (генерируется Alembic).

**Проверки:**
- `ruff check .` → All checks passed.
- `pytest` → **31 passed** (7 unit: money/status; 24 integration: API + вебхук).
- `alembic upgrade head` (SQLite) → 3 таблицы + alembic_version.
- Бут-проверка: `uvicorn app.main:app` на SQLite → `GET /tariffs` вернул basic/standard/premium с ценами 990000/1990000/2990000.
- YAML `ci.yml` и `docker-compose.yml` валидны.

**Ограничение окружения:** Docker в этой среде не установлен → `docker compose up --build` не запускался; вместо этого бут-путь (migrate + uvicorn + `/tariffs`) проверен локально на SQLite. Файлы Docker/compose/CI написаны и структурно верны, но не прогонялись в контейнере.

**Осталось:** пользователь вручную — коммит/пуш/merge; при наличии Docker — прогнать `docker compose up --build`; затем архивировать изменение (`/opsx-archive`) и синк-спеков в main.

---

## 2026-10-17 — Редактирование плана (`/opsx-update`): DSN, без SQLite, тесты со стабами

Пользователь создал `.env` с DSN Postgres и попросил пересмотреть план (только артефакты, код не трогать). Четыре пункта:

1. **DSN через `pydantic_settings`**: объявлять DSN типом `PostgresDsn` из pydantic в `BaseSettings` (читает `.env`), убрать статические `_url()` в `alembic/env.py` и `_database_url()` в `app/db.py`.
2. **Убрать SQLite** — не используется.
3. **Деньги**: все суммы в копейках целым числом (19 900 ₽ → 1990000); значения тарифов `990000/1990000/2990000` корректны, но в планах не было рубля-контекста — сделал явным.
4. **Тесты**: заменить SQLite на PostgreSQL и использовать mock-заглушки вместо подключения к реальной базе. Пользователь выбрал **вариант A** — стабим слой DB-сессии (без реального подключения), диалект PostgreSQL.

**Изменения в артефактах:**
- `design.md`: переписал решение 10 (тесты: PostgreSQL + стаб сессии, без live-БД, без SQLite); добавил решение 12 (конфиг: DSN/секреты через `pydantic_settings.BaseSettings`, тип `PostgresDsn`, без статического fallback); обновил Risks (убрал риск SQLite → риск стаба) и Open Questions.
- `specs/payments/spec.md`: в «Tariff catalog» и «Money as integer kopecks» добавил рублёвые эквиваленты (9 900 ₽ = 990000 и т.д.) и пример конвертации.
- `proposal.md`: тарифы с рублёвыми эквивалентами; в зависимости добавил `pydantic-settings` (+ `psycopg`).
- `tasks.md`: 1.2 добавил `pydantic-settings`; новая задача **1.5** (DSN через `BaseSettings`/`PostgresDsn`, убрать `_url()`/`_database_url()`); **7.1** переписал (переписать тестовую обвязку на стаб сессии + прогнать suite) и снял галку.

**Состояние:** `openspec validate --strict` → валидно. SQLite из планов полностью убран. Задачи: 20/22 (открыты 1.5 и 7.1).

**Осталось:** `/opsx-apply` — внести дельту в код (настроить `BaseSettings`/`PostgresDsn`, убрать статические URL, переписать тесты на стаб сессии). Затем коммит/пуш/merge вручную.

---

## 2026-10-18 — Диагностика Postgres и решение снять интеграционные тесты

**Проблема:** интеграционные тесты (24) не проходят — `admin.connect()` падает. Диагностика (diag13–diag17 + сырой захват провода) показала:
- Ошибка на проводе — `08P01 protocol_violation` из `ProcessStartupPacket`: Postgres получает повреждённые байты стартового пакета.
- Исключено: баг кода, формат DSN, `pg_hba.conf` (стандартный), IPv4/IPv6 (все три формы хоста ведут себя одинаково), исчерпание соединений, состояние сервиса (рестарт не помог).
- Проявление «плывёт»: то 15/15 OK, через секунды 0/24. Сторонние скрипты-коннекторы проходят, pytest падает.
- Вероятная причина — **Windows Defender** (`MsMpEng.exe`): сетевая инспекция ломает локальные TCP-потоки. Это проблема окружения, не кода.

**Решение пользователя:** отказаться от интеграционных тестов с записью в Postgres (обязательного требования к ним не было). Выбрано: **удалить** интеграционные тесты (не переводить на SQLite).

**Изменения:**
- Удалены `tests/test_api.py` и `tests/conftest.py`. Остались только юнит-тесты: `tests/test_money.py`, `tests/test_status.py` (чистые функции, без БД).
- `tasks.md`: **1.5** → `[x]` (DSN/`WEBHOOK_SECRET` через `BaseSettings`/`PostgresDsn` реализовано и проверено); **7.1** → `[x]` с переформулировкой (интеграционные тесты сняты, чистая логика покрыта юнит-тестами).
- `design.md`: решение 10 переписано (тесты: юнит-тесты чистой логики; интеграционные сняты); обновлены Risks и Open Questions.

**Проверки:** `pytest` → 7 passed (только юнит); `ruff check .` → clean.

**Осталось:** коммит/пуш/merge вручную; при желании — архивировать изменение (`/opsx-archive`) и синк спеков в main.

---

## 2026-10-18 — Мелкие правки: postgres:17 и GET /payments/{id}

По запросу пользователя:
- `docker-compose.yml`: `postgres:16` → `postgres:17` (соответствие локальному Postgres 17); для консистентности обновлены упоминания в `design.md` и `tasks.md`.
- Маршрут `GET /payments/{payment_id}` → `GET /payments/{id}` (`app/routers/payments.py`); заголовок раздела и curl в `README.md` приведены к `{id}`. Поле `payment_id` в теле вебхука не менялось — это имя поля payload, а не параметр маршрута.

**Проверки:** `ruff check .` → clean; пути из OpenAPI: `/payments`, `/payments/{id}`, `/tariffs`, `/webhooks/bank`.

**Решение по `alembic upgrade head`:** запускать «однократно» не нужно — команда идемпотентна (если БД уже на head, это no-op). Текущий пэттерн (запуск при каждом старте контейнера api) безопасен и стандартен для контейнерных приложений.

---

## 2026-10-18 — Возврат интеграционных тестов (задача 7.1)

Пользователь передумал: интеграционные тесты возвращаем, но с другим подходом к БД (отдельная тестовая база + откат транзакции на каждый тест). Пересобраны артефакты (`/opsx-update`), затем реализация (`/opsx-apply`).

**Подход (реализован в `tests/conftest.py`):**
- Вся точка приложения направлена на **отдельную тестовую БД** `<main>_test` (в нашем случае `kvitto_test`), никогда не на основную. Имя/URL выводятся из `DATABASE_URL` из `.env` путём замены имени БД на `<имя>_test`.
- Переопределение `DATABASE_URL` в `os.environ` + `get_settings.cache_clear()` выполняются **до** импорта `app.db`/`app.main`, чтобы модульный `engine` сразу смотрел в тестовую БД.
- Схема тестовой БД создаётся **`alembic upgrade head`** (программно, `alembic.config.Config` на `alembic.ini`), а не `create_all`.
- Изоляция каждого теста — **откат транзакции** после теста: `connection.begin()` на engine тестовой БД, `sessionmaker(bind=connection)` (режим savepoint по умолчанию → `commit()` приложения не «протекает» наружу), в конце `transaction.rollback()`. Таблицы и БД не удаляются, ничего не чистится.
- Если тестовую БД создать не удалось (нет прав/нет `postgres`-БД) — явная ошибка с подсказкой создать её вручную.

**Файлы:**
- Созданы `tests/conftest.py` и `tests/test_api.py` (8 сценариев: сумма ± промокод вкл. нижний регистр; график 3/6/12 сумма == amount; новый ключ → 201, повтор → 200 без дубля; дозволённый переход → 200; запрещённый переход → 409 без смены статуса; 404 для несуществующего; неверная подпись вебхука → 401).
- `alembic.ini`: добавлен `path_separator = os` (убирает DeprecationWarning при программном запуске Alembic).
- `tasks.md`: **7.1** → `[x]`.

**Проверки:** `pytest` → **15 passed** (7 unit + 8 integration); `ruff check .` → All checks passed. `openspec instructions apply` → state `all_done`, 22/22.

**Осталось:** коммит/пуш/merge вручную; при желании — архивировать изменение (`/opsx-archive`) и синк спеков в main.

---

## 2026-10-18 — Миграция тестового клиента httpx → httpx2

После возврата интеграционных тестов при запуске `pytest` в `.venv` появилось предупреждение `StarletteDeprecationWarning` из `fastapi/testclient.py`: «Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.» — идёт из самой библиотеки (не из нашего кода), advisory, тесты от него не падали.

**Механизм** (`.venv/.../starlette/testclient.py`): TestClient сначала пробует `import httpx2 as httpx`; только если `httpx2` не установлен — падает на `import httpx` и выдаёт предупреждение. Значит, достаточно установить `httpx2` — библиотека сама на него переключится, наш `conftest.py` менять не нужно (он импортирует `TestClient`, который под капотом уже на `httpx2`).

**Изменения:**
- Установлен `httpx2` (2.14.0, вместе с `httpcore2` и `truststore`) в `.venv`.
- `requirements.txt`: `httpx` → `httpx2`.
- `README.md`: «pytest + httpx» → «pytest + httpx2»; заодно привёл в порядок устаревшее (PostgreSQL 16 → 17; «in-memory SQLite» → «отдельная тестовая БД Postgres») — эти строки давно не соответствовали реальности после прежних миграций.

**Проверки:** `pytest` в `.venv` → **15 passed**, предупреждение `httpx2` исчезло. `ruff check .` → clean (Python-файлы не тронуты).

**Осталось:** коммит/пуш/merge вручную; при желании — архивировать изменение (`/opsx-archive`) и синк спеков в main.
