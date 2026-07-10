"""Tests for Redis connection pool manager."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from thoth_mcp.config import RedisDatasourceConfig


def _make_config(instances=None):
    """Create a mock DatasourcesConfig with Redis instances."""
    config = MagicMock()
    config.redis = instances or {}
    config.mysql = {}
    return config


def _make_ds_config(**kwargs):
    """Create a RedisDatasourceConfig with defaults."""
    defaults = {"host": "localhost"}
    defaults.update(kwargs)
    return RedisDatasourceConfig(**defaults)


class TestRedisPoolManagerLifecycle:
    """Test RedisPoolManager async context manager lifecycle."""

    @pytest.mark.asyncio
    async def test_context_manager_enter_creates_pools(self):
        """Pools and clients are created on __aenter__."""
        from thoth_mcp.db.redis import RedisPoolManager

        config = _make_config({
            "test_redis": _make_ds_config(max_pool_size=15),
        })

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool) as mock_pool_cls, \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=mock_client):
            manager = RedisPoolManager(config)
            result = await manager.__aenter__()

            assert result is manager
            mock_pool_cls.assert_called_once()
            # Verify decode_responses=True and max_connections
            call_kwargs = mock_pool_cls.call_args[1]
            assert call_kwargs["decode_responses"] is True
            assert call_kwargs["max_connections"] == 15
            assert "test_redis" in manager._pools
            assert "test_redis" in manager._clients

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_context_manager_exit_closes_clients_and_pools(self):
        """Clients and pools are closed gracefully on __aexit__."""
        from thoth_mcp.db.redis import RedisPoolManager

        config = _make_config({
            "test_redis": _make_ds_config(),
        })

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=mock_client):
            manager = RedisPoolManager(config)
            await manager.__aenter__()
            await manager.__aexit__(None, None, None)

            mock_client.aclose.assert_called_once()
            mock_pool.aclose.assert_called_once()
            assert len(manager._clients) == 0
            assert len(manager._pools) == 0


class TestRedisPoolManagerHealthCheck:
    """Test RedisPoolManager health check methods."""

    @pytest.mark.asyncio
    async def test_health_check_returns_true_for_reachable(self):
        """health_check(name) returns True for reachable instance."""
        from thoth_mcp.db.redis import RedisPoolManager

        config = _make_config({
            "test_redis": _make_ds_config(),
        })

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=mock_client):
            manager = RedisPoolManager(config)
            await manager.__aenter__()

            result = await manager.health_check("test_redis")
            assert result is True

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_error(self):
        """health_check(name) returns False when ping fails."""
        from thoth_mcp.db.redis import RedisPoolManager
        from redis.exceptions import ConnectionError

        config = _make_config({
            "test_redis": _make_ds_config(),
        })

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("Connection refused"))
        mock_client.aclose = AsyncMock()

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=mock_client):
            manager = RedisPoolManager(config)
            await manager.__aenter__()

            result = await manager.health_check("test_redis")
            assert result is False

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_health_check_raises_for_unknown_instance(self):
        """health_check(name) raises ValueError for unknown instance."""
        from thoth_mcp.db.redis import RedisPoolManager

        config = _make_config({})

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=AsyncMock()):
            manager = RedisPoolManager(config)
            await manager.__aenter__()

            with pytest.raises(ValueError, match="Unknown instance"):
                await manager.health_check("unknown_redis")

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_health_check_all_returns_dict(self):
        """health_check_all() returns dict[str, bool] for all instances."""
        from thoth_mcp.db.redis import RedisPoolManager

        config = _make_config({
            "redis1": _make_ds_config(host="host1"),
            "redis2": _make_ds_config(host="host2"),
        })

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=AsyncMock()) as mock_redis_cls:
            # Create two different mock clients
            client1 = AsyncMock()
            client1.ping = AsyncMock(return_value=True)
            client1.aclose = AsyncMock()
            client2 = AsyncMock()
            client2.ping = AsyncMock(side_effect=Exception("down"))
            client2.aclose = AsyncMock()

            mock_redis_cls.side_effect = [client1, client2]

            manager = RedisPoolManager(config)
            await manager.__aenter__()

            result = await manager.health_check_all()

            assert isinstance(result, dict)
            assert "redis1" in result
            assert "redis2" in result
            assert result["redis1"] is True
            assert result["redis2"] is False

            await manager.__aexit__(None, None, None)


class TestRedisPoolManagerStatus:
    """Test RedisPoolManager status reporting methods."""

    @pytest.mark.asyncio
    async def test_get_pool_status_returns_stats(self):
        """get_pool_status(name) returns dict with name and max_connections."""
        from thoth_mcp.db.redis import RedisPoolManager

        config = _make_config({
            "test_redis": _make_ds_config(max_pool_size=20),
        })

        mock_pool = MagicMock()
        mock_pool.max_connections = 20
        mock_pool.aclose = AsyncMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=mock_client):
            manager = RedisPoolManager(config)
            await manager.__aenter__()

            result = manager.get_pool_status("test_redis")

            assert isinstance(result, dict)
            assert result["name"] == "test_redis"
            assert result["max_connections"] == 20

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_get_pool_status_unknown_raises(self):
        """get_pool_status(name) raises ValueError for unknown instance."""
        from thoth_mcp.db.redis import RedisPoolManager

        config = _make_config({})

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=AsyncMock()):
            manager = RedisPoolManager(config)
            await manager.__aenter__()

            with pytest.raises(ValueError, match="Unknown instance"):
                manager.get_pool_status("unknown_redis")

            await manager.__aexit__(None, None, None)


class TestRedisPoolManagerPipeline:
    """Test RedisPoolManager execute_pipeline method."""

    @pytest.mark.asyncio
    async def test_execute_pipeline_success(self):
        """execute_pipeline executes commands and returns ordered results."""
        from thoth_mcp.db.redis import RedisPoolManager

        config = _make_config({
            "test_redis": _make_ds_config(),
        })

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        # Mock pipeline
        mock_pipe = AsyncMock()
        mock_pipe.get = MagicMock(return_value=mock_pipe)
        mock_pipe.hget = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(return_value=["value1", "field_value"])
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=False)

        mock_client.pipeline = MagicMock(return_value=mock_pipe)

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=mock_client):
            manager = RedisPoolManager(config)
            await manager.__aenter__()

            result = await manager.execute_pipeline(
                "test_redis",
                [("GET", "key1"), ("HGET", "hash1", "field1")],
            )

            assert result == ["value1", "field_value"]
            mock_pipe.get.assert_called_once_with("key1")
            mock_pipe.hget.assert_called_once_with("hash1", "field1")

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_execute_pipeline_rejects_unsafe_command(self):
        """execute_pipeline raises RedisSafetyError for unsafe commands."""
        from thoth_mcp.db.redis import RedisPoolManager
        from thoth_mcp.utils.redis_safety import RedisSafetyError

        config = _make_config({
            "test_redis": _make_ds_config(),
        })

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=mock_client):
            manager = RedisPoolManager(config)
            await manager.__aenter__()

            with pytest.raises(RedisSafetyError):
                await manager.execute_pipeline(
                    "test_redis",
                    [("SET", "key1", "value1")],  # SET is not in allowlist
                )

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_execute_pipeline_unknown_instance(self):
        """execute_pipeline raises ValueError for unknown instance."""
        from thoth_mcp.db.redis import RedisPoolManager

        config = _make_config({})

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=AsyncMock()):
            manager = RedisPoolManager(config)
            await manager.__aenter__()

            with pytest.raises(ValueError, match="Unknown instance"):
                await manager.execute_pipeline("unknown_redis", [("GET", "key1")])

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_execute_pipeline_empty_commands(self):
        """execute_pipeline returns empty list for empty commands."""
        from thoth_mcp.db.redis import RedisPoolManager

        config = _make_config({
            "test_redis": _make_ds_config(),
        })

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=mock_client):
            manager = RedisPoolManager(config)
            await manager.__aenter__()

            result = await manager.execute_pipeline("test_redis", [])
            assert result == []

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_execute_pipeline_fail_fast_on_unsafe(self):
        """Pipeline rejects batch containing any unsafe command before Redis communication."""
        from thoth_mcp.db.redis import RedisPoolManager
        from thoth_mcp.utils.redis_safety import RedisSafetyError

        config = _make_config({
            "test_redis": _make_ds_config(),
        })

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()
        mock_client.pipeline = MagicMock()  # Should NOT be called

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=mock_client):
            manager = RedisPoolManager(config)
            await manager.__aenter__()

            # GET is safe, SET is not — entire batch should be rejected
            with pytest.raises(RedisSafetyError):
                await manager.execute_pipeline(
                    "test_redis",
                    [("GET", "key1"), ("SET", "key2", "value2")],
                )

            # Pipeline should never have been created
            mock_client.pipeline.assert_not_called()

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_execute_pipeline_redis_error(self):
        """execute_pipeline logs and re-raises RedisError."""
        from thoth_mcp.db.redis import RedisPoolManager
        from redis.exceptions import ConnectionError

        config = _make_config({
            "test_redis": _make_ds_config(),
        })

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        mock_pipe = AsyncMock()
        mock_pipe.get = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(side_effect=ConnectionError("Connection lost"))
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=False)

        mock_client.pipeline = MagicMock(return_value=mock_pipe)

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=mock_client):
            manager = RedisPoolManager(config)
            await manager.__aenter__()

            with pytest.raises(ConnectionError):
                await manager.execute_pipeline("test_redis", [("GET", "key1")])

            await manager.__aexit__(None, None, None)


class TestCreatePoolManager:
    """Test create_pool_manager factory function."""

    def test_create_pool_manager_returns_manager(self):
        """Factory function returns RedisPoolManager instance."""
        from thoth_mcp.db.redis import create_pool_manager, RedisPoolManager

        config = _make_config({})
        manager = create_pool_manager(config)

        assert isinstance(manager, RedisPoolManager)
        assert manager._config is config


class TestRedisPoolManagerStartup:
    """Test startup health check behavior."""

    @pytest.mark.asyncio
    async def test_startup_health_check_success(self):
        """Successful startup ping logs at INFO level."""
        from thoth_mcp.db.redis import RedisPoolManager

        config = _make_config({
            "test_redis": _make_ds_config(),
        })

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.aclose = AsyncMock()

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=mock_client), \
             patch("thoth_mcp.db.redis.logger") as mock_logger:
            manager = RedisPoolManager(config)
            await manager.__aenter__()

            # Should log INFO for successful health check
            info_calls = [c for c in mock_logger.info.call_args_list if "health check passed" in str(c)]
            assert len(info_calls) > 0

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_startup_health_check_failure_continues(self):
        """Failed startup ping logs WARNING but does not raise."""
        from thoth_mcp.db.redis import RedisPoolManager
        from redis.exceptions import ConnectionError

        config = _make_config({
            "test_redis": _make_ds_config(),
        })

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("refused"))
        mock_client.aclose = AsyncMock()

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", return_value=mock_client), \
             patch("thoth_mcp.db.redis.logger") as mock_logger:
            manager = RedisPoolManager(config)
            # Should NOT raise despite ping failure
            await manager.__aenter__()

            # Should log WARNING for failed health check
            warning_calls = [c for c in mock_logger.warning.call_args_list if "health check failed" in str(c)]
            assert len(warning_calls) > 0

            await manager.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_shutdown_closes_all_pools(self):
        """__aexit__ calls aclose on all clients and pools and clears dicts."""
        from thoth_mcp.db.redis import RedisPoolManager

        config = _make_config({
            "redis1": _make_ds_config(host="host1"),
            "redis2": _make_ds_config(host="host2"),
        })

        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()

        client1 = AsyncMock()
        client1.ping = AsyncMock(return_value=True)
        client1.aclose = AsyncMock()

        client2 = AsyncMock()
        client2.ping = AsyncMock(return_value=True)
        client2.aclose = AsyncMock()

        with patch("thoth_mcp.db.redis.ConnectionPool", return_value=mock_pool), \
             patch("thoth_mcp.db.redis.redis.Redis", side_effect=[client1, client2]):
            manager = RedisPoolManager(config)
            await manager.__aenter__()

            assert len(manager._clients) == 2
            assert len(manager._pools) == 2

            await manager.__aexit__(None, None, None)

            client1.aclose.assert_called_once()
            client2.aclose.assert_called_once()
            mock_pool.aclose.assert_called()
            assert len(manager._clients) == 0
            assert len(manager._pools) == 0
