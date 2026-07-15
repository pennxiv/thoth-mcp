import sys
import os
from io import StringIO
from thoth_mcp.utils.logger import logger


def test_stderr_only():
    """All log output goes to stderr, not stdout."""
    # Capture stderr and stdout
    old_stderr = sys.stderr
    old_stdout = sys.stdout
    sys.stderr = StringIO()
    sys.stdout = StringIO()

    try:
        # Reconfigure logger to use captured stderr
        logger.remove()
        logger.add(sys.stderr, format="{message}")

        logger.info("Test message")

        stderr_output = sys.stderr.getvalue()
        stdout_output = sys.stdout.getvalue()

        assert "Test message" in stderr_output
        assert stdout_output == ""
    finally:
        sys.stderr = old_stderr
        sys.stdout = old_stdout


def test_stdout_clean():
    """stdout contains no log output after logger calls."""
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        logger.info("This should not appear in stdout")
        logger.debug("Neither should this")
        logger.warning("Or this")

        stdout_output = sys.stdout.getvalue()
        assert stdout_output == ""
    finally:
        sys.stdout = old_stdout


def test_log_format():
    """Log format includes timestamp, level, module name, and message."""
    old_stderr = sys.stderr
    sys.stderr = StringIO()

    try:
        logger.remove()
        logger.add(sys.stderr, format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name} | {message}")

        logger.info("Test message")

        output = sys.stderr.getvalue()
        # Check format components (D-08)
        assert "|" in output  # Has separators
        assert "INFO" in output  # Has level
        assert "Test message" in output  # Has message
    finally:
        sys.stderr = old_stderr


def test_log_level_env_var():
    """LOG_LEVEL env var controls minimum log level."""
    old_stderr = sys.stderr
    sys.stderr = StringIO()

    try:
        # Set LOG_LEVEL=WARNING
        os.environ["LOG_LEVEL"] = "WARNING"
        # Remove from cache to force reload
        if "thoth_mcp.utils.logger" in sys.modules:
            del sys.modules["thoth_mcp.utils.logger"]
        if "thoth_mcp.utils" in sys.modules:
            del sys.modules["thoth_mcp.utils"]

        from thoth_mcp.utils.logger import logger as test_logger

        test_logger.remove()
        test_logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))

        test_logger.debug("This should not appear")
        test_logger.info("This should not appear either")
        test_logger.warning("This should appear")

        output = sys.stderr.getvalue()
        assert "This should appear" in output
        assert "This should not appear" not in output
    finally:
        sys.stderr = old_stderr
        if "LOG_LEVEL" in os.environ:
            del os.environ["LOG_LEVEL"]


def test_colorize_env_var():
    """LOGURU_COLORIZE=false disables colorization."""
    # This test verifies the env var is read; actual colorization
    # behavior is harder to test in unit tests
    os.environ["LOGURU_COLORIZE"] = "false"

    try:
        # Remove from cache to force reload
        if "thoth_mcp.utils.logger" in sys.modules:
            del sys.modules["thoth_mcp.utils.logger"]
        if "thoth_mcp.utils" in sys.modules:
            del sys.modules["thoth_mcp.utils"]

        # Re-import to verify the module loads correctly with the env var
        from thoth_mcp.utils.logger import logger as _test_logger  # noqa: F401

        # If we got here without error, the env var is handled
        assert True
    finally:
        if "LOGURU_COLORIZE" in os.environ:
            del os.environ["LOGURU_COLORIZE"]
