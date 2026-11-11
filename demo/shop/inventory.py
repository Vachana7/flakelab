"""In-memory stock levels.

Planted problem (test-order dependency): stock is kept in a module-level
dictionary that tests share. Two tests silently rely on data created by an
earlier test, so they only pass when tests run in the default order.
"""

_STOCK: dict = {}


def add_stock(sku: str, quantity: int) -> int:
    _STOCK[sku] = _STOCK.get(sku, 0) + quantity
    return _STOCK[sku]


def stock_level(sku: str) -> int:
    return _STOCK[sku]  # raises KeyError for unknown products


def reserve(sku: str, quantity: int) -> int:
    available = stock_level(sku)
    if quantity > available:
        raise ValueError(f"only {available} units of {sku} available")
    _STOCK[sku] = available - quantity
    return _STOCK[sku]


def low_stock(sku: str, threshold: int = 5) -> bool:
    return stock_level(sku) < threshold
