"""
Pre-migration validation models and data structures.

Defines structured models for validation issues, severity levels, and validation results.
"""

from enum import Enum
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    """Severity levels for validation issues."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationCategory(str, Enum):
    """Categories of validation checks."""
    DEPENDENCY_MISSING = "dependency_missing"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    CONFIGURATION = "configuration"
    ENVIRONMENT = "environment"
    SERVICE_ID = "service_id"


class ValidationIssue(BaseModel):
    """Represents a single validation issue."""

    service_id: str = Field(
        ...,
        description="Service ID that failed validation"
    )
    category: ValidationCategory = Field(
        ...,
        description="Category of validation check"
    )
    severity: SeverityLevel = Field(
        ...,
        description="Severity level of the issue"
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
        min_length=1
    )
    details: Optional[dict] = Field(
        default=None,
        description="Additional details about the issue (e.g., missing dependencies, cycle path)"
    )

    class Config:
        populate_by_name = True


class PreMigrationValidationResult(BaseModel):
    """Complete pre-migration validation result."""

    ready: bool = Field(
        ...,
        description="Whether the inventory is ready for migration (no blocking errors)"
    )
    total_services: int = Field(
        ...,
        description="Total number of services in inventory",
        ge=0
    )
    valid_services: int = Field(
        ...,
        description="Number of services that passed validation",
        ge=0
    )
    invalid_services: int = Field(
        ...,
        description="Number of services with validation errors",
        ge=0
    )
    errors: List[ValidationIssue] = Field(
        default_factory=list,
        description="Validation errors (blocking issues)"
    )
    warnings: List[ValidationIssue] = Field(
        default_factory=list,
        description="Validation warnings (non-blocking issues)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When validation was performed"
    )

    class Config:
        populate_by_name = True


class CyclePath(BaseModel):
    """Represents a cycle in the dependency graph."""

    services: List[str] = Field(
        ...,
        description="Ordered list of service IDs forming a cycle (e.g., [A, B, C, A])"
    )
    length: int = Field(
        ...,
        description="Length of the cycle (number of unique services)",
        ge=2
    )

    class Config:
        populate_by_name = True
