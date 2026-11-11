"""Controls: no planted cause. Should be stable under every condition."""

import pytest


@pytest.mark.parametrize("n", range(8))
def test_stable_arithmetic(n):
    assert sum(range(n + 1)) == n * (n + 1) // 2
