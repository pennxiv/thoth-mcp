"""Tests for MySQL connection pool manager."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


class TestMySQLPoolManagerLifecycle:
    """Test MySQLPoolManager async context manager lifecycle."""

    @pytest.mark.asyncio
    async def test_context_manager_enter_creates_pools(self):
        """Pools are created on __aenter__."""
        from thoth_mcp.db.mysql import MySQLPoolManager
        from thoth_mcp.config import MySQLDatasourceConfig

        # Create config without loading from YAML
        config = MagicMock()
        config.mysql = {
            "test_db": MySQLDatasourceConfig(
                host="localhost",
                port=3306,
                user="test",
                password="test",
                database="test",
                min_pool_size=1,
                max_pool_size=5,
            )
        }

        mock_pool = MagicMock()  # Use MagicMock since close() is sync

        with patch("thoth_mcp.db.mysql.aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            manager = MySQLPoolManager(config)
            result = await manager.__aenter__()

            assert result is manager
            mock_create_pool.assert_called_once()
            assert "test_db" in manager._pools

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_context_manager_exit_closes_pools(self):
        """Pools are closed gracefully on __aexit__."""
        from thoth_mcp.db.mysql import MySQLPoolManager
        from thoth_mcp.config import MySQLDatasourceConfig

        config = MagicMock()
        config.mysql = {
            "test_db": MySQLDatasourceConfig(
                host="localhost",
                port=3306,
                user="test",
                password="test",
                database="test",
            )
        }

        mock_pool = MagicMock()
        mock_pool.close = MagicMock()  # close() is synchronous
        mock_pool.wait_closed = AsyncMock()  # wait_closed() is async

        with patch("thoth_mcp.db.mysql.aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            manager = MySQLPoolManager(config)
            await manager.__aenter__()
            await manager.__aexit__(None, None, None)

            mock_pool.close.assert_called_once()
            mock_pool.wait_closed.assert_called_once()


class TestMySQLPoolManagerExecute:
    """Test MySQLPoolManager execute method."""

    @pytest.mark.asyncio
    async def test_execute_returns_list_of_dict(self):
        """execute() returns list[dict] using DictCursor."""
        from thoth_mcp.db.mysql import MySQLPoolManager
        from thoth_mcp.config import MySQLDatasourceConfig
        import aiomysql

        config = MagicMock()
        config.mysql = {
            "test_db": MySQLDatasourceConfig(
                host="localhost",
                port=3306,
                user="test",
                password="test",
                database="test",
            )
        }

        # Create proper async context manager for pool.acquire()
        class MockAcquire:
            def __init__(self, conn):
                self._conn = conn

            async def __aenter__(self):
                return self._conn

            async def __aexit__(self, *args):
                pass

        # Create proper async context manager for conn.cursor()
        class MockCursorContext:
            def __init__(self, cursor):
                self._cursor = cursor

            async def __aenter__(self):
                return self._cursor

            async def __aexit__(self, *args):
                pass

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = AsyncMock()

        # Mock cursor to return dict-style results
        mock_cursor.fetchall.return_value = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        mock_conn.cursor.return_value = MockCursorContext(mock_cursor)
        mock_pool.acquire.return_value = MockAcquire(mock_conn)

        with patch("thoth_mcp.db.mysql.aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            manager = MySQLPoolManager(config)
            await manager.__aenter__()

            result = await manager.execute("test_db", "SELECT * FROM users")

            assert isinstance(result, list)
            assert len(result) == 2
            assert result[0] == {"id": 1, "name": "Alice"}

            # Verify DictCursor was used
            mock_conn.cursor.assert_called_once_with(aiomysql.DictCursor)

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_execute_unknown_datasource_raises(self):
        """execute() raises ValueError for unknown datasource."""
        from thoth_mcp.db.mysql import MySQLPoolManager

        config = MagicMock()
        config.mysql = {}

        with patch("thoth_mcp.db.mysql.aiomysql.create_pool", new_callable=AsyncMock):
            manager = MySQLPoolManager(config)
            await manager.__aenter__()

            with pytest.raises(ValueError, match="Unknown datasource"):
                await manager.execute("unknown_db", "SELECT 1")

            await manager.__aexit__(None, None, None)


class TestMySQLPoolManagerConfiguration:
    """Test MySQLPoolManager configuration."""

    @pytest.mark.asyncio
    async def test_pool_recycle_configured(self):
        """Pool uses pool_recycle=25200 (7 hours) to prevent stale connections."""
        from thoth_mcp.db.mysql import MySQLPoolManager
        from thoth_mcp.config import MySQLDatasourceConfig

        config = MagicMock()
        config.mysql = {
            "test_db": MySQLDatasourceConfig(
                host="localhost",
                port=3306,
                user="test",
                password="test",
                database="test",
            )
        }

        mock_pool = MagicMock()  # Use MagicMock since close() is sync

        with patch("thoth_mcp.db.mysql.aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            manager = MySQLPoolManager(config)
            await manager.__aenter__()

            # Verify pool_recycle was passed
            call_kwargs = mock_create_pool.call_args[1]
            assert call_kwargs["pool_recycle"] == 25200

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_multiple_datasources_independent_pools(self):
        """Each datasource gets independent pool."""
        from thoth_mcp.db.mysql import MySQLPoolManager
        from thoth_mcp.config import MySQLDatasourceConfig

        config = MagicMock()
        config.mysql = {
            "db1": MySQLDatasourceConfig(
                host="host1",
                port=3306,
                user="user1",
                password="pass1",
                database="db1",
            ),
            "db2": MySQLDatasourceConfig(
                host="host2",
                port=3306,
                user="user2",
                password="pass2",
                database="db2",
            ),
        }

        mock_pool = MagicMock()  # Use MagicMock since close() is sync

        with patch("thoth_mcp.db.mysql.aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            manager = MySQLPoolManager(config)
            await manager.__aenter__()

            # Two pools created
            assert mock_create_pool.call_count == 2
            assert len(manager._pools) == 2
            assert "db1" in manager._pools
            assert "db2" in manager._pools

            await manager.__aexit__(None, None, None)


class TestCreatePoolManager:
    """Test create_pool_manager factory function."""

    def test_create_pool_manager_returns_manager(self):
        """Factory function returns MySQLPoolManager instance."""
        from thoth_mcp.db.mysql import create_pool_manager, MySQLPoolManager

        config = MagicMock()
        config.mysql = {}
        manager = create_pool_manager(config)

        assert isinstance(manager, MySQLPoolManager)
        assert manager._config is config


class TestMySQLPoolManagerHealthCheck:
    """Test MySQLPoolManager health check methods."""

    @pytest.mark.asyncio
    async def test_health_check_returns_true_for_reachable(self):
        """health_check(name) returns True for reachable datasource."""
        from thoth_mcp.db.mysql import MySQLPoolManager
        from thoth_mcp.config import MySQLDatasourceConfig

        config = MagicMock()
        config.mysql = {
            "test_db": MySQLDatasourceConfig(
                host="localhost",
                port=3306,
                user="test",
                password="test",
                database="test",
            )
        }

        # Create proper async context manager for pool.acquire()
        class MockAcquire:
            def __init__(self, conn):
                self._conn = conn

            async def __aenter__(self):
                return self._conn

            async def __aexit__(self, *args):
                pass

        class MockCursorContext:
            def __init__(self, cursor):
                self._cursor = cursor

            async def __aenter__(self):
                return self._cursor

            async def __aexit__(self, *args):
                pass

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = AsyncMock()

        # Mock cursor to return (1,) for SELECT 1
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value = MockCursorContext(mock_cursor)
        mock_pool.acquire.return_value = MockAcquire(mock_conn)

        with patch("thoth_mcp.db.mysql.aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            manager = MySQLPoolManager(config)
            await manager.__aenter__()

            result = await manager.health_check("test_db")

            assert result is True

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_health_check_returns_false_for_unknown(self):
        """health_check(name) returns False for unknown datasource."""
        from thoth_mcp.db.mysql import MySQLPoolManager

        config = MagicMock()
        config.mysql = {}

        with patch("thoth_mcp.db.mysql.aiomysql.create_pool", new_callable=AsyncMock):
            manager = MySQLPoolManager(config)
            await manager.__aenter__()

            result = await manager.health_check("unknown_db")

            assert result is False

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_health_check_all_returns_dict(self):
        """health_check_all() returns dict[str, bool] for all datasources."""
        from thoth_mcp.db.mysql import MySQLPoolManager
        from thoth_mcp.config import MySQLDatasourceConfig

        config = MagicMock()
        config.mysql = {
            "db1": MySQLDatasourceConfig(
                host="host1",
                port=3306,
                user="user1",
                password="pass1",
                database="db1",
            ),
            "db2": MySQLDatasourceConfig(
                host="host2",
                port=3306,
                user="user2",
                password="pass2",
                database="db2",
            ),
        }

        mock_pool = MagicMock()

        with patch("thoth_mcp.db.mysql.aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            manager = MySQLPoolManager(config)
            await manager.__aenter__()

            # Mock health_check to return True for db1, False for db2
            async def mock_health_check(name):
                return name == "db1"

            manager.health_check = mock_health_check

            result = await manager.health_check_all()

            assert isinstance(result, dict)
            assert "db1" in result
            assert "db2" in result
            assert result["db1"] is True
            assert result["db2"] is False

            await manager.__aexit__(None, None, None)


class TestMySQLPoolManagerStatus:
    """Test MySQLPoolManager status reporting methods."""

    @pytest.mark.asyncio
    async def test_get_pool_status_returns_stats(self):
        """get_pool_status(name) returns dict with name, size, minsize, maxsize, freesize."""
        from thoth_mcp.db.mysql import MySQLPoolManager
        from thoth_mcp.config import MySQLDatasourceConfig

        config = MagicMock()
        config.mysql = {
            "test_db": MySQLDatasourceConfig(
                host="localhost",
                port=3306,
                user="test",
                password="test",
                database="test",
                min_pool_size=2,
                max_pool_size=10,
            )
        }

        mock_pool = MagicMock()
        mock_pool.size = 5
        mock_pool.minsize = 2
        mock_pool.maxsize = 10
        mock_pool.freesize = 3

        with patch("thoth_mcp.db.mysql.aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            manager = MySQLPoolManager(config)
            await manager.__aenter__()

            result = manager.get_pool_status("test_db")

            assert isinstance(result, dict)
            assert result["name"] == "test_db"
            assert result["size"] == 5
            assert result["minsize"] == 2
            assert result["maxsize"] == 10
            assert result["freesize"] == 3

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_get_pool_status_unknown_raises(self):
        """get_pool_status(name) raises ValueError for unknown datasource."""
        from thoth_mcp.db.mysql import MySQLPoolManager

        config = MagicMock()
        config.mysql = {}

        with patch("thoth_mcp.db.mysql.aiomysql.create_pool", new_callable=AsyncMock):
            manager = MySQLPoolManager(config)
            await manager.__aenter__()

            with pytest.raises(ValueError, match="Unknown datasource"):
                manager.get_pool_status("unknown_db")

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_get_all_pool_status_returns_all(self):
        """get_all_pool_status() returns dict[str, dict] for all pools."""
        from thoth_mcp.db.mysql import MySQLPoolManager
        from thoth_mcp.config import MySQLDatasourceConfig

        config = MagicMock()
        config.mysql = {
            "db1": MySQLDatasourceConfig(
                host="host1",
                port=3306,
                user="user1",
                password="pass1",
                database="db1",
            ),
            "db2": MySQLDatasourceConfig(
                host="host2",
                port=3306,
                user="user2",
                password="pass2",
                database="db2",
            ),
        }

        mock_pool = MagicMock()
        mock_pool.size = 5
        mock_pool.minsize = 1
        mock_pool.maxsize = 10
        mock_pool.freesize = 3

        with patch("thoth_mcp.db.mysql.aiomysql.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_create_pool.return_value = mock_pool

            manager = MySQLPoolManager(config)
            await manager.__aenter__()

            result = manager.get_all_pool_status()

            assert isinstance(result, dict)
            assert "db1" in result
            assert "db2" in result
            assert result["db1"]["name"] == "db1"
            assert result["db2"]["name"] == "db2"

            await manager.__aexit__(None, None, None)
