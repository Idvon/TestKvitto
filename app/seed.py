"""Idempotent startup seeding of the tariff catalog and promo code."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PromoCode, Tariff

TARIFFS: list[tuple[str, int]] = [
    ("basic", 990_000),
    ("standard", 1_990_000),
    ("premium", 2_990_000),
]

PROMO_CODES: list[tuple[str, int]] = [
    ("KVITTO10", 10),
]


def seed(db: Session) -> None:
    """Upsert the fixed catalog rows; safe to run on every startup."""
    for title, price in TARIFFS:
        row = db.execute(select(Tariff).where(Tariff.title == title)).scalar_one_or_none()
        if row is None:
            db.add(Tariff(title=title, price=price))
        elif row.price != price:
            row.price = price

    for code, pct in PROMO_CODES:
        row = db.execute(select(PromoCode).where(PromoCode.code == code)).scalar_one_or_none()
        if row is None:
            db.add(PromoCode(code=code, discount_pct=pct))
        elif row.discount_pct != pct:
            row.discount_pct = pct

    db.commit()
