"""
Health check models and data structures.

Defines structured models for per-service health check results and the
aggregate health check summary returned by Phase 2B active probing.
"""

from enum import Enum
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    """Health status of a checked service."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"


class ServiceHealthResult(BaseModel):
    """Health check result for a single service."""

    service_id: str = Field(
        ...,
        description="Service ID that was checked"
    )
    service_name: str = Field(
        ...,
        description="Human-readable service name"
    )
    status: HealthStatus = Field(
        ...,
        description="Health status determined for the service"
    )
    http_status: Optional[int] = Field(
        default=None,
        description="HTTP status code returned by the health endpoint, if any"
    )
    latency_ms: Optional[float] = Field(
        default=None,
        description="Round-trip latency of the health check in milliseconds"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message when the service is unhealthy, unreachable, or timed out"
    )
    checked_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the health check was performed"
    )

    class Config:
        populate_by_name = True


class HealthCheckSummary(BaseModel):
    """Aggregate health check result across the service inventory."""

    total_services: int = Field(
        ...,
        description="Total number of services checked",
        ge=0
    )
    healthy_count: int = Field(
        ...,
        description="Number of services reporting healthy",
        ge=0
    )
    unhealthy_count: int = Field(
        ...,
        description="Number of services reporting unhealthy, unreachable, or timed out",
        ge=0
    )
    results: List[ServiceHealthResult] = Field(
        default_factory=list,
        description="Per-service health check results"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the health check run completed"
    )

    class Config:
        populate_by_name = True
