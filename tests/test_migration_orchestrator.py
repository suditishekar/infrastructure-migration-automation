"""
Tests for the Phase 3 migration orchestrator, updated for Phase 4
persistence.

The service inventory (as seen by both the orchestrator and the reused
Phase 2A validator) is faked. Migration state is persisted through a
MigrationRepository backed by an isolated in-memory SQLite database (never
the real app.db), so these tests run fully offline: no real network
calls, no touching config/services.yaml or the real database file, and
the application is never started.

The post-migration health check defaults to a deterministic
SimulatedHealthChecker (no real network calls), which is what allows the
default simulated migration flow to succeed without depending on the
sample inventory's legacy hosts being resolvable. Phase 2B's real
HealthCheckService remains available and injectable; its own unmodified
behavior is covered by tests/test_health_check.py, plus an injection
check here.
"""

import urllib.error
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import ServiceNotFoundError
from app.database.session import create_sqlite_engine, init_db
from app.schemas import ServiceModel
from app.schemas.health import HealthStatus, ServiceHealthResult
from app.schemas.migration import MigrationState
from app.services.health_check import HealthCheckService
from app.services.migration_orchestrator import MigrationOrchestrator
from app.services.migration_provider import SimulatedHealthChecker, SimulatedMigrationProvider
from app.services.migration_repository import MigrationRepository


def make_service(service_id, dependencies=None, host=None):
    return ServiceModel(
        id=service_id,
        name=f"{service_id} name",
        host=host or f"{service_id}.internal",
        port=8080,
        source_environment="legacy",
        target_environment="modern",
        health_endpoint="/health",
        dependencies=dependencies or [],
    )


class FakeInventoryLoader:
    """Stand-in for InventoryLoader used by both the orchestrator and validator."""

    def __init__(self, services):
        self._services = services

    def get_all_services(self):
        return dict(self._services)

    def get_service(self, service_id):
        if service_id not in self._services:
            raise ServiceNotFoundError(f"Service '{service_id}' not found in inventory")
        return self._services[service_id]


class FakeHealthCheckService:
    """Controllable, deterministic stand-in for a health checker in tests."""

    def __init__(self, health_status=HealthStatus.HEALTHY, error=None):
        self.health_status = health_status
        self.error = error
        self.calls = 0

    def check_service(self, service):
        self.calls += 1
        return ServiceHealthResult(
            service_id=service.id,
            service_name=service.name,
            status=self.health_status,
            http_status=200 if self.health_status == HealthStatus.HEALTHY else None,
            latency_ms=1.0 if self.health_status == HealthStatus.HEALTHY else None,
            error=self.error,
        )


class CountingMigrationProvider(SimulatedMigrationProvider):
    """SimulatedMigrationProvider that records calls, for retry/idempotency assertions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.migrate_calls = []
        self.rollback_calls = []

    def migrate(self, service):
        self.migrate_calls.append(service.id)
        super().migrate(service)

    def rollback(self, service):
        self.rollback_calls.append(service.id)
        super().rollback(service)


def patch_inventory(monkeypatch, services):
    loader = FakeInventoryLoader(services)
    monkeypatch.setattr(
        "app.services.migration_orchestrator.get_inventory_loader", lambda: loader
    )
    monkeypatch.setattr(
        "app.services.pre_migration_validator.get_inventory_loader", lambda: loader
    )
    return loader


def make_session_factory():
    """An isolated, disposable in-memory SQLite session factory for one test."""
    engine = create_sqlite_engine("sqlite:///:memory:")
    init_db(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def make_repository():
    """A fresh MigrationRepository backed by its own isolated in-memory database."""
    return MigrationRepository(session_factory=make_session_factory())


# ---------------------------------------------------------------------------
# Successful migration / idempotency
# ---------------------------------------------------------------------------


def test_successful_simulated_migration_reaches_completed(monkeypatch):
    """
    Regression test for the health-check integration fix: with no
    health_checker injected, the orchestrator must use the default
    deterministic SimulatedHealthChecker rather than Phase 2B's real
    HealthCheckService, so a service with a non-resolvable legacy host
    (like the real inventory's legacy-auth.internal) still completes.
    """
    services = {"auth-service": make_service("auth-service", host="legacy-auth.internal")}
    patch_inventory(monkeypatch, services)

    provider = CountingMigrationProvider()
    orchestrator = MigrationOrchestrator(
        provider=provider, repository=make_repository(), max_retries=2
    )

    record = orchestrator.migrate_service("auth-service")

    assert record.state == MigrationState.COMPLETED
    assert record.error is None
    assert len(record.attempts) == 1
    assert record.attempts[0].success is True
    assert record.rollback is None
    assert record.completed_at is not None
    assert provider.migrate_calls == ["auth-service"]
    assert isinstance(orchestrator.health_checker, SimulatedHealthChecker)


def test_idempotent_repeated_migration_does_not_reexecute(monkeypatch):
    services = {"auth-service": make_service("auth-service")}
    patch_inventory(monkeypatch, services)

    provider = CountingMigrationProvider()
    orchestrator = MigrationOrchestrator(
        provider=provider, repository=make_repository(), max_retries=2
    )

    first = orchestrator.migrate_service("auth-service")
    second = orchestrator.migrate_service("auth-service")

    assert first.state == MigrationState.COMPLETED
    assert second.state == MigrationState.COMPLETED
    assert first.migration_id == second.migration_id
    # Repeated request must not re-run the migration.
    assert provider.migrate_calls == ["auth-service"]


def test_idempotency_uses_persisted_state_not_process_memory(monkeypatch):
    """
    A brand-new MigrationOrchestrator (and repository object) backed by the
    same underlying database must still recognize a service as already
    COMPLETED and must not re-run its migration - idempotency must not
    depend on any in-process cache.
    """
    services = {"auth-service": make_service("auth-service")}
    patch_inventory(monkeypatch, services)

    session_factory = make_session_factory()

    provider_1 = CountingMigrationProvider()
    orchestrator_1 = MigrationOrchestrator(
        provider=provider_1,
        repository=MigrationRepository(session_factory=session_factory),
        max_retries=2,
    )
    first = orchestrator_1.migrate_service("auth-service")
    assert first.state == MigrationState.COMPLETED

    # A completely new orchestrator/repository object, same underlying DB.
    provider_2 = CountingMigrationProvider()
    orchestrator_2 = MigrationOrchestrator(
        provider=provider_2,
        repository=MigrationRepository(session_factory=session_factory),
        max_retries=2,
    )

    fetched = orchestrator_2.get_migration(first.migration_id)
    assert fetched is not None
    assert fetched.state == MigrationState.COMPLETED

    second = orchestrator_2.migrate_service("auth-service")
    assert second.migration_id == first.migration_id
    assert second.state == MigrationState.COMPLETED
    assert provider_2.migrate_calls == []  # never invoked - idempotent short-circuit


# ---------------------------------------------------------------------------
# Errors: unknown service, validation failure
# ---------------------------------------------------------------------------


def test_unknown_service_raises_service_not_found(monkeypatch):
    patch_inventory(monkeypatch, {})

    orchestrator = MigrationOrchestrator(
        provider=SimulatedMigrationProvider(), repository=make_repository(), max_retries=1
    )

    with pytest.raises(ServiceNotFoundError):
        orchestrator.migrate_service("does-not-exist")


def test_validation_failure_when_dependency_not_ready(monkeypatch):
    services = {
        "auth-service": make_service("auth-service"),
        "payment-service": make_service("payment-service", dependencies=["auth-service"]),
    }
    patch_inventory(monkeypatch, services)

    orchestrator = MigrationOrchestrator(
        provider=SimulatedMigrationProvider(), repository=make_repository(), max_retries=1
    )

    # auth-service has never been migrated, so payment-service cannot proceed.
    record = orchestrator.migrate_service("payment-service")

    assert record.state == MigrationState.VALIDATION_FAILED
    assert "auth-service" in record.error
    assert record.attempts == []


# ---------------------------------------------------------------------------
# Migration failure / retries / rollback
# ---------------------------------------------------------------------------


def test_migration_failure_retries_then_rolls_back(monkeypatch):
    """Migration failure: max_attempts is respected, every attempt is recorded,
    and the final state is ROLLED_BACK once rollback succeeds."""
    services = {"payment-service": make_service("payment-service")}
    patch_inventory(monkeypatch, services)

    provider = CountingMigrationProvider(always_fail_service_ids={"payment-service"})
    orchestrator = MigrationOrchestrator(
        provider=provider, repository=make_repository(), max_retries=2
    )

    record = orchestrator.migrate_service("payment-service")

    # max_attempts = 1 initial + 2 retries = 3, and it is respected exactly.
    assert record.max_attempts == 3
    assert len(record.attempts) == 3
    for index, attempt in enumerate(record.attempts, start=1):
        assert attempt.attempt_number == index
        assert attempt.success is False
        assert attempt.error is not None
    assert provider.migrate_calls == ["payment-service"] * 3
    assert provider.rollback_calls == ["payment-service"]
    assert record.rollback is not None
    assert record.rollback.attempted is True
    assert record.rollback.succeeded is True
    assert record.state == MigrationState.ROLLED_BACK


def test_health_check_failure_retries_then_rolls_back(monkeypatch):
    """Health-check failure: causes retries (migrate succeeds each time, health
    check fails each time), and the final state is ROLLED_BACK once rollback succeeds."""
    services = {"payment-service": make_service("payment-service")}
    patch_inventory(monkeypatch, services)

    provider = CountingMigrationProvider()
    fake_health = FakeHealthCheckService(health_status=HealthStatus.UNHEALTHY, error="boom")
    orchestrator = MigrationOrchestrator(
        provider=provider,
        health_checker=fake_health,
        repository=make_repository(),
        max_retries=1,
    )

    record = orchestrator.migrate_service("payment-service")

    assert record.max_attempts == 2
    assert provider.migrate_calls == ["payment-service"] * 2  # migrate succeeded both times
    assert fake_health.calls == 2  # 1 initial + 1 retry, health check failed both times
    assert len(record.attempts) == 2
    assert all(attempt.success is False for attempt in record.attempts)
    assert record.state == MigrationState.ROLLED_BACK
    assert record.rollback.attempted is True
    assert record.rollback.succeeded is True


def test_rollback_failure_preserves_failure_state_without_crashing(monkeypatch):
    """Rollback failure: represented clearly (rollback.succeeded=False, error set),
    original failure state preserved, and no exception escapes the orchestrator."""
    services = {"payment-service": make_service("payment-service")}
    patch_inventory(monkeypatch, services)

    provider = CountingMigrationProvider(
        always_fail_service_ids={"payment-service"},
        always_fail_rollback_service_ids={"payment-service"},
    )
    orchestrator = MigrationOrchestrator(
        provider=provider, repository=make_repository(), max_retries=1
    )

    # Must return normally (not raise) even though both migration and rollback fail.
    record = orchestrator.migrate_service("payment-service")

    # Migration ultimately failed and rollback also failed: the failure
    # state must be preserved rather than overwritten to ROLLED_BACK.
    assert record.state == MigrationState.MIGRATION_FAILED
    assert record.error is not None
    assert record.rollback.attempted is True
    assert record.rollback.succeeded is False
    assert record.rollback.error is not None


# ---------------------------------------------------------------------------
# Health-check abstraction: injectability (Phase 2B behavior unchanged)
# ---------------------------------------------------------------------------


def test_real_health_check_service_behavior_unchanged_when_injected(monkeypatch):
    """
    Phase 2B's real HealthCheckService still performs a real (mocked here)
    HTTP GET and can be injected into the orchestrator unchanged; its own
    dedicated behavior is covered by tests/test_health_check.py.
    """
    services = {"auth-service": make_service("auth-service")}
    patch_inventory(monkeypatch, services)

    fake_response = MagicMock()
    fake_response.getcode.return_value = 200
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False

    real_health_checker = HealthCheckService(timeout=1.0)
    provider = CountingMigrationProvider()
    orchestrator = MigrationOrchestrator(
        provider=provider,
        health_checker=real_health_checker,
        repository=make_repository(),
        max_retries=1,
    )

    with patch(
        "app.services.health_check.urllib.request.urlopen",
        return_value=fake_response,
    ):
        record = orchestrator.migrate_service("auth-service")

    assert record.state == MigrationState.COMPLETED
    assert record.attempts[0].success is True


def test_real_health_check_service_unreachable_host_fails_migration(monkeypatch):
    """
    Confirms the real HealthCheckService's unreachable-host handling is
    unchanged: when explicitly injected, an unresolvable host still fails
    the post-migration check (this is the exact condition the default
    SimulatedHealthChecker now avoids for the default simulated flow).
    """
    services = {"auth-service": make_service("auth-service", host="legacy-auth.internal")}
    patch_inventory(monkeypatch, services)

    real_health_checker = HealthCheckService(timeout=1.0)
    provider = CountingMigrationProvider()
    orchestrator = MigrationOrchestrator(
        provider=provider,
        health_checker=real_health_checker,
        repository=make_repository(),
        max_retries=0,
    )

    with patch(
        "app.services.health_check.urllib.request.urlopen",
        side_effect=urllib.error.URLError(reason=OSError("Name or service not known")),
    ):
        record = orchestrator.migrate_service("auth-service")

    assert record.state in (MigrationState.HEALTH_CHECK_FAILED, MigrationState.ROLLED_BACK)
    assert record.attempts[0].success is False
