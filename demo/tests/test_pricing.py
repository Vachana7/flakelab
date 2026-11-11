import pytest
from shop.pricing import add_gst, apply_discount


def test_discount():
    assert apply_discount(200.0, 10) == 180.0


def test_gst():
    assert add_gst(100.0) == 118.0


def test_invalid_discount():
    with pytest.raises(ValueError):
        apply_discount(100.0, 150)
