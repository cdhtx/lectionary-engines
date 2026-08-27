"""
Pytest configuration for web tests
"""

import pytest
from web.database import init_db, close_db


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Initialize the test database before any tests run."""
    init_db()
    yield
    close_db()
