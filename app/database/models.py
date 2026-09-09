"""
SQLAlchemy ORM models for Phase 4 migration persistence.

These are pure storage models mapping to the migration_records and
migration_attempts tables. Conversion to/from the Pydantic domain models
in app.schemas.migration happens in the repository layer (see
app.services.migration_repository), not here.
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class MigrationRecordORM(Base):
    """Persisted migration record for a single service."""

    __tablename__ = "migration_records"

    migration_id = Column(String, primary_key=True)
    service_id = Column(String, nullable=False, index=True)
    service_name = Column(String, nullable=False)
    state = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    max_attempts = Column(Integer, nullable=False)
    error = Column(Text, nullable=True)

    # Rollback outcome is 1:1 with the record, so it is flattened onto
    # this table rather than given its own table.
    rollback_attempted = Column(Boolean, nullable=False, default=False)
    rollback_started_at = Column(DateTime, nullable=True)
    rollback_completed_at = Column(DateTime, nullable=True)
    rollback_succeeded = Column(Boolean, nullable=True)
    rollback_error = Column(Text, nullable=True)

    attempts = relationship(
        "MigrationAttemptORM",
        back_populates="migration",
        cascade="all, delete-orphan",
        order_by="MigrationAttemptORM.attempt_number",
    )


class MigrationAttemptORM(Base):
    """A single persisted migration attempt belonging to a migration record."""

    __tablename__ = "migration_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    migration_id = Column(
        String, ForeignKey("migration_records.migration_id"), nullable=False, index=True
    )
    attempt_number = Column(Integer, nullable=False)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    success = Column(Boolean, nullable=True)
    error = Column(Text, nullable=True)

    migration = relationship("MigrationRecordORM", back_populates="attempts")
