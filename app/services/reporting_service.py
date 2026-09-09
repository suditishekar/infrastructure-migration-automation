"""
Phase 4 migration reporting.

Builds aggregate and failure-focused reports from persisted migration
records via MigrationRepository, rather than duplicating persistence
access logic.
"""

from datetime import datetime
from typing import Optional

from app.core.logging import get_logger
from app.schemas.migration import MigrationState
from app.schemas.reports import (
    FailureReport,
    FailureReportEntry,
    MigrationReport,
    MigrationReportEntry,
)
from app.services.migration_repository import MigrationRepository, get_migration_repository

logger = get_logger("reporting_service")

_FAILURE_STATES = {
    MigrationState.VALIDATION_FAILED,
    MigrationState.MIGRATION_FAILED,
    MigrationState.HEALTH_CHECK_FAILED,
    MigrationState.ROLLED_BACK,
}


class ReportingService:
    """Builds migration and failure reports from persisted migration records."""

    def __init__(self, repository: Optional[MigrationRepository] = None):
        self.repository = repository or get_migration_repository()

    def build_migration_report(self) -> MigrationReport:
        """Build an aggregate report covering every persisted migration record."""
        records = self.repository.list_all()
        entries = [
            MigrationReportEntry(
                migration_id=r.migration_id,
                service_id=r.service_id,
                service_name=r.service_name,
                state=r.state,
                attempt_count=len(r.attempts),
                created_at=r.created_at,
                updated_at=r.updated_at,
                completed_at=r.completed_at,
                duration_seconds=(
                    round((r.completed_at - r.created_at).total_seconds(), 3)
                    if r.completed_at is not None
                    else None
                ),
                error=r.error,
            )
            for r in records
        ]
        logger.info(f"Built migration report with {len(entries)} entries")
        return MigrationReport(total=len(entries), generated_at=datetime.utcnow(), entries=entries)

    def build_failure_report(self) -> FailureReport:
        """Build a report covering only failed/rolled-back migrations, with attempts and rollback detail."""
        records = self.repository.list_all()
        failures = [r for r in records if r.state in _FAILURE_STATES]
        entries = [
            FailureReportEntry(
                migration_id=r.migration_id,
                service_id=r.service_id,
                service_name=r.service_name,
                state=r.state,
                error=r.error,
                attempts=r.attempts,
                rollback=r.rollback,
                updated_at=r.updated_at,
            )
            for r in failures
        ]
        logger.info(f"Built failure report with {len(entries)} entries")
        return FailureReport(total=len(entries), generated_at=datetime.utcnow(), entries=entries)


# Global reporting service instance
_reporting_service: Optional[ReportingService] = None


def get_reporting_service() -> ReportingService:
    """
    Get or create the global reporting service instance.

    Returns:
        The ReportingService instance.
    """
    global _reporting_service
    if _reporting_service is None:
        _reporting_service = ReportingService()
    return _reporting_service
