"""Tests for MySQL MCP tools."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from thoth_mcp.tools.mysql import query_mysql, list_tables, describe_table


def _make_pool_manager(datasources=None):
    """Create a mock MySQLPoolManager."""
    mock = MagicMock()
    ds_list = datasources or []
    mock._pools = {name: MagicMock() for name in ds_list}

    async def _execute(name, sql, params=()):
        if name not in ds_list:
            raise ValueError(f"Unknown datasource: {name}")
        return []

    mock.execute = AsyncMock(side_effect=_execute)
    return mock


class TestQueryMysql:
    """Test query_mysql tool function."""

    @pytest.mark.asyncio
    async def test_query_mysql_success(self):
        """Valid SELECT query returns formatted Markdown table."""
        pool_manager = _make_pool_manager(["prod_db"])
        pool_manager.execute = AsyncMock(return_value=[
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ])

        result = await query_mysql(pool_manager, "prod_db", "SELECT * FROM users LIMIT 10")

        assert "Alice" in result
        assert "Bob" in result
        assert "| id | name |" in result
        pool_manager.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_mysql_validates_sql(self):
        """Non-SELECT query is rejected with friendly message."""
        pool_manager = _make_pool_manager(["prod_db"])

        result = await query_mysql(pool_manager, "prod_db", "DROP TABLE users")

        assert "Query rejected" in result
        pool_manager.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_mysql_injection_blocked(self):
        """SQL injection patterns are rejected."""
        pool_manager = _make_pool_manager(["prod_db"])

        result = await query_mysql(
            pool_manager, "prod_db",
            "SELECT * FROM users UNION SELECT * FROM admin"
        )

        assert "Query rejected" in result
        pool_manager.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_mysql_unknown_datasource(self):
        """Unknown datasource returns descriptive error."""
        pool_manager = _make_pool_manager(["prod_db", "analytics"])
        pool_manager.execute = AsyncMock(side_effect=ValueError("Unknown datasource: unknown_db"))

        result = await query_mysql(pool_manager, "unknown_db", "SELECT 1")

        assert "Unknown datasource: unknown_db" in result

    @pytest.mark.asyncio
    async def test_query_mysql_execution_error(self):
        """Database execution error returns sanitized message."""
        pool_manager = _make_pool_manager(["prod_db"])
        pool_manager.execute = AsyncMock(side_effect=Exception("Connection lost"))

        result = await query_mysql(pool_manager, "prod_db", "SELECT * FROM users LIMIT 10")

        assert "Query execution failed" in result
        # Should NOT contain connection details
        assert "host" not in result.lower()
        assert "password" not in result.lower()

    @pytest.mark.asyncio
    async def test_query_mysql_empty_result(self):
        """Empty result set returns 'No results found' message."""
        pool_manager = _make_pool_manager(["prod_db"])
        pool_manager.execute = AsyncMock(return_value=[])

        result = await query_mysql(pool_manager, "prod_db", "SELECT * FROM users LIMIT 10")

        assert "No results found" in result

    @pytest.mark.asyncio
    async def test_query_mysql_limit_injected(self):
        """SQL without LIMIT gets LIMIT added by validate_sql."""
        pool_manager = _make_pool_manager(["prod_db"])
        pool_manager.execute = AsyncMock(return_value=[{"id": 1}])

        await query_mysql(pool_manager, "prod_db", "SELECT * FROM users")

        # Verify the SQL passed to execute contains LIMIT
        call_args = pool_manager.execute.call_args
        executed_sql = call_args[0][1]  # second positional arg is sql
        assert "LIMIT" in executed_sql


class TestListTables:
    """Test list_tables tool function."""

    @pytest.mark.asyncio
    async def test_list_tables_success(self):
        """Returns Markdown table of table names."""
        pool_manager = _make_pool_manager(["prod_db"])
        pool_manager.execute = AsyncMock(return_value=[
            {"Table": "users"},
            {"Table": "orders"},
            {"Table": "products"},
        ])

        result = await list_tables(pool_manager, "prod_db")

        assert "| 1 | users |" in result
        assert "| 2 | orders |" in result
        assert "| 3 | products |" in result
        assert "3 table(s) found" in result

    @pytest.mark.asyncio
    async def test_list_tables_empty(self):
        """Empty database returns 'No tables found' message."""
        pool_manager = _make_pool_manager(["prod_db"])
        pool_manager.execute = AsyncMock(return_value=[])

        result = await list_tables(pool_manager, "prod_db")

        assert "No tables found" in result

    @pytest.mark.asyncio
    async def test_list_tables_unknown_datasource(self):
        """Unknown datasource returns error with available names."""
        pool_manager = _make_pool_manager(["prod_db", "analytics"])
        pool_manager.execute = AsyncMock(side_effect=ValueError("Unknown datasource: unknown_db"))

        result = await list_tables(pool_manager, "unknown_db")

        assert "Unknown datasource" in result

    @pytest.mark.asyncio
    async def test_list_tables_execution_error(self):
        """Database error returns sanitized message."""
        pool_manager = _make_pool_manager(["prod_db"])
        pool_manager.execute = AsyncMock(side_effect=Exception("Connection refused"))

        result = await list_tables(pool_manager, "prod_db")

        assert "Failed to list tables" in result


class TestDescribeTable:
    """Test describe_table tool function."""

    @pytest.mark.asyncio
    async def test_describe_table_success(self):
        """Returns Markdown table with column details."""
        pool_manager = _make_pool_manager(["prod_db"])
        pool_manager.execute = AsyncMock(return_value=[
            {"Field": "id", "Type": "int", "Null": "NO", "Key": "PRI", "Default": None, "Extra": "auto_increment"},
            {"Field": "name", "Type": "varchar(255)", "Null": "YES", "Key": "", "Default": None, "Extra": ""},
        ])

        result = await describe_table(pool_manager, "prod_db", "users")

        assert "id" in result
        assert "int" in result
        assert "name" in result
        assert "varchar" in result

    @pytest.mark.asyncio
    async def test_describe_table_invalid_name(self):
        """Table name with special characters is rejected."""
        pool_manager = _make_pool_manager(["prod_db"])

        result = await describe_table(pool_manager, "prod_db", "users; DROP TABLE users")

        assert "Invalid table name" in result
        pool_manager.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_describe_table_unknown_datasource(self):
        """Unknown datasource returns error with available names."""
        pool_manager = _make_pool_manager(["prod_db"])
        pool_manager.execute = AsyncMock(side_effect=ValueError("Unknown datasource: unknown_db"))

        result = await describe_table(pool_manager, "unknown_db", "users")

        assert "Unknown datasource" in result

    @pytest.mark.asyncio
    async def test_describe_table_not_found(self):
        """Table not found returns appropriate message."""
        pool_manager = _make_pool_manager(["prod_db"])
        pool_manager.execute = AsyncMock(return_value=[])

        result = await describe_table(pool_manager, "prod_db", "nonexistent")

        assert "not found" in result

    @pytest.mark.asyncio
    async def test_describe_table_execution_error(self):
        """Database error returns sanitized message."""
        pool_manager = _make_pool_manager(["prod_db"])
        pool_manager.execute = AsyncMock(side_effect=Exception("Table doesn't exist"))

        result = await describe_table(pool_manager, "prod_db", "users")

        assert "Failed to describe table" in result


class TestSecurityDescriptions:
    """Test that all tool descriptions follow SAFE-05 4-part format."""

    def test_query_mysql_has_security_description(self):
        """query_mysql docstring has allowed operations, examples, and boundary statement."""
        doc = query_mysql.__doc__
        assert "Allowed operations" in doc
        assert "Examples" in doc
        assert "does NOT support INSERT, UPDATE, DELETE, DROP, ALTER" in doc

    def test_list_tables_has_security_description(self):
        """list_tables docstring has allowed operations, examples, and boundary statement."""
        doc = list_tables.__doc__
        assert "Allowed operations" in doc
        assert "Examples" in doc
        assert "does not modify" in doc

    def test_describe_table_has_security_description(self):
        """describe_table docstring has allowed operations, examples, and boundary statement."""
        doc = describe_table.__doc__
        assert "Allowed operations" in doc
        assert "Examples" in doc
        assert "does not modify" in doc


class TestIntegrationPipeline:
    """Test full validate → execute → format pipeline."""

    @pytest.mark.asyncio
    async def test_query_mysql_full_pipeline(self):
        """SQL goes through validate → execute → format pipeline."""
        pool_manager = _make_pool_manager(["prod_db"])
        pool_manager.execute = AsyncMock(return_value=[{"id": 1, "name": "test"}])

        result = await query_mysql(pool_manager, "prod_db", "SELECT * FROM users")

        # Verify execute was called with LIMIT-injected SQL
        call_args = pool_manager.execute.call_args
        assert "LIMIT" in call_args[0][1]
        # Verify format_mysql_result was applied (Markdown table)
        assert "| id | name |" in result

    @pytest.mark.asyncio
    async def test_query_mysql_select_with_where(self):
        """SELECT with WHERE clause works through pipeline."""
        pool_manager = _make_pool_manager(["prod_db"])
        pool_manager.execute = AsyncMock(return_value=[{"name": "Alice"}])

        result = await query_mysql(pool_manager, "prod_db", "SELECT name FROM users WHERE id = 1")

        assert "Alice" in result
        pool_manager.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_describe_table_validates_name_before_query(self):
        """Invalid table name prevents query execution."""
        pool_manager = _make_pool_manager(["prod_db"])
        # Don't override execute — if called, the test should still detect it

        result = await describe_table(pool_manager, "prod_db", "users; DROP TABLE users")

        assert "Invalid table name" in result
        pool_manager.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_tools_have_security_descriptions(self):
        """All tool functions have SAFE-05 compliant docstrings."""
        for func in [query_mysql, list_tables, describe_table]:
            doc = func.__doc__
            assert "Allowed operations" in doc, f"{func.__name__} missing 'Allowed operations'"
            assert "does NOT" in doc or "does not" in doc, f"{func.__name__} missing boundary statement"
