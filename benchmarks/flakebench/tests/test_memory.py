"""Planted cause: memory. Allocations above / below a 128 MB container limit."""

from bench.helpers import allocate_in_worker


def test_memory_200mb():
    assert allocate_in_worker(200) == 0


def test_memory_160mb():
    assert allocate_in_worker(160) == 0


def test_memory_40mb_control():
    # Fits in 128 MB: should stay stable under every condition.
    assert allocate_in_worker(40) == 0
