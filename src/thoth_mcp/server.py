"""FastMCP server assembly for Thoth MCP."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from thoth_mcp.config import load_config
from thoth_mcp.db.mysql import create_pool_manager as create_mysql_pool_manager
from thoth_mcp.db.postgresql import create_pool_manager as create_postgres_pool_manager
from thoth_mcp.db.redis import create_pool_manager as create_redis_pool_manager
from thoth_mcp.tools.discovery import list_datasources as list_datasources_tool
from thoth_mcp.tools.mysql import (
    describe_table as describe_table_tool,
    list_tables as list_tables_tool,
    query_mysql as query_mysql_tool,
)
from thoth_mcp.tools.postgresql import (
    describe_table_postgres as describe_table_postgres_tool,
    get_table_ddl_postgres as get_table_ddl_postgres_tool,
    list_tables_postgres as list_tables_postgres_tool,
    query_postgres as query_postgres_tool,
)
from thoth_mcp.tools.redis import query_redis as query_redis_tool
from thoth_mcp.utils.logger import logger

SERVER_INSTRUCTIONS = (
    "Use health_check_all first to determine which datasources are available. "
    "Use list_datasources when you are unsure which datasource to query. "
    "Use health_check(datasource=...) to test a single datasource before querying it. "
    "If a query fails, the error message will tell you exactly what went wrong — read it and adapt. "
    "Choose a datasource first before running queries. "
    "MySQL access is read-only and you should prefer LIMIT clauses. "
    "Use list_tables and describe_table before querying unfamiliar MySQL tables. "
    "PostgreSQL access is read-only and you should prefer LIMIT clauses. "
    "Use list_tables_postgres and describe_table_postgres before querying unfamiliar PostgreSQL tables. "
    "Use get_table_ddl_postgres to get the full CREATE TABLE DDL for a PostgreSQL table. "
    "Redis access supports only safe read-only commands."
)


class _FallbackFastMCP:
    """Minimal fallback used when the MCP SDK is unavailable in the environment."""

    def __init__(self, name: str, instructions: str = "", lifespan=None):
        self.name = name
        self.instructions = instructions
        self.lifespan = lifespan
        self._tools: dict[str, Any] = {}

    def tool(self, name: str | None = None):
        def decorator(func):
            self._tools[name or func.__name__] = func
            return func

        return decorator


try:
    from fastmcp import FastMCP, Context  # type: ignore
except Exception:
    try:
        from mcp.server.fastmcp import FastMCP, Context  # type: ignore
    except Exception:  # pragma: no cover - fallback for local test env
        FastMCP = _FallbackFastMCP
        Context = None  # type: ignore


@asynccontextmanager
async def app_lifespan(_: Any):
    """Create shared config and pool managers for the FastMCP app."""
    config = load_config()
    mysql_pool_manager = create_mysql_pool_manager(config)
    postgres_pool_manager = create_postgres_pool_manager(config)
    redis_pool_manager = create_redis_pool_manager(config)

    mysql_entered = None
    postgres_entered = None
    redis_entered = None
    try:
        mysql_entered = await mysql_pool_manager.__aenter__()
        postgres_entered = await postgres_pool_manager.__aenter__()
        redis_entered = await redis_pool_manager.__aenter__()
        yield {
            "config": config,
            "mysql_pool_manager": mysql_entered,
            "postgres_pool_manager": postgres_entered,
            "redis_pool_manager": redis_entered,
        }
    finally:
        shutdown_errors: list[Exception] = []
        if postgres_entered is not None:
            try:
                await postgres_pool_manager.__aexit__(None, None, None)
            except Exception as exc:  # pragma: no cover
                shutdown_errors.append(exc)
                logger.error(f"PostgreSQL shutdown failed: {exc}")
        if redis_entered is not None:
            try:
                await redis_pool_manager.__aexit__(None, None, None)
            except Exception as exc:  # pragma: no cover
                shutdown_errors.append(exc)
                logger.error(f"Redis shutdown failed: {exc}")
        if mysql_entered is not None:
            try:
                await mysql_pool_manager.__aexit__(None, None, None)
            except Exception as exc:  # pragma: no cover
                shutdown_errors.append(exc)
                logger.error(f"MySQL shutdown failed: {exc}")
        if shutdown_errors:
            logger.warning("Server shutdown completed with cleanup errors")


def _sanitize_unexpected_error(exc: Exception, tool_name: str) -> str:
    """Return a useful error message without leaking sensitive internals."""
    logger.error(f"{tool_name} unhandled error: {exc}", exc_info=True)
    exc_name = type(exc).__name__
    exc_msg = str(exc)
    # Truncate long messages but keep the type visible
    if len(exc_msg) > 200:
        exc_msg = exc_msg[:200] + "..."
    return f"Unexpected error in {tool_name}: {exc_name}: {exc_msg}"


def create_app():
    """Create and configure the FastMCP application."""
    app = FastMCP("thoth-mcp", instructions=SERVER_INSTRUCTIONS, lifespan=app_lifespan)

    @app.tool()
    async def query_mysql(datasource: str, sql: str, ctx: Context, params: list[str] | None = None) -> str:
        """Execute a SELECT query against a MySQL datasource. Use %s placeholders with params for safe value injection."""
        try:
            return await query_mysql_tool(
                ctx.request_context.lifespan_context["mysql_pool_manager"], datasource, sql, params
            )
        except Exception as exc:
            return _sanitize_unexpected_error(exc, "query_mysql")

    @app.tool()
    async def list_tables(datasource: str, ctx: Context) -> str:
        """List all tables in a MySQL datasource."""
        try:
            return await list_tables_tool(
                ctx.request_context.lifespan_context["mysql_pool_manager"], datasource
            )
        except Exception as exc:
            return _sanitize_unexpected_error(exc, "list_tables")

    @app.tool()
    async def describe_table(datasource: str, table: str, ctx: Context) -> str:
        """Describe column details for a MySQL table."""
        try:
            return await describe_table_tool(
                ctx.request_context.lifespan_context["mysql_pool_manager"], datasource, table
            )
        except Exception as exc:
            return _sanitize_unexpected_error(exc, "describe_table")

    @app.tool()
    async def query_postgres(datasource: str, sql: str, ctx: Context, params: list[str] | None = None) -> str:
        """Execute a SELECT query against a PostgreSQL datasource. Use $1, $2 placeholders with params for safe value injection."""
        try:
            return await query_postgres_tool(
                ctx.request_context.lifespan_context["postgres_pool_manager"], datasource, sql, params
            )
        except Exception as exc:
            return _sanitize_unexpected_error(exc, "query_postgres")

    @app.tool()
    async def list_tables_postgres(datasource: str, ctx: Context) -> str:
        """List all tables in a PostgreSQL datasource."""
        try:
            return await list_tables_postgres_tool(
                ctx.request_context.lifespan_context["postgres_pool_manager"], datasource
            )
        except Exception as exc:
            return _sanitize_unexpected_error(exc, "list_tables_postgres")

    @app.tool()
    async def describe_table_postgres(datasource: str, table: str, ctx: Context) -> str:
        """Describe column details for a PostgreSQL table."""
        try:
            return await describe_table_postgres_tool(
                ctx.request_context.lifespan_context["postgres_pool_manager"], datasource, table
            )
        except Exception as exc:
            return _sanitize_unexpected_error(exc, "describe_table_postgres")

    @app.tool()
    async def get_table_ddl_postgres(datasource: str, table: str, ctx: Context) -> str:
        """Get the DDL (CREATE TABLE) for a PostgreSQL table."""
        try:
            return await get_table_ddl_postgres_tool(
                ctx.request_context.lifespan_context["postgres_pool_manager"], datasource, table
            )
        except Exception as exc:
            return _sanitize_unexpected_error(exc, "get_table_ddl_postgres")

    @app.tool()
    async def query_redis(datasource: str, command: str, ctx: Context, args: list[str] | None = None) -> str:
        """Execute a safe read-only Redis command."""
        try:
            return await query_redis_tool(
                ctx.request_context.lifespan_context["redis_pool_manager"], datasource, command, args
            )
        except Exception as exc:
            return _sanitize_unexpected_error(exc, "query_redis")

    @app.tool()
    async def list_datasources(ctx: Context) -> str:
        """List all configured datasources."""
        try:
            return await list_datasources_tool(ctx.request_context.lifespan_context["config"])
        except Exception as exc:
            return _sanitize_unexpected_error(exc, "list_datasources")

    @app.tool()
    async def health_check(datasource: str, ctx: Context) -> str:
        """Check if a datasource is reachable. Returns OK or an error description.

        Use this before querying a datasource to verify it's available.
        """
        try:
            lifespan = ctx.request_context.lifespan_context
            config = lifespan.get("config")
            # Check MySQL
            mysql = lifespan.get("mysql_pool_manager")
            if mysql and (datasource in mysql._pools or (config and datasource in config.mysql)):
                if datasource in mysql._pools:
                    ok = await mysql.health_check(datasource)
                    return f"OK: MySQL datasource '{datasource}' is reachable." if ok else f"DOWN: MySQL datasource '{datasource}' health check failed."
                return f"DOWN: MySQL datasource '{datasource}' is configured but not connected (may retry on next query)."
            # Check PostgreSQL
            pg = lifespan.get("postgres_pool_manager")
            if pg and (datasource in pg._pools or (config and datasource in config.postgres)):
                if datasource in pg._pools:
                    ok = await pg.health_check(datasource)
                    return f"OK: PostgreSQL datasource '{datasource}' is reachable." if ok else f"DOWN: PostgreSQL datasource '{datasource}' health check failed."
                return f"DOWN: PostgreSQL datasource '{datasource}' is configured but not connected (may retry on next query)."
            # Check Redis
            rds = lifespan.get("redis_pool_manager")
            if rds and (datasource in rds._clients or (config and datasource in config.redis)):
                if datasource in rds._clients:
                    ok = await rds.health_check(datasource)
                    return f"OK: Redis instance '{datasource}' is reachable." if ok else f"DOWN: Redis instance '{datasource}' health check failed."
                return f"DOWN: Redis instance '{datasource}' is configured but not connected (may retry on next query)."
            return f"Unknown datasource '{datasource}'. Use list_datasources to see available names."
        except Exception as exc:
            return _sanitize_unexpected_error(exc, "health_check")

    @app.tool()
    async def health_check_all(ctx: Context) -> str:
        """Check all datasources and return a health summary.

        Use this first to discover which datasources are available before running queries.
        """
        try:
            lifespan = ctx.request_context.lifespan_context
            lines = ["## Datasource Health", ""]

            mysql = lifespan.get("mysql_pool_manager")
            if mysql:
                results = await mysql.health_check_all()
                if results:
                    lines.append("### MySQL")
                    for name, ok in sorted(results.items()):
                        lines.append(f"- {'✅' if ok else '❌'} **{name}**: {'reachable' if ok else 'unreachable'}")
                    lines.append("")

            pg = lifespan.get("postgres_pool_manager")
            if pg:
                results = await pg.health_check_all()
                if results:
                    lines.append("### PostgreSQL")
                    for name, ok in sorted(results.items()):
                        lines.append(f"- {'✅' if ok else '❌'} **{name}**: {'reachable' if ok else 'unreachable'}")
                    lines.append("")

            rds = lifespan.get("redis_pool_manager")
            if rds:
                results = await rds.health_check_all()
                if results:
                    lines.append("### Redis")
                    for name, ok in sorted(results.items()):
                        lines.append(f"- {'✅' if ok else '❌'} **{name}**: {'reachable' if ok else 'unreachable'}")
                    lines.append("")

            if not lines[2:]:
                return "No datasources configured."
            return "\n".join(lines)
        except Exception as exc:
            return _sanitize_unexpected_error(exc, "health_check_all")

    return app