from shop.auth import new_session_token


def test_session_tokens_unique():
    tokens = {new_session_token("alice") for _ in range(40)}
    assert len(tokens) == 40
