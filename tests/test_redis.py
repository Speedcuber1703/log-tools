from log_tools import LogContext
from log_tools.redis import get_logging_redis_class


class TestRedisLogging:
    def test_redis_commands_captured(self):
        with LogContext("redis_test") as collector:
            collector.add_redis("GET", ("mykey",), duration_ms=1.5)

        redis_entries = collector.redis_entries()
        assert len(redis_entries) == 1
        assert redis_entries[0].data["command"] == "GET"
        assert redis_entries[0].data["args"] == ("mykey",)

    def test_redis_multiple_commands(self):
        with LogContext("redis_multi") as collector:
            collector.add_redis("SET", ("key1", "val1"), duration_ms=0.5)
            collector.add_redis("GET", ("key1",), duration_ms=0.3)
            collector.add_redis("DELETE", ("key1",), duration_ms=0.2)

        assert len(collector.redis_entries()) == 3
        commands = [entry.data["command"] for entry in collector.redis_entries()]
        assert commands == ["SET", "GET", "DELETE"]

    def test_redis_slow_detection(self):
        with LogContext("redis_slow", slow_threshold_ms=1) as collector:
            collector.add_redis("SLOWCOMMAND", ("arg",), duration_ms=50.0)

        assert collector.redis_entries()[0].is_slow is True

    def test_logging_redis_class_exists(self):
        cls = get_logging_redis_class()
        assert cls is not None
        assert hasattr(cls, "execute_command")
