import pytest

from log_tools import LogContext, current_collector, Collector
from log_tools.collector import EntryType


class TestCollector:
    def test_basic_collecting(self):
        collector = Collector("test")
        collector.start()
        collector.add_sql("SELECT 1", duration_ms=5.0)
        collector.add_redis("GET", ("key",), duration_ms=1.0)
        collector.add_timing("step1", 10.0)
        collector.add_log("info message")
        collector.finish()

        summary = collector.summary()
        assert summary["name"] == "test"
        assert summary["sql_count"] == 1
        assert summary["redis_count"] == 1
        assert summary["elapsed_ms"] > 0
        assert len(collector.entries) == 4

    def test_slow_detection(self):
        collector = Collector("slow_test", slow_threshold_ms=10)
        collector.start()
        collector.add_sql("SELECT pg_sleep(1)", duration_ms=50.0)
        collector.add_redis("SLOW", (), duration_ms=50.0)
        collector.finish()

        assert collector.entries[0].is_slow is True
        assert collector.entries[1].is_slow is True
        assert len(collector.summary()["sql_slow"]) == 1
        assert len(collector.summary()["redis_slow"]) == 1

    def test_entries_filtered(self):
        collector = Collector("filter_test")
        collector.start()
        collector.add_sql("SELECT 1")
        collector.add_redis("SET", ("k", "v"))
        collector.add_timing("t", 1.0)
        collector.add_log("msg")
        collector.finish()

        assert len(collector.sql_entries()) == 1
        assert len(collector.redis_entries()) == 1
        assert len(collector.timing_entries()) == 1
        assert collector.sql_entries()[0].type == EntryType.SQL
        assert collector.redis_entries()[0].type == EntryType.REDIS

    def test_concurrent_collectors(self):
        first = Collector("first")
        first.start()
        assert current_collector() is first

        second = Collector("second")
        second.start()
        assert current_collector() is second

        second.finish()
        assert current_collector() is first

        first.finish()
        assert current_collector() is None


class TestLogContext:
    def test_basic_context(self):
        with LogContext("block") as collector:
            assert current_collector() is collector
            collector.add_sql("SELECT 1")
        assert current_collector() is None
        assert len(collector.entries) == 1

    def test_decorator(self):
        @LogContext("decorated")
        def my_func():
            col = current_collector()
            col.add_sql("SELECT 2")
            return 42

        result = my_func()
        assert result == 42

    def test_nested_context(self):
        with LogContext("outer") as outer:
            outer.add_sql("outer query")
            with LogContext("inner") as inner:
                inner.add_sql("inner query")
                assert current_collector() is inner
            assert current_collector() is outer

        assert len(outer.entries) == 2
        assert len(inner.entries) == 1
        assert inner.entries[0].data["sql"] == "inner query"
        assert outer.entries[0].data["sql"] == "outer query"
        assert outer.entries[1].data["sql"] == "inner query"

    def test_exception_safety(self):
        with pytest.raises(ValueError):
            with LogContext("safe_block") as collector:
                collector.add_sql("before error")
                raise ValueError("boom")

        assert current_collector() is None
        assert len(collector.entries) == 1

    def test_inheritance_slow_threshold(self):
        with LogContext("parent") as parent:
            with LogContext("child") as child:
                assert child.slow_threshold_ms == parent.slow_threshold_ms


class TestDecorator:
    def test_preserves_function_metadata(self):
        @LogContext("meta_test")
        def documented_func():
            """This is documentation."""
            pass

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is documentation."

    def test_with_args(self):
        @LogContext("args_test")
        def add(a, b, extra=None):
            return a + b

        assert add(1, 2) == 3
        assert add(1, 2, extra="x") == 3
