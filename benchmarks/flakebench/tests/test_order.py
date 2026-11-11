"""Planted cause: test-order dependency through shared module state.

Two kinds from the literature (iDFlakies terminology):
* brittle tests need state created by an earlier test (fail when run first);
* victim tests break when a polluter test runs before them.
"""

from bench import state


def test_order_setup():
    state.INVENTORY["SKU-1"] = 5
    assert state.INVENTORY["SKU-1"] == 5


def test_order_brittle_reserve():
    state.INVENTORY["SKU-1"] -= 2
    assert state.INVENTORY["SKU-1"] == 3


def test_order_brittle_report():
    assert "SKU-1" in state.INVENTORY


def test_order_victim_currency():
    assert state.SETTINGS["currency"] == "INR"


def test_order_polluter():
    state.SETTINGS["currency"] = "USD"  # never restored
    assert state.SETTINGS["currency"] == "USD"
