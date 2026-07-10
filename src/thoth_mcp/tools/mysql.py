"""MySQL MCP tools for querying datasources and inspecting schemas."""
import re

from thoth_mcp.db.mysql import MySQLPoolManager
from thoth_mcp.utils.safe_sql import validate_sql, SQLValidationError
from thoth_mcp.utils.formatters import format_mysql_result
from thoth_mcp.utils.logger import logger


async def query_mysql(pool_manager: MySQLPoolManager, datasource: str, sql: str, params: list[str] | None = None) -> str:
    """Execute a SELECT query against a MySQL datasource and return results as a Markdown table.

    Allowed operations: SELECT queries only. All queries are validated before
    execution — non-SELECT statements (INSERT, UPDATE, DELETE, DROP, ALTER, etc.)
    are rejected. SQL injection patterns are detected and blocked.

    Examples:
    - query_mysql(datasource="prod_db", sql="SELECT * FROM users LIMIT 10")
    - query_mysql(datasource="prod_db", sql="SELECT * FROM users WHERE id = %s", params=["42"])
    - query_mysql(datasource="analytics", sql="SELECT COUNT(*) FROM events WHERE date > '2024-01-01'")

    This tool does NOT support INSERT, UPDATE, DELETE, DROP, ALTER, or any
    write operations. All queries are validated as SELECT-only before execution.
    SQL injection patterns (UNION injection, comment obfuscation, multi-statement
    attacks) are detected and blocked.
    """
    logger.debug(f"query_mysql: datasource='{datasource}', sql='{sql[:100]}'")

    # Step 1: Validate SQL through three-layer defense
    try:
        validated_sql = validate_sql(sql)
    except SQLValidationError as e:
        logger.warning(f"SQL validation failed: {e}")
        return f"Query rejected: {e}"

    # Step 2: Execute validated query
    try:
        safe_params = tuple(params) if params else ()
        rows = await pool_manager.execute(datasource, validated_sql, safe_params)
    except ValueError as e:
        return str(e)
    except Exception as e:
        # Database error — sanitize to avoid leaking connection details (SAFE-04)
        logger.error(f"Query execution failed for '{datasource}': {e}")
        return f"Query execution failed: {type(e).__name__}. Check the SQL syntax and datasource availability."

    # Step 3: Format results as Markdown table
    return format_mysql_result(rows)


async def list_tables(pool_manager: MySQLPoolManager, datasource: str) -> str:
    """List all tables in a MySQL datasource (current database only).

    Allowed operations: Read-only schema inspection. Returns table names only.

    Examples:
    - list_tables(datasource="prod_db")
    - list_tables(datasource="analytics")

    This tool only reads schema metadata and does not modify the database.
    It does not show table sizes, row counts, or index information.
    """
    logger.info(f"list_tables: datasource='{datasource}'")

    try:
        rows = await pool_manager.execute(
            datasource,
            "SELECT TABLE_NAME AS \"Table\" FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME")
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"list_tables failed for '{datasource}': {e}")
        return f"Failed to list tables: {type(e).__name__}. Check datasource availability."

    if not rows:
        return f"No tables found in datasource '{datasource}'."

    # Format as Markdown table
    lines = []
    lines.append("| # | Table |")
    lines.append("| --- | --- |")
    for i, row in enumerate(rows, 1):
        table_name = row["Table"]
        lines.append(f"| {i} | {table_name} |")

    lines.append(f"\n{len(rows)} table(s) found.")
    return "\n".join(lines)


async def describe_table(
    pool_manager: MySQLPoolManager, datasource: str, table: str
) -> str:
    """Describe the schema of a table in a MySQL datasource.

    Returns column names, types, nullability, keys, and defaults as a
    Markdown table.

    Allowed operations: Read-only schema inspection for a single table.

    Examples:
    - describe_table(datasource="prod_db", table="users")
    - describe_table(datasource="analytics", table="events")

    This tool only reads schema metadata and does not modify the database.
    It does not show indexes, foreign keys, or row counts.
    """
    logger.info(f"describe_table: datasource='{datasource}', table='{table}'")

    # D-19: Validate table name to prevent injection
    try:
        _validate_table_name(table)
    except ValueError:
        return f"Invalid table name: {table}. Only alphanumeric characters and underscores are allowed."

    try:
        rows = await pool_manager.execute(
            datasource,
            """SELECT COLUMN_NAME AS "Field",
                      COLUMN_TYPE AS "Type",
                      IF(IS_NULLABLE = 'YES', 'YES', 'NO') AS "Null",
                      COLUMN_DEFAULT AS "Default"
               FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION""",
            (table,))
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"describe_table failed for '{datasource}.{table}': {e}")
        return f"Failed to describe table '{table}': {type(e).__name__}. Check the table name and datasource availability."

    if not rows:
        return f"Table '{table}' not found in datasource '{datasource}'."

    return format_mysql_result(rows)


def _validate_table_name(table: str) -> str:
    """Validate table name as safe MySQL identifier. Per D-19."""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
        raise ValueError(f"Invalid table name: {table}")
    return table