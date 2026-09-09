"""
Migration operation abstraction.

Defines the interface a migration provider must implement to execute and
roll back a service's migration, plus the post-migration health-check
abstraction the orchestrator uses to confirm a migration succeeded. The
default SimulatedMigrationProvider/SimulatedHealthChecker perform no real
infrastructure changes or network calls and are fully deterministic, so
the default migration flow does not depend on the sample inventory's
legacy hosts being resolvable. A real provider or Phase 2B's
HealthCheckService can be substituted later without changing the
orchestrator, since both satisfy the same `check_service` shape.
"""

from abc import ABC, abstractmethod
from typing import Optional, Protocol, Set

from app.core.exceptions import MigrationExecutionError, RollbackError
from app.core.logging import get_logger
from app.schemas import ServiceModel
from app.schemas.health import HealthStatus, ServiceHealthResult

logger = get_logger("migration_provider")


class MigrationProvider(ABC):
    """Abstraction for executing a migration attempt and its rollback."""

    @abstractmethod
    def migrate(self, service: ServiceModel) -> None:
        """
        Execute a migration attempt for a service.

        Raises:
            MigrationExecutionError: If the migration attempt fails.
        """
        raise NotImplementedError

    @abstractmethod
    def rollback(self, service: ServiceModel) -> None:
        """
        Roll back a previously attempted migration for a service.

        Raises:
            RollbackError: If the rollback attempt fails.
        """
        raise NotImplementedError


class SimulatedMigrationProvider(MigrationProvider):
    """
    Deterministic, side-effect-free default migration provider.

    Does not perform any real infrastructure changes. By default every
    migration and rollback succeeds; specific service IDs can be forced to
    fail (used to exercise retry/rollback behavior in tests) via the
    constructor.
    """

    def __init__(
        self,
        always_fail_service_ids: Optional[Set[str]] = None,
        always_fail_rollback_service_ids: Optional[Set[str]] = None,
    ):
        self._always_fail = always_fail_service_ids or set()
        self._always_fail_rollback = always_fail_rollback_service_ids or set()

    def migrate(self, service: ServiceModel) -> None:
        logger.info(
            f"Simulating migration for '{service.id}' "
            f"({service.source_environment} -> {service.target_environment})"
        )
        if service.id in self._always_fail:
            raise MigrationExecutionError(
                f"Simulated migration failure for service '{service.id}'"
            )

    def rollback(self, service: ServiceModel) -> None:
        logger.info(f"Simulating rollback for '{service.id}'")
        if service.id in self._always_fail_rollback:
            raise RollbackError(
                f"Simulated rollback failure for service '{service.id}'"
            )


class HealthChecker(Protocol):
    """Structural interface for a post-migration health checker."""

    def check_service(self, service: ServiceModel) -> ServiceHealthResult:
        ...


class SimulatedHealthChecker:
    """
    Deterministic, side-effect-free default post-migration health checker.

    Performs no real network calls, so it does not depend on the sample
    inventory's legacy hosts (e.g. legacy-auth.internal) being resolvable.
    By default every checked service reports healthy; specific service IDs
    can be forced to report unhealthy (used to exercise health-check
    failure/retry/rollback behavior in tests) via the constructor.

    A real checker (e.g. Phase 2B's HealthCheckService) can be injected
    into MigrationOrchestrator instead, since it implements the same
    `check_service` shape.
    """

    def __init__(self, always_fail_service_ids: Optional[Set[str]] = None):
        self._always_fail = always_fail_service_ids or set()

    def check_service(self, service: ServiceModel) -> ServiceHealthResult:
        if service.id in self._always_fail:
            logger.warning(f"Simulating unhealthy post-migration check for '{service.id}'")
            return ServiceHealthResult(
                service_id=service.id,
                service_name=service.name,
                status=HealthStatus.UNHEALTHY,
                error=f"Simulated health check failure for service '{service.id}'",
            )

        logger.info(f"Simulating healthy post-migration check for '{service.id}'")
        return ServiceHealthResult(
            service_id=service.id,
            service_name=service.name,
            status=HealthStatus.HEALTHY,
            http_status=200,
            latency_ms=0.0,
        )
