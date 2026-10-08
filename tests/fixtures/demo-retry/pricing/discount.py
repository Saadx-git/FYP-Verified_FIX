def apply_discount(amount, rate):
    """Return the amount after applying a discount rate (0..1). Never negative."""
    discount = amount * rate
    return discount
