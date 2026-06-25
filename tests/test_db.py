import pytest

from log_tools import LogContext


@pytest.mark.django_db
class TestDBLogging:
    def test_queries_captured(self):
        from django.contrib.auth.models import User

        with LogContext("db_test") as collector:
            list(User.objects.all())

        sql_entries = collector.sql_entries()
        assert len(sql_entries) >= 1
        assert "auth_user" in sql_entries[0].data["sql"]

    def test_multiple_queries(self):
        from django.contrib.auth.models import User

        with LogContext("multi_db") as collector:
            list(User.objects.all())
            list(User.objects.all())

        assert len(collector.sql_entries()) >= 2

    def test_slow_query_detection(self):
        from django.contrib.auth.models import User

        with LogContext("slow_db", slow_threshold_ms=0.001) as collector:
            list(User.objects.all())

        assert any(entry.is_slow for entry in collector.sql_entries())
