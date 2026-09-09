"""
Tests for the Phase 2B health check service.

All HTTP calls are mocked; no real network requests are made and the
application is not started.
"""

import socket
import urllib.error
from unittest.mock import MagicMock, patch

from app.schemas import ServiceModel
from app.schemas.health import HealthStatus
from app.services.health_check import HealthCheckService


def make_service(service_id="test-service", health_endpoint="/health"):
    return ServiceModel(
        id=service_id,
        name="Test Service",
        host=f"{service_id}.internal",
        port=8080,
        source_environment="legacy",
        target_environment="modern",
        health_endpoint=health_endpoint,
        dependencies=[],
    )


def fake_response(status_code):
    response = MagicMock()
    response.getcode.return_value = status_code
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def test_healthy_service_reports_healthy_status():
    service = make_service(service_id="auth-service")

    with patch(
        "app.services.health_check.urllib.request.urlopen",
        return_value=fake_response(200),
    ):
        result = HealthCheckService(timeout=1.0).check_service(service)

    # Service information
    assert result.service_id == "auth-service"
    assert result.service_name == service.name
    # HTTP 200 status
    assert result.status == HealthStatus.HEALTHY
    assert result.http_status == 200
    assert result.error is None
    # Latency captured
    assert result.latency_ms is not None
    assert result.latency_ms >= 0


def test_http_error_reports_unhealthy_with_status_code():
    service = make_service()
    http_error = urllib.error.HTTPError(
        url="http://test.internal:8080/health", code=503, msg="Service Unavailable", hdrs=None, fp=None
    )

    with patch(
        "app.services.health_check.urllib.request.urlopen",
        side_effect=http_error,
    ):
        result = HealthCheckService(timeout=1.0).check_service(service)

    assert result.status == HealthStatus.UNHEALTHY
    assert result.http_status == 503
    assert result.error is not None


def test_connection_error_reports_unreachable():
    service = make_service()
    url_error = urllib.error.URLError(reason=ConnectionRefusedError("connection refused"))

    with patch(
        "app.services.health_check.urllib.request.urlopen",
        side_effect=url_error,
    ):
        result = HealthCheckService(timeout=1.0).check_service(service)

    assert result.status == HealthStatus.UNREACHABLE
    assert result.http_status is None
    assert result.error is not None


def test_timeout_reports_timeout_status():
    service = make_service()

    with patch(
        "app.services.health_check.urllib.request.urlopen",
        side_effect=socket.timeout(),
    ):
        result = HealthCheckService(timeout=0.5).check_service(service)

    assert result.status == HealthStatus.TIMEOUT
    assert result.error is not None


def test_check_all_aggregates_results_without_raising(monkeypatch):
    services = [make_service("svc-a"), make_service("svc-b")]

    class FakeInventoryLoader:
        def get_all_services_list(self):
            return services

    monkeypatch.setattr(
        "app.services.health_check.get_inventory_loader",
        lambda: FakeInventoryLoader(),
    )

    def fake_urlopen(url, timeout=None):
        if "svc-a" in url:
            return fake_response(200)
        raise urllib.error.URLError(reason=OSError("unreachable"))

    with patch(
        "app.services.health_check.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        summary = HealthCheckService(timeout=1.0).check_all()

    assert summary.total_services == 2
    assert summary.healthy_count == 1
    assert summary.unhealthy_count == 1
    assert len(summary.results) == 2
