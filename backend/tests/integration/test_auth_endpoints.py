import pytest
from httpx import AsyncClient


class TestSignup:
    @pytest.mark.asyncio
    async def test_signup_returns_tokens(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "test@example.com",
                "password": "password123",  # pragma: allowlist secret
                "full_name": "Test User",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_duplicate_email_returns_409(self, client: AsyncClient) -> None:
        payload = {
            "email": "dup@example.com",
            "password": "pass123",  # pragma: allowlist secret
            "full_name": "Dup User",
        }
        await client.post("/api/v1/auth/signup", json=payload)
        response = await client.post("/api/v1/auth/signup", json=payload)
        assert response.status_code == 409


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_with_valid_credentials(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "login@example.com",
                "password": "pass123",  # pragma: allowlist secret
                "full_name": "Login User",
            },
        )
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "login@example.com",
                "password": "pass123",  # pragma: allowlist secret
            },
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(self, client: AsyncClient) -> None:
        await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "wp@example.com",
                "password": "correct",  # pragma: allowlist secret
                "full_name": "WP User",
            },
        )
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "wp@example.com",
                "password": "wrong",  # pragma: allowlist secret
            },
        )
        assert response.status_code == 401


class TestMe:
    @pytest.mark.asyncio
    async def test_me_returns_user(self, client: AsyncClient) -> None:
        signup = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "me@example.com",
                "password": "pass123",  # pragma: allowlist secret
                "full_name": "Me User",
            },
        )
        token = signup.json()["access_token"]
        response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["email"] == "me@example.com"

    @pytest.mark.asyncio
    async def test_me_without_token_returns_403(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/me")
        assert response.status_code in (401, 403)
