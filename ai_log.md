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
