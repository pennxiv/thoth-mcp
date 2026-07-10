"""Lightweight end-to-end integration contract tests.

These tests validate the expected seeded flows and artifact presence.
Runtime Docker execution is delegated to scripts/run_integration_tests.sh.
"""
from pathlib import Path

import pytest

from thoth_mcp.tools.discovery import list_datasources
from thoth_mcp.tools.mysql import query_mysql
from thoth_mcp.tools.redis import query_redis
from thoth_mcp.config import MySQLDatasourceConfig, RedisDatasourceConfig


class DummyConfig:
    def __init__(self):
        self.mysql = {
            "test_db": MySQLDatasourceConfig(
                host="mysql", port=3306, user="thoth", password="thoth", database="thoth"
            )
        }
        self.redis = {
            "cache": RedisDatasourceConfig(host="redis", port=6379, db=0)
        }
        self.postgres = {}


class DummyMySQLPool:
    def __init__(self):
        self._pools = {"test_db": object()}

    async def execute(self, datasource, sql, params=()):
        if datasource != "test_db":
            raise ValueError("Unknown datasource")
        if "DROP" in sql.upper():
            raise Exception("should not execute unsafe sql")
        return [{"id": 1, "name": "Alice", "email": "alice@example.com"}]


class DummyRedisPool:
    def __init__(self):
        self._clients = {"cache": object()}

    async def execute_pipeline(self, datasource, commands):
        if datasource != "cache":
            raise ValueError("Unknown instance")
        command = commands[0][0].upper()
        if command == "GET":
            return ["Alice"]
        raise Exception("unexpected command")


@pytest.mark.asyncio
async def test_datasource_discovery_flow():
    result = await list_datasources(DummyConfig())
    assert "test_db" in result
    assert "cache" in result


@pytest.mark.asyncio
async def test_mysql_query_success_flow():
    result = await query_mysql(DummyMySQLPool(), "test_db", "SELECT * FROM users LIMIT 1")
    assert "Alice" in result


@pytest.mark.asyncio
async def test_redis_query_success_flow():
    result = await query_redis(DummyRedisPool(), "cache", "GET", ["user:1"])
    assert "Alice" in result


@pytest.mark.asyncio
async def test_rejected_unsafe_operation_flow():
    result = await query_redis(DummyRedisPool(), "cache", "SET", ["user:1", "Mallory"])
    assert "rejected" in result.lower()


def test_integration_artifacts_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "Dockerfile").exists()
    assert (root / "docker-compose.yml").exists()
    assert (root / "scripts" / "run_integration_tests.sh").exists()
