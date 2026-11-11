from shop.inventory import add_stock, low_stock, reserve


def test_add_stock():
    assert add_stock("SKU-1", 5) == 5


def test_reserve_stock():
    # Relies on test_add_stock having created SKU-1 (shared state).
    assert reserve("SKU-1", 2) == 3


def test_low_stock_alert():
    # Also relies on SKU-1 existing.
    assert low_stock("SKU-1") is True
