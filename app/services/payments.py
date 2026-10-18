"""Payment creation (idempotent) and bank-webhook status transitions."""
from __future__ import annotations

import uuid
from enum import Enum

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import money
from app.models import Method, Payment, PromoCode, Tariff
from app.schemas import PaymentCreate
from app.status import PaymentStatus, is_allowed

VALID_INSTALLMENT_MONTHS = (3, 6, 12)


class TransitionResult(str, Enum):
    OK = "ok"
    NOT_FOUND = "not_found"
    INVALID = "invalid_transition"


def _resolve_discount_pct(db: Session, promo_code: str | None) -> int:
    if promo_code is None:
        return 0
    row = db.execute(
        select(PromoCode).where(PromoCode.code == promo_code.strip().upper())
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=422, detail="unknown promo code")
    return row.discount_pct


def create_payment(
    db: Session, data: PaymentCreate, idempotency_key: uuid.UUID | None
) -> tuple[Payment, bool]:
    """Create a payment, or return the existing one for a repeated key.

    Returns ``(payment, created)`` where ``created`` is True only when a new
    row was inserted. Unknown tariffs/promo codes and invalid installment
    values raise ``422``.
    """
    tariff = db.execute(select(Tariff).where(Tariff.id == data.tariff_id)).scalar_one_or_none()
    if tariff is None:
        raise HTTPException(status_code=422, detail="unknown tariff")

    discount_pct = _resolve_discount_pct(db, data.promo_code)
    amount, discount = money.apply_discount(tariff.price, discount_pct)

    installment_months = None
    schedule = None
    if data.method == Method.INSTALLMENT:
        if data.installment_months not in VALID_INSTALLMENT_MONTHS:
            raise HTTPException(status_code=422, detail="invalid installment_months")
        installment_months = data.installment_months
        schedule = money.build_schedule(amount, installment_months)

    key = idempotency_key if idempotency_key is not None else uuid.uuid4()

    existing = db.execute(
        select(Payment).where(Payment.idempotency_key == key)
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    payment = Payment(
        idempotency_key=key,
        tariff_id=tariff.id,
        email=data.email,
        method=data.method,
        installment_months=installment_months,
        amount=amount,
        discount=discount,
        schedule=schedule,
        status=PaymentStatus.PENDING,
    )
    db.add(payment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.execute(
            select(Payment).where(Payment.idempotency_key == key)
        ).scalar_one()
        return existing, False
    db.refresh(payment)
    return payment, True


def apply_webhook_status(
    db: Session, payment_id: uuid.UUID, new_status: PaymentStatus
) -> TransitionResult:
    """Apply a bank status transition to a payment.

    Returns ``OK`` on success, ``NOT_FOUND`` for an unknown payment, or
    ``INVALID`` for a forbidden transition (status left unchanged).
    """
    payment = db.get(Payment, payment_id)
    if payment is None:
        return TransitionResult.NOT_FOUND
    if not is_allowed(payment.status, new_status):
        return TransitionResult.INVALID
    payment.status = new_status
    db.commit()
    db.refresh(payment)
    return TransitionResult.OK
