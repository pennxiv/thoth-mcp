"""SQL safety validation module with three-layer defense."""
import re
import sqlparse
from thoth_mcp.utils.logger import logger


DEFAULT_LIMIT = 100  # D-07


class SQLValidationError(Exception):
    """Raised when SQL fails safety validation."""
    pass


def validate_sql(sql: str, limit: int = DEFAULT_LIMIT) -> str:
    """
    Validate SQL through three-layer defense.

    Args:
        sql: SQL query string to validate
        limit: Default LIMIT to apply if missing (default: 100)

    Returns:
        Validated SQL string with LIMIT clause

    Raises:
        SQLValidationError: If validation fails
    """
    # Layer 1: SELECT-only enforcement
    _validate_select_only(sql)

    # Layer 2: Injection pattern detection
    _detect_injection_patterns(sql)

    # Layer 3: Automatic LIMIT injection
    validated_sql = _inject_limit(sql, limit)

    return validated_sql


def _validate_select_only(sql: str) -> None:
    """Layer 1: Reject non-SELECT statements."""
    parsed = sqlparse.parse(sql)
    if not parsed:
        logger.warning("Empty SQL statement rejected")
        raise SQLValidationError("Empty SQL statement")

    stmt = parsed[0]
    stmt_type = stmt.get_type()

    if stmt_type != "SELECT":
        logger.warning(f"Non-SELECT query rejected: {stmt_type}")
        raise SQLValidationError(f"Only SELECT queries are allowed. Found: {stmt_type}")


def _detect_injection_patterns(sql: str) -> None:
    """Layer 2: Detect SQL injection patterns."""
    patterns = [
        (r'\bUNION\b.*\bSELECT\b', "UNION injection"),
        (r'--', "comment sequence '--'"),
        (r'/\*.*?\*/', "comment sequence '/* */'"),
        # Semicolon followed by additional SQL (multi-statement attack)
        (r';\s*\w+', "semicolon (multi-statement)"),
    ]

    for pattern, description in patterns:
        if re.search(pattern, sql, re.IGNORECASE | re.DOTALL):
            logger.warning(f"SQL injection detected: {description}")
            raise SQLValidationError(f"SQL injection detected: {description}")


def _inject_limit(sql: str, limit: int) -> str:
    """Layer 3: Append LIMIT if not present."""
    if re.search(r'\bLIMIT\b\s+\d+', sql, re.IGNORECASE):
        return sql

    # Strip trailing semicolon, append LIMIT
    clean_sql = sql.rstrip().rstrip(';')
    return f"{clean_sql} LIMIT {limit}"
