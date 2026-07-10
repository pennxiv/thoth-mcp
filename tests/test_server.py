"""Tests for server assembly."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from thoth_mcp.server import SERVER_INSTRUCTIONS, app_lifespan, create_app


def test_create_app_returns_app():
    app = create_app()
    assert app is not None
    assert hasattr(app, "tool")


def test_server_instructions_contain_guidance():
    assert "list_datasources" in SERVER_INSTRUCTIONS
    assert "read-only" in SERVER_INSTRUCTIONS
    assert "LIMIT" in SERVER_INSTRUCTIONS
    assert "describe_table" in SERVER_INSTRUCTIONS


@pytest.mark.asyncio
async def test_all_expected_tools_registered():
    app = create_app()
    assert hasattr(app, "tool")
    # Use public list_tools() API (works for both real FastMCP and fallback)
    if hasattr(app, "_tools"):
        # Fallback FastMCP: synchronous _tools dict
        tools_dict = app._tools
    else:
        # Real FastMCP: async list_tools()
        tools = await app.list_tools()
        tools_dict = {t.name: t for t in tools}
    expected = [
        "query_mysql",
        "list_tables",
        "describe_table",
        "query_postgres",
        "list_tables_postgres",
        "describe_table_postgres",
        "get_table_ddl_postgres",
        "query_redis",
        "list_datasources",
        "health_check",
        "health_check_all",
    ]
    for name in expected:
        assert name in tools_dict, f"Tool '{name}' not found in registered tools"


@pytest.mark.asyncio
async def test_lifespan_yields_expected_state_keys():
    mock_config = MagicMock()
    mock_mysql_manager = MagicMock()
    mock_mysql_manager.__aenter__ = AsyncMock(return_value="mysql-entered")
    mock_mysql_manager.__aexit__ = AsyncMock(return_value=None)
    mock_redis_manager = MagicMock()
    mock_redis_manager.__aenter__ = AsyncMock(return_value="redis-entered")
    mock_redis_manager.__aexit__ = AsyncMock(return_value=None)

    with patch("thoth_mcp.server.load_config", return_value=mock_config), \
         patch("thoth_mcp.server.create_mysql_pool_manager", return_value=mock_mysql_manager), \
         patch("thoth_mcp.server.create_redis_pool_manager", return_value=mock_redis_manager):
        async with app_lifespan(None) as state:
            assert state["config"] is mock_config
            assert state["mysql_pool_manager"] == "mysql-entered"
            assert state["redis_pool_manager"] == "redis-entered"


@pytest.mark.asyncio
async def test_lifespan_shutdown_attempts_both_cleanups_on_error():
    mock_config = MagicMock()
    mock_mysql_manager = MagicMock()
    mock_mysql_manager.__aenter__ = AsyncMock(return_value="mysql-entered")
    mock_mysql_manager.__aexit__ = AsyncMock(side_effect=RuntimeError("mysql close failed"))
    mock_redis_manager = MagicMock()
    mock_redis_manager.__aenter__ = AsyncMock(return_value="redis-entered")
    mock_redis_manager.__aexit__ = AsyncMock(side_effect=RuntimeError("redis close failed"))

    with patch("thoth_mcp.server.load_config", return_value=mock_config), \
         patch("thoth_mcp.server.create_mysql_pool_manager", return_value=mock_mysql_manager), \
         patch("thoth_mcp.server.create_redis_pool_manager", return_value=mock_redis_manager):
        async with app_lifespan(None) as state:
            assert state["config"] is mock_config

    mock_mysql_manager.__aexit__.assert_called_once()
    mock_redis_manager.__aexit__.assert_called_once()
