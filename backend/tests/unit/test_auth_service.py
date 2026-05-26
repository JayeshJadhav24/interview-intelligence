import pytest

from app.exceptions import UnauthorizedError
from app.services.auth import create_tokens, decode_token, hash_password, verify_password


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self) -> None:
        hashed = hash_password("secret123")
        assert hashed != "secret123"

    def test_correct_password_verifies(self) -> None:
        hashed = hash_password("mypassword")
        assert verify_password("mypassword", hashed) is True

    def test_wrong_password_fails(self) -> None:
        hashed = hash_password("mypassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_different_hashes_for_same_password(self) -> None:
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt uses random salt


class TestJWTTokens:
    def test_access_token_round_trip(self) -> None:
        tokens = create_tokens("user-123")
        user_id = decode_token(tokens.access_token, expected_type="access")
        assert user_id == "user-123"

    def test_refresh_token_round_trip(self) -> None:
        tokens = create_tokens("user-456")
        user_id = decode_token(tokens.refresh_token, expected_type="refresh")
        assert user_id == "user-456"

    def test_wrong_token_type_raises(self) -> None:
        tokens = create_tokens("user-789")
        with pytest.raises(UnauthorizedError):
            decode_token(tokens.access_token, expected_type="refresh")

    def test_invalid_token_raises(self) -> None:
        with pytest.raises(UnauthorizedError):
            decode_token("not.a.valid.token", expected_type="access")

    def test_token_response_has_bearer_type(self) -> None:
        tokens = create_tokens("user-abc")
        assert tokens.token_type == "bearer"
