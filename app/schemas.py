"""Pydantic v2 request/response schemas."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models import Method
from app.status import PaymentStatus


class PaymentCreate(BaseModel):
    """Request body for ``POST /payments``."""

    tariff_id: int
    email: EmailStr
    method: Method
    promo_code: str | None = None
    installment_months: int | None = None


class TariffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    price: int


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: PaymentStatus
    tariff_id: int
    amount: int
    discount: int
    method: Method
    installment_months: int | None
    schedule: list[int] | None
    email: str
    created_at: datetime
