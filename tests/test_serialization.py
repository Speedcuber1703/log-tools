from log_tools._serialization import (
    normalize_sql,
    _substitute_params,
    detect_n_plus_one,
)


class TestNormalizeSql:
    def test_numbers_are_normalized(self):
        a = normalize_sql("SELECT * FROM users WHERE id = 5")
        b = normalize_sql("SELECT * FROM users WHERE id = 9999")
        assert a == b
        assert "?" in a
        assert "5" not in a and "9999" not in b

    def test_string_literals_are_normalized(self):
        a = normalize_sql("SELECT * FROM t WHERE name = 'alice'")
        b = normalize_sql("SELECT * FROM t WHERE name = 'bob'")
        assert a == b

    def test_placeholders_collapse(self):
        assert normalize_sql("a = %s") == normalize_sql("a = ?")

    def test_whitespace_and_case(self):
        assert normalize_sql("SELECT   *\n  FROM t") == "select * from t"


class TestSubstituteParams:
    def test_positional_question_mark(self):
        assert _substitute_params("a=? AND b=?", [10, 20]) == "a=10 AND b=20"

    def test_positional_percent_s_keeps_quote(self):
        assert _substitute_params("a=%s", ["hello"]) == "a='hello'"

    def test_placeholder_inside_value_is_safe(self):
        assert _substitute_params("a=? AND b=?", ["x?", "y"]) == "a='x?' AND b='y'"

    def test_named_params_escape_quotes(self):
        assert _substitute_params("name=%(n)s", {"n": "O'Brien"}) == "name='O''Brien'"

    def test_fewer_params_than_placeholders(self):
        assert _substitute_params("a=? AND b=?", [1]) == "a=1 AND b=?"


class TestDetectNPlusOne:
    def _sql_entry(self, raw, duration=1.0):
        return {
            "type": "sql",
            "duration_ms": duration,
            "data": {"sql": raw, "normalized_sql": normalize_sql(raw)},
        }

    def test_detects_repeated_lookups_by_id(self):
        entries = [
            self._sql_entry(f"SELECT * FROM app_user WHERE id = {i}")
            for i in range(5)
        ]
        result = detect_n_plus_one(entries)
        assert len(result) == 1
        assert result[0]["table"] == "app_user"
        assert result[0]["count"] == 5

    def test_below_threshold_is_ignored(self):
        entries = [
            self._sql_entry("SELECT * FROM app_user WHERE id = 1"),
            self._sql_entry("SELECT * FROM app_user WHERE id = 2"),
        ]
        assert detect_n_plus_one(entries) == []
