"""Text taken from a workflow file must never control the terminal or the comment.

Rule being tested: ANY text that comes from the file under review is
untrusted, wherever in the code it entered. Written before the fix.
"""

import pytest

from pipedelta.delta import Finding, compare
from pipedelta.powers import Power
from pipedelta.report import render_markdown, render_text

BASE = "on: push\npermissions:\n  contents: read\njobs:\n  build:\n    runs-on: x\n    steps:\n      - run: make\n"
NASTY = "x\x1b[31m\nFAKE LINE [link](http://e.example) @everyone \x07\r\x00"


def assert_terminal_safe(text: str) -> None:
    for char in text:
        assert char == "\n" or (char.isprintable()), f"control character {char!r} in output"
    assert not any(line.startswith("FAKE") for line in text.splitlines())


def test_secret_name_from_a_bracket_string_is_cleaned_where_it_is_read():
    # This exact input printed an escape character and a fake line before the fix.
    new = BASE + "        env:\n          K: \"${{ secrets['x\\e[31m\\nFAKE LINE'] }}\"\n"
    findings = compare(BASE, new)
    names = [f.power.name for f in findings if f.power.kind == "secret"]
    assert names
    assert "\x1b" not in names[0]
    assert "\n" not in names[0]
    assert_terminal_safe(render_text({"ci.yml": findings}))


def test_very_long_secret_name_is_cut():
    new = BASE + "        env:\n          K: ${{ secrets['" + "A" * 5000 + "'] }}\n"
    names = [f.power.name for f in compare(BASE, new) if f.power.kind == "secret"]
    assert names
    assert len(names[0]) <= 100


@pytest.mark.parametrize("where", ["message", "path"])
def test_printing_is_safe_even_if_some_code_path_forgets_to_clean(where):
    # Defence at the exit: build a finding by hand, as a future bug might.
    message = NASTY if where == "message" else "ok"
    path = NASTY if where == "path" else "ci.yml"
    results = {path: [Finding("high", Power("secret", "K", "build"), message)]}
    assert_terminal_safe(render_text(results))


def test_markdown_message_is_safe_even_if_some_code_path_forgets_to_clean():
    results = {"ci.yml": [Finding("high", Power("secret", "K", "build"), NASTY)]}
    text = render_markdown(results)
    assert "\x1b" not in text
    assert "\x00" not in text
    assert "[link](http" not in text
    assert "@everyone" not in text
    assert not any(line.startswith("FAKE") for line in text.splitlines())


def test_markdown_path_stays_inside_its_code_span():
    # The path is shown as code, where links and mentions are not active.
    # It must not be able to close the code span or start a new line.
    results = {NASTY + " `break out` ": [Finding("high", Power("secret", "K", "build"), "ok")]}
    heading = next(line for line in render_markdown(results).splitlines() if line.startswith("###"))
    assert heading.startswith("### `")
    assert heading.endswith("`")
    assert "`" not in heading[5:-1]
    assert "\x1b" not in heading
    assert "\x00" not in heading


def test_ordinary_output_is_unchanged_by_the_escaping():
    new = BASE + "        env:\n          K: ${{ secrets.DEPLOY_KEY }}\n"
    text = render_text({".github/workflows/ci.yml": compare(BASE, new)})
    assert "[MEDIUM ] In job 'build', can now read the secret DEPLOY_KEY." in text
    assert ".github/workflows/ci.yml" in text
