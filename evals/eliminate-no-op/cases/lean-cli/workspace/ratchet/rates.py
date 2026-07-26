from decimal import Decimal


def apply_fx(cents: int, rate: Decimal) -> int:
    return int((Decimal(cents) * rate).to_integral_value())
