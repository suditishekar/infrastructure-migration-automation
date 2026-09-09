"""
Tests for the Phase 4 MigrationRepository (SQLAlchemy/SQLite persistence).

Every test uses its own isolated in-memory SQLite database - never the
real app.db file - so these tests never touch disk or leave state behind.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import sessionmaker

from app.database.session import create_sqlite_engine, init_db
from app.schemas.migration import MigrationAttempt, MigrationRecord, MigrationState, RollbackInfo
from app.services.migration_repository import MigrationRepository


def make_session_factory():
    engine = create_sqlite_engine("sqlite:///:memory:")
    init_db(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def make_record(migration_id="mig-1", service_id="auth-service", state=MigrationState.COMPLETED, attempts=None, rollback=None):
    now = datetime.utcnow()
    return MigrationRecord(
        migration_id=migration_id,
        service_id=service_id,
        service_name=f"{service_id} name",
        state=state,
        created_at=now,
        updated_at=now,
        completed_at=now if state == MigrationState.COMPLETED else None,
        max_attempts=3,
        attempts=attempts or [],
        rollback=rollback,
    )


def test_save_and_get_by_migration_id_round_trips():
    repo = MigrationRepository(session_factory=make_session_factory())
    record = make_record()

    repo.save(record)
    fetched = repo.get_by_migration_id(record.migration_id)

    assert fetched is not None
    assert fetched.migration_id == record.migration_id
    assert fetched.service_id == record.service_id
    assert fetched.service_name == record.service_name
    assert fetched.state == MigrationState.COMPLETED
    assert fetched.max_attempts == 3


def test_get_by_migration_id_missing_returns_none():
    repo = MigrationRepository(session_factory=make_session_factory())

    assert repo.get_by_migration_id("does-not-exist") is None


def test_attempts_are_persisted_and_ordered():
    attempts = [
        MigrationAttempt(attempt_number=1, success=False, error="first failure"),
        MigrationAttempt(attempt_number=2, success=False, error="second failure"),
        MigrationAttempt(attempt_number=3, success=True),
    ]
    record = make_record(state=MigrationState.COMPLETED, attempts=attempts)
    repo = MigrationRepository(session_factory=make_session_factory())

    repo.save(record)
    fetched = repo.get_by_migration_id(record.migration_id)

    assert len(fetched.attempts) == 3
    assert [a.attempt_number for a in fetched.attempts] == [1, 2, 3]
    assert fetched.attempts[0].error == "first failure"
    assert fetched.attempts[2].success is True


def test_rollback_info_is_persisted():
    rollback = RollbackInfo(attempted=True, succeeded=False, error="rollback boom")
    record = make_record(state=MigrationState.MIGRATION_FAILED, rollback=rollback)
    repo = MigrationRepository(session_factory=make_session_factory())

    repo.save(record)
    fetched = repo.get_by_migration_id(record.migration_id)

    assert fetched.rollback is not None
    assert fetched.rollback.attempted is True
    assert fetched.rollback.succeeded is False
    assert fetched.rollback.error == "rollback boom"


def test_save_updates_existing_record_and_replaces_attempts():
    repo = MigrationRepository(session_factory=make_session_factory())
    record = make_record(
        state=MigrationState.MIGRATING,
        attempts=[MigrationAttempt(attempt_number=1, success=False, error="attempt 1 failed")],
    )
    repo.save(record)

    # Simulate the orchestrator re-saving the same migration_id with an
    # updated state and a full, updated attempts list.
    record.state = MigrationState.COMPLETED
    record.attempts = [
        MigrationAttempt(attempt_number=1, success=False, error="attempt 1 failed"),
        MigrationAttempt(attempt_number=2, success=True),
    ]
    repo.save(record)

    fetched = repo.get_by_migration_id(record.migration_id)
    assert fetched.state == MigrationState.COMPLETED
    assert len(fetched.attempts) == 2


def test_get_by_service_id_returns_latest_record():
    repo = MigrationRepository(session_factory=make_session_factory())
    older = make_record(migration_id="mig-old", service_id="auth-service")
    older.created_at = datetime.utcnow() - timedelta(hours=1)
    newer = make_record(migration_id="mig-new", service_id="auth-service")
    newer.created_at = datetime.utcnow()

    repo.save(older)
    repo.save(newer)

    fetched = repo.get_by_service_id("auth-service")
    assert fetched.migration_id == "mig-new"


def test_list_all_returns_every_record():
    repo = MigrationRepository(session_factory=make_session_factory())
    repo.save(make_record(migration_id="mig-1", service_id="auth-service"))
    repo.save(make_record(migration_id="mig-2", service_id="database-service"))

    records = repo.list_all()

    assert {r.migration_id for r in records} == {"mig-1", "mig-2"}


def test_migration_record_survives_repository_object_recreation():
    """
    The same underlying database must retain a saved record even when the
    MigrationRepository (and the session it uses) is a brand-new object -
    the persistence-survives-restart requirement, without needing to
    spawn a real separate process.
    """
    session_factory = make_session_factory()
    record = make_record(state=MigrationState.COMPLETED)

    first_repo = MigrationRepository(session_factory=session_factory)
    first_repo.save(record)
    del first_repo  # simulate the repository object going away

    second_repo = MigrationRepository(session_factory=session_factory)
    fetched = second_repo.get_by_migration_id(record.migration_id)

    assert fetched is not None
    assert fetched.state == MigrationState.COMPLETED
    assert fetched.service_id == record.service_id
