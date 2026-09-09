"""
Migration orchestration models and data structures.

Defines the structured models for Phase 3 core migration orchestration:
migration state, per-attempt records, rollback outcome, and the overall
migration record returned by the orchestrator and exposed via the API.
"""

from enum import Enum
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field


class MigrationState(str, Enum):
    """Lifecycle states of a single service's migration."""
    DISCOVERED = "discovered"
    VALIDATING = "validating"
    READY = "ready"
    MIGRATING = "migrating"
    HEALTH_CHECK = "health_check"
    COMPLETED = "completed"
    VALIDATION_FAILED = "validation_failed"
    MIGRATION_FAILED = "migration_failed"
    HEALTH_CHECK_FAILED = "health_check_failed"
    ROLLED_BACK = "rolled_back"


class MigrationAttempt(BaseModel):
    """A single migration attempt (migrate step + post-migration health check)."""

    attempt_number: int = Field(
        ...,
        description="1-indexed attempt number",
        ge=1
    )
    started_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the attempt started"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When the attempt finished"
    )
    success: Optional[bool] = Field(
        default=None,
        description="Whether this attempt succeeded"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if the attempt failed"
    )

    class Config:
        populate_by_name = True


class RollbackInfo(BaseModel):
    """Outcome of a rollback attempt following a failed migration."""

    attempted: bool = Field(
        default=False,
        description="Whether rollback was attempted"
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description="When rollback started"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When rollback finished"
    )
    succeeded: Optional[bool] = Field(
        default=None,
        description="Whether rollback succeeded"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if rollback failed"
    )

    class Config:
        populate_by_name = True


class MigrationRecord(BaseModel):
    """Complete migration state/result for a single service."""

    migration_id: str = Field(
        ...,
        description="Unique identifier for this service's migration record"
    )
    service_id: str = Field(
        ...,
        description="Service ID being migrated"
    )
    service_name: str = Field(
        ...,
        description="Human-readable service name"
    )
    state: MigrationState = Field(
        ...,
        description="Current migration state"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the migration record was first created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the migration record was last updated"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When the migration reached COMPLETED"
    )
    max_attempts: int = Field(
        ...,
        description="Maximum migration attempts allowed (1 + configured retries)",
        ge=1
    )
    attempts: List[MigrationAttempt] = Field(
        default_factory=list,
        description="Migration attempts made during the current run"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message for the current failure state, if any"
    )
    rollback: Optional[RollbackInfo] = Field(
        default=None,
        description="Rollback outcome, if rollback was executed"
    )

    class Config:
        populate_by_name = True
