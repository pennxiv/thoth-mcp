# Thoth MCP

A security-first, **read-only** MCP (Model Context Protocol) server that lets AI assistants safely query pre-configured MySQL, PostgreSQL, and Redis datasources.

Every query passes through a layered safety pipeline before it ever reaches your database — so you can give an AI assistant data-access capabilities without handing it a loaded gun.

## Why use this?

- **Read-only by design.** Writes are structurally impossible — there is no `execute` path that ever mutates data.
- **Defense in depth.** SQL is validated three ways (SELECT enforcement → injection detection → automatic LIMIT). Redis commands are restricted to an explicit allowlist.
- **Secrets never leave your config.** Passwords are loaded from env vars and stripped from logs and error messages.
- **One server, many datasources.** Connect to all your databases through a single MCP endpoint.
- **Works with any MCP client** — Claude Code, Cursor, Windsurf, and anything else that speaks MCP.

## Features

- Query multiple MySQL, PostgreSQL, and Redis instances through one server
- Three-layer SQL safety (SELECT enforcement + injection detection + automatic LIMIT)
- Redis command allowlist (only explicitly safe read-only commands)
- Markdown output for efficient AI context usage
- stdio, SSE, and streamable-http transports
- Docker Compose stack with seed data for local development

## Quick Start

### Requirements

- Python 3.10+
- Docker and Docker Compose (optional, for containerized deployment)

### Install and run locally

```bash
# Clone
git clone https://github.com/pennxiv/thoth-mcp.git
cd thoth-mcp

# Set up a virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install
pip install -e ".[dev]"

# Point at your datasources and run
export THOTH_DATASOURCES_FILE=config/datasources.yaml
python -m thoth_mcp
```

### Run with Docker

```bash
# Starts the server in streamable-http mode on port 8080
docker compose up -d --build

# Connect from any machine on your network:
# http://<server-ip>:8080/mcp
```

### Connect your MCP client

**Claude Code** (`~/.claude.json` or project `.mcp.json`):
```json
{
  "mcpServers": {
    "thoth": {
      "url": "http://<server-ip>:8080/mcp",
      "transport": "streamable-http"
    }
  }
}
```

**Cursor / Windsurf** (`.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "thoth": {
      "url": "http://<server-ip>:8080/mcp",
      "transport": "streamable-http"
    }
  }
}
```

For local-only use, configure the client to launch the server over stdio instead — no HTTP exposure needed.

## Configuration

Create a `datasources.yaml` file (or set `THOTH_DATASOURCES_FILE` to point at one):

```yaml
mysql:
  prod_db:
    host: mysql.example.com
    port: 3306
    user: readonly_user
    password: ${MYSQL_PROD_PASSWORD}  # overridden via environment variable
    database: production
    min_pool_size: 1
    max_pool_size: 10

redis:
  cache:
    host: redis.example.com
    port: 6379
    db: 0
    min_pool_size: 1
    max_pool_size: 10
```

### Supplying secrets

Passwords should never live in config files. Override them via environment variables using the pattern `THOTH_<TYPE>__<NAME>__PASSWORD`:

```bash
export THOTH_MYSQL__PROD_DB__PASSWORD=secret123
export THOTH_POSTGRES__WAREHOUSE__PASSWORD=another_secret
export THOTH_REDIS__CACHE__PASSWORD=redis_secret
```

See `config/datasources.yaml` for a full example with all three datasource types.

## MCP Tools

| Tool | Description |
|------|-------------|
| `query_mysql(datasource, sql)` | Execute a SELECT query against a MySQL datasource |
| `list_tables(datasource)` | List all tables in a MySQL datasource |
| `describe_table(datasource, table)` | Show column details for a MySQL table |
| `query_postgres(datasource, sql)` | Execute a SELECT query against a PostgreSQL datasource |
| `list_tables_postgres(datasource)` | List all tables in a PostgreSQL datasource (public schema) |
| `describe_table_postgres(datasource, table)` | Show column details for a PostgreSQL table |
| `query_redis(datasource, command, args?)` | Execute a safe read-only Redis command |
| `list_datasources()` | List all configured MySQL, PostgreSQL, and Redis datasources |

## Security

This server is built around the assumption that anything reaching the database must be read-only and injection-free.

### SQL safety (three-layer defense)

1. **SELECT-only enforcement** — only SELECT statements are permitted.
2. **Injection pattern detection** — blocks UNION injection, comment obfuscation, and multi-statement attacks.
3. **Automatic LIMIT injection** — queries without a LIMIT clause receive a default limit (100 rows) to prevent unbounded scans.

### Redis safety

Only these read-only commands are permitted: `GET`, `HGET`, `HGETALL`, `LRANGE`, `SMEMBERS`, `TTL`, `TYPE`, `LLEN`, `SCARD`, `EXISTS`, `HEXISTS`, `SRANDMEMBER`, `ZCARD`, `ZSCORE`, `ZRANGE`.

Commands like `SET`, `DEL`, `KEYS`, and `FLUSHALL` are explicitly blocked.

### Error sanitization

Error messages never expose hostnames, IPs, connection strings, or credentials. This holds even when connection setup or query execution fails.

### Network exposure

When running in `streamable-http` or `sse` mode, the server listens on `0.0.0.0:8080` by default. Place it behind authenticated network boundaries — do not expose it directly to the public internet without additional auth. See [SECURITY.md](SECURITY.md).

## Transports

| Mode | Use case | Env |
|------|----------|-----|
| `stdio` (default) | Client and server on the same machine | `MCP_TRANSPORT=stdio` |
| `streamable-http` | Remote clients over HTTP | `MCP_TRANSPORT=streamable-http` |
| `sse` | Browser-based / unidirectional streaming | `MCP_TRANSPORT=sse` |

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `stdio` | Transport mode |
| `MCP_HOST` | `0.0.0.0` | Listen host (http/sse only) |
| `MCP_PORT` | `8080` | Listen port (http/sse only) |

SSE mode exposes `/sse` (client connections) and `/messages/` (POST endpoint).

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      FastMCP Server                          │
│  ┌─────────────┐ ┌──────────────┐ ┌─────────────┐          │
│  │ MySQL Tools │ │PostgreSQL    │ │ Redis Tools │          │
│  │             │ │Tools         │ │             │          │
│  └──────┬──────┘ └──────┬───────┘ └──────┬──────┘          │
│         │               │                │                  │
│  ┌──────▼──────┐ ┌──────▼───────┐ ┌──────▼──────┐          │
│  │ MySQL Pool  │ │PostgreSQL    │ │ Redis Pool  │          │
│  │   Manager   │ │Pool Manager  │ │   Manager   │          │
│  └──────┬──────┘ └──────┬───────┘ └──────┬──────┘          │
│         │               │                │   ┌──────────┐  │
│  ┌──────▼──────┐ ┌──────▼───────┐ ┌──────▼──────┐          │
│  │  SQL Safety │ │  SQL Safety  │ │Redis Safety │          │
│  └──────┬──────┘ └──────┬───────┘ └──────┬──────┘          │
│         └───────────────┴────────────────┴───│  Config  │  │
│                                              └──────────┘  │
└──────────────────────────────────────────────────────────────┘
          │               │                │
     ┌────▼────┐    ┌────▼─────┐     ┌────▼────┐
     │  MySQL  │    │PostgreSQL│     │  Redis  │
     │   DB    │    │    DB    │     │Instance │
     └─────────┘    └──────────┘     └─────────┘
```

## Development

```bash
# Run the test suite
pytest tests/ -v

# Run a single test file
pytest tests/test_mysql_tools.py -v

# Run with coverage
pytest tests/ --cov=src/thoth_mcp --cov-report=html

# Lint
ruff check src/ tests/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines and [CHANGELOG.md](CHANGELOG.md) for version history.

### Project structure

```
thoth-mcp/
├── src/thoth_mcp/
│   ├── config.py          # Configuration loading
│   ├── server.py          # FastMCP server assembly
│   ├── __main__.py        # Entry point
│   ├── db/                # Connection pool managers (mysql, postgresql, redis)
│   ├── tools/             # MCP tools (mysql, postgresql, redis, discovery)
│   └── utils/             # Safety layers, formatters, logging
├── tests/                 # Test suite
├── docker/                # Docker seed data
├── config/                # Example configurations
└── pyproject.toml
```

## License

MIT License — see [LICENSE](LICENSE).
