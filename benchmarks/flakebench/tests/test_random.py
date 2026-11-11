"""Planted cause: internal randomness. No environmental condition explains these."""

import random

import pytest


@pytest.mark.parametrize("probability", [0.05, 0.2, 0.5])
def test_random_failure(probability):
    assert random.random() >= probability
