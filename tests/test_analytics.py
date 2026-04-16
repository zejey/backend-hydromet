"""
Tests for analytics endpoints:
  GET /api/analytics/overview
  GET /api/analytics/users
  GET /api/analytics/logins
  GET /api/analytics/notifications
"""


def test_analytics_overview(client):
    """GET /api/analytics/overview returns counts."""
    resp = client.get("/api/analytics/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_users" in body
    assert "total_notifications" in body


def test_analytics_users(client):
    """GET /api/analytics/users returns a time series."""
    resp = client.get("/api/analytics/users?interval=month")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_analytics_logins(client):
    """GET /api/analytics/logins returns a time series."""
    resp = client.get("/api/analytics/logins?interval=day")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_analytics_notifications(client):
    """GET /api/analytics/notifications returns a time series."""
    resp = client.get("/api/analytics/notifications")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
