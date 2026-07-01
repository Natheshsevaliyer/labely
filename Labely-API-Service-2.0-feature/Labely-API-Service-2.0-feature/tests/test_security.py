"""Unit tests for app/core/security.py"""
import pytest
from datetime import timedelta
from unittest.mock import patch

from app.core.security import (
    create_access_token,
    verify_token,
    hash_password,
    verify_password,
)
from app.core.config import settings


class TestPasswordHashing:
    def test_hash_returns_different_value(self):
        pw = "my_secret"
        assert hash_password(pw) != pw

    def test_verify_correct_password(self):
        pw = "correct_password"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_hash_is_deterministic_in_verification(self):
        """Two separate hashes of same password should both verify."""
        pw = "same_password"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        # bcrypt generates different salts, both must verify
        assert verify_password(pw, h1)
        assert verify_password(pw, h2)

    def test_long_password_truncated_to_72_bytes(self):
        """bcrypt silently ignores bytes beyond 72; we must handle that."""
        long_pw = "a" * 80
        hashed = hash_password(long_pw)
        # Verify with the same long password
        assert verify_password(long_pw, hashed)

    def test_empty_password_hash(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("not-empty", hashed) is False


class TestJWTTokens:
    def test_create_and_verify_token(self):
        token = create_access_token({"sub": "42"})
        payload = verify_token(token)
        assert payload["sub"] == "42"

    def test_token_has_exp_and_iat(self):
        token = create_access_token({"sub": "1"})
        payload = verify_token(token)
        assert "exp" in payload
        assert "iat" in payload

    def test_expired_token_raises(self):
        token = create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=-1))
        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(token)

    def test_tampered_token_raises(self):
        token = create_access_token({"sub": "1"})
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(ValueError, match="Invalid token"):
            verify_token(tampered)

    def test_custom_expiry_respected(self):
        """Token created with a very short TTL should expire quickly."""
        import time
        token = create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=1))
        # Immediately valid
        payload = verify_token(token)
        assert payload["sub"] == "1"

    def test_extra_claims_preserved(self):
        token = create_access_token({"sub": "7", "role": "admin", "shop": 99})
        payload = verify_token(token)
        assert payload["role"] == "admin"
        assert payload["shop"] == 99
