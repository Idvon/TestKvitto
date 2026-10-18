"""Unit tests for the pure money math in app.money."""
from app import money


def test_apply_discount_standard_with_promo():
    amount, discount = money.apply_discount(1_990_000, 10)
    assert (amount, discount) == (1_791_000, 199_000)


def test_apply_discount_no_promo():
    amount, discount = money.apply_discount(1_990_000, 0)
    assert (amount, discount) == (1_990_000, 0)


def test_apply_discount_rounds_down():
    amount, discount = money.apply_discount(100_001, 10)
    assert discount == 10_000
    assert amount + discount == 100_001


def test_build_schedule_sums_to_amount_for_3_6_12():
    for n in (3, 6, 12):
        schedule = money.build_schedule(1_990_000, n)
        assert len(schedule) == n
        assert sum(schedule) == 1_990_000


def test_build_schedule_three_month_standard():
    assert money.build_schedule(1_990_000, 3) == [663_334, 663_333, 663_333]
