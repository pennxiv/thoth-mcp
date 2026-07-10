"""Shared pytest fixtures for configuration tests."""

import pytest


@pytest.fixture
def sample_mysql_config():
    """Sample MySQL datasource configuration."""
    return {
        "host": "localhost",
        "port": 3306,
        "user": "test_user",
        "password": "test_password",
        "database": "test_db",
    }


@pytest.fixture
def sample_redis_config():
    """Sample Redis datasource configuration."""
    return {
        "host": "localhost",
        "port": 6379,
        "db": 0,
    }
