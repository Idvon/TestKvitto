"""Pure money math in integer kopecks (no floats, no Decimal)."""
from __future__ import annotations


def apply_discount(price: int, pct: int) -> tuple[int, int]:
    """Return ``(amount, discount)`` for ``price`` discounted by ``pct`` percent.

    ``discount = price * pct // 100`` and ``amount = price - discount``.
    Both are exact integers; ``amount + discount == price`` always holds.
    """
    discount = price * pct // 100
    amount = price - discount
    return amount, discount


def build_schedule(amount: int, n: int) -> list[int]:
    """Split ``amount`` into ``n`` integer parts that sum exactly to ``amount``.

    The remainder of the division is distributed one kopeck at a time into the
    first payments, so ``sum(schedule) == amount`` holds by construction.
    """
    if n <= 0:
        raise ValueError("n must be a positive integer")
    base, rem = divmod(amount, n)
    return [base + 1] * rem + [base] * (n - rem)
