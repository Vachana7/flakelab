import time

STATE = []


def test_first():
    STATE.append("ready")


def test_needs_first():
    assert STATE == ["ready"]


def test_timezone():
    assert time.strftime("%H:%M", time.localtime(0)) == "00:00"


def test_always_passes():
    assert 1 + 1 == 2
