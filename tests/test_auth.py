"""
Tests for user authentication endpoints:
  POST /api/auth/register
  POST /api/auth/login
  POST /api/auth/refresh
"""

import uuid


# ---------------------------------------------------------------------------
# POST /api/auth/register
# ---------------------------------------------------------------------------


def test_register_success(client):
    """A new user can register with valid data."""
    unique = uuid.uuid4().hex[:8]
    resp = client.post(
        "/api/auth/register",
        json={
            "first_name": "Test",
            "last_name": "User",
            "email": f"test_{unique}@example.com",
            "password": "SecurePass123",
            "phone_number": f"09{unique[:9]}",
            "house_address": "123 Test St",
            "barangay": "TestBarangay",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


def test_register_duplicate_email(client):
    """Registering with an already-used email returns 409."""
    unique = uuid.uuid4().hex[:8]
    payload = {
        "first_name": "Dup",
        "last_name": "User",
        "email": f"dup_{unique}@example.com",
        "password": "SecurePass123",
        "phone_number": f"09{unique[:9]}",
        "house_address": "456 Main",
        "barangay": "Brgy1",
    }
    # First registration
    resp1 = client.post("/api/auth/register", json=payload)
    assert resp1.status_code == 201

    # Second registration — same email, different phone
    payload["phone_number"] = f"09{''.join(reversed(unique[:9]))}"
    resp2 = client.post("/api/auth/register", json=payload)
    assert resp2.status_code == 409


def test_register_short_password(client):
    """Password shorter than 8 characters is rejected (422)."""
    resp = client.post(
        "/api/auth/register",
        json={
            "first_name": "A",
            "last_name": "B",
            "email": "short@example.com",
            "password": "short",
            "phone_number": "09123456789",
            "house_address": "x",
            "barangay": "y",
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------


def test_login_success(client):
    """A registered user can log in with correct credentials."""
    unique = uuid.uuid4().hex[:8]
    email = f"login_{unique}@example.com"
    password = "MyPassword99"

    # Register first
    client.post(
        "/api/auth/register",
        json={
            "first_name": "Login",
            "last_name": "Test",
            "email": email,
            "password": password,
            "phone_number": f"09{unique[:9]}",
            "house_address": "789 Elm",
            "barangay": "Brgy2",
        },
    )

    # Login
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


def test_login_wrong_password(client):
    """Login with wrong password returns 401."""
    unique = uuid.uuid4().hex[:8]
    email = f"wrong_{unique}@example.com"

    client.post(
        "/api/auth/register",
        json={
            "first_name": "Wrong",
            "last_name": "Pass",
            "email": email,
            "password": "CorrectPassword1",
            "phone_number": f"09{unique[:9]}",
            "house_address": "addr",
            "barangay": "brgy",
        },
    )

    resp = client.post("/api/auth/login", json={"email": email, "password": "WrongPassword1"})
    assert resp.status_code == 401


def test_login_nonexistent_email(client):
    """Login with an email that was never registered returns 401."""
    resp = client.post(
        "/api/auth/login",
        json={"email": "nobody@nowhere.test", "password": "whatever123"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/auth/refresh
# ---------------------------------------------------------------------------


def test_refresh_success(client):
    """A valid refresh token yields a new token pair."""
    unique = uuid.uuid4().hex[:8]
    email = f"refresh_{unique}@example.com"

    reg = client.post(
        "/api/auth/register",
        json={
            "first_name": "Refresh",
            "last_name": "Test",
            "email": email,
            "password": "RefreshPass1",
            "phone_number": f"09{unique[:9]}",
            "house_address": "addr",
            "barangay": "brgy",
        },
    )
    refresh_token = reg.json()["refresh_token"]

    resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


def test_refresh_with_access_token_fails(client):
    """Using an access token as a refresh token should fail."""
    unique = uuid.uuid4().hex[:8]
    email = f"badref_{unique}@example.com"

    reg = client.post(
        "/api/auth/register",
        json={
            "first_name": "Bad",
            "last_name": "Refresh",
            "email": email,
            "password": "SomePass123",
            "phone_number": f"09{unique[:9]}",
            "house_address": "addr",
            "barangay": "brgy",
        },
    )
    access_token = reg.json()["access_token"]

    resp = client.post("/api/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401
