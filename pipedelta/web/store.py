"""Local storage for the web app: connected repositories and analysis history.

One SQLite file, standard library only. Every statistic the dashboard shows is
computed from these rows. Nothing is stored that the engine did not produce,
and the GitHub token is never stored.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    full_name TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    added_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE TABLE IF NOT EXISTS analyses (
    id         TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    repo       TEXT,
    mode       TEXT NOT NULL,
    source     TEXT NOT NULL,
    title      TEXT NOT NULL,
    level      TEXT NOT NULL,
    high       INTEGER NOT NULL,
    medium     INTEGER NOT NULL,
    low        INTEGER NOT NULL,
    files      INTEGER NOT NULL,
    data       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS analyses_created ON analyses (created_at DESC);
CREATE INDEX IF NOT EXISTS analyses_repo ON analyses (repo);
"""

SUMMARY_COLUMNS = "id, created_at, repo, mode, source, title, level, high, medium, low, files"


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    # ---- repositories ------------------------------------------------------

    def save_repo(self, repo: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO repos (full_name, data) VALUES (?, ?) "
                "ON CONFLICT(full_name) DO UPDATE SET data = excluded.data",
                (repo["full_name"], json.dumps(repo)),
            )
            self._db.commit()

    def repos(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT data, added_at FROM repos ORDER BY added_at DESC"
            ).fetchall()
            result = []
            for row in rows:
                repo = json.loads(row["data"])
                repo["added_at"] = row["added_at"]
                last = self._db.execute(
                    "SELECT id, level, created_at, title FROM analyses WHERE repo = ? "
                    "ORDER BY created_at DESC, rowid DESC LIMIT 1",
                    (repo["full_name"],),
                ).fetchone()
                repo["last_analysis"] = dict(last) if last else None
                result.append(repo)
        return result

    def remove_repo(self, full_name: str) -> bool:
        with self._lock:
            cursor = self._db.execute("DELETE FROM repos WHERE full_name = ?", (full_name,))
            self._db.commit()
            return cursor.rowcount > 0

    # ---- analyses ----------------------------------------------------------

    def save_analysis(self, result: dict[str, Any]) -> None:
        summary = result["summary"]
        with self._lock:
            self._db.execute(
                "INSERT INTO analyses (id, created_at, repo, mode, source, title, level, "
                "high, medium, low, files, data) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    result["id"],
                    result["created_at"],
                    result.get("repo"),
                    result["mode"],
                    result["source"],
                    result["title"],
                    summary["level"],
                    summary["counts"]["high"],
                    summary["counts"]["medium"],
                    summary["counts"]["low"],
                    summary["files"],
                    json.dumps(result),
                ),
            )
            self._db.commit()

    def analyses(self, repo: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = f"SELECT {SUMMARY_COLUMNS} FROM analyses"
        args: list[Any] = []
        if repo:
            query += " WHERE repo = ?"
            args.append(repo)
        query += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        args.append(max(1, min(limit, 500)))
        with self._lock:
            rows = self._db.execute(query, args).fetchall()
        return [self._summary(row) for row in rows]

    @staticmethod
    def _summary(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "repo": row["repo"],
            "mode": row["mode"],
            "source": row["source"],
            "title": row["title"],
            "level": row["level"],
            "counts": {"high": row["high"], "medium": row["medium"], "low": row["low"]},
            "files": row["files"],
        }

    def analysis(self, analysis_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT data FROM analyses WHERE id = ?", (analysis_id,)
            ).fetchone()
        return None if row is None else json.loads(row["data"])

    def remove_analysis(self, analysis_id: str) -> bool:
        with self._lock:
            cursor = self._db.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
            self._db.commit()
            return cursor.rowcount > 0

    # ---- dashboard numbers, all computed from the rows above ---------------

    def stats(self) -> dict[str, Any]:
        with self._lock:
            rows = self._db.execute(
                f"SELECT {SUMMARY_COLUMNS}, data FROM analyses ORDER BY created_at ASC, rowid ASC"
            ).fetchall()
            repo_count = self._db.execute("SELECT COUNT(*) FROM repos").fetchone()[0]
        levels: Counter[str] = Counter()
        severity = {"high": 0, "medium": 0, "low": 0}
        kinds: Counter[str] = Counter()
        confidence: Counter[str] = Counter()
        trend = []
        latest_by_repo: dict[str, str] = {}
        for row in rows:
            levels[row["level"]] += 1
            for name in severity:
                severity[name] += row[name]
            data = json.loads(row["data"])
            kinds.update(data["summary"]["kinds"])
            confidence.update(data["summary"]["confidence"])
            trend.append(
                {
                    "id": row["id"],
                    "at": row["created_at"],
                    "title": row["title"],
                    "level": row["level"],
                    "high": row["high"],
                    "medium": row["medium"],
                    "low": row["low"],
                }
            )
            if row["repo"]:
                latest_by_repo[row["repo"]] = row["level"]
        return {
            "analyses": len(rows),
            "repositories": repo_count,
            "levels": {name: levels.get(name, 0) for name in ("high", "medium", "low", "none")},
            "findings": severity,
            "kinds": dict(kinds.most_common()),
            "confidence": {name: confidence.get(name, 0) for name in ("high", "medium", "low")},
            "trend": trend[-30:],
            "repos_at_risk": sum(1 for level in latest_by_repo.values() if level == "high"),
        }
