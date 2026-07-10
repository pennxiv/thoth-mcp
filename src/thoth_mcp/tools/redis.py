"""Redis MCP tools for querying Redis instances."""
from thoth_mcp.db.redis import RedisPoolManager
from thoth_mcp.utils.redis_safety import validate_command, RedisSafetyError
from thoth_mcp.utils.formatters import format_redis_result
from thoth_mcp.utils.logger import logger


async def query_redis(
    pool_manager: RedisPoolManager,
    datasource: str,
    command: str,
    args: list[str] | None = None,
) -> str:
    """Execute a safe read-only command against a Redis instance and return formatted results.

    Allowed operations: Read-only Redis commands only. Only explicitly allowed
    commands are executable (GET, MGET, HGET, HGETALL, HKEYS, HVALS, HLEN,
    LRANGE, LINDEX, SMEMBERS, SISMEMBER, TTL, TYPE, LLEN, SCARD, EXISTS,
    HEXISTS, SRANDMEMBER, ZCARD, ZSCORE, ZRANGE, ZRANK, ZREVRANK, ZCOUNT,
    STRLEN, PING).
    All other commands are rejected.

    Examples:
    - query_redis(datasource="cache", command="GET", args=["user:123"])
    - query_redis(datasource="session_store", command="HGETALL", args=["session:abc"])
    - query_redis(datasource="cache", command="TTL", args=["temp_key"])

    This tool does NOT support SET, DEL, FLUSHALL, FLUSHDB, or any write
    operations. Only explicitly allowed read-only commands are permitted.
    Commands like KEYS (dangerous in production) and GETSET (atomic
    get-and-set) are explicitly excluded.
    """
    logger.debug(f"query_redis: datasource='{datasource}', command='{command}', args={args}")

    # Step 1: Validate command against allowlist
    try:
        validate_command(command)
    except RedisSafetyError as e:
        logger.warning(f"Redis command rejected: {command}")
        return f"Command rejected: {e}"

    # Step 2: Execute command via pipeline
    cmd_args = args or []
    try:
        results = await pool_manager.execute_pipeline(
            datasource, [(command, *cmd_args)]
        )
    except ValueError as e:
        return str(e)
    except Exception as e:
        # Database error — sanitize (SAFE-04)
        logger.error(f"Redis command failed for '{datasource}': {e}")
        return f"Command execution failed: {type(e).__name__}. Check the instance availability and command arguments."

    # Step 3: Format result
    if not results:
        return "No result returned."

    return format_redis_result(results[0], command)
