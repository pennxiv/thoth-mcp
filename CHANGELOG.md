# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-04-23

### Added
- MCP server with stdio, SSE, and streamable-http transports
- MySQL query tools (`query_mysql`, `list_tables`, `describe_table`)
- PostgreSQL query tools (`query_postgres`, `list_tables_postgres`, `describe_table_postgres`)
- Redis query tools (`query_redis`, `list_datasources`)
- Three-layer SQL safety: SELECT enforcement, injection detection, automatic LIMIT
- Redis command allowlist (read-only commands only)
- Markdown result formatting for AI context efficiency
- Connection pool managers for MySQL, PostgreSQL, and Redis
- Docker Compose stack with seed data for local development
- Error sanitization (no hostnames, IPs, or credentials in error messages)
