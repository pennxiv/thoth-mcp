"""Redis command safety validation module with allowlist enforcement."""
from thoth_mcp.utils.logger import logger


# D-03, D-05: Allowed commands (read-only, safe)
ALLOWED_COMMANDS = frozenset({
    "GET",
    "MGET",
    "STRLEN",
    "HGET",
    "HGETALL",
    "HKEYS",
    "HVALS",
    "HLEN",
    "HEXISTS",
    "LRANGE",
    "LINDEX",
    "LLEN",
    "SMEMBERS",
    "SISMEMBER",
    "SCARD",
    "SRANDMEMBER",
    "ZRANGE",
    "ZRANK",
    "ZREVRANK",
    "ZSCORE",
    "ZCARD",
    "ZCOUNT",
    "TTL",
    "TYPE",
    "EXISTS",
    "PING",
})


class RedisSafetyError(Exception):
    """Raised when Redis command fails safety validation."""
    pass


def validate_command(command: str) -> None:
    """
    Validate Redis command against allowlist.

    Args:
        command: Redis command name to validate

    Returns:
        None if command is allowed

    Raises:
        RedisSafetyError: If command is not in the allowlist
    """
    cmd_upper = command.upper().strip()

    if cmd_upper not in ALLOWED_COMMANDS:
        logger.warning(f"Redis command rejected: {command}")
        raise RedisSafetyError(
            f"Command '{command}' is not allowed. "
            f"Allowed commands: {', '.join(sorted(ALLOWED_COMMANDS))}"
        )
