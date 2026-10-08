from pricing.discount import apply_discount


def test_discount_applied():
    assert apply_discount(100, 0.25) == 75


def test_zero_rate_unchanged():
    assert apply_discount(50, 0) == 50


def test_never_negative():
    assert apply_discount(10, 1.5) == 0
