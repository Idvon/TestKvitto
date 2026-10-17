"""SQLAlchemy ORM models.

Money columns are integer kopecks. ``method`` and ``status`` are stored as
short strings (VARCHAR + CHECK) so the schema is portable across PostgreSQL
and SQLite. ``payments.id`` is a UUID (referenced by the bank webhook) and
``payments.idempotency_key`` is a non-null unique UUID.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Uuid,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.status import PaymentStatus


class Method(str, Enum):
    CARD = "card"
    SBP = "sbp"
    INSTALLMENT = "installment"


class Tariff(Base):
    __tablename__ = "tariffs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)


class PromoCode(Base):
    __tablename__ = "promo_codes"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    discount_pct: Mapped[int] = mapped_column(Integer, nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, nullable=False)
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id"), nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    method: Mapped[Method] = mapped_column(
        SAEnum(
            Method,
            name="pay_method",
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    installment_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    schedule: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(
            PaymentStatus,
            name="pay_status",
            native_enum=False,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=PaymentStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
