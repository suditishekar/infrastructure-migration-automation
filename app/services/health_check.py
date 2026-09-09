"""
Active health check service.

Performs live HTTP probing against each configured service's health
endpoint, using the existing service inventory. Unlike Phase 2A's static
PreMigrationValidator, this issues real network requests and reports
reachability/status rather than configuration correctness.
"""

import socket
import time
import urllib.error
import urllib.request
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas import ServiceModel
from app.schemas.health import HealthCheckSummary, HealthStatus, ServiceHealthResult
from app.services.inventory import get_inventory_loader

logger = get_logger("health_check")


class HealthCheckService:
    """Performs active HTTP health checks against inventory services."""

    def __init__(self, timeout: Optional[float] = None):
        """
        Initialize the health check service.

        Args:
            timeout: Per-service request timeout in seconds.
                     Defaults to settings.HEALTH_CHECK_TIMEOUT if not provided.
        """
        self.timeout = timeout if timeout is not None else settings.HEALTH_CHECK_TIMEOUT

    def check_service(self, service: ServiceModel) -> ServiceHealthResult:
        """
        Perform a health check against a single service.

        Args:
            service: The service to check.

        Returns:
            ServiceHealthResult describing the outcome. Never raises: connection
            errors, timeouts, and invalid responses are captured as a result.
        """
        url = f"http://{service.host}:{service.port}{service.health_endpoint}"
        start = time.monotonic()

        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                latency_ms = (time.monotonic() - start) * 1000
                http_status = response.getcode()
                is_healthy = 200 <= http_status < 300
                if not is_healthy:
                    logger.warning(
                        f"Service {service.id} health check returned status {http_status}"
                    )
                return ServiceHealthResult(
                    service_id=service.id,
                    service_name=service.name,
                    status=HealthStatus.HEALTHY if is_healthy else HealthStatus.UNHEALTHY,
                    http_status=http_status,
                    latency_ms=round(latency_ms, 2),
                )
        except urllib.error.HTTPError as e:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning(f"Service {service.id} health check returned HTTP error {e.code}")
            return ServiceHealthResult(
                service_id=service.id,
                service_name=service.name,
                status=HealthStatus.UNHEALTHY,
                http_status=e.code,
                latency_ms=round(latency_ms, 2),
                error=str(e),
            )
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                logger.warning(
                    f"Service {service.id} health check timed out after {self.timeout}s"
                )
                return ServiceHealthResult(
                    service_id=service.id,
                    service_name=service.name,
                    status=HealthStatus.TIMEOUT,
                    error=f"Health check timed out after {self.timeout}s",
                )
            logger.warning(f"Service {service.id} is unreachable: {e.reason}")
            return ServiceHealthResult(
                service_id=service.id,
                service_name=service.name,
                status=HealthStatus.UNREACHABLE,
                error=str(e.reason),
            )
        except socket.timeout:
            logger.warning(
                f"Service {service.id} health check timed out after {self.timeout}s"
            )
            return ServiceHealthResult(
                service_id=service.id,
                service_name=service.name,
                status=HealthStatus.TIMEOUT,
                error=f"Health check timed out after {self.timeout}s",
            )
        except Exception as e:
            logger.error(f"Unexpected error checking service {service.id}: {e}")
            return ServiceHealthResult(
                service_id=service.id,
                service_name=service.name,
                status=HealthStatus.UNHEALTHY,
                error=str(e),
            )

    def check_all(self) -> HealthCheckSummary:
        """
        Perform health checks across all services in the inventory.

        Returns:
            HealthCheckSummary with per-service results and aggregate counts.
        """
        inventory = get_inventory_loader()
        services = inventory.get_all_services_list()

        logger.info(f"Running health checks for {len(services)} services")
        results = [self.check_service(service) for service in services]

        healthy_count = sum(1 for r in results if r.status == HealthStatus.HEALTHY)
        unhealthy_count = len(results) - healthy_count

        logger.info(
            f"Health check run complete: {healthy_count} healthy, {unhealthy_count} unhealthy"
        )

        return HealthCheckSummary(
            total_services=len(results),
            healthy_count=healthy_count,
            unhealthy_count=unhealthy_count,
            results=results,
        )


# Global health check service instance
_health_check_service: Optional[HealthCheckService] = None


def get_health_check_service() -> HealthCheckService:
    """
    Get or create the global health check service instance.

    Returns:
        The HealthCheckService instance.
    """
    global _health_check_service
    if _health_check_service is None:
        _health_check_service = HealthCheckService()
    return _health_check_service
