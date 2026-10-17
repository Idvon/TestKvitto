"""Payment creation and query endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Payment
from app.schemas import PaymentCreate, PaymentOut
from app.services.payments import create_payment
from app.status import PaymentStatus

router = APIRouter()


@router.post("/payments", response_model=PaymentOut)
def create_payment_endpoint(
    response: Response,
    data: PaymentCreate,
    db: Session = Depends(get_db),
    idempotency_key: uuid.UUID | None = Header(default=None, alias="Idempotency-Key"),
):
    payment, created = create_payment(db, data, idempotency_key)
    response.status_code = 201 if created else 200
    return payment


@router.get("/payments/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: uuid.UUID, db: Session = Depends(get_db)):
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="payment not found")
    return payment


@router.get("/payments", response_model=list[PaymentOut])
def list_payments(
    db: Session = Depends(get_db),
    email: str | None = Query(default=None),
    status: PaymentStatus | None = Query(default=None),
):
    query = select(Payment)
    if email is not None:
        query = query.where(Payment.email == email)
    if status is not None:
        query = query.where(Payment.status == status)
    return db.execute(query.order_by(Payment.created_at, Payment.id)).scalars().all()
