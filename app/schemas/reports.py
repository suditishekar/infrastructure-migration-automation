"""
Phase 4 migration reporting models.

Defines the structured reports built from persisted migration records
(see app.services.reporting_service). Reuses the existing MigrationState,
MigrationAttempt, and RollbackInfo models from app.schemas.migration
rather than duplicating them.
"""

from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.migration import MigrationAttempt, MigrationState, RollbackInfo


class MigrationReportEntry(BaseModel):
    """Summary of a single migration for the aggregate migration report."""

    migration_id: str = Field(..., description="Unique migration record identifier")
    service_id: str = Field(..., description="Service ID being migrated")
    service_name: str = Field(..., description="Human-readable service name")
    state: MigrationState = Field(..., description="Current migration state")
    attempt_count: int = Field(..., description="Number of migration attempts recorded", ge=0)
    created_at: datetime = Field(..., description="When the migration record was first created")
    updated_at: datetime = Field(..., description="When the migration record was last updated")
    completed_at: Optional[datetime] = Field(default=None, description="When the migration reached COMPLETED")
    duration_seconds: Optional[float] = Field(
        default=None, description="created_at to completed_at, if the migration completed"
    )
    error: Optional[str] = Field(default=None, description="Error message for the current failure state, if any")

    class Config:
        populate_by_name = True


class MigrationReport(BaseModel):
    """Aggregate report over all persisted migration records."""

    total: int = Field(..., description="Total number of migration records included", ge=0)
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="When this report was generated")
    entries: List[MigrationReportEntry] = Field(default_factory=list, description="Per-migration summaries")

    class Config:
        populate_by_name = True


class FailureReportEntry(BaseModel):
    """Detailed view of a single failed or rolled-back migration."""

    migration_id: str = Field(..., description="Unique migration record identifier")
    service_id: str = Field(..., description="Service ID being migrated")
    service_name: str = Field(..., description="Human-readable service name")
    state: MigrationState = Field(..., description="Terminal failure state (validation/migration/health-check failed, or rolled back)")
    error: Optional[str] = Field(default=None, description="Error message for the current failure state, if any")
    attempts: List[MigrationAttempt] = Field(default_factory=list, description="Migration attempts recorded for this run")
    rollback: Optional[RollbackInfo] = Field(default=None, description="Rollback outcome, if rollback was executed")
    updated_at: datetime = Field(..., description="When the migration record was last updated")

    class Config:
        populate_by_name = True


class FailureReport(BaseModel):
    """Report of failed and rolled-back migrations."""

    total: int = Field(..., description="Total number of failed/rolled-back migrations included", ge=0)
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="When this report was generated")
    entries: List[FailureReportEntry] = Field(default_factory=list, description="Per-migration failure details")

    class Config:
        populate_by_name = True
