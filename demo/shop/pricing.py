"""Pricing rules. No planted problems: these tests should stay stable."""


def apply_discount(price: float, percent: float) -> float:
    if not 0 <= percent <= 100:
        raise ValueError("discount must be between 0 and 100")
    return round(price * (1 - percent / 100), 2)


def add_gst(price: float, rate: float = 18.0) -> float:
    return round(price * (1 + rate / 100), 2)
