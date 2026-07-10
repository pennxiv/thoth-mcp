"""Tests for result formatters."""
from thoth_mcp.utils.formatters import format_mysql_result, format_redis_result


class TestMySQLFormatter:
    """Test MySQL result Markdown formatting."""

    def test_empty_result(self):
        """Empty result returns 'No results found.'"""
        result = format_mysql_result([])
        assert result == "No results found."

    def test_single_row(self):
        """Single row displays as Markdown table with headers and row count."""
        rows = [{"id": 1, "name": "Alice"}]
        result = format_mysql_result(rows)
        assert "| id | name |" in result
        assert "| --- | --- |" in result
        assert "| 1 | Alice |" in result
        assert "1 row(s) returned." in result

    def test_multiple_rows(self):
        """Multiple rows display with correct row count."""
        rows = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
            {"id": 3, "name": "Charlie"},
        ]
        result = format_mysql_result(rows)
        assert "| 1 | Alice |" in result
        assert "| 2 | Bob |" in result
        assert "| 3 | Charlie |" in result
        assert "3 row(s) returned." in result

    def test_null_values(self):
        """NULL values (Python None) display as 'NULL' string."""
        rows = [{"id": 1, "name": None}]
        result = format_mysql_result(rows)
        assert "| 1 | NULL |" in result

    def test_column_extraction(self):
        """Columns extracted from first row keys."""
        rows = [{"col_a": "val1", "col_b": "val2"}]
        result = format_mysql_result(rows)
        assert "| col_a | col_b |" in result

    def test_custom_columns(self):
        """Columns parameter overrides auto-detection."""
        rows = [{"id": 1, "name": "Alice", "email": "alice@example.com"}]
        result = format_mysql_result(rows, columns=["id", "name"])
        assert "| id | name |" in result
        assert "email" not in result

    def test_special_characters_in_values(self):
        """Special characters in values are handled correctly."""
        rows = [{"text": "hello | world"}]
        result = format_mysql_result(rows)
        assert "hello | world" in result


class TestMySQLTruncation:
    """Test MySQL result truncation behavior."""

    def test_truncation_at_100_rows(self):
        """Large result sets (>100 rows) truncate with count indicator."""
        rows = [{"id": i, "value": f"val_{i}"} for i in range(150)]
        result = format_mysql_result(rows)
        assert "Showing 100 of 150 rows." in result
        # First row should be present
        assert "| 0 | val_0 |" in result
        # Row 100 should not be present (only 0-99 shown)
        assert "| 100 | val_100 |" not in result

    def test_custom_max_rows(self):
        """Custom max_rows parameter works correctly."""
        rows = [{"id": i} for i in range(50)]
        result = format_mysql_result(rows, max_rows=20)
        assert "Showing 20 of 50 rows." in result

    def test_exact_max_rows(self):
        """Exactly 100 rows shows '100 row(s) returned.' (no truncation)."""
        rows = [{"id": i} for i in range(100)]
        result = format_mysql_result(rows)
        assert "100 row(s) returned." in result
        assert "Showing" not in result

    def test_truncation_preserves_headers(self):
        """Headers present in truncated output."""
        rows = [{"id": i, "name": f"name_{i}"} for i in range(150)]
        result = format_mysql_result(rows)
        assert "| id | name |" in result
        assert "| --- | --- |" in result

    def test_max_rows_one(self):
        """max_rows=1 shows single row with correct count."""
        rows = [{"id": 1}, {"id": 2}, {"id": 3}]
        result = format_mysql_result(rows, max_rows=1)
        assert "Showing 1 of 3 rows." in result
        assert "| 1 |" in result
        assert "| 2 |" not in result


class TestMySQLEdgeCases:
    """Test MySQL formatter edge cases."""

    def test_empty_string_value(self):
        """Empty string values display as empty."""
        rows = [{"name": ""}]
        result = format_mysql_result(rows)
        # Empty string should show as empty cell
        assert "|  |" in result

    def test_numeric_values(self):
        """Numeric values are converted to strings correctly."""
        rows = [{"int_val": 42, "float_val": 3.14}]
        result = format_mysql_result(rows)
        assert "| 42 | 3.14 |" in result

    def test_boolean_values(self):
        """Boolean values are converted to strings."""
        rows = [{"flag": True}, {"flag": False}]
        result = format_mysql_result(rows)
        assert "| True |" in result
        assert "| False |" in result

    def test_missing_column_in_row(self):
        """Missing column in a row shows as empty (dict.get returns None)."""
        rows = [{"id": 1, "name": "Alice"}, {"id": 2}]  # Second row missing 'name'
        result = format_mysql_result(rows)
        assert "| 2 | NULL |" in result


class TestRedisFormatter:
    """Test Redis result formatting."""

    def test_get_string(self):
        """GET command returns plain text."""
        result = format_redis_result("hello world", "GET")
        assert result == "hello world"

    def test_get_bytes(self):
        """GET with bytes result decodes UTF-8."""
        result = format_redis_result(b"hello world", "GET")
        assert result == "hello world"

    def test_get_binary_fallback(self):
        """GET with non-UTF8 bytes shows size indicator."""
        binary_data = b"\x00\x01\x02\xff\xfe"
        result = format_redis_result(binary_data, "GET")
        assert "<binary data: 5 bytes>" in result

    def test_hget_value(self):
        """HGET returns single field value."""
        result = format_redis_result("field_value", "HGET")
        assert result == "field_value"

    def test_hget_not_found(self):
        """HGET with None result returns 'Field not found.'"""
        result = format_redis_result(None, "HGET")
        assert result == "Field not found."

    def test_hgetall_table(self):
        """HGETALL returns Markdown table format."""
        data = {b"field1": b"value1", b"field2": b"value2"}
        result = format_redis_result(data, "HGETALL")
        assert "| Field | Value |" in result
        assert "| field1 | value1 |" in result
        assert "| field2 | value2 |" in result

    def test_hgetall_empty(self):
        """HGETALL with empty hash returns message."""
        result = format_redis_result({}, "HGETALL")
        assert "empty" in result.lower()

    def test_lrange_numbered_list(self):
        """LRANGE returns numbered list format."""
        data = [b"item1", b"item2", b"item3"]
        result = format_redis_result(data, "LRANGE")
        assert "1. item1" in result
        assert "2. item2" in result
        assert "3. item3" in result

    def test_lrange_empty(self):
        """LRANGE with empty list returns message."""
        result = format_redis_result([], "LRANGE")
        assert "empty" in result.lower()

    def test_smembers_bullet_list(self):
        """SMEMBERS returns bullet list format."""
        data = {b"member1", b"member2", b"member3"}
        result = format_redis_result(data, "SMEMBERS")
        assert "- member1" in result
        assert "- member2" in result
        assert "- member3" in result

    def test_smembers_empty(self):
        """SMEMBERS with empty set returns message."""
        result = format_redis_result(set(), "SMEMBERS")
        assert "empty" in result.lower()

    def test_zrange_with_scores(self):
        """ZRANGE returns numbered list with scores."""
        data = [(b"member1", 1.5), (b"member2", 2.0)]
        result = format_redis_result(data, "ZRANGE")
        assert "1. member1 (score: 1.5)" in result
        assert "2. member2 (score: 2.0)" in result

    def test_zrange_empty(self):
        """ZRANGE with empty sorted set returns message."""
        result = format_redis_result([], "ZRANGE")
        assert "empty" in result.lower()

    def test_ttl_seconds(self):
        """TTL returns human-readable seconds."""
        result = format_redis_result(300, "TTL")
        assert "300 seconds" in result

    def test_ttl_not_exists(self):
        """TTL -2 returns 'Key does not exist.'"""
        result = format_redis_result(-2, "TTL")
        assert "does not exist" in result

    def test_ttl_no_expiry(self):
        """TTL -1 returns 'Key exists but has no expiry.'"""
        result = format_redis_result(-1, "TTL")
        assert "no expiry" in result

    def test_type_string(self):
        """TYPE returns plain string."""
        result = format_redis_result("string", "TYPE")
        assert result == "string"

    def test_exists_true(self):
        """EXISTS returns 'true' for 1."""
        result = format_redis_result(1, "EXISTS")
        assert result == "true"

    def test_exists_false(self):
        """EXISTS returns 'false' for 0."""
        result = format_redis_result(0, "EXISTS")
        assert result == "false"

    def test_none_result(self):
        """None result for GET returns 'Key not found or no value.'"""
        result = format_redis_result(None, "GET")
        assert "not found" in result.lower()

    def test_llen_scalar(self):
        """LLEN returns integer as string."""
        result = format_redis_result(42, "LLEN")
        assert result == "42"

    def test_scard_scalar(self):
        """SCARD returns integer as string."""
        result = format_redis_result(10, "SCARD")
        assert result == "10"

    def test_zscore_scalar(self):
        """ZSCORE returns float as string."""
        result = format_redis_result(3.14, "ZSCORE")
        assert result == "3.14"

    def test_zscore_none(self):
        """ZSCORE with None returns 'Member not found in sorted set.'"""
        result = format_redis_result(None, "ZSCORE")
        assert "not found" in result.lower()


class TestRedisTruncation:
    """Test Redis result truncation behavior."""

    def test_list_truncation(self):
        """List truncates at 100 items."""
        data = [f"item_{i}".encode() for i in range(150)]
        result = format_redis_result(data, "LRANGE")
        assert "Showing 100 of 150 items." in result
        assert "1. item_0" in result
        assert "item_100" not in result

    def test_set_truncation(self):
        """Set truncates at 100 items."""
        data = {f"member_{i}".encode() for i in range(150)}
        result = format_redis_result(data, "SMEMBERS")
        assert "Showing 100 of 150 items." in result

    def test_zset_truncation(self):
        """Sorted set truncates at 100 items."""
        data = [(f"member_{i}".encode(), float(i)) for i in range(150)]
        result = format_redis_result(data, "ZRANGE")
        assert "Showing 100 of 150 items." in result

    def test_custom_max_items(self):
        """Custom max_items parameter works."""
        data = [f"item_{i}".encode() for i in range(50)]
        result = format_redis_result(data, "LRANGE", max_items=20)
        assert "Showing 20 of 50 items." in result

    def test_exact_max_items(self):
        """Exactly 100 items shows no truncation message."""
        data = [f"item_{i}".encode() for i in range(100)]
        result = format_redis_result(data, "LRANGE")
        assert "Showing" not in result
