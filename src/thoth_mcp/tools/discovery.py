"""Discovery MCP tools for listing available datasources."""
from thoth_mcp.config import DatasourcesConfig
from thoth_mcp.utils.logger import logger


async def list_datasources(config: DatasourcesConfig) -> str:
    """List all available MySQL, PostgreSQL, and Redis datasources configured in the server.

    Allowed operations: Read-only configuration inspection. Returns datasource
    names and connection metadata only.

    Examples:
    - list_datasources()

    This tool only reads configuration metadata and does not connect to or
    modify any datasource.
    """
    logger.info("list_datasources")

    sections = []

    # MySQL datasources
    if config.mysql:
        lines = ["## MySQL Datasources", ""]
        for name, ds_config in sorted(config.mysql.items()):
            lines.append(f"- **{name}** ({ds_config.host}:{ds_config.port}/{ds_config.database})")
        sections.append("\n".join(lines))

    # PostgreSQL datasources
    if config.postgres:
        lines = ["## PostgreSQL Datasources", ""]
        for name, ds_config in sorted(config.postgres.items()):
            lines.append(f"- **{name}** ({ds_config.host}:{ds_config.port}/{ds_config.database})")
        sections.append("\n".join(lines))

    # Redis instances
    if config.redis:
        lines = ["## Redis Instances", ""]
        for name, ds_config in sorted(config.redis.items()):
            db_info = f"/{ds_config.db}" if ds_config.db else ""
            lines.append(f"- **{name}** ({ds_config.host}:{ds_config.port}{db_info})")
        sections.append("\n".join(lines))

    if not sections:
        return "No datasources configured."

    return "\n\n".join(sections)
