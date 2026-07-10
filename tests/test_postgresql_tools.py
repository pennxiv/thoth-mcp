"""Tests for PostgreSQL MCP tools."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from thoth_mcp.tools.postgresql import query_postgres, list_tables_postgres, describe_table_postgres


def _make_pool_manager(datasources=None):
    """Create a mock PostgreSQLPoolManager."""
    mock = MagicMock()
    ds_list = datasources or []
    mock._pools = {name: MagicMock() for name in ds_list}

    async def _execute(name, sql, *args):
        if name not in ds_list:
            raise ValueError(f"Unknown datasource: {name}")
        return []

    mock.execute = AsyncMock(side_effect=_execute)
    return mock


class TestQueryPostgres:
    @pytest.mark.asyncio
    async def test_query_postgres_success(self):
        pool_manager = _make_pool_manager(["analytics"])
        pool_manager.execute = AsyncMock(return_value=[
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ])
        result = await query_postgres(pool_manager, "analytics", "SELECT * FROM users LIMIT 10")
        assert "Alice" in result
        assert "| id | name |" in result

    @pytest.mark.asyncio
    async def test_query_postgres_validates_sql(self):
        pool_manager = _make_pool_manager(["analytics"])
        result = await query_postgres(pool_manager, "analytics", "DROP TABLE users")
        assert "Query rejected" in result
        pool_manager.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_postgres_injection_blocked(self):
        pool_manager = _make_pool_manager(["analytics"])
        result = await query_postgres(pool_manager, "analytics", "SELECT * FROM users UNION SELECT * FROM admin")
        assert "Query rejected" in result

    @pytest.mark.asyncio
    async def test_query_postgres_unknown_datasource(self):
        pool_manager = _make_pool_manager(["analytics", "warehouse"])
        pool_manager.execute = AsyncMock(side_effect=ValueError("Unknown datasource: unknown_db"))
        result = await query_postgres(pool_manager, "unknown_db", "SELECT 1")
        assert "Unknown datasource: unknown_db" in result

    @pytest.mark.asyncio
    async def test_query_postgres_execution_error(self):
        pool_manager = _make_pool_manager(["analytics"])
        pool_manager.execute = AsyncMock(side_effect=Exception("Connection Lost"))
        result = await query_postgres(pool_manager, "analytics", "SELECT * FROM users LIMIT 10")
        assert "Query execution failed" in result
        assert "host" not in result.lower()

    @pytest.mark.asyncio
    async def test_query_postgres_empty_result(self):
        pool_manager = _make_pool_manager(["analytics"])
        pool_manager.execute = AsyncMock(return_value=[])
        result = await query_postgres(pool_manager, "analytics", "SELECT * FROM users LIMIT 10")
        assert "No results found" in result

    @pytest.mark.asyncio
    async def test_query_postgres_limit_injected(self):
        pool_manager = _make_pool_manager(["analytics"])
        pool_manager.execute = AsyncMock(return_value=[{"id": 1}])
        await query_postgres(pool_manager, "analytics", "SELECT * FROM users")
        executed_sql = pool_manager.execute.call_args[0][1]
        assert "LIMIT" in executed_sql


class TestListTablesPostgres:
    @pytest.mark.asyncio
    async def test_list_tables_success(self):
        pool_manager = _make_pool_manager(["analytics"])
        pool_manager.execute = AsyncMock(return_value=[
            {"Table": "users"},
            {"Table": "orders"},
        ])
        result = await list_tables_postgres(pool_manager, "analytics")
        assert "| 1 | users |" in result
        assert "| 2 | orders |" in result
        assert "2 table(s) found" in result

    @pytest.mark.asyncio
    async def test_list_tables_empty(self):
        pool_manager = _make_pool_manager(["analytics"])
        pool_manager.execute = AsyncMock(return_value=[])
        result = await list_tables_postgres(pool_manager, "analytics")
        assert "No tables found" in result

    @pytest.mark.asyncio
    async def test_list_tables_unknown_datasource(self):
        pool_manager = _make_pool_manager(["analytics"])
        pool_manager.execute = AsyncMock(side_effect=ValueError("Unknown datasource: unknown_db"))
        result = await list_tables_postgres(pool_manager, "unknown_db")
        assert "Unknown datasource" in result

    @pytest.mark.asyncio
    async def test_list_tables_execution_error(self):
        pool_manager = _make_pool_manager(["analytics"])
        pool_manager.execute = AsyncMock(side_effect=Exception("Connection refused"))
        result = await list_tables_postgres(pool_manager, "analytics")
        assert "Failed to list tables" in result


class TestDescribeTablePostgres:
    @pytest.mark.asyncio
    async def test_describe_table_success(self):
        pool_manager = _make_pool_manager(["analytics"])
        pool_manager.execute = AsyncMock(return_value=[
            {"Field": "id", "Type": "integer", "Null": "NO", "Default": "nextval('...')"},
            {"Field": "name", "Type": "character varying", "Null": "YES", "Default": None},
        ])
        result = await describe_table_postgres(pool_manager, "analytics", "users")
        assert "id" in result
        assert "integer" in result

    @pytest.mark.asyncio
    async def test_describe_table_invalid_name(self):
        pool_manager = _make_pool_manager(["analytics"])
        result = await describe_table_postgres(pool_manager, "analytics", "users; DROP TABLE users")
        assert "Invalid table name" in result
        pool_manager.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_describe_table_unknown_datasource(self):
        pool_manager = _make_pool_manager(["analytics"])
        pool_manager.execute = AsyncMock(side_effect=ValueError("Unknown datasource: unknown_db"))
        result = await describe_table_postgres(pool_manager, "unknown_db", "users")
        assert "Unknown datasource" in result

    @pytest.mark.asyncio
    async def test_describe_table_not_found(self):
        pool_manager = _make_pool_manager(["analytics"])
        pool_manager.execute = AsyncMock(return_value=[])
        result = await describe_table_postgres(pool_manager, "analytics", "nonexistent")
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_describe_table_execution_error(self):
        pool_manager = _make_pool_manager(["analytics"])
        pool_manager.execute = AsyncMock(side_effect=Exception("Connection refused"))
        result = await describe_table_postgres(pool_manager, "analytics", "users")
        assert "Failed to describe table" in result


class TestSecurityDescriptions:
    def test_query_postgres_has_security_description(self):
        doc = query_postgres.__doc__
        assert "Allowed operations" in doc
        assert "Examples" in doc
        assert "does NOT support INSERT, UPDATE, DELETE, DROP, ALTER" in doc

    def test_list_tables_postgres_has_security_description(self):
        doc = list_tables_postgres.__doc__
        assert "Allowed operations" in doc
        assert "does not modify" in doc

    def test_describe_table_postgres_has_security_description(self):
        doc = describe_table_postgres.__doc__
        assert "Allowed operations" in doc
        assert "does not modify" in doc
