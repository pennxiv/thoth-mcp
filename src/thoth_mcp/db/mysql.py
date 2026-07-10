"""MySQL connection pool manager with per-datasource independent pools."""
import aiomysql
from thoth_mcp.config import DatasourcesConfig
from thoth_mcp.utils.logger import logger


class MySQLPoolManager:
    """Manages independent aiomysql connection pools for each MySQL datasource.

    Per D-02: Single class that manages all MySQL datasource pools.
    Per D-04: Async context manager for pool lifecycle.
    Per D-06: Each datasource gets its own aiomysql.Pool keyed by name.
    """

    def __init__(self, config: DatasourcesConfig) -> None:
        """Initialize pool manager with configuration.

        Args:
            config: Validated datasource configuration
        """
        self._config = config
        self._pools: dict[str, aiomysql.Pool] = {}

    async def __aenter__(self) -> "MySQLPoolManager":
        """Create connection pools for all MySQL datasources.

        Per D-05: Pools created on __aenter__.
        Per D-17: Log WARNING and continue if datasource unavailable.
        """
        for name, ds_config in self._config.mysql.items():
            try:
                pool = await aiomysql.create_pool(
                    host=ds_config.host,
                    port=ds_config.port,
                    connect_timeout=5,
                    user=ds_config.user,
                    password=ds_config.password,
                    db=ds_config.database,
                    minsize=ds_config.min_pool_size,
                    maxsize=ds_config.max_pool_size,
                    pool_recycle=25200,  # D-15: 7 hours, less than MySQL's 8-hour wait_timeout
                    autocommit=True,
                )
                self._pools[name] = pool
                logger.info(f"Created MySQL pool for '{name}' (min={ds_config.min_pool_size}, max={ds_config.max_pool_size})")
            except Exception as e:
                # D-17: Log WARNING and continue if datasource unavailable
                logger.warning(f"Failed to create MySQL pool for '{name}': {e}")

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close all connection pools gracefully.

        Per D-05: Pools closed on __aexit__.
        """
        for name, pool in self._pools.items():
            try:
                pool.close()
                await pool.wait_closed()
                logger.info(f"Closed MySQL pool for '{name}'")
            except Exception as e:
                logger.error(f"Error closing MySQL pool for '{name}': {e}")

        self._pools.clear()

    async def _ensure_pool(self, name: str) -> None:
        """Lazy-initialize a pool for a datasource that was unavailable at startup.

        If a datasource is in the config but has no pool (startup failed),
        attempt to create it now. This allows transient network issues at
        startup to self-heal without a server restart.
        """
        if name in self._pools:
            return
        if name not in self._config.mysql:
            raise ValueError(f"Unknown datasource: {name}")

        ds_config = self._config.mysql[name]
        logger.info(f"Lazy-creating MySQL pool for '{name}' (was unavailable at startup)")
        try:
            pool = await aiomysql.create_pool(
                host=ds_config.host,
                port=ds_config.port,
                connect_timeout=5,
                user=ds_config.user,
                password=ds_config.password,
                db=ds_config.database,
                minsize=ds_config.min_pool_size,
                maxsize=ds_config.max_pool_size,
                pool_recycle=25200,
                autocommit=True,
            )
            self._pools[name] = pool
            logger.info(f"Lazy-created MySQL pool for '{name}'")
        except Exception as e:
            logger.warning(f"Failed to lazy-create MySQL pool for '{name}': {e}")
            raise ValueError(f"Datasource '{name}' is configured but currently unreachable. It will be retried on the next request.") from e

    async def execute(
        self,
        name: str,
        sql: str,
        params: tuple = (),
    ) -> list[dict]:
        """Execute SQL query and return results as list of dicts.

        Per D-23: Uses aiomysql.DictCursor for dict results.
        Per D-24: Returns list[dict] matching formatter input.

        Args:
            name: Datasource name
            sql: SQL query string (should be validated by safe_sql first)
            params: Query parameters for parameterized queries

        Returns:
            List of dict rows from query result

        Raises:
            ValueError: If datasource name is unknown
            aiomysql.Error: If query execution fails
        """
        await self._ensure_pool(name)

        pool = self._pools[name]

        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, params)
                result = await cur.fetchall()
                return list(result) if result else []

    async def health_check(self, name: str) -> bool:
        """Check if a datasource is reachable.

        Per D-08: Uses SELECT 1 query.
        Per D-09: Returns bool.

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
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    result = await cur.fetchone()
                    return result is not None and result[0] == 1
        except Exception as e:
            # D-22: Log errors at ERROR level
            logger.error(f"Health check failed for '{name}': {e}")
            return False

    async def health_check_all(self) -> dict[str, bool]:
        """Check health of all datasources.

        Per D-10: Returns dict[str, bool].
        Per D-18: Logs results at INFO level.

        Returns:
            Dict mapping datasource name to health status
        """
        results = {}
        for name in self._pools:
            status = await self.health_check(name)
            results[name] = status
            # D-18: Log each result at INFO level
            if status:
                logger.info(f"Health check passed for '{name}'")
            else:
                logger.warning(f"Health check failed for '{name}'")
        return results

    def get_pool_status(self, name: str) -> dict:
        """Get status for a specific pool.

        Per D-12: Returns dict with pool stats.
        Per D-13: Status includes name, size, minsize, maxsize, freesize.

        Args:
            name: Datasource name

        Returns:
            Dict with pool status

        Raises:
            ValueError: If datasource name is unknown
        """
        if name not in self._pools:
            raise ValueError(f"Unknown datasource: {name}")

        pool = self._pools[name]
        return {
            "name": name,
            "size": pool.size,
            "minsize": pool.minsize,
            "maxsize": pool.maxsize,
            "freesize": pool.freesize,
        }

    def get_all_pool_status(self) -> dict[str, dict]:
        """Get status for all pools.

        Per D-14: Returns dict[str, dict].

        Returns:
            Dict mapping datasource name to pool status
        """
        return {name: self.get_pool_status(name) for name in self._pools}


def create_pool_manager(config: DatasourcesConfig) -> MySQLPoolManager:
    """Factory function to create MySQLPoolManager.

    Per D-03: Factory function returning MySQLPoolManager instance.

    Args:
        config: Validated datasource configuration

    Returns:
        MySQLPoolManager instance (not yet entered)
    """
    return MySQLPoolManager(config)