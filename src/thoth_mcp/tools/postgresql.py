"""PostgreSQL MCP tools for querying datasources and inspecting schemas."""
import re

from thoth_mcp.db.postgresql import PostgreSQLPoolManager
from thoth_mcp.utils.safe_sql import validate_sql, SQLValidationError
from thoth_mcp.utils.formatters import format_mysql_result
from thoth_mcp.utils.logger import logger


async def query_postgres(pool_manager: PostgreSQLPoolManager, datasource: str, sql: str, params: list[str] | None = None) -> str:
    """Execute a SELECT query against a PostgreSQL datasource and return results as a Markdown table.

    Allowed operations: SELECT queries only. All queries are validated before
    execution — non-SELECT statements (INSERT, UPDATE, DELETE, DROP, ALTER, etc.)
    are rejected. SQL injection patterns are detected and blocked.

    Examples:
    - query_postgres(datasource="analytics", sql="SELECT * FROM users LIMIT 10")
    - query_postgres(datasource="analytics", sql="SELECT * FROM users WHERE id = $1", params=["42"])
    - query_postgres(datasource="warehouse", sql="SELECT COUNT(*) FROM events WHERE date > '2024-01-01'")

    This tool does NOT support INSERT, UPDATE, DELETE, DROP, ALTER, or any
    write operations. All queries are validated as SELECT-only before execution.
    SQL injection patterns (UNION injection, comment obfuscation, multi-statement
    attacks) are detected and blocked.
    """
    logger.debug(f"query_postgres: datasource='{datasource}', sql='{sql[:100]}'")

    try:
        validated_sql = validate_sql(sql)
    except SQLValidationError as e:
        logger.warning(f"SQL validation failed: {e}")
        return f"Query rejected: {e}"

    try:
        safe_params = tuple(params) if params else ()
        rows = await pool_manager.execute(datasource, validated_sql, *safe_params)
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"Query execution failed for '{datasource}': {e}")
        return f"Query execution failed: {type(e).__name__}. Check the SQL syntax and datasource availability."

    return format_mysql_result(rows)


async def list_tables_postgres(pool_manager: PostgreSQLPoolManager, datasource: str) -> str:
    """List all tables in a PostgreSQL datasource (public schema).

    Allowed operations: Read-only schema inspection. Returns table names only.

    Examples:
    - list_tables_postgres(datasource="analytics")

    This tool only reads schema metadata and does not modify the database.
    It does not show table sizes, row counts, or index information.
    """
    logger.info(f"list_tables_postgres: datasource='{datasource}'")

    try:
        rows = await pool_manager.execute(
            datasource,
            "SELECT tablename AS \"Table\" FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"list_tables_postgres failed for '{datasource}': {e}")
        return f"Failed to list tables: {type(e).__name__}. Check datasource availability."

    if not rows:
        return f"No tables found in datasource '{datasource}'."

    # Format as Markdown table
    lines = ["| # | Table |", "| --- | --- |"]
    for i, row in enumerate(rows, 1):
        table_name = row["Table"]
        lines.append(f"| {i} | {table_name} |")

    lines.append(f"\n{len(rows)} table(s) found.")
    return "\n".join(lines)


async def describe_table_postgres(
    pool_manager: PostgreSQLPoolManager, datasource: str, table: str
) -> str:
    """Describe the schema of a table in a PostgreSQL datasource (public schema).

    Returns column names, types, nullability, and defaults as a
    Markdown table.

    Allowed operations: Read-only schema inspection for a single table.

    Examples:
    - describe_table_postgres(datasource="analytics", table="users")
    - describe_table_postgres(datasource="warehouse", table="events")

    This tool only reads schema metadata and does not modify the database.
    It does not show indexes, foreign keys, or row counts.
    """
    logger.info(f"describe_table_postgres: datasource='{datasource}', table='{table}'")

    try:
        _validate_table_name(table)
    except ValueError:
        return f"Invalid table name: {table}. Only alphanumeric characters and underscores are allowed."

    try:
        rows = await pool_manager.execute(
            datasource,
            """SELECT column_name AS "Field",
                      data_type AS "Type",
                      CASE WHEN is_nullable = 'YES' THEN 'YES' ELSE 'NO' END AS "Null",
                      column_default AS "Default"
               FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = $1
               ORDER BY ordinal_position""",
            table,
        )
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"describe_table_postgres failed for '{datasource}.{table}': {e}")
        return f"Failed to describe table '{table}': {type(e).__name__}. Check the table name and datasource availability."

    if not rows:
        return f"Table '{table}' not found in datasource '{datasource}'."

    return format_mysql_result(rows)


def _validate_table_name(table: str) -> str:
    """Validate table name as safe identifier."""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table):
        raise ValueError(f"Invalid table name: {table}")
    return table


async def get_table_ddl_postgres(
    pool_manager: PostgreSQLPoolManager, datasource: str, table: str
) -> str:
    """Get the DDL (CREATE TABLE statement) for a table in a PostgreSQL datasource.

    Returns a CREATE TABLE statement with column definitions, data types,
    nullability, defaults, primary key, unique constraints, and check constraints.

    Allowed operations: Read-only schema inspection for a single table.

    Examples:
    - get_table_ddl_postgres(datasource="analytics", table="users")
    - get_table_ddl_postgres(datasource="warehouse", table="events")

    This tool only reads schema metadata and does not modify the database.
    """
    logger.info(f"get_table_ddl_postgres: datasource='{datasource}', table='{table}'")

    try:
        _validate_table_name(table)
    except ValueError:
        return f"Invalid table name: {table}. Only alphanumeric characters and underscores are allowed."

    try:
        # Get column definitions
        columns_rows = await pool_manager.execute(
            datasource,
            """SELECT column_name AS name,
                      data_type AS type,
                      character_maximum_length AS char_len,
                      numeric_precision AS num_precision,
                      numeric_scale AS num_scale,
                      is_nullable AS nullable,
                      column_default AS default_val,
                      is_identity
               FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = $1
               ORDER BY ordinal_position""",
            table,
        )
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error(f"get_table_ddl_postgres failed for '{datasource}.{table}': {e}")
        return f"Failed to get DDL for '{table}': {type(e).__name__}. Check the table name and datasource availability."

    if not columns_rows:
        return f"Table '{table}' not found in datasource '{datasource}'."

    # Get primary key info
    pk_rows = await pool_manager.execute(
        datasource,
        """SELECT kcu.column_name
           FROM information_schema.table_constraints tc
           JOIN information_schema.key_column_usage kcu
             ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
           WHERE tc.constraint_type = 'PRIMARY KEY'
             AND tc.table_schema = 'public'
             AND tc.table_name = $1
           ORDER BY kcu.ordinal_position""",
        table,
    )
    primary_keys = {row["column_name"] for row in pk_rows}

    # Get unique constraints
    unique_rows = await pool_manager.execute(
        datasource,
        """SELECT kcu.column_name, tc.constraint_name
           FROM information_schema.table_constraints tc
           JOIN information_schema.key_column_usage kcu
             ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
           WHERE tc.constraint_type = 'UNIQUE'
             AND tc.table_schema = 'public'
             AND tc.table_name = $1
           ORDER BY tc.constraint_name, kcu.ordinal_position""",
        table,
    )

    # Get check constraints
    check_rows = await pool_manager.execute(
        datasource,
        """SELECT cc.check_clause
           FROM information_schema.check_constraints cc
           WHERE cc.constraint_schema = 'public'
             AND cc.table_name = $1""",
        table,
    )

    # Get indexes (excluding primary key indexes)
    index_rows = await pool_manager.execute(
        datasource,
        """SELECT ix.indexname, ix.indexdef
           FROM pg_indexes ix
           WHERE ix.schemaname = 'public'
             AND ix.tablename = $1
             AND ix.indexname NOT IN (
                 SELECT constraint_name
                 FROM information_schema.table_constraints
                 WHERE table_schema = 'public'
                   AND table_name = $1
             )""",
        table,
    )

    # Build DDL
    lines = [f"CREATE TABLE {table} ("]
    column_defs = []

    for col in columns_rows:
        col_name = col["name"]
        col_type = col["type"]

        # Handle type with length/precision
        if col["char_len"] is not None:
            col_type = f"{col['type']}({col['char_len']})"
        elif col["num_precision"] is not None and col["num_scale"] is not None:
            col_type = f"{col['type']}({col['num_precision']},{col['num_scale']})"
        elif col["num_precision"] is not None:
            col_type = f"{col['type']}({col['num_precision']})"

        col_def = f"  {col_name} {col_type}"

        if col["nullable"] == "NO":
            col_def += " NOT NULL"
        if col["default_val"] is not None:
            col_def += f" DEFAULT {col['default_val']}"
        if col["is_identity"] == "YES":
            col_def += " GENERATED ALWAYS AS IDENTITY"

        column_defs.append(col_def)

    # Add primary key constraint
    if primary_keys:
        column_defs.append(f"  PRIMARY KEY ({', '.join(sorted(primary_keys))})")

    # Add unique constraints
    unique_constraints: dict[str, list[str]] = {}
    for row in unique_rows:
        constraint_name = row["constraint_name"]
        if constraint_name not in unique_constraints:
            unique_constraints[constraint_name] = []
        unique_constraints[constraint_name].append(row["column_name"])

    for constraint_name, columns in unique_constraints.items():
        column_defs.append(f"  UNIQUE ({', '.join(columns)})")

    # Add check constraints
    for row in check_rows:
        column_defs.append(f"  CHECK ({row['check_clause']})")

    lines.append(",\n".join(column_defs))
    lines.append(");")

    # Add index definitions
    for row in index_rows:
        index_def = row["indexdef"]
        # Index def already includes the full CREATE INDEX statement
        lines.append(f"\n{index_def};")

    return "\n".join(lines)
