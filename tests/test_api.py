"""
Tests for core API endpoints (health, root, users, admins, weather).
"""


def test_root_endpoint(client):
    """GET / returns API info."""
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "endpoints" in body


def test_health_endpoint(client):
    """GET /health returns healthy status."""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"


def test_get_users(client):
    """GET /api/users returns a list."""
    resp = client.get("/api/users")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_hotlines(client):
    """GET /api/hotlines returns a list."""
    resp = client.get("/api/hotlines")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_safety_categories(client):
    """GET /api/safety/categories returns a list."""
    resp = client.get("/api/safety/categories")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_notifications(client):
    """GET /api/notifications returns a list."""
    resp = client.get("/api/notifications")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
