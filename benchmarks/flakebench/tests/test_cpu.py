"""Planted cause: CPU / timing. Wall-clock deadlines on fixed CPU work."""

from bench.helpers import timed_cpu_work


def test_cpu_strong():
    assert timed_cpu_work(0.06) < 0.15


def test_cpu_medium():
    assert timed_cpu_work(0.04) < 0.12


def test_cpu_marginal():
    # Small margin: under a 0.25-core limit it fails only some of the time.
    assert timed_cpu_work(0.03) < 0.14
