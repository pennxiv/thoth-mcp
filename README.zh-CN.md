<div align="center">

# Thoth MCP

一个以安全为先的**只读** MCP 服务器,让 AI 助手安全查询 MySQL、PostgreSQL 和 Redis。

[![CI](https://github.com/pennxiv/thoth-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/pennxiv/thoth-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io)

[English](README.md) · **简体中文**

</div>

---

每一条查询在到达数据库之前,都要经过层层安全校验——这样你可以放心地赋予 AI 助手数据访问能力,而不必担心它误操作你的数据。

## 目录

- [为什么用它?](#为什么用它)
- [功能特性](#功能特性)
- [快速开始](#快速开始)
- [配置](#配置)
- [MCP 工具](#mcp-工具)
- [安全](#安全)
- [传输模式](#传输模式)
- [架构](#架构)
- [开发](#开发)
- [许可证](#许可证)

## 为什么用它?

- **天生只读。** 写操作在结构上就被禁止——没有任何 `execute` 路径能修改数据。
- **纵深防御。** SQL 经过三重校验(SELECT 强制 → 注入检测 → 自动加 LIMIT);Redis 命令限制在明确的白名单内。
- **密钥不外泄。** 密码从环境变量加载,日志和错误信息中一律脱敏。
- **一个服务,多数据源。** 通过单个 MCP 端点连接你所有的数据库。
- **兼容任意 MCP 客户端**——Claude Code、Cursor、Windsurf,以及任何支持 MCP 协议的客户端。

## 功能特性

- 通过单个服务查询多个 MySQL、PostgreSQL 和 Redis 实例
- 三层 SQL 安全防护(SELECT 强制 + 注入检测 + 自动 LIMIT)
- Redis 命令白名单(仅允许明确安全的只读命令)
- Markdown 格式输出,高效利用 AI 上下文
- 支持 stdio、SSE、streamable-http 三种传输模式
- 自带 Docker Compose 栈和种子数据,便于本地开发

## 快速开始

### 环境要求

- Python 3.10+
- Docker 和 Docker Compose(可选,用于容器化部署)

### 本地安装与运行

```bash
# 克隆仓库
git clone https://github.com/pennxiv/thoth-mcp.git
cd thoth-mcp

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows 用 .venv\Scripts\activate

# 安装依赖
pip install -e ".[dev]"

# 指定数据源配置并启动
export THOTH_DATASOURCES_FILE=config/datasources.yaml
python -m thoth_mcp
```

### 用 Docker 运行

```bash
# 以 streamable-http 模式启动,监听 8080 端口
docker compose up -d --build

# 网络内任意机器可通过以下地址连接:
# http://<服务器IP>:8080/mcp
```

### 连接你的 MCP 客户端

**Claude Code**(`~/.claude.json` 或项目 `.mcp.json`):

```json
{
  "mcpServers": {
    "thoth": {
      "url": "http://<服务器IP>:8080/mcp",
      "transport": "streamable-http"
    }
  }
}
```

**Cursor / Windsurf**(`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "thoth": {
      "url": "http://<服务器IP>:8080/mcp",
      "transport": "streamable-http"
    }
  }
}
```

如果只在本地使用,可以把客户端配置为通过 stdio 启动服务,无需暴露 HTTP 端口。

## 配置

创建一个 `datasources.yaml` 文件(或通过 `THOTH_DATASOURCES_FILE` 环境变量指定路径):

```yaml
mysql:
  prod_db:
    host: mysql.example.com
    port: 3306
    user: readonly_user
    password: ${MYSQL_PROD_PASSWORD}  # 通过环境变量覆盖
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

### 提供密钥

密码不应写在配置文件里。通过环境变量覆盖,命名规则为 `THOTH_<类型>__<名称>__PASSWORD`:

```bash
export THOTH_MYSQL__PROD_DB__PASSWORD=secret123
export THOTH_POSTGRES__WAREHOUSE__PASSWORD=another_secret
export THOTH_REDIS__CACHE__PASSWORD=redis_secret
```

三种数据源的完整示例见 `config/datasources.yaml`。

## MCP 工具

| 工具 | 说明 |
|------|------|
| `query_mysql(datasource, sql)` | 对 MySQL 数据源执行 SELECT 查询 |
| `list_tables(datasource)` | 列出 MySQL 数据源中的所有表 |
| `describe_table(datasource, table)` | 查看 MySQL 表的列详情 |
| `query_postgres(datasource, sql)` | 对 PostgreSQL 数据源执行 SELECT 查询 |
| `list_tables_postgres(datasource)` | 列出 PostgreSQL 数据源中的所有表(public schema) |
| `describe_table_postgres(datasource, table)` | 查看 PostgreSQL 表的列详情 |
| `query_redis(datasource, command, args?)` | 执行安全的只读 Redis 命令 |
| `list_datasources()` | 列出所有已配置的 MySQL、PostgreSQL 和 Redis 数据源 |

## 安全

本服务器的核心假设是:任何到达数据库的请求都必须是只读的、无注入风险的。

### SQL 安全(三层防御)

1. **SELECT 强制**——只允许 SELECT 语句。
2. **注入检测**——拦截 UNION 注入、注释混淆、多语句攻击。
3. **自动注入 LIMIT**——没有 LIMIT 子句的查询会自动加上默认限制(100 行),防止全表扫描。

### Redis 安全

仅允许以下只读命令:`GET`、`HGET`、`HGETALL`、`LRANGE`、`SMEMBERS`、`TTL`、`TYPE`、`LLEN`、`SCARD`、`EXISTS`、`HEXISTS`、`SRANDMEMBER`、`ZCARD`、`ZSCORE`、`ZRANGE`。

`SET`、`DEL`、`KEYS`、`FLUSHALL` 等命令被明确禁止。

### 错误信息脱敏

错误信息绝不暴露主机名、IP、连接字符串或凭据。即使在连接建立或查询执行失败时也保持这一原则。

### 网络暴露

以 `streamable-http` 或 `sse` 模式运行时,服务器默认监听 `0.0.0.0:8080`。请将其置于带认证的网络边界之后——不要在未加额外认证的情况下直接暴露到公网。详见 [SECURITY.md](SECURITY.md)。

## 传输模式

| 模式 | 适用场景 | 环境变量 |
|------|----------|----------|
| `stdio`(默认) | 客户端与服务在同一台机器 | `MCP_TRANSPORT=stdio` |
| `streamable-http` | 远程客户端通过 HTTP 连接 | `MCP_TRANSPORT=streamable-http` |
| `sse` | 浏览器端 / 单向流式连接 | `MCP_TRANSPORT=sse` |

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MCP_TRANSPORT` | `stdio` | 传输模式 |
| `MCP_HOST` | `0.0.0.0` | 监听地址(仅 http/sse) |
| `MCP_PORT` | `8080` | 监听端口(仅 http/sse) |

SSE 模式暴露 `/sse`(客户端连接)和 `/messages/`(POST 端点)。

## 架构

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

## 开发

```bash
# 运行测试套件
pytest tests/ -v

# 运行单个测试文件
pytest tests/test_mysql_tools.py -v

# 带覆盖率运行
pytest tests/ --cov=src/thoth_mcp --cov-report=html

# 代码检查
ruff check src/ tests/
```

贡献指南见 [CONTRIBUTING.md](CONTRIBUTING.md),版本历史见 [CHANGELOG.md](CHANGELOG.md)。

### 项目结构

```
thoth-mcp/
├── src/thoth_mcp/
│   ├── config.py          # 配置加载
│   ├── server.py          # FastMCP 服务器装配
│   ├── __main__.py        # 入口
│   ├── db/                # 连接池管理(mysql、postgresql、redis)
│   ├── tools/             # MCP 工具(mysql、postgresql、redis、discovery)
│   └── utils/             # 安全层、格式化、日志
├── tests/                 # 测试套件
├── docker/                # Docker 种子数据
├── config/                # 示例配置
└── pyproject.toml
```

## 许可证

MIT 许可证——详见 [LICENSE](LICENSE)。
