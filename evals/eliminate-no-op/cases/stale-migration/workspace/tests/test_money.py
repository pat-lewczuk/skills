from decimal import Decimal

from checkout.money import to_minor_units


def test_to_minor_units() -> None:
    assert to_minor_units(Decimal("12.34")) == 1234
