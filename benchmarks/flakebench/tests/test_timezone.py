"""Planted cause: timezone assumptions."""

import time

EVENING_UTC = 1795291200  # 2026-11-21 20:00 UTC


def test_timezone_report_title():
    assert time.strftime("%H:%M", time.localtime(EVENING_UTC)) == "20:00"


def test_timezone_date_boundary():
    # 20:00 UTC is already the next day at UTC+5:30.
    assert time.strftime("%Y-%m-%d", time.localtime(EVENING_UTC)) == "2026-11-21"
