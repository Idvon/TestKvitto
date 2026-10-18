"""Unit tests for the payment status machine in app.status."""
from app.status import PaymentStatus, is_allowed

EXPECTED_ALLOWED = {
    (PaymentStatus.PENDING, PaymentStatus.SUCCEEDED),
    (PaymentStatus.PENDING, PaymentStatus.FAILED),
    (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED),
}


def test_exactly_the_three_transitions_are_allowed():
    observed = {
        (src, dst)
        for src in PaymentStatus
        for dst in PaymentStatus
        if is_allowed(src, dst)
    }
    assert observed == EXPECTED_ALLOWED


def test_forbidden_pairs_are_rejected():
    for src in PaymentStatus:
        for dst in PaymentStatus:
            if (src, dst) not in EXPECTED_ALLOWED:
                assert not is_allowed(src, dst)
