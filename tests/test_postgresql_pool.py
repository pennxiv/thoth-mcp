"""Tests for PostgreSQL connection pool manager."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class MockAcquire:
    """Proper async context manager for pool.acquire() mock."""

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *args):
        pass


class TestPostgreSQLPoolManagerLifecycle:
    """Test PostgreSQLPoolManager async context manager lifecycle."""

    @pytest.mark.asyncio
    async def test_context_manager_enter_creates_pools(self):
        """Pools are created on __aenter__."""
        from thoth_mcp.db.postgresql import PostgreSQLPoolManager

        config = MagicMock()
        config.postgres = {
            "test_db": MagicMock(
                host="localhost",
                port=5432,
                user="test",
                password="test",
                database="test",
                min_pool_size=1,
                max_pool_size=5,
            )
        }

        mock_pool = MagicMock()

        with patch("thoth_mcp.db.postgresql.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            manager = PostgreSQLPoolManager(config)
            result = await manager.__aenter__()

            assert result is manager
            mock_create_pool.assert_called_once()
            assert "test_db" in manager._pools

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_context_manager_exit_closes_pools(self):
        """Pools are closed gracefully on __aexit__."""
        from thoth_mcp.db.postgresql import PostgreSQLPoolManager

        config = MagicMock()
        config.postgres = {
            "test_db": MagicMock(
                host="localhost",
                port=5432,
                user="test",
                password="test",
                database="test",
            )
        }

        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()

        with patch("thoth_mcp.db.postgresql.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            manager = PostgreSQLPoolManager(config)
            await manager.__aenter__()
            await manager.__aexit__(None, None, None)

            mock_pool.close.assert_called_once()


class TestPostgreSQLPoolManagerExecute:
    """Test PostgreSQLPoolManager execute method."""

    @pytest.mark.asyncio
    async def test_execute_returns_list_of_dict(self):
        """execute() returns list[dict] from asyncpg Record objects."""
        from thoth_mcp.db.postgresql import PostgreSQLPoolManager

        config = MagicMock()
        config.postgres = {
            "test_db": MagicMock(
                host="localhost",
                port=5432,
                user="test",
                password="test",
                database="test",
            )
        }

        class MockRecord(dict):
            pass

        mock_records = [
            MockRecord(id=1, name="Alice"),
            MockRecord(id=2, name="Bob"),
        ]

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = mock_records
        mock_pool.acquire.return_value = MockAcquire(mock_conn)

        with patch("thoth_mcp.db.postgresql.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            manager = PostgreSQLPoolManager(config)
            await manager.__aenter__()

            result = await manager.execute("test_db", "SELECT * FROM users")

            assert isinstance(result, list)
            assert len(result) == 2
            assert result[0] == {"id": 1, "name": "Alice"}

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_execute_unknown_datasource_raises(self):
        """execute() raises ValueError for unknown datasource."""
        from thoth_mcp.db.postgresql import PostgreSQLPoolManager

        config = MagicMock()
        config.postgres = {}

        with patch("thoth_mcp.db.postgresql.asyncpg.create_pool", new_callable=AsyncMock):
            manager = PostgreSQLPoolManager(config)
            await manager.__aenter__()

            with pytest.raises(ValueError, match="Unknown datasource"):
                await manager.execute("unknown_db", "SELECT 1")

            await manager.__aexit__(None, None, None)


class TestCreatePoolManager:
    """Test create_pool_manager factory function."""

    def test_create_pool_manager_returns_manager(self):
        """Factory function returns PostgreSQLPoolManager instance."""
        from thoth_mcp.db.postgresql import create_pool_manager, PostgreSQLPoolManager

        config = MagicMock()
        config.postgres = {}
        manager = create_pool_manager(config)

        assert isinstance(manager, PostgreSQLPoolManager)
        assert manager._config is config


class TestPostgreSQLPoolManagerHealthCheck:
    """Test PostgreSQLPoolManager health check methods."""

    @pytest.mark.asyncio
    async def test_health_check_returns_true_for_reachable(self):
        """health_check(name) returns True for reachable datasource."""
        from thoth_mcp.db.postgresql import PostgreSQLPoolManager

        config = MagicMock()
        config.postgres = {
            "test_db": MagicMock(
                host="localhost",
                port=5432,
                user="test",
                password="test",
                database="test",
            )
        }

        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = 1
        mock_pool.acquire.return_value = MockAcquire(mock_conn)

        with patch("thoth_mcp.db.postgresql.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            manager = PostgreSQLPoolManager(config)
            await manager.__aenter__()

            result = await manager.health_check("test_db")

            assert result is True

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_health_check_returns_false_for_unknown(self):
        """health_check(name) returns False for unknown datasource."""
        from thoth_mcp.db.postgresql import PostgreSQLPoolManager

        config = MagicMock()
        config.postgres = {}

        with patch("thoth_mcp.db.postgresql.asyncpg.create_pool", new_callable=AsyncMock):
            manager = PostgreSQLPoolManager(config)
            await manager.__aenter__()

            result = await manager.health_check("unknown_db")

            assert result is False

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_health_check_all_returns_dict(self):
        """health_check_all() returns dict[str, bool] for all datasources."""
        from thoth_mcp.db.postgresql import PostgreSQLPoolManager

        config = MagicMock()
        config.postgres = {
            "db1": MagicMock(host="h1", port=5432, user="u", password="p", database="d"),
            "db2": MagicMock(host="h2", port=5432, user="u", password="p", database="d"),
        }

        with patch("thoth_mcp.db.postgresql.asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = AsyncMock()

            manager = PostgreSQLPoolManager(config)
            await manager.__aenter__()

            async def mock_health_check(name):
                return name == "db1"

            manager.health_check = mock_health_check

            result = await manager.health_check_all()

            assert isinstance(result, dict)
            assert result["db1"] is True
            assert result["db2"] is False

            await manager.__aexit__(None, None, None)
