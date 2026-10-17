# Spec Delta

## Purpose

Defines how the online school accepts and tracks course payments through Kvitto, with exact integer-kopeck arithmetic, idempotent payment creation, and a strict payment-status lifecycle driven by bank webhooks.

## ADDED Requirements

### Requirement: Tariff catalog
The system SHALL expose the list of course tariffs, each with an `id`, a `title`, and a `price` expressed in integer kopecks. The catalog SHALL be seeded at startup with `basic` (990000), `standard` (1990000), and `premium` (2990000).

#### Scenario: List tariffs
- **WHEN** a client sends `GET /tariffs`
- **THEN** the response is `200` and the body is a list of `{id, title, price}` for `basic`, `standard`, and `premium` with prices `990000`, `1990000`, and `2990000` respectively

### Requirement: Money as integer kopecks
All monetary amounts in API requests, API responses, and storage SHALL be represented as integers in kopecks. The system SHALL NOT use floating-point values for money.

#### Scenario: Amounts are integer kopecks
- **WHEN** a payment for `standard` without a promo code is created
- **THEN** its `amount` is the integer `1990000` and no fractional currency unit appears anywhere in the response

### Requirement: Payment creation
The system SHALL create a payment when a valid request is posted to `POST /payments` with a body containing `tariff_id`, `email`, and `method`, returning `201` and the created payment. `promo_code` is optional and `installment_months` is required only for the `installment` method.

#### Scenario: Create a card payment
- **WHEN** a client posts `POST /payments` with a valid `tariff_id`, `email`, and `method: "card"`
- **THEN** the response is `201` and the body is the created payment

#### Scenario: Unknown tariff rejected
- **WHEN** a client posts `POST /payments` with a `tariff_id` that does not exist
- **THEN** the response is `422`

### Requirement: Payment response shape
Payment responses SHALL include `id`, `status`, `tariff_id`, `amount`, `discount`, `method`, `installment_months`, `schedule`, `email`, and `created_at`. `amount` is the total to pay after any discount, and `discount` is the discount amount in kopecks (`0` when no promo code is applied).

#### Scenario: Payment fields present
- **WHEN** a payment is created without a promo code and with a non-installment method
- **THEN** the response includes all listed fields, `discount` is `0`, `installment_months` is `null`, and `schedule` is `null`

### Requirement: Promo code discount
The system SHALL apply a 10% discount to the tariff price when the promo code `KVITTO10` is provided, matching case-insensitively. An unrecognized promo code SHALL be rejected with `422`.

#### Scenario: Promo code applied
- **WHEN** a payment for `standard` is created with `promo_code: "KVITTO10"`
- **THEN** `discount` is `199000` and `amount` is `1791000`

#### Scenario: Promo code is case-insensitive
- **WHEN** a payment for `standard` is created with the same code written in all-lowercase letters (or any other mixed case)
- **THEN** the 10% discount is applied exactly as with the uppercase form

#### Scenario: Unknown promo code rejected
- **WHEN** a payment is created with a `promo_code` that is not a known code
- **THEN** the response is `422` and no payment is created

### Requirement: Installment schedule
For the `installment` method, `installment_months` SHALL be one of `3`, `6`, or `12`; any other value SHALL be rejected with `422`. The `schedule` SHALL be a list of integer-kopeck parts that sum exactly to `amount`, with any remainder distributed into the first payments. For all other methods, `schedule` SHALL be `null`.

#### Scenario: Three-month schedule
- **WHEN** a payment for `standard` (amount `1990000`) is created with `method: "installment"` and `installment_months: 3`
- **THEN** `schedule` is `[663334, 663333, 663333]` and the parts sum to exactly `1990000`

#### Scenario: Six- and twelve-month schedules
- **WHEN** a payment for `standard` is created with `installment_months` of `6` or `12`
- **THEN** the `schedule` has that many parts and the parts sum to exactly `1990000`

#### Scenario: Installment without valid months rejected
- **WHEN** a payment is created with `method: "installment"` and an `installment_months` value outside {3, 6, 12} (or missing)
- **THEN** the response is `422`

#### Scenario: Non-installment has no schedule
- **WHEN** a payment is created with `method: "card"` or `method: "sbp"`
- **THEN** `schedule` is `null`

### Requirement: Idempotent payment creation
When `POST /payments` includes an `Idempotency-Key` header, the system SHALL use that key as a stable identifier. If a payment with that key already exists, the system SHALL return that existing payment with `200` and SHALL NOT create a second payment. Distinct keys SHALL produce distinct payments.

#### Scenario: Repeat with same key returns existing payment
- **WHEN** a client posts `POST /payments` twice with the same `Idempotency-Key`
- **THEN** the second response is `200`, both responses reference the same payment `id`, and exactly one payment exists for that key

#### Scenario: Distinct keys create distinct payments
- **WHEN** a client posts `POST /payments` twice with different `Idempotency-Key` values
- **THEN** two separate payments are created

#### Scenario: Malformed idempotency key rejected
- **WHEN** a client posts `POST /payments` with an `Idempotency-Key` header that is not a valid UUID
- **THEN** the response is `422` and no payment is created

### Requirement: New payment starts pending
A newly created payment SHALL have status `pending`.

#### Scenario: Created payment is pending
- **WHEN** a payment is successfully created
- **THEN** its `status` is `pending`

### Requirement: Payment status transitions
The system SHALL allow only the transitions `pending → succeeded`, `pending → failed`, and `succeeded → refunded`. Every other transition SHALL be rejected with `409` and the payment status SHALL remain unchanged.

#### Scenario: Allowed transitions succeed
- **WHEN** a bank webhook requests `succeeded` on a `pending` payment, `failed` on a `pending` payment, or `refunded` on a `succeeded` payment
- **THEN** the transition is applied and the response is `200`

#### Scenario: Forbidden transition rejected
- **WHEN** a bank webhook requests a transition that is not allowed (for example `refunded` on a `pending` payment, or `succeeded` on a `failed` payment)
- **THEN** the response is `409` with body `{ "error": "invalid_transition" }` and the payment status is unchanged

### Requirement: Bank webhook intake
The system SHALL accept bank status updates at `POST /webhooks/bank` with a body containing `payment_id` and `status`. If the payment does not exist the response SHALL be `404`; on a successful update the response SHALL be `200` with body `{ "result": "ok" }`.

#### Scenario: Valid webhook updates status
- **WHEN** a correctly signed webhook posts a valid `payment_id` and an allowed `status`
- **THEN** the payment status is updated and the response is `200` with `{ "result": "ok" }`

#### Scenario: Webhook for unknown payment
- **WHEN** a correctly signed webhook posts a `payment_id` that does not exist
- **THEN** the response is `404`

### Requirement: Webhook signature verification
The system SHALL verify the `X-Signature` header on `POST /webhooks/bank` as the HMAC-SHA256 of the raw request body, keyed by the `WEBHOOK_SECRET` environment variable. A missing or invalid signature SHALL be rejected with `401` before any status is processed.

#### Scenario: Valid signature accepted
- **WHEN** a webhook request carries an `X-Signature` equal to the HMAC-SHA256 of its raw body under `WEBHOOK_SECRET`
- **THEN** the request is processed normally

#### Scenario: Invalid signature rejected
- **WHEN** a webhook request carries an `X-Signature` that does not match the HMAC-SHA256 of its raw body
- **THEN** the response is `401` and no status change is applied

### Requirement: Get payment by id
The system SHALL return the payment at `GET /payments/{id}`, or `404` when no payment has that id.

#### Scenario: Existing payment returned
- **WHEN** a client sends `GET /payments/{id}` for an existing payment
- **THEN** the response is `200` with that payment

#### Scenario: Missing payment
- **WHEN** a client sends `GET /payments/{id}` for an id that does not exist
- **THEN** the response is `404`

### Requirement: List payments with filters
The system SHALL return payments at `GET /payments`, optionally filtered by an `email` query parameter and/or a `status` query parameter. When a parameter is omitted it SHALL not filter on that field.

#### Scenario: Filter by email
- **WHEN** a client sends `GET /payments?email=a@b.c`
- **THEN** the response contains only payments with that email

#### Scenario: Filter by status
- **WHEN** a client sends `GET /payments?status=pending`
- **THEN** the response contains only payments with status `pending`

#### Scenario: No filters
- **WHEN** a client sends `GET /payments` with no query parameters
- **THEN** the response contains all payments
