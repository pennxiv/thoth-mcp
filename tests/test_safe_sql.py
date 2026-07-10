"""Tests for SQL safety validation module."""
import pytest
from thoth_mcp.utils.safe_sql import validate_sql, SQLValidationError


class TestSelectOnlyEnforcement:
    """Test Layer 1: SELECT-only enforcement."""

    def test_select_allowed(self):
        """Valid SELECT passes validation."""
        result = validate_sql("SELECT * FROM users")
        assert "SELECT" in result

    def test_insert_rejected(self):
        """INSERT is rejected with clear message."""
        with pytest.raises(SQLValidationError, match="Only SELECT queries are allowed.*INSERT"):
            validate_sql("INSERT INTO users VALUES (1, 'admin')")

    def test_update_rejected(self):
        """UPDATE is rejected with clear message."""
        with pytest.raises(SQLValidationError, match="Only SELECT queries are allowed.*UPDATE"):
            validate_sql("UPDATE users SET name = 'hacked' WHERE id = 1")

    def test_delete_rejected(self):
        """DELETE is rejected with clear message."""
        with pytest.raises(SQLValidationError, match="Only SELECT queries are allowed.*DELETE"):
            validate_sql("DELETE FROM users")

    def test_drop_rejected(self):
        """DROP is rejected with clear message."""
        with pytest.raises(SQLValidationError, match="Only SELECT queries are allowed.*DROP"):
            validate_sql("DROP TABLE users")

    def test_alter_rejected(self):
        """ALTER is rejected with clear message."""
        with pytest.raises(SQLValidationError, match="Only SELECT queries are allowed.*ALTER"):
            validate_sql("ALTER TABLE users ADD COLUMN password TEXT")

    def test_empty_sql_rejected(self):
        """Empty SQL statement is rejected."""
        with pytest.raises(SQLValidationError, match="Empty SQL statement"):
            validate_sql("")

    def test_whitespace_only_rejected(self):
        """Whitespace-only SQL is rejected."""
        with pytest.raises(SQLValidationError, match="Empty SQL statement"):
            validate_sql("   ")


class TestInjectionDetection:
    """Test Layer 2: SQL injection pattern detection."""

    def test_union_injection_rejected(self):
        """UNION SELECT is detected."""
        with pytest.raises(SQLValidationError, match="UNION injection"):
            validate_sql("SELECT * FROM users WHERE id = 1 UNION SELECT * FROM passwords")

    def test_union_all_injection_rejected(self):
        """UNION ALL SELECT is detected."""
        with pytest.raises(SQLValidationError, match="UNION injection"):
            validate_sql("SELECT * FROM users WHERE id = 1 UNION ALL SELECT * FROM passwords")

    def test_single_line_comment_rejected(self):
        """Single-line comment sequence -- is detected."""
        with pytest.raises(SQLValidationError, match="comment"):
            validate_sql("SELECT * FROM users WHERE id = 1 -- bypass")

    def test_multi_line_comment_rejected(self):
        """Multi-line comment sequence /* */ is detected."""
        with pytest.raises(SQLValidationError, match="comment"):
            validate_sql("SELECT * FROM users WHERE id = 1 /* bypass */")

    def test_semicolon_rejected(self):
        """Semicolons are detected (multi-statement attack)."""
        with pytest.raises(SQLValidationError, match="semicolon"):
            validate_sql("SELECT * FROM users; DROP TABLE users")


class TestLimitInjection:
    """Test Layer 3: Automatic LIMIT injection."""

    def test_limit_added_when_missing(self):
        """LIMIT is appended if not present."""
        result = validate_sql("SELECT * FROM users")
        assert "LIMIT 100" in result

    def test_limit_not_added_when_present(self):
        """Existing LIMIT is preserved."""
        result = validate_sql("SELECT * FROM users LIMIT 10")
        assert "LIMIT 10" in result
        assert "LIMIT 100" not in result

    def test_custom_limit(self):
        """Custom limit parameter works."""
        result = validate_sql("SELECT * FROM users", limit=50)
        assert "LIMIT 50" in result

    def test_limit_with_offset_preserved(self):
        """LIMIT with OFFSET is preserved."""
        result = validate_sql("SELECT * FROM users LIMIT 10 OFFSET 5")
        assert "LIMIT 10" in result
        assert "OFFSET 5" in result
        assert "LIMIT 100" not in result

    def test_trailing_semicolon_stripped_before_limit(self):
        """Trailing semicolon is stripped before LIMIT injection."""
        result = validate_sql("SELECT * FROM users;")
        assert result == "SELECT * FROM users LIMIT 100"


class TestValidationSequence:
    """Test that all three layers run in sequence."""

    def test_select_check_before_injection_check(self):
        """SELECT-only check runs before injection check."""
        # INSERT should be rejected for being non-SELECT, not for injection
        with pytest.raises(SQLValidationError, match="Only SELECT queries are allowed"):
            validate_sql("INSERT INTO users VALUES (1, 'admin')")

    def test_injection_check_before_limit_injection(self):
        """Injection check runs before LIMIT injection."""
        # UNION injection should be detected before LIMIT is added
        with pytest.raises(SQLValidationError, match="UNION injection"):
            validate_sql("SELECT * FROM users UNION SELECT * FROM passwords")

    def test_all_layers_pass_returns_validated_sql(self):
        """All three layers pass returns validated SQL with LIMIT."""
        result = validate_sql("SELECT * FROM users")
        assert "SELECT" in result
        assert "LIMIT 100" in result
