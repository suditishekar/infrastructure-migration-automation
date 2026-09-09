"""
Tests for the Phase 4 ReportingService, built from persisted migration
records via an isolated in-memory SQLite-backed MigrationRepository.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import sessionmaker

from app.database.session import create_sqlite_engine, init_db
from app.schemas.migration import MigrationAttempt, MigrationRecord, MigrationState, RollbackInfo
from app.services.migration_repository import MigrationRepository
from app.services.reporting_service import ReportingService


def make_repository():
    engine = create_sqlite_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return MigrationRepository(session_factory=session_factory)


def make_record(migration_id, service_id, state, attempts=None, rollback=None, error=None, duration_seconds=None):
    created_at = datetime.utcnow()
    completed_at = created_at + timedelta(seconds=duration_seconds) if duration_seconds is not None else None
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
        error=error,
        rollback=rollback,
    )


def test_migration_report_includes_every_record_with_duration():
    repo = make_repository()
    repo.save(make_record("mig-1", "auth-service", MigrationState.COMPLETED, duration_seconds=12))
    repo.save(make_record("mig-2", "payment-service", MigrationState.VALIDATION_FAILED, error="bad dep"))

    report = ReportingService(repository=repo).build_migration_report()

    assert report.total == 2
    by_id = {entry.migration_id: entry for entry in report.entries}
    assert by_id["mig-1"].duration_seconds == 12.0
    assert by_id["mig-1"].state == MigrationState.COMPLETED
    assert by_id["mig-2"].duration_seconds is None
    assert by_id["mig-2"].error == "bad dep"


def test_migration_report_on_empty_repository_is_empty():
    repo = make_repository()

    report = ReportingService(repository=repo).build_migration_report()

    assert report.total == 0
    assert report.entries == []


def test_failure_report_includes_only_failed_and_rolled_back_migrations():
    repo = make_repository()
    repo.save(make_record("mig-1", "auth-service", MigrationState.COMPLETED))
    repo.save(make_record("mig-2", "payment-service", MigrationState.MIGRATING))
    repo.save(make_record(
        "mig-3", "database-service", MigrationState.MIGRATION_FAILED,
        attempts=[MigrationAttempt(attempt_number=1, success=False, error="boom")],
        error="boom",
    ))
    repo.save(make_record(
        "mig-4", "cache-service", MigrationState.ROLLED_BACK,
        rollback=RollbackInfo(attempted=True, succeeded=True),
        error="unhealthy",
    ))

    report = ReportingService(repository=repo).build_failure_report()

    assert report.total == 2
    ids = {entry.migration_id for entry in report.entries}
    assert ids == {"mig-3", "mig-4"}

    failed_entry = next(e for e in report.entries if e.migration_id == "mig-3")
    assert failed_entry.error == "boom"
    assert len(failed_entry.attempts) == 1

    rolled_back_entry = next(e for e in report.entries if e.migration_id == "mig-4")
    assert rolled_back_entry.rollback is not None
    assert rolled_back_entry.rollback.succeeded is True


def test_failure_report_excludes_successful_and_in_progress_migrations():
    repo = make_repository()
    repo.save(make_record("mig-1", "auth-service", MigrationState.COMPLETED))
    repo.save(make_record("mig-2", "payment-service", MigrationState.READY))

    report = ReportingService(repository=repo).build_failure_report()

    assert report.total == 0
