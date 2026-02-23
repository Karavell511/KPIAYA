from datetime import timedelta

import pytest

pytest.importorskip("jose")

from app.core.security import create_token, decode_token


def test_token_roundtrip():
    token = create_token("1", "access", timedelta(minutes=5))
    payload = decode_token(token, "access")
    assert payload["sub"] == "1"
    assert payload["type"] == "access"
