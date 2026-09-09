"""
Phase 4 migration metrics models.

Defines the structured aggregate metrics computed from persisted migration
records (see app.services.metrics_service).
"""

from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field


class MigrationMetrics(BaseModel):
    """Aggregate migration metrics derived from persisted migration records."""

    total_migrations: int = Field(
        ...,
        description="Total number of migration records",
        ge=0
    )
    completed_migrations: int = Field(
        ...,
        description="Migrations that reached COMPLETED",
        ge=0
    )
    failed_migrations: int = Field(
        ...,
        description="Migrations in a terminal *_FAILED state (rollback did not succeed or was not applicable)",
        ge=0
    )
    rolled_back_migrations: int = Field(
        ...,
        description="Migrations that reached ROLLED_BACK (rollback succeeded)",
        ge=0
    )
    failure_count: int = Field(
        ...,
        description="Total unsuccessful terminal migrations (failed_migrations + rolled_back_migrations)",
        ge=0
    )
    in_progress_migrations: int = Field(
        ...,
        description="Migrations currently in a non-terminal state",
        ge=0
    )
    total_attempts: int = Field(
        ...,
        description="Total migration attempts recorded across all migrations",
        ge=0
    )
    success_rate: float = Field(
        ...,
        description="completed_migrations / (completed_migrations + failure_count), 0.0 if none finished",
        ge=0.0,
        le=1.0
    )
    average_migration_duration_seconds: Optional[float] = Field(
        default=None,
        description="Average duration (created_at to completed_at) across COMPLETED migrations, if any"
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When these metrics were computed"
    )

    class Config:
        populate_by_name = True
