"""Tests for Redis command safety validation module."""
import pytest
from thoth_mcp.utils.redis_safety import (
    validate_command,
    RedisSafetyError,
    ALLOWED_COMMANDS,
)


class TestAllowlistEnforcement:
    """Test allowlist enforcement for Redis commands."""

    def test_allowed_commands_pass(self):
        """All allowed commands pass validation without exception."""
        for cmd in ALLOWED_COMMANDS:
            # Should not raise
            validate_command(cmd)

    def test_getset_explicitly_excluded(self):
        """GETSET is explicitly excluded from allowlist (D-04)."""
        with pytest.raises(RedisSafetyError, match="GETSET"):
            validate_command("GETSET")

    def test_dangerous_commands_rejected(self):
        """Dangerous write commands are rejected."""
        dangerous = ["SET", "DEL", "KEYS", "FLUSHALL", "FLUSHDB", "INCR", "LPUSH", "SADD", "ZADD"]
        for cmd in dangerous:
            with pytest.raises(RedisSafetyError, match=cmd):
                validate_command(cmd)


class TestCommandValidation:
    """Test command validation behavior."""

    def test_case_insensitive(self):
        """Command validation is case-insensitive."""
        # All should pass without exception
        validate_command("get")
        validate_command("GET")
        validate_command("Get")

    def test_whitespace_handling(self):
        """Whitespace is stripped from command."""
        # Should not raise
        validate_command("  GET  ")

    def test_error_message_includes_command(self):
        """Error message includes the rejected command name."""
        with pytest.raises(RedisSafetyError, match="SET"):
            validate_command("SET")

    def test_error_message_includes_allowed_list(self):
        """Error message lists allowed commands."""
        with pytest.raises(RedisSafetyError, match="GET"):
            validate_command("SET")
        # Check that some allowed commands are mentioned
        with pytest.raises(RedisSafetyError, match="HGET"):
            validate_command("SET")

    def test_rejected_command_logged_at_warning(self):
        """Rejected commands are logged at WARNING level."""
        import sys
        from io import StringIO

        old_stderr = sys.stderr
        sys.stderr = StringIO()

        try:
            # Reconfigure logger to use captured stderr
            from thoth_mcp.utils.logger import logger
            logger.remove()
            logger.add(sys.stderr, format="{level} | {message}")

            with pytest.raises(RedisSafetyError):
                validate_command("SET")

            stderr_output = sys.stderr.getvalue()
            assert "WARNING" in stderr_output
            assert "rejected" in stderr_output.lower()
        finally:
            sys.stderr = old_stderr


class TestAllowlistContents:
    """Test that allowlist contains expected commands."""

    def test_allowlist_has_26_commands(self):
        """Allowlist contains exactly 26 read-only commands."""
        assert len(ALLOWED_COMMANDS) == 26

    def test_get_in_allowlist(self):
        """GET is in allowlist."""
        assert "GET" in ALLOWED_COMMANDS

    def test_hget_in_allowlist(self):
        """HGET is in allowlist."""
        assert "HGET" in ALLOWED_COMMANDS

    def test_hgetall_in_allowlist(self):
        """HGETALL is in allowlist."""
        assert "HGETALL" in ALLOWED_COMMANDS

    def test_lrange_in_allowlist(self):
        """LRANGE is in allowlist."""
        assert "LRANGE" in ALLOWED_COMMANDS

    def test_smembers_in_allowlist(self):
        """SMEMBERS is in allowlist."""
        assert "SMEMBERS" in ALLOWED_COMMANDS

    def test_ttl_in_allowlist(self):
        """TTL is in allowlist."""
        assert "TTL" in ALLOWED_COMMANDS

    def test_type_in_allowlist(self):
        """TYPE is in allowlist."""
        assert "TYPE" in ALLOWED_COMMANDS

    def test_getset_not_in_allowlist(self):
        """GETSET is NOT in allowlist (D-04)."""
        assert "GETSET" not in ALLOWED_COMMANDS

    def test_keys_not_in_allowlist(self):
        """KEYS is NOT in allowlist (prevents O(N) blocking)."""
        assert "KEYS" not in ALLOWED_COMMANDS

    def test_flushall_not_in_allowlist(self):
        """FLUSHALL is NOT in allowlist (prevents data destruction)."""
        assert "FLUSHALL" not in ALLOWED_COMMANDS
