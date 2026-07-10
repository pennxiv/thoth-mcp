"""Result formatters for MySQL and Redis query results."""
from typing import Any


# Default max items for Redis collections (D-15)
DEFAULT_MAX_ITEMS = 100


def format_mysql_result(
    rows: list[dict[str, Any]],
    columns: list[str] | None = None,
    max_rows: int = 100,
) -> str:
    """
    Format MySQL query result as Markdown table.

    Args:
        rows: Query result rows (list of dicts from aiomysql DictCursor)
        columns: Column names (if None, extracted from first row)
        max_rows: Maximum rows to display (default: 100)

    Returns:
        Markdown table string with row count
    """
    # Empty result check
    if not rows:
        return "No results found."

    # Extract columns from first row if not provided
    if columns is None:
        columns = list(rows[0].keys())

    # Calculate totals
    total_rows = len(rows)
    display_rows = rows[:max_rows]

    # Build Markdown table
    lines = []

    # Header row
    header = "| " + " | ".join(str(col) for col in columns) + " |"
    lines.append(header)

    # Separator row
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    lines.append(separator)

    # Data rows
    for row in display_rows:
        values = []
        for col in columns:
            val = row.get(col)
            if val is None:
                values.append("NULL")
            else:
                values.append(str(val))
        lines.append("| " + " | ".join(values) + " |")

    # Row count indicator (per D-08)
    if total_rows > max_rows:
        lines.append(f"\nShowing {max_rows} of {total_rows} rows.")
    else:
        lines.append(f"\n{total_rows} row(s) returned.")

    return "\n".join(lines)


def format_redis_result(
    result: Any,
    command: str,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> str:
    """
    Format Redis command result as readable Markdown.

    Args:
        result: Raw result from Redis command
        command: Redis command name (determines format)
        max_items: Maximum items to display for collections (default: 100)

    Returns:
        Formatted Markdown string
    """
    cmd = command.upper()

    # Dispatch based on command (some commands handle None specially)
    if cmd == "GET":
        if result is None:
            return "Key not found or no value."
        return _format_string(result)
    if cmd == "MGET":
        return _format_list(result, max_items)
    if cmd in ("HGET", "HGETALL"):
        return _format_hash(result, cmd)
    if cmd in ("HKEYS", "HVALS"):
        return _format_list(result, max_items)
    if cmd == "LRANGE":
        return _format_list(result, max_items)
    if cmd == "LINDEX":
        if result is None:
            return "Index out of range or key not found."
        return _format_string(result)
    if cmd in ("SMEMBERS", "SRANDMEMBER"):
        return _format_set(result, max_items)
    if cmd == "ZRANGE":
        return _format_zset(result, max_items)
    # Scalar commands: TTL, TYPE, LLEN, HLEN, STRLEN, SCARD, EXISTS, HEXISTS, SISMEMBER, ZCARD, ZSCORE, ZRANK, ZREVRANK, ZCOUNT
    return _format_scalar(result, cmd)


def _format_string(result: Any) -> str:
    """Format string result (GET command)."""
    if isinstance(result, bytes):
        try:
            return result.decode("utf-8")
        except UnicodeDecodeError:
            return f"<binary data: {len(result)} bytes>"
    return str(result)


def _format_hash(result: Any, cmd: str) -> str:
    """Format hash result (HGET, HGETALL commands)."""
    if cmd == "HGET":
        if result is None:
            return "Field not found."
        return _format_string(result)

    # HGETALL
    if not result:
        return "Hash is empty or key not found."

    # Decode bytes keys/values if needed
    decoded = {}
    for k, v in result.items():
        key = k.decode("utf-8") if isinstance(k, bytes) else str(k)
        if v is None:
            decoded[key] = "NULL"
        elif isinstance(v, bytes):
            try:
                decoded[key] = v.decode("utf-8")
            except UnicodeDecodeError:
                decoded[key] = f"<binary data: {len(v)} bytes>"
        else:
            decoded[key] = str(v)

    # Build Markdown table
    lines = ["| Field | Value |", "| --- | --- |"]
    for key, value in decoded.items():
        lines.append(f"| {key} | {value} |")

    return "\n".join(lines)


def _format_list(result: Any, max_items: int) -> str:
    """Format list result (LRANGE command)."""
    if not result:
        return "List is empty."

    total = len(result)
    display = result[:max_items]

    lines = []
    for i, item in enumerate(display, 1):
        if isinstance(item, bytes):
            try:
                item = item.decode("utf-8")
            except UnicodeDecodeError:
                item = f"<binary data: {len(item)} bytes>"
        lines.append(f"{i}. {item}")

    if total > max_items:
        lines.append(f"\nShowing {max_items} of {total} items.")

    return "\n".join(lines)


def _format_set(result: Any, max_items: int) -> str:
    """Format set result (SMEMBERS, SRANDMEMBER commands)."""
    if not result:
        return "Set is empty."

    # Convert set to sorted list for consistent output
    items = sorted(result, key=lambda x: x.decode("utf-8") if isinstance(x, bytes) else str(x))
    total = len(items)
    display = items[:max_items]

    lines = []
    for item in display:
        if isinstance(item, bytes):
            try:
                item = item.decode("utf-8")
            except UnicodeDecodeError:
                item = f"<binary data: {len(item)} bytes>"
        lines.append(f"- {item}")

    if total > max_items:
        lines.append(f"\nShowing {max_items} of {total} items.")

    return "\n".join(lines)


def _format_zset(result: Any, max_items: int) -> str:
    """Format sorted set result (ZRANGE command)."""
    if not result:
        return "Sorted set is empty."

    total = len(result)
    display = result[:max_items]

    lines = []
    for i, item in enumerate(display, 1):
        # Handle both plain list and list of (member, score) tuples
        if isinstance(item, tuple) and len(item) == 2:
            member, score = item
            if isinstance(member, bytes):
                try:
                    member = member.decode("utf-8")
                except UnicodeDecodeError:
                    member = f"<binary data: {len(member)} bytes>"
            lines.append(f"{i}. {member} (score: {score})")
        else:
            if isinstance(item, bytes):
                try:
                    item = item.decode("utf-8")
                except UnicodeDecodeError:
                    item = f"<binary data: {len(item)} bytes>"
            lines.append(f"{i}. {item}")

    if total > max_items:
        lines.append(f"\nShowing {max_items} of {total} items.")

    return "\n".join(lines)


def _format_scalar(result: Any, cmd: str) -> str:
    """Format scalar result (TTL, TYPE, LLEN, HLEN, STRLEN, SCARD, EXISTS, HEXISTS, SISMEMBER, ZCARD, ZSCORE, ZRANK, ZREVRANK, ZCOUNT)."""
    if cmd == "TTL":
        if result == -2:
            return "Key does not exist."
        if result == -1:
            return "Key exists but has no expiry."
        return f"{result} seconds"

    if cmd in ("EXISTS", "HEXISTS", "SISMEMBER"):
        return "true" if result else "false"

    if cmd in ("ZSCORE", "ZRANK", "ZREVRANK"):
        if result is None:
            return "Member not found in sorted set."
        return str(result)

    # All other scalars: LLEN, HLEN, STRLEN, SCARD, ZCARD, ZCOUNT, TYPE
    return str(result) if result is not None else "(nil)"
