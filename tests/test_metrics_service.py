"""
Tests for the Phase 4 MetricsService, computed from persisted migration
records via an isolated in-memory SQLite-backed MigrationRepository.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import sessionmaker

from app.database.session import create_sqlite_engine, init_db
from app.schemas.migration import MigrationAttempt, MigrationRecord, MigrationState
from app.services.metrics_service import MetricsService
from app.services.migration_repository import MigrationRepository


def make_repository():
    engine = create_sqlite_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return MigrationRepository(session_factory=session_factory)


def make_record(migration_id, service_id, state, attempts=None, duration_seconds=None):
    created_at = datetime.utcnow()
    completed_at = None
    if state == MigrationState.COMPLETED:
        completed_at = created_at + timedelta(seconds=duration_seconds or 0)
    return MigrationRecord(
        migration_id=migration_id,
        service_id=service_id,
        service_name=f"{service_id} name",
        state=state,
        created_at=created_at,
        updated_at=created_at,
        completed_at=completed_at,
        max_attempts=3,
        attempts=attempts or [],
    )


def test_metrics_on_empty_repository_are_all_zero():
    repo = make_repository()
    metrics = MetricsService(repository=repo).compute_metrics()

    assert metrics.total_migrations == 0
    assert metrics.completed_migrations == 0
    assert metrics.failed_migrations == 0
    assert metrics.rolled_back_migrations == 0
    assert metrics.failure_count == 0
    assert metrics.in_progress_migrations == 0
    assert metrics.total_attempts == 0
    assert metrics.success_rate == 0.0
    assert metrics.average_migration_duration_seconds is None


def test_metrics_counts_mixed_outcomes_correctly():
    repo = make_repository()

    repo.save(make_record("mig-1", "auth-service", MigrationState.COMPLETED, attempts=[
        MigrationAttempt(attempt_number=1, success=True),
    ], duration_seconds=10))
    repo.save(make_record("mig-2", "database-service", MigrationState.COMPLETED, attempts=[
        MigrationAttempt(attempt_number=1, success=True),
    ], duration_seconds=20))
    repo.save(make_record("mig-3", "payment-service", MigrationState.MIGRATION_FAILED, attempts=[
        MigrationAttempt(attempt_number=1, success=False),
        MigrationAttempt(attempt_number=2, success=False),
    ]))
    repo.save(make_record("mig-4", "cache-service", MigrationState.ROLLED_BACK, attempts=[
        MigrationAttempt(attempt_number=1, success=False),
    ]))
    repo.save(make_record("mig-5", "message-queue", MigrationState.MIGRATING))

    metrics = MetricsService(repository=repo).compute_metrics()

    assert metrics.total_migrations == 5
    assert metrics.completed_migrations == 2
    assert metrics.failed_migrations == 1
    assert metrics.rolled_back_migrations == 1
    assert metrics.failure_count == 2
    assert metrics.in_progress_migrations == 1
    # attempts: mig-1=1, mig-2=1, mig-3=2, mig-4=1, mig-5=0
    assert metrics.total_attempts == 5
    # completed / (completed + failure_count) = 2 / (2 + 2) = 0.5
    assert metrics.success_rate == 0.5
    # average of the two completed durations: (10 + 20) / 2 = 15
    assert metrics.average_migration_duration_seconds == 15.0


def test_metrics_average_duration_ignores_incomplete_migrations():
    repo = make_repository()
    repo.save(make_record("mig-1", "auth-service", MigrationState.COMPLETED, duration_seconds=5))
    repo.save(make_record("mig-2", "payment-service", MigrationState.VALIDATION_FAILED))

    metrics = MetricsService(repository=repo).compute_metrics()

    assert metrics.average_migration_duration_seconds == 5.0
