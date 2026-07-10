"""Tests for Redis and Discovery MCP tools."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from thoth_mcp.tools.redis import query_redis
from thoth_mcp.tools.discovery import list_datasources
from thoth_mcp.config import MySQLDatasourceConfig, RedisDatasourceConfig


def _make_redis_pool_manager(instances=None):
    """Create a mock RedisPoolManager."""
    mock = MagicMock()
    inst_list = instances or []
    mock._clients = {name: MagicMock() for name in inst_list}
    mock._pools = {name: MagicMock() for name in inst_list}

    async def _execute_pipeline(name, commands):
        if name not in inst_list:
            raise ValueError(f"Unknown instance: {name}")
        return ["result"]

    mock.execute_pipeline = AsyncMock(side_effect=_execute_pipeline)
    return mock


def _make_config(mysql=None, redis=None, postgres=None):
    """Create a mock DatasourcesConfig."""
    config = MagicMock()
    config.mysql = mysql or {}
    config.redis = redis or {}
    config.postgres = postgres or {}
    return config


class TestQueryRedis:
    """Test query_redis tool function."""

    @pytest.mark.asyncio
    async def test_query_redis_get_success(self):
        """GET command returns formatted string result."""
        pool_manager = _make_redis_pool_manager(["cache"])
        pool_manager.execute_pipeline = AsyncMock(return_value=["my_value"])

        result = await query_redis(pool_manager, "cache", "GET", ["user:123"])

        assert "my_value" in result
        pool_manager.execute_pipeline.assert_called_once_with(
            "cache", [("GET", "user:123")]
        )

    @pytest.mark.asyncio
    async def test_query_redis_rejects_unsafe_command(self):
        """Unsafe command (SET) is rejected with friendly message."""
        pool_manager = _make_redis_pool_manager(["cache"])

        result = await query_redis(pool_manager, "cache", "SET", ["key1", "value1"])

        assert "Command rejected" in result
        pool_manager.execute_pipeline.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_redis_unknown_datasource(self):
        """Unknown datasource returns descriptive error."""
        pool_manager = _make_redis_pool_manager(["cache", "session_store"])
        pool_manager.execute_pipeline = AsyncMock(
            side_effect=ValueError("Unknown instance: unknown")
        )

        result = await query_redis(pool_manager, "unknown", "GET", ["key1"])

        assert "Unknown instance: unknown" in result

    @pytest.mark.asyncio
    async def test_query_redis_execution_error(self):
        """Execution error returns sanitized message."""
        pool_manager = _make_redis_pool_manager(["cache"])
        pool_manager.execute_pipeline = AsyncMock(
            side_effect=Exception("Connection refused")
        )

        result = await query_redis(pool_manager, "cache", "GET", ["key1"])

        assert "Command execution failed" in result
        assert "host" not in result.lower()
        assert "password" not in result.lower()

    @pytest.mark.asyncio
    async def test_query_redis_no_args(self):
        """Command with args works (e.g., EXISTS with key)."""
        pool_manager = _make_redis_pool_manager(["cache"])
        pool_manager.execute_pipeline = AsyncMock(return_value=[True])

        result = await query_redis(pool_manager, "cache", "EXISTS", ["mykey"])

        # EXISTS returns boolean, formatted as "true"
        assert "true" in result

    @pytest.mark.asyncio
    async def test_query_redis_empty_result(self):
        """Empty pipeline result returns 'No result' message."""
        pool_manager = _make_redis_pool_manager(["cache"])
        pool_manager.execute_pipeline = AsyncMock(return_value=[])

        result = await query_redis(pool_manager, "cache", "GET", ["nonexistent"])

        assert "No result" in result

    @pytest.mark.asyncio
    async def test_query_redis_hgetall(self):
        """HGETALL command returns formatted hash result."""
        pool_manager = _make_redis_pool_manager(["cache"])
        pool_manager.execute_pipeline = AsyncMock(
            return_value=[{"field1": "val1", "field2": "val2"}]
        )

        result = await query_redis(pool_manager, "cache", "HGETALL", ["myhash"])

        assert "field1" in result
        assert "val1" in result

    @pytest.mark.asyncio
    async def test_query_redis_keys_rejected(self):
        """KEYS command is rejected (not in allowlist, dangerous in production)."""
        pool_manager = _make_redis_pool_manager(["cache"])

        result = await query_redis(pool_manager, "cache", "KEYS", ["*"])

        assert "Command rejected" in result
        pool_manager.execute_pipeline.assert_not_called()


class TestListDatasources:
    """Test list_datasources tool function."""

    @pytest.mark.asyncio
    async def test_list_datasources_both_types(self):
        """Shows both MySQL and Redis datasources grouped by type."""
        config = _make_config(
            mysql={
                "prod_db": MySQLDatasourceConfig(
                    host="db.example.com", port=3306, user="admin", password="secret", database="production"
                ),
            },
            redis={
                "cache": RedisDatasourceConfig(host="redis.example.com", port=6379),
            },
        )

        result = await list_datasources(config)

        assert "MySQL Datasources" in result
        assert "Redis Instances" in result
        assert "prod_db" in result
        assert "cache" in result
        assert "db.example.com" in result
        assert "redis.example.com" in result

    @pytest.mark.asyncio
    async def test_list_datasources_mysql_only(self):
        """Only MySQL section shown when no Redis configured."""
        config = _make_config(
            mysql={
                "analytics": MySQLDatasourceConfig(
                    host="analytics.db", port=3306, user="reader", password="secret", database="analytics"
                ),
            },
        )

        result = await list_datasources(config)

        assert "MySQL Datasources" in result
        assert "analytics" in result
        assert "Redis" not in result

    @pytest.mark.asyncio
    async def test_list_datasources_redis_only(self):
        """Only Redis section shown when no MySQL configured."""
        config = _make_config(
            redis={
                "session_store": RedisDatasourceConfig(host="redis.local", port=6379, db=1),
            },
        )

        result = await list_datasources(config)

        assert "Redis Instances" in result
        assert "session_store" in result
        assert "MySQL" not in result

    @pytest.mark.asyncio
    async def test_list_datasources_empty(self):
        """No datasources returns appropriate message."""
        config = _make_config()

        result = await list_datasources(config)

        assert "No datasources configured" in result

    @pytest.mark.asyncio
    async def test_list_datasources_sorted(self):
        """Datasources are sorted by name within each section."""
        config = _make_config(
            mysql={
                "z_db": MySQLDatasourceConfig(host="z", port=3306, user="u", password="p", database="z"),
                "a_db": MySQLDatasourceConfig(host="a", port=3306, user="u", password="p", database="a"),
            },
        )

        result = await list_datasources(config)

        a_pos = result.index("a_db")
        z_pos = result.index("z_db")
        assert a_pos < z_pos


class TestSecurityDescriptions:
    """Test that all tool descriptions follow SAFE-05 4-part format."""

    def test_query_redis_has_security_description(self):
        """query_redis docstring has allowed operations, examples, and boundary statement."""
        doc = query_redis.__doc__
        assert "Allowed operations" in doc
        assert "Examples" in doc
        assert "does NOT support SET, DEL" in doc

    def test_list_datasources_has_security_description(self):
        """list_datasources docstring has allowed operations, examples, and boundary statement."""
        doc = list_datasources.__doc__
        assert "Allowed operations" in doc
        assert "Examples" in doc
        assert "does not" in doc or "does NOT" in doc


class TestErrorSanitization:
    """Test that error messages never expose connection details (SAFE-04)."""

    @pytest.mark.asyncio
    async def test_query_redis_no_connection_details_in_error(self):
        """Error messages never contain host, port, or password."""
        pool_manager = _make_redis_pool_manager(["cache"])
        pool_manager.execute_pipeline = AsyncMock(
            side_effect=Exception("Connection to redis.prod.internal:6379 failed, password=secret123")
        )

        result = await query_redis(pool_manager, "cache", "GET", ["key1"])

        # Must NOT contain the leaked details from the exception
        assert "redis.prod.internal" not in result
        assert "secret123" not in result
        assert "password" not in result.lower()
