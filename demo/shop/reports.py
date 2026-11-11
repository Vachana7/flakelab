"""Sales report titles.

Planted problem (timezone assumption): the title uses the machine's local
time. The test's expected value was written on a machine set to UTC, so it
fails on any runner in a different timezone.
"""

import time


def report_title(epoch_seconds: int) -> str:
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(epoch_seconds))
    return f"Daily sales report: {stamp}"
