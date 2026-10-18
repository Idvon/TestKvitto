"""Payment status enum and the allowed transition set (pure logic)."""
from __future__ import annotations

from enum import Enum


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


ALLOWED: set[tuple[PaymentStatus, PaymentStatus]] = {
    (PaymentStatus.PENDING, PaymentStatus.SUCCEEDED),
    (PaymentStatus.PENDING, PaymentStatus.FAILED),
    (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED),
}


def is_allowed(current: PaymentStatus, new: PaymentStatus) -> bool:
    """Return True if the transition ``current -> new`` is permitted."""
    return (current, new) in ALLOWED
