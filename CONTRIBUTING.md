# Contributing to Thoth MCP

Thanks for your interest in contributing! This guide covers the basics.

## Development setup

```bash
git clone https://github.com/pennxiv/thoth-mcp.git
cd thoth-mcp
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

## Running tests

```bash
# Unit tests
pytest tests/ -v

# Integration tests (requires Docker)
./scripts/run_integration_tests.sh
```

## Before submitting a PR

1. **Run the linter:** `ruff check src/ tests/`
2. **Run the tests:** `pytest tests/ -v`
3. **Keep changes focused** — one logical change per PR
4. **Add tests** for new functionality
5. **Update CHANGELOG.md** under the `[Unreleased]` section

## Code style

- Python 3.10+ (type hints encouraged)
- Line length: 120 chars (configured in `pyproject.toml`)
- Follow existing patterns in `src/thoth_mcp/`

## Security considerations

This server executes database queries. When adding tools or changing safety logic:

- All SQL must pass through `validate_sql()` in `src/thoth_mcp/utils/safe_sql.py`
- Redis commands must be validated against the allowlist in `src/thoth_mcp/utils/redis_safety.py`
- Error messages must never expose hostnames, IPs, or credentials
- Add tests covering the new safety behavior

## Reporting issues

Open a GitHub issue with:
- What you expected
- What happened (include logs with sensitive values redacted)
- How to reproduce
- Your Python version, OS, and relevant config (no secrets!)
