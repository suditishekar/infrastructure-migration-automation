"""
Migration persistence repository.

Translates between the Pydantic domain models in app.schemas.migration
(MigrationRecord, MigrationAttempt, RollbackInfo) and the SQLAlchemy ORM
rows in app.database.models, so the orchestrator, metrics, reporting, and
API layers never touch SQL or ORM objects directly.
"""

from typing import List, Optional

from sqlalchemy.orm import sessionmaker

from app.core.logging import get_logger
from app.database.models import MigrationAttemptORM, MigrationRecordORM
from app.database.session import SessionLocal
from app.schemas.migration import (
    MigrationAttempt,
    MigrationRecord,
    MigrationState,
    RollbackInfo,
)

logger = get_logger("migration_repository")


class MigrationRepository:
    """Repository for persisting and retrieving migration records."""

    def __init__(self, session_factory: Optional[sessionmaker] = None):
        """
        Initialize the repository.

        Args:
            session_factory: SQLAlchemy sessionmaker to use.
                              Defaults to the app-wide SessionLocal bound
                              to settings.DATABASE_URL.
        """
        self._session_factory = session_factory or SessionLocal

    def save(self, record: MigrationRecord) -> None:
        """
        Insert or update a migration record, its rollback info, and its
        full set of attempts.

        Args:
            record: The migration record to persist.
        """
        with self._session_factory() as session:
            orm_record = session.get(MigrationRecordORM, record.migration_id)
            if orm_record is None:
                orm_record = MigrationRecordORM(migration_id=record.migration_id)
                session.add(orm_record)

            orm_record.service_id = record.service_id
            orm_record.service_name = record.service_name
            orm_record.state = record.state.value
            orm_record.created_at = record.created_at
            orm_record.updated_at = record.updated_at
            orm_record.completed_at = record.completed_at
            orm_record.max_attempts = record.max_attempts
            orm_record.error = record.error

            if record.rollback:
                orm_record.rollback_attempted = record.rollback.attempted
                orm_record.rollback_started_at = record.rollback.started_at
                orm_record.rollback_completed_at = record.rollback.completed_at
                orm_record.rollback_succeeded = record.rollback.succeeded
                orm_record.rollback_error = record.rollback.error
            else:
                orm_record.rollback_attempted = False
                orm_record.rollback_started_at = None
                orm_record.rollback_completed_at = None
                orm_record.rollback_succeeded = None
                orm_record.rollback_error = None

            # The orchestrator always rebuilds the full attempts list for a
            # run rather than appending incrementally, so a full replace
            # here is the simplest correct way to keep attempts in sync.
            session.query(MigrationAttemptORM).filter_by(
                migration_id=record.migration_id
            ).delete()
            for attempt in record.attempts:
                session.add(
                    MigrationAttemptORM(
                        migration_id=record.migration_id,
                        attempt_number=attempt.attempt_number,
                        started_at=attempt.started_at,
                        completed_at=attempt.completed_at,
                        success=attempt.success,
                        error=attempt.error,
                    )
                )

            session.commit()

    def get_by_migration_id(self, migration_id: str) -> Optional[MigrationRecord]:
        """Look up a migration record by migration ID."""
        with self._session_factory() as session:
            orm_record = session.get(MigrationRecordORM, migration_id)
            if orm_record is None:
                return None
            return self._to_domain(orm_record)

    def get_by_service_id(self, service_id: str) -> Optional[MigrationRecord]:
        """Look up the (most recently created) migration record for a service."""
        with self._session_factory() as session:
            orm_record = (
                session.query(MigrationRecordORM)
                .filter_by(service_id=service_id)
                .order_by(MigrationRecordORM.created_at.desc())
                .first()
            )
            if orm_record is None:
                return None
            return self._to_domain(orm_record)

    def list_all(self) -> List[MigrationRecord]:
        """List all persisted migration records, oldest first."""
        with self._session_factory() as session:
            orm_records = (
                session.query(MigrationRecordORM)
                .order_by(MigrationRecordORM.created_at)
                .all()
            )
            return [self._to_domain(r) for r in orm_records]

    @staticmethod
    def _to_domain(orm_record: MigrationRecordORM) -> MigrationRecord:
        """Convert a persisted ORM row (with its attempts) into the domain model."""
        rollback = None
        if orm_record.rollback_attempted:
            rollback = RollbackInfo(
                attempted=orm_record.rollback_attempted,
                started_at=orm_record.rollback_started_at,
                completed_at=orm_record.rollback_completed_at,
                succeeded=orm_record.rollback_succeeded,
                error=orm_record.rollback_error,
            )

        attempts = [
            MigrationAttempt(
                attempt_number=a.attempt_number,
                started_at=a.started_at,
                completed_at=a.completed_at,
                success=a.success,
                error=a.error,
            )
            for a in sorted(orm_record.attempts, key=lambda a: a.attempt_number)
        ]

        return MigrationRecord(
            migration_id=orm_record.migration_id,
            service_id=orm_record.service_id,
            service_name=orm_record.service_name,
            state=MigrationState(orm_record.state),
            created_at=orm_record.created_at,
            updated_at=orm_record.updated_at,
            completed_at=orm_record.completed_at,
            max_attempts=orm_record.max_attempts,
            attempts=attempts,
            error=orm_record.error,
            rollback=rollback,
        )


# Global migration repository instance
_repository: Optional[MigrationRepository] = None


def get_migration_repository() -> MigrationRepository:
    """
    Get or create the global migration repository instance.

    Returns:
        The MigrationRepository instance.
    """
    global _repository
    if _repository is None:
        _repository = MigrationRepository()
    return _repository
