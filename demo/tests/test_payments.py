from shop.payments import PAYMENT_SLA_SECONDS, authorize, refund


def test_authorize_within_sla():
    result = authorize("4111111111111111", 499.0)
    assert result["elapsed"] < PAYMENT_SLA_SECONDS, (
        f"authorisation took {result['elapsed']:.3f}s, SLA is {PAYMENT_SLA_SECONDS}s"
    )


def test_refund_deducts_fee():
    assert refund(100.0) == 98.0
