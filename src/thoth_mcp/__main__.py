"""Entrypoint for running Thoth MCP."""
import os

from starlette.responses import JSONResponse
from starlette.requests import Request

from thoth_mcp.server import create_app


def _add_health_route(app):
    """Add a /health endpoint for dashboard monitoring (returns quickly, no hang)."""

    @app.custom_route("/health", methods=["GET"])
    async def health_check(_request: Request):
        return JSONResponse({"status": "ok"})

    return app


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")

    app = create_app()
    _add_health_route(app)
    run = getattr(app, "run", None)
    if callable(run):
        if transport == "stdio":
            run(transport=transport)
        else:
            # "sse", "streamable-http", "http" all use HTTP server
            host = os.environ.get("MCP_HOST", "0.0.0.0")
            port = int(os.environ.get("MCP_PORT", "8080"))
            root_path = os.environ.get("MCP_ROOT_PATH", "")
            uvicorn_config = {}
            if root_path:
                uvicorn_config["root_path"] = root_path
            run(transport=transport, host=host, port=port, uvicorn_config=uvicorn_config or None)
        return
    raise RuntimeError("FastMCP runtime is not installed. Install the MCP SDK to run the server.")


if __name__ == "__main__":
    main()
