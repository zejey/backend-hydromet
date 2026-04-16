"""
Shared test fixtures for the Hydromet API test suite.

Provides a FastAPI TestClient that talks to the real app instance
but uses httpx for async-compatible transport.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    """Synchronous test client reused across the entire test session."""
    with TestClient(app) as c:
        yield c
