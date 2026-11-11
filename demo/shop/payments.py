"""Payment authorisation with a fraud check that has a fixed CPU budget.

Planted problem (CPU / timing): the test asserts a wall-clock SLA. On a fast,
idle machine the fraud check finishes well inside it; when CPU is scarce the
same amount of work takes longer in real time and the SLA assertion fails.
"""

import hashlib
import time

FRAUD_CHECK_CPU_BUDGET = 0.06  # seconds of CPU time the fraud model may use
PAYMENT_SLA_SECONDS = 0.15  # authorisation must answer within this time


def fraud_score(card_number: str) -> float:
    """Return a risk score between 0 and 1.

    Like many real fraud models, it evaluates as many rules as it can within a
    fixed compute budget (here: repeated hashing until the budget is used).
    """
    score = hashlib.sha256(card_number.encode()).digest()[0] / 255
    digest = card_number.encode()
    start = time.process_time()
    while time.process_time() - start < FRAUD_CHECK_CPU_BUDGET:
        digest = hashlib.sha256(digest).digest()
    return score


def authorize(card_number: str, amount: float) -> dict:
    started = time.perf_counter()
    score = fraud_score(card_number)
    elapsed = time.perf_counter() - started
    return {"approved": score < 0.9 and amount <= 10_000, "risk": score, "elapsed": elapsed}


def refund(amount: float, fee_percent: float = 2.0) -> float:
    if amount <= 0:
        raise ValueError("refund amount must be positive")
    return round(amount * (1 - fee_percent / 100), 2)
