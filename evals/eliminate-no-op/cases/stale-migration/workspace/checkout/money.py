from decimal import Decimal


def to_minor_units(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value())


def match_currency(a: str, b: str) -> bool:
    match (a, b):
        case (x, y) if x == y:
            return True
        case _:
            return False
