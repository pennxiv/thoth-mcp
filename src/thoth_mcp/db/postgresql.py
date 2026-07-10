"""PostgreSQL connection pool manager with per-datasource independent pools."""
import asyncpg
from thoth_mcp.config import DatasourcesConfig
from thoth_mcp.utils.logger import logger


class PostgreSQLPoolManager:
    """Manages independent asyncpg connection pools for each PostgreSQL datasource."""

    def __init__(self, config: DatasourcesConfig) -> None:
        """Initialize pool manager with configuration.

        Args:
            config: Validated datasource configuration
        """
        self._config = config
        self._pools: dict[str, asyncpg.Pool] = {}

    async def __aenter__(self) -> "PostgreSQLPoolManager":
        """Create connection pools for all PostgreSQL datasources."""
        for name, ds_config in self._config.postgres.items():
            try:
                pool = await asyncpg.create_pool(
                    host=ds_config.host,
                    port=ds_config.port,
                    user=ds_config.user,
                    password=ds_config.password,
                    database=ds_config.database,
                    min_size=0,  # Don't pre-connect, avoids hanging on unreachable hosts
                    max_size=ds_config.max_pool_size,
                )
                self._pools[name] = pool
                logger.info(f"Created PostgreSQL pool for '{name}' (min={ds_config.min_pool_size}, max={ds_config.max_pool_size})")
            except Exception as e:
                logger.warning(f"Failed to create PostgreSQL pool for '{name}': {e}")

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close all connection pools gracefully."""
        for name, pool in self._pools.items():
            try:
                await pool.close()
                logger.info(f"Closed PostgreSQL pool for '{name}'")
            except Exception as e:
                logger.error(f"Error closing PostgreSQL pool for '{name}': {e}")

        self._pools.clear()

    async def _ensure_pool(self, name: str) -> None:
        """Lazy-initialize a pool for a datasource that was unavailable at startup."""
        if name in self._pools:
            return
        if name not in self._config.postgres:
            raise ValueError(f"Unknown datasource: {name}")

        ds_config = self._config.postgres[name]
        logger.info(f"Lazy-creating PostgreSQL pool for '{name}' (was unavailable at startup)")
        try:
            pool = await asyncpg.create_pool(
                host=ds_config.host,
                port=ds_config.port,
                user=ds_config.user,
                password=ds_config.password,
                database=ds_config.database,
                min_size=ds_config.min_pool_size,
                max_size=ds_config.max_pool_size,
            )
            self._pools[name] = pool
            logger.info(f"Lazy-created PostgreSQL pool for '{name}'")
        except Exception as e:
            logger.warning(f"Failed to lazy-create PostgreSQL pool for '{name}': {e}")
            raise ValueError(f"Datasource '{name}' is configured but currently unreachable. It will be retried on the next request.") from e

    async def execute(
        self,
        name: str,
        sql: str,
        *args,
    ) -> list[dict]:
        """Execute SQL query and return results as list of dicts.

        Args:
            name: Datasource name
            sql: SQL query string (should be validated by safe_sql first)
            *args: Query parameters for parameterized queries (asyncpg $1, $2, ...)

        Returns:
            List of dict rows from query result

        Raises:
            ValueError: If datasource name is unknown
            asyncpg.PostgresError: If query execution fails
        """
        await self._ensure_pool(name)

        pool = self._pools[name]

        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
            return [dict(row) for row in rows]

    async def health_check(self, name: str) -> bool:
        """Check if a datasource is reachable.

        Args:
            name: Datasource name

        Returns:
            True if datasource is reachable, False otherwise
        """
        if name not in self._pools:
            return False

        pool = self._pools[name]

        try:
            async with pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception as e:
            logger.error(f"Health check failed for '{name}': {e}")
            return False

    async def health_check_all(self) -> dict[str, bool]:
        """Check health of all datasources.

        Returns:
            Dict mapping datasource name to health status
        """
        results = {}
        for name in self._pools:
            status = await self.health_check(name)
            results[name] = status
            if status:
                logger.info(f"Health check passed for '{name}'")
            else:
                logger.warning(f"Health check failed for '{name}'")
        return results


def create_pool_manager(config: DatasourcesConfig) -> PostgreSQLPoolManager:
    """Factory function to create PostgreSQLPoolManager.

    Args:
        config: Validated datasource configuration

    Returns:
        PostgreSQLPoolManager instance (not yet entered)
    """
    return PostgreSQLPoolManager(config)