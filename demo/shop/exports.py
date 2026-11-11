"""Catalogue CSV export, built in a worker process.

Planted problem (memory): the export builds the whole file in memory
(about 200 MB). On a machine with little RAM the worker process is killed by
the operating system and the export fails.
"""

import multiprocessing

EXPORT_SIZE_MB = 200
ROW = b"SKU-000000,Widget,19.99,in_stock\n"


class ExportFailed(RuntimeError):
    pass


def _build_export(size_mb: int) -> None:
    rows = (size_mb * 1024 * 1024) // len(ROW)
    data = ROW * rows  # the whole CSV in memory at once
    assert len(data) > 0


def export_catalog(size_mb: int = EXPORT_SIZE_MB) -> str:
    ctx = multiprocessing.get_context("spawn")
    worker = ctx.Process(target=_build_export, args=(size_mb,))
    worker.start()
    worker.join(120)
    if worker.exitcode != 0:
        raise ExportFailed(f"export worker exited with code {worker.exitcode}")
    return "catalog.csv"
