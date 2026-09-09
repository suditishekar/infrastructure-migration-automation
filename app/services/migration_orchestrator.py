"""
Phase 3 core migration orchestration.

Coordinates the per-service migration workflow: reuses Phase 2A's
pre-migration validation, adds a dependency-readiness gate, and executes a
migration through a pluggable provider abstraction with configurable
retries and rollback-on-failure. The post-migration health check is also
pluggable: it defaults to a deterministic simulated checker (since the
default migration is itself simulated and the sample inventory's legacy
hosts are not real/resolvable), but Phase 2B's real HealthCheckService can
be injected instead without any other change.

Phase 4: migration state is persisted through MigrationRepository (SQLite
via SQLAlchemy) rather than held only in process memory, so idempotency,
dependency-readiness checks, and API reads all survive an application
restart. Each call still runs synchronously to completion; there is no
queue or background worker involved.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from app.core.config import settings
from app.core.exceptions import InvalidDependencyGraphError, MigrationExecutionError
from app.core.logging import get_logger
from app.schemas import ServiceModel
from app.schemas.health import HealthStatus
from app.schemas.migration import (
    MigrationAttempt,
    MigrationRecord,
    MigrationState,
    RollbackInfo,
)
from app.schemas.validation import ValidationCategory
from app.services.inventory import get_inventory_loader
from app.services.migration_orderer import build_migration_order
from app.services.migration_provider import (
    HealthChecker,
    MigrationProvider,
    SimulatedHealthChecker,
    SimulatedMigrationProvider,
)
from app.services.migration_repository import MigrationRepository, get_migration_repository
from app.services.pre_migration_validator import get_validator

logger = get_logger("migration_orchestrator")


class MigrationOrchestrator:
    """Orchestrates the migration workflow for individual services."""

    def __init__(
        self,
        provider: Optional[MigrationProvider] = None,
        health_checker: Optional[HealthChecker] = None,
        repository: Optional[MigrationRepository] = None,
        max_retries: Optional[int] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            provider: Migration operation abstraction to use.
                      Defaults to a safe, deterministic SimulatedMigrationProvider.
            health_checker: Post-migration health check abstraction to use.
                      Defaults to a safe, deterministic SimulatedHealthChecker.
                      Phase 2B's real HealthCheckService can be injected here
                      instead to probe real endpoints.
            repository: Persistence layer for migration records/attempts.
                      Defaults to the app-wide MigrationRepository (SQLite).
            max_retries: Additional attempts allowed after the first failure.
                         Defaults to settings.MIGRATION_MAX_RETRIES.
        """
        self.provider = provider or SimulatedMigrationProvider()
        self.health_checker = health_checker or SimulatedHealthChecker()
        self.repository = repository or get_migration_repository()
        self.max_retries = (
            max_retries if max_retries is not None else settings.MIGRATION_MAX_RETRIES
        )

    def get_migration(self, migration_id: str) -> Optional[MigrationRecord]:
        """Look up a migration record by migration ID (from persisted state)."""
        return self.repository.get_by_migration_id(migration_id)

    def list_migrations(self) -> List[MigrationRecord]:
        """List all migration records (from persisted state)."""
        return self.repository.list_all()

    def migrate_service(self, service_id: str) -> MigrationRecord:
        """
        Run (or return the existing result of) the migration workflow for a service.

        Args:
            service_id: The service to migrate.

        Returns:
            MigrationRecord describing the resulting migration state.

        Raises:
            ServiceNotFoundError: If the service does not exist in the inventory.
        """
        inventory = get_inventory_loader()
        service = inventory.get_service(service_id)  # raises ServiceNotFoundError

        existing = self.repository.get_by_service_id(service_id)
        if existing and existing.state == MigrationState.COMPLETED:
            logger.info(f"Service '{service_id}' already migrated; returning existing result")
            return existing

        record = existing or self._create_record(service)
        # Fresh run: reset transient state from any prior failed attempt.
        record.service_name = service.name
        record.attempts = []
        record.rollback = None
        record.error = None
        record.completed_at = None
        record.updated_at = datetime.utcnow()
        self._persist(record)

        if not self._run_validation_gate(record, service):
            return record

        self._run_migration_with_retries(record, service)
        return record

    def _create_record(self, service: ServiceModel) -> MigrationRecord:
        record = MigrationRecord(
            migration_id=f"mig-{uuid.uuid4().hex[:12]}",
            service_id=service.id,
            service_name=service.name,
            state=MigrationState.DISCOVERED,
            max_attempts=self.max_retries + 1,
        )
        self._persist(record)
        return record

    def _persist(self, record: MigrationRecord) -> None:
        """Persist the current state of a migration record (and its attempts)."""
        self.repository.save(record)

    def _run_validation_gate(self, record: MigrationRecord, service: ServiceModel) -> bool:
        """
        Run pre-migration validation and dependency-readiness checks.

        Returns:
            True if the service is READY to migrate, False if the record
            was transitioned to VALIDATION_FAILED.
        """
        record.state = MigrationState.VALIDATING
        record.updated_at = datetime.utcnow()
        self._persist(record)
        logger.info(f"Validating service '{service.id}' for migration")

        # Reuse Phase 2A's pre-migration validation in full.
        validator = get_validator()
        result = validator.validate()

        blocking = [
            issue
            for issue in result.errors
            if issue.service_id == service.id
            or (
                issue.category == ValidationCategory.CIRCULAR_DEPENDENCY
                and service.id in (issue.details or {}).get("cycle_path", [])
            )
        ]
        if blocking:
            record.error = "; ".join(issue.message for issue in blocking)
            record.state = MigrationState.VALIDATION_FAILED
            record.updated_at = datetime.utcnow()
            self._persist(record)
            logger.warning(f"Validation failed for '{service.id}': {record.error}")
            return False

        # Confirm the whole graph is orderable (reuses the validator-based
        # cycle detection above rather than a second implementation).
        try:
            build_migration_order(validator.services)
        except InvalidDependencyGraphError as e:
            record.error = str(e)
            record.state = MigrationState.VALIDATION_FAILED
            record.updated_at = datetime.utcnow()
            self._persist(record)
            logger.warning(f"Dependency graph invalid for '{service.id}': {record.error}")
            return False

        # Dependency readiness: direct dependencies must already be COMPLETED
        # (checked against persisted state, so this survives restarts too).
        not_ready = []
        for dep_id in service.dependencies:
            dep_record = self.repository.get_by_service_id(dep_id)
            dep_state = dep_record.state.value if dep_record else "not started"
            if dep_record is None or dep_record.state != MigrationState.COMPLETED:
                not_ready.append(f"'{dep_id}' (state: {dep_state})")

        if not_ready:
            record.error = f"Dependencies not ready: {', '.join(not_ready)}"
            record.state = MigrationState.VALIDATION_FAILED
            record.updated_at = datetime.utcnow()
            self._persist(record)
            logger.warning(f"Dependency readiness failed for '{service.id}': {record.error}")
            return False

        record.state = MigrationState.READY
        record.updated_at = datetime.utcnow()
        self._persist(record)
        return True

    def _run_migration_with_retries(self, record: MigrationRecord, service: ServiceModel) -> None:
        """Execute migrate + health-check attempts up to record.max_attempts, then rollback on final failure."""
        last_error: Optional[str] = None
        last_failure_state = MigrationState.MIGRATION_FAILED

        for attempt_number in range(1, record.max_attempts + 1):
            attempt = MigrationAttempt(attempt_number=attempt_number)
            record.state = MigrationState.MIGRATING
            record.updated_at = datetime.utcnow()
            self._persist(record)
            logger.info(
                f"Migration attempt {attempt_number}/{record.max_attempts} for '{service.id}'"
            )

            try:
                self.provider.migrate(service)
            except MigrationExecutionError as e:
                attempt.success = False
                attempt.error = str(e)
                attempt.completed_at = datetime.utcnow()
                record.attempts.append(attempt)
                record.updated_at = datetime.utcnow()
                self._persist(record)
                last_error, last_failure_state = str(e), MigrationState.MIGRATION_FAILED
                logger.warning(
                    f"Migration attempt {attempt_number} failed for '{service.id}': {e}"
                )
                continue

            record.state = MigrationState.HEALTH_CHECK
            record.updated_at = datetime.utcnow()
            self._persist(record)
            health_result = self.health_checker.check_service(service)
            attempt.completed_at = datetime.utcnow()

            if health_result.status == HealthStatus.HEALTHY:
                attempt.success = True
                record.attempts.append(attempt)
                record.state = MigrationState.COMPLETED
                record.error = None
                record.completed_at = datetime.utcnow()
                record.updated_at = datetime.utcnow()
                self._persist(record)
                logger.info(f"Migration completed for '{service.id}'")
                return

            attempt.success = False
            attempt.error = health_result.error or (
                f"Health check reported status '{health_result.status.value}'"
            )
            record.attempts.append(attempt)
            record.updated_at = datetime.utcnow()
            self._persist(record)
            last_error, last_failure_state = attempt.error, MigrationState.HEALTH_CHECK_FAILED
            logger.warning(
                f"Post-migration health check failed on attempt {attempt_number} "
                f"for '{service.id}': {attempt.error}"
            )

        record.state = last_failure_state
        record.error = last_error
        record.updated_at = datetime.utcnow()
        self._persist(record)
        logger.error(
            f"Migration failed for '{service.id}' after {record.max_attempts} attempt(s): {last_error}"
        )

        self._execute_rollback(record, service)

    def _execute_rollback(self, record: MigrationRecord, service: ServiceModel) -> None:
        """Run the rollback workflow after a final migration failure."""
        record.rollback = RollbackInfo(attempted=True, started_at=datetime.utcnow())
        record.updated_at = datetime.utcnow()
        self._persist(record)
        logger.info(f"Executing rollback for '{service.id}'")

        try:
            self.provider.rollback(service)
        except Exception as e:
            record.rollback.succeeded = False
            record.rollback.error = str(e)
            record.rollback.completed_at = datetime.utcnow()
            record.updated_at = datetime.utcnow()
            self._persist(record)
            # Preserve the original failure state; rollback did not resolve it.
            logger.error(f"Rollback failed for '{service.id}': {e}")
            return

        record.rollback.succeeded = True
        record.rollback.completed_at = datetime.utcnow()
        record.state = MigrationState.ROLLED_BACK
        record.updated_at = datetime.utcnow()
        self._persist(record)
        logger.info(f"Rollback succeeded for '{service.id}'")


# Global migration orchestrator instance
_orchestrator: Optional[MigrationOrchestrator] = None


def get_migration_orchestrator() -> MigrationOrchestrator:
    """
    Get or create the global migration orchestrator instance.

    The default SimulatedMigrationProvider/SimulatedHealthChecker are
    configured from settings.SIMULATE_*_FAILURES (unset by default), so a
    migration or health-check failure can be demonstrated deterministically
    via environment variables alone - no code change and no edit to
    config/services.yaml. This only affects this default singleton;
    explicit dependency injection (as used throughout the test suite)
    is unaffected.

    Returns:
        The MigrationOrchestrator instance.
    """
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MigrationOrchestrator(
            provider=SimulatedMigrationProvider(
                always_fail_service_ids=settings.get_simulated_migration_failure_ids(),
                always_fail_rollback_service_ids=settings.get_simulated_rollback_failure_ids(),
            ),
            health_checker=SimulatedHealthChecker(
                always_fail_service_ids=settings.get_simulated_health_check_failure_ids(),
            ),
        )
    return _orchestrator
