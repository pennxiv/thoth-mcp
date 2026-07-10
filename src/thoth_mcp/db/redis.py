"""Redis connection pool manager with per-instance independent pools."""
from typing import Any

import redis.asyncio as redis
from redis.asyncio import ConnectionPool
from redis.exceptions import RedisError

from thoth_mcp.config import DatasourcesConfig
from thoth_mcp.utils.logger import logger
from thoth_mcp.utils.redis_safety import validate_command


class RedisPoolManager:
    """Manages independent redis.asyncio connection pools for each Redis instance.

    Per D-02: Single class that manages all Redis instance pools.
    Per D-04: Async context manager for pool lifecycle.
    Per D-06: Each instance gets its own ConnectionPool keyed by name.
    """

    def __init__(self, config: DatasourcesConfig) -> None:
        """Initialize pool manager with configuration.

        Args:
            config: Validated datasource configuration
        """
        self._config = config
        self._pools: dict[str, ConnectionPool] = {}
        self._clients: dict[str, redis.Redis] = {}

    async def __aenter__(self) -> "RedisPoolManager":
        """Create connection pools for all Redis instances.

        Per D-05: Pools created on __aenter__.
        Per D-15: Log WARNING and continue if instance unavailable.
        """
        for name, ds_config in self._config.redis.items():
            try:
                pool = ConnectionPool(
                    host=ds_config.host,
                    port=ds_config.port,
                    password=ds_config.password,
                    db=ds_config.db,
                    max_connections=ds_config.max_pool_size,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    decode_responses=True,  # D-09: returns strings not bytes
                )
                client = redis.Redis(connection_pool=pool)
                self._pools[name] = pool
                self._clients[name] = client
                logger.info(
                    f"Created Redis pool for '{name}' "
                    f"(max_connections={ds_config.max_pool_size})"
                )
            except Exception as e:
                # D-15: Log WARNING and continue if instance unavailable
                logger.warning(f"Failed to create Redis pool for '{name}': {e}")

        await self._run_startup_health_checks()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close all connection pools gracefully.

        Per D-27: Use aclose() for redis.asyncio pools.
        Per D-28: Log each close.
        """
        for name, client in self._clients.items():
            try:
                await client.aclose()
                logger.info(f"Closed Redis client for '{name}'")
            except Exception as e:
                logger.error(f"Error closing Redis client for '{name}': {e}")

        for name, pool in self._pools.items():
            try:
                await pool.aclose()
                logger.info(f"Closed Redis pool for '{name}'")
            except Exception as e:
                logger.error(f"Error closing Redis pool for '{name}': {e}")

        self._clients.clear()
        self._pools.clear()

    async def _run_startup_health_checks(self) -> None:
        """Run health checks on all instances after pool creation. Per D-14."""
        for name, client in self._clients.items():
            try:
                await client.ping()
                logger.info(f"Redis health check passed for '{name}'")
            except Exception as e:
                logger.warning(f"Redis health check failed for '{name}': {e}")

    async def health_check(self, name: str) -> bool:
        """Check if a Redis instance is reachable.

        Per D-11: Uses PING command.
        Per D-12: Returns bool.

        Args:
            name: Instance name

        Returns:
            True if instance is reachable, False otherwise

        Raises:
            ValueError: If instance name is unknown
        """
        if name not in self._clients:
            raise ValueError(f"Unknown instance: {name}")

        client = self._clients[name]

        try:
            return await client.ping()
        except Exception as e:
            # D-31: Log errors at ERROR level
            logger.error(f"Health check failed for '{name}': {e}")
            return False

    async def health_check_all(self) -> dict[str, bool]:
        """Check health of all instances.

        Per D-13: Returns dict[str, bool].
        Per D-14: Logs results at INFO level.

        Returns:
            Dict mapping instance name to health status
        """
        results = {}
        for name in self._clients:
            try:
                status = await self.health_check(name)
            except ValueError:
                status = False
            results[name] = status
            if status:
                logger.info(f"Health check passed for '{name}'")
            else:
                logger.warning(f"Health check failed for '{name}'")
        return results

    def get_pool_status(self, name: str) -> dict:
        """Get status for a specific pool.

        Per D-16: Returns dict with pool stats.
        Per D-17: Status includes name, max_connections.

        Args:
            name: Instance name

        Returns:
            Dict with pool status

        Raises:
            ValueError: If instance name is unknown
        """
        if name not in self._pools:
            raise ValueError(f"Unknown instance: {name}")

        pool = self._pools[name]
        return {
            "name": name,
            "max_connections": pool.max_connections,
        }

    def get_all_pool_status(self) -> dict[str, dict]:
        """Get status for all pools.

        Per D-18: Returns dict[str, dict].

        Returns:
            Dict mapping instance name to pool status
        """
        return {name: self.get_pool_status(name) for name in self._pools}

    async def _ensure_client(self, name: str) -> None:
        """Lazy-initialize a client for an instance that was unavailable at startup."""
        if name in self._clients:
            return
        if name not in self._config.redis:
            raise ValueError(f"Unknown instance: {name}")

        ds_config = self._config.redis[name]
        logger.info(f"Lazy-creating Redis client for '{name}' (was unavailable at startup)")
        try:
            pool = ConnectionPool(
                host=ds_config.host,
                port=ds_config.port,
                password=ds_config.password,
                db=ds_config.db,
                max_connections=ds_config.max_pool_size,
                socket_connect_timeout=5,
                socket_timeout=5,
                decode_responses=True,
            )
            client = redis.Redis(connection_pool=pool)
            # Quick health check
            await client.ping()
            self._pools[name] = pool
            self._clients[name] = client
            logger.info(f"Lazy-created Redis client for '{name}'")
        except Exception as e:
            logger.warning(f"Failed to lazy-create Redis client for '{name}': {e}")
            raise ValueError(f"Instance '{name}' is configured but currently unreachable. It will be retried on the next request.") from e

    async def execute_pipeline(
        self,
        name: str,
        commands: list[tuple[str, ...]],
    ) -> list[Any]:
        """Execute multiple Redis commands in a pipeline batch.

        Per D-19: Single pipeline method for batch commands.
        Per D-20: Commands are list of tuples (command, *args).
        Per D-21: ALL commands validated before execution (fail-fast).
        Per D-22: Uses redis.asyncio Pipeline with transaction=False.
        Per D-23: Returns list of raw results.

        Args:
            name: Instance name
            commands: List of command tuples, e.g., [("GET", "key1"), ("HGET", "hash1", "field1")]

        Returns:
            List of results in same order as commands

        Raises:
            ValueError: If instance name is unknown
            RedisSafetyError: If any command is not in the allowlist
            RedisError: If pipeline execution fails
        """
        # Empty commands — no Redis communication needed
        if not commands:
            return []

        await self._ensure_client(name)

        # D-21: Validate ALL commands before execution (fail-fast)
        for cmd_tuple in commands:
            validate_command(cmd_tuple[0])

        client = self._clients[name]

        try:
            async with client.pipeline(transaction=False) as pipe:
                for cmd_tuple in commands:
                    command = cmd_tuple[0].lower()
                    args = cmd_tuple[1:]
                    getattr(pipe, command)(*args)
                results = await pipe.execute()
            return results
        except RedisError as e:
            # D-31: Log errors at ERROR level with instance name
            logger.error(f"Pipeline execution failed for '{name}': {e}")
            raise


def create_pool_manager(config: DatasourcesConfig) -> RedisPoolManager:
    """Factory function to create RedisPoolManager.

    Per D-03: Factory function returning RedisPoolManager instance.

    Args:
        config: Validated datasource configuration

    Returns:
        RedisPoolManager instance (not yet entered)
    """
    return RedisPoolManager(config)
