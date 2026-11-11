from shop.reports import report_title

EXPO_DAY_MIDNIGHT_UTC = 1795219200  # 2026-11-21 00:00 UTC


def test_report_title():
    assert report_title(EXPO_DAY_MIDNIGHT_UTC) == "Daily sales report: 2026-11-21 00:00"
