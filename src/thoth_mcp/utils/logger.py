"""Loguru logger configured for stderr-only output.

Per D-11: All log output goes to stderr — stdout is reserved for MCP JSON-RPC protocol.
This is critical for MCP servers: any logging to stdout corrupts the JSON-RPC stream.
"""
import sys
import os
from loguru import logger

# Remove default handler (which goes to stderr, but we want explicit control)
logger.remove()

# Configure stderr handler per D-08, D-09, D-10, D-11
logger.add(
    sys.stderr,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name} | {message}",
    level=os.getenv("LOG_LEVEL", "INFO"),
    colorize=os.getenv("LOGURU_COLORIZE", "true").lower() != "false",
)

# Export configured logger
__all__ = ["logger"]
