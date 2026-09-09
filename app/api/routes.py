"""
API routes for the infrastructure migration system.

This module defines all REST API endpoints for accessing application health,
service inventory, service details, and pre-migration validation.
"""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status

from app.core.exceptions import ServiceNotFoundError
from app.core.logging import get_logger
from app.schemas import ServiceModel
from app.schemas.health import HealthCheckSummary
from app.schemas.metrics import MigrationMetrics
from app.schemas.migration import MigrationRecord
from app.schemas.reports import FailureReport, MigrationReport
from app.schemas.validation import PreMigrationValidationResult
from app.services.health_check import get_health_check_service
from app.services.inventory import get_inventory_loader
from app.services.metrics_service import get_metrics_service
from app.services.migration_orchestrator import get_migration_orchestrator
from app.services.pre_migration_validator import get_validator
from app.services.reporting_service import get_reporting_service

logger = get_logger("api.routes")

router = APIRouter()


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    tags=["health"],
    summary="Health Check",
    description="Returns the health status of the infrastructure migration service.",
)
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint.

    Returns:
        JSON response indicating the health status of the application.
    """
    logger.debug("Health check requested")
    return {
        "status": "healthy",
        "service": "infrastructure-migration",
        "version": "0.1.0",
    }


@router.get(
    "/services",
    status_code=status.HTTP_200_OK,
    tags=["services"],
    summary="List All Services",
    description="Returns a list of all services in the inventory.",
)
async def list_services() -> Dict[str, Any]:
    """
    Get all services from the inventory.

    Returns:
        JSON response containing all services and metadata.
    """
    try:
        inventory = get_inventory_loader()
        services = inventory.get_all_services_list()
        logger.info(f"Listing all services ({len(services)} total)")
        return {
            "total": len(services),
            "services": [service.model_dump() for service in services],
        }
    except Exception as e:
        logger.error(f"Error listing services: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve services",
        )


@router.get(
    "/services/{service_id}",
    status_code=status.HTTP_200_OK,
    tags=["services"],
    summary="Get Service Details",
    description="Returns detailed information about a specific service.",
)
async def get_service(service_id: str) -> Dict[str, Any]:
    """
    Get a specific service by ID.

    Args:
        service_id: The unique service identifier.

    Returns:
        JSON response containing the service details.

    Raises:
        HTTPException: If the service is not found (404).
    """
    try:
        inventory = get_inventory_loader()
        service = inventory.get_service(service_id)
        logger.info(f"Retrieved service details for {service_id}")
        return {
            "service": service.model_dump(),
        }
    except Exception as e:
        logger.warning(f"Service not found: {service_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_id}' not found",
        )


@router.post(
    "/validation/pre-migration",
    status_code=status.HTTP_200_OK,
    tags=["validation"],
    summary="Pre-Migration Validation",
    description="Performs static pre-migration validation of the service inventory.",
    response_model=PreMigrationValidationResult,
)
async def validate_pre_migration() -> PreMigrationValidationResult:
    """
    Perform pre-migration validation of the service inventory.

    Validates:
    - Service configuration readiness
    - Dependency references (all dependencies exist)
    - Circular dependency detection
    - Environment consistency

    Returns:
        PreMigrationValidationResult with validation status and issues

    Raises:
        HTTPException: If validation fails unexpectedly (500)
    """
    try:
        logger.info("Pre-migration validation endpoint invoked")
        validator = get_validator()
        result = validator.validate()
        logger.info(f"Pre-migration validation completed: ready={result.ready}")
        return result
    except Exception as e:
        logger.error(f"Pre-migration validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Pre-migration validation failed",
        )


@router.post(
    "/health/check",
    status_code=status.HTTP_200_OK,
    tags=["health-check"],
    summary="Run Service Health Checks",
    description="Performs active HTTP health checks against every configured service's health endpoint.",
    response_model=HealthCheckSummary,
)
async def run_health_checks() -> HealthCheckSummary:
    """
    Perform active health checks across all services in the inventory.

    Probes each configured service's health endpoint over HTTP with a
    bounded timeout. Connection errors, timeouts, and invalid responses
    are captured per-service rather than raised.

    Returns:
        HealthCheckSummary with per-service results and aggregate counts.

    Raises:
        HTTPException: If the health check run fails unexpectedly (500)
    """
    try:
        logger.info("Health check endpoint invoked")
        health_service = get_health_check_service()
        result = health_service.check_all()
        logger.info(
            f"Health check run completed: {result.healthy_count}/{result.total_services} healthy"
        )
        return result
    except Exception as e:
        logger.error(f"Health check run failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Health check run failed",
        )


@router.post(
    "/migrations/{service_id}",
    status_code=status.HTTP_200_OK,
    tags=["migrations"],
    summary="Migrate Service",
    description=(
        "Initiates the migration workflow for a single service: pre-migration validation, "
        "dependency readiness, a simulated migration with retries, a post-migration health "
        "check, and rollback on final failure. Already-completed migrations are returned "
        "as-is without re-executing."
    ),
    response_model=MigrationRecord,
)
async def migrate_service(service_id: str) -> MigrationRecord:
    """
    Initiate (or return the existing result of) a service migration.

    Returns:
        MigrationRecord describing the resulting migration state.

    Raises:
        HTTPException: 404 if the service does not exist, 500 on unexpected errors.
    """
    try:
        orchestrator = get_migration_orchestrator()
        record = orchestrator.migrate_service(service_id)
        logger.info(f"Migration request for '{service_id}' resulted in state={record.state}")
        return record
    except ServiceNotFoundError:
        logger.warning(f"Migration requested for unknown service: {service_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service_id}' not found",
        )
    except Exception as e:
        logger.error(f"Migration failed unexpectedly for '{service_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Migration failed unexpectedly",
        )


@router.get(
    "/migrations",
    status_code=status.HTTP_200_OK,
    tags=["migrations"],
    summary="List Migrations",
    description="Returns all migration records tracked by the in-memory orchestration state.",
)
async def list_migrations() -> Dict[str, Any]:
    """
    List all migration records.

    Returns:
        JSON response containing all tracked migration records.
    """
    orchestrator = get_migration_orchestrator()
    migrations = orchestrator.list_migrations()
    logger.info(f"Listing all migrations ({len(migrations)} total)")
    return {
        "total": len(migrations),
        "migrations": [m.model_dump() for m in migrations],
    }


@router.get(
    "/migrations/{migration_id}",
    status_code=status.HTTP_200_OK,
    tags=["migrations"],
    summary="Get Migration Details",
    description="Returns the migration record for a specific migration ID.",
)
async def get_migration(migration_id: str) -> Dict[str, Any]:
    """
    Get a specific migration record by migration ID.

    Returns:
        JSON response containing the migration record.

    Raises:
        HTTPException: If the migration record is not found (404).
    """
    orchestrator = get_migration_orchestrator()
    record = orchestrator.get_migration(migration_id)
    if record is None:
        logger.warning(f"Migration not found: {migration_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Migration '{migration_id}' not found",
        )
    logger.info(f"Retrieved migration details for {migration_id}")
    return {"migration": record.model_dump()}


@router.get(
    "/metrics",
    status_code=status.HTTP_200_OK,
    tags=["metrics"],
    summary="Migration Metrics",
    description="Returns aggregate migration metrics derived from persisted migration records.",
    response_model=MigrationMetrics,
)
async def get_metrics() -> MigrationMetrics:
    """
    Compute aggregate migration metrics from persisted migration records.

    Returns:
        MigrationMetrics with counts, success rate, and average duration.

    Raises:
        HTTPException: If metrics computation fails unexpectedly (500)
    """
    try:
        metrics_service = get_metrics_service()
        metrics = metrics_service.compute_metrics()
        logger.info(
            f"Metrics computed: total={metrics.total_migrations}, "
            f"completed={metrics.completed_migrations}, failures={metrics.failure_count}"
        )
        return metrics
    except Exception as e:
        logger.error(f"Failed to compute metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute metrics",
        )


@router.get(
    "/reports/migrations",
    status_code=status.HTTP_200_OK,
    tags=["reports"],
    summary="Migration Report",
    description="Returns an aggregate report summarizing all persisted migration records.",
    response_model=MigrationReport,
)
async def get_migration_report() -> MigrationReport:
    """
    Build an aggregate report over all persisted migration records.

    Returns:
        MigrationReport with a per-migration summary.

    Raises:
        HTTPException: If report generation fails unexpectedly (500)
    """
    try:
        reporting_service = get_reporting_service()
        report = reporting_service.build_migration_report()
        logger.info(f"Migration report generated: {report.total} record(s)")
        return report
    except Exception as e:
        logger.error(f"Failed to build migration report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build migration report",
        )


@router.get(
    "/reports/failures",
    status_code=status.HTTP_200_OK,
    tags=["reports"],
    summary="Failure Report",
    description="Returns details of failed and rolled-back migrations, including attempts and rollback outcome.",
    response_model=FailureReport,
)
async def get_failure_report() -> FailureReport:
    """
    Build a report covering failed and rolled-back migrations.

    Returns:
        FailureReport with per-migration error, attempt, and rollback detail.

    Raises:
        HTTPException: If report generation fails unexpectedly (500)
    """
    try:
        reporting_service = get_reporting_service()
        report = reporting_service.build_failure_report()
        logger.info(f"Failure report generated: {report.total} record(s)")
        return report
    except Exception as e:
        logger.error(f"Failed to build failure report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build failure report",
        )
