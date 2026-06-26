import pytest
from django.http import HttpRequest, HttpResponse
from django.test import override_settings

from log_tools.middleware import LogToolsMiddleware, get_collector_from_request
from log_tools.collector import current_collector


def dummy_view(request):
    return HttpResponse("ok")


@pytest.mark.django_db
class TestMiddleware:
    def test_collector_attached_to_request(self):
        mw = LogToolsMiddleware(dummy_view)
        request = HttpRequest()
        request.method = "GET"
        request.path = "/test/"

        response = mw(request)

        assert response.status_code == 200
        collector = get_collector_from_request(request)
        assert collector is not None
        assert collector.name == "GET /test/"

    def test_timing_recorded(self):
        mw = LogToolsMiddleware(dummy_view)
        request = HttpRequest()
        request.method = "POST"
        request.path = "/api/data"

        mw(request)

        collector = get_collector_from_request(request)
        timing_entries = collector.timing_entries()
        assert len(timing_entries) == 1
        assert timing_entries[0].data["label"] == "total"
        assert timing_entries[0].duration_ms > 0

    def test_summary_populated(self):
        mw = LogToolsMiddleware(dummy_view)
        request = HttpRequest()
        request.method = "GET"
        request.path = "/summary-test"

        mw(request)

        collector = get_collector_from_request(request)
        summary = collector.summary()
        assert summary["name"] == "GET /summary-test"
        assert summary["elapsed_ms"] > 0
        assert summary["total_entries"] >= 1

    @override_settings(LOG_TOOLS_SLOW_THRESHOLD_MS=0.001)
    def test_configured_slow_threshold_is_applied(self):
        mw = LogToolsMiddleware(dummy_view)
        request = HttpRequest()
        request.method = "GET"
        request.path = "/slow"

        mw(request)

        collector = get_collector_from_request(request)
        # Настроенный порог должен дойти до коллектора, а не быть зашитой сотней.
        assert collector.slow_threshold_ms == 0.001
        total = collector.timing_entries()[0]
        assert total.data["label"] == "total"
        assert total.is_slow is True
