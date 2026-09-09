"""
Phase 4 migration metrics.

Derives aggregate metrics from persisted migration records via
MigrationRepository, rather than duplicating persistence access logic.
"""

from typing import List, Optional

from app.core.logging import get_logger
from app.schemas.metrics import MigrationMetrics
from app.schemas.migration import MigrationRecord, MigrationState
from app.services.migration_repository import MigrationRepository, get_migration_repository

logger = get_logger("metrics_service")

# Terminal failure states where rollback either did not succeed or never ran.
_FAILED_STATES = {
    MigrationState.VALIDATION_FAILED,
    MigrationState.MIGRATION_FAILED,
    MigrationState.HEALTH_CHECK_FAILED,
}
_IN_PROGRESS_STATES = {
    MigrationState.DISCOVERED,
    MigrationState.VALIDATING,
    MigrationState.READY,
    MigrationState.MIGRATING,
    MigrationState.HEALTH_CHECK,
}


class MetricsService:
    """Computes migration metrics from persisted migration records."""

    def __init__(self, repository: Optional[MigrationRepository] = None):
        self.repository = repository or get_migration_repository()

    def compute_metrics(self) -> MigrationMetrics:
        """Compute aggregate metrics across all persisted migration records."""
        records = self.repository.list_all()
        return self._compute_from_records(records)

    @staticmethod
    def _compute_from_records(records: List[MigrationRecord]) -> MigrationMetrics:
        total = len(records)
        completed = sum(1 for r in records if r.state == MigrationState.COMPLETED)
        rolled_back = sum(1 for r in records if r.state == MigrationState.ROLLED_BACK)
        failed = sum(1 for r in records if r.state in _FAILED_STATES)
        in_progress = sum(1 for r in records if r.state in _IN_PROGRESS_STATES)
        total_attempts = sum(len(r.attempts) for r in records)

        failure_count = failed + rolled_back
        finished = completed + failure_count
        success_rate = (completed / finished) if finished else 0.0

        durations = [
            (r.completed_at - r.created_at).total_seconds()
            for r in records
            if r.state == MigrationState.COMPLETED and r.completed_at is not None
        ]
        average_duration = (sum(durations) / len(durations)) if durations else None

        return MigrationMetrics(
            total_migrations=total,
            completed_migrations=completed,
            failed_migrations=failed,
            rolled_back_migrations=rolled_back,
            failure_count=failure_count,
            in_progress_migrations=in_progress,
            total_attempts=total_attempts,
            success_rate=round(success_rate, 4),
            average_migration_duration_seconds=(
                round(average_duration, 3) if average_duration is not None else None
            ),
        )


# Global metrics service instance
_metrics_service: Optional[MetricsService] = None


def get_metrics_service() -> MetricsService:
    """
    Get or create the global metrics service instance.

    Returns:
        The MetricsService instance.
    """
    global _metrics_service
    if _metrics_service is None:
        _metrics_service = MetricsService()
    return _metrics_service
