"""Crafted input must not make the reader slow or make it crash.

Found on 17 Nov 2026: ``expressions.bodies()`` used a lazy regex that, when a
``${{`` is never closed, rescans the whole rest of the text for every ``${{``
it contains. The work grows with the square of the text length. A pull
request author controls workflow text, so this let them keep the check busy
for a very long time (a failed or timed-out check fails closed, so it is not a
way past the check; it wastes the project's runner minutes).

Every time limit below is far above the normal cost (a few milliseconds) and
far below the cost before the fix (many seconds), so these tests are not flaky.
"""

import time

from pipedelta import expressions
from pipedelta.delta import compare
from pipedelta.powers import extract_powers

LIMIT_SECONDS = 2.0
N = 20000


def seconds(fn) -> float:  # type: ignore[no-untyped-def]
    started = time.perf_counter()
    fn()
    return time.perf_counter() - started


# ---- what bodies() returns must not change ----------------------------------


def test_bodies_returns_the_text_between_the_markers():
    assert expressions.bodies("a ${{ x }} b ${{ y.z }} c") == [" x ", " y.z "]


def test_bodies_empty_expression():
    assert expressions.bodies("${{}}") == [""]


def test_bodies_ends_at_the_first_closing_marker():
    assert expressions.bodies("${{ a }} }} ${{ b }}") == [" a ", " b "]


def test_bodies_spans_lines():
    assert expressions.bodies("${{ a\n  b }}") == [" a\n  b "]


def test_bodies_a_second_opening_inside_an_expression_stays_inside_it():
    assert expressions.bodies("${{ a ${{ b }}") == [" a ${{ b "]


def test_bodies_unclosed_expression_is_ignored():
    assert expressions.bodies("${{ never closed") == []
    assert expressions.bodies("${{ ok }} ${{ never closed") == [" ok "]


def test_bodies_no_markers():
    assert expressions.bodies("") == []
    assert expressions.bodies("plain text } { $ {{ }}") == []


# ---- speed -------------------------------------------------------------------


def test_many_unclosed_openings_are_read_in_linear_time():
    assert seconds(lambda: expressions.bodies("${{ " * N)) < LIMIT_SECONDS


def test_the_same_through_the_whole_reader():
    doc = "on: push\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: |\n          echo "
    text = doc + "${{ " * 8000 + "\n"
    assert seconds(lambda: extract_powers(text)) < LIMIT_SECONDS


def test_the_same_through_a_comparison():
    doc = "on: push\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: |\n          echo "
    old = doc + "hello\n"
    new = doc + "${{ " * 8000 + "\n"
    assert seconds(lambda: compare(old, new)) < LIMIT_SECONDS


def test_many_complete_expressions_are_read_in_linear_time():
    assert seconds(lambda: expressions.has_untrusted_value("${{ a }}" * N)) < LIMIT_SECONDS


def test_one_very_long_body_is_read_in_linear_time():
    assert (
        seconds(lambda: expressions.has_untrusted_value("${{ " + "a.b " * N + "}}")) < LIMIT_SECONDS
    )


def test_a_very_long_unclosed_string_is_read_in_linear_time():
    assert (
        seconds(lambda: expressions.has_untrusted_value("${{ '" + "x" * 200000 + " }}"))
        < LIMIT_SECONDS
    )


# ---- depth -------------------------------------------------------------------


def test_deeply_nested_brackets_do_not_crash():
    text = "${{ " + "a[" * 3000 + "b" + "]" * 3000 + " }}"
    expressions.has_untrusted_value(text)  # must return, not raise RecursionError


def test_deeply_nested_parentheses_do_not_crash():
    text = "${{ " + "f(" * 3000 + "b" + ")" * 3000 + " }}"
    expressions.has_untrusted_value(text)


def test_many_unclosed_square_brackets_are_read_in_linear_time():
    assert (
        seconds(lambda: expressions.has_untrusted_value("${{ " + "a[" * N + " }}")) < LIMIT_SECONDS
    )


def test_stray_closing_brackets_are_ignored():
    assert expressions.references("a]]") == [("a",)]


def test_references_inside_brackets_are_still_found_and_come_first():
    assert expressions.references("secrets[matrix.name]") == [("matrix", "name"), ("secrets", None)]
    assert expressions.references("a[b[c.d]]") == [("c", "d"), ("b", None), ("a", None)]
