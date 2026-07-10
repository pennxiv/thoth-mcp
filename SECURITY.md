# Security Policy

## Supported versions

Only the latest release receives security updates.

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please report vulnerabilities privately:

1. Email: **pennxiv@gmail.com**
2. Include a description of the issue and reproduction steps
3. Do not include live credentials or production data

You should receive a response within 72 hours.

## Security considerations

This server exposes database query access through MCP. Keep the following in mind:

- **Read-only by design**: All SQL is validated as SELECT-only; Redis commands are restricted to a read-only allowlist. This limits (but does not eliminate) risk.
- **Error sanitization**: Error messages are scrubbed of hostnames, IPs, and credentials. Verify this holds if you modify error-handling code.
- **Network exposure**: When running in `streamable-http` or `sse` mode, the server listens on `0.0.0.0:8080` by default. Place it behind authenticated network boundaries — do not expose it directly to the public internet without additional auth.
- **Secrets management**: Database passwords should be supplied via environment variables (`THOTH_*__PASSWORD`), never committed to `config/` files.
- **Least privilege**: Configure database users with read-only permissions at the database level. Do not rely solely on the application-layer safety checks.
