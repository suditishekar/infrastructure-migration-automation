"""
Pydantic models for service inventory validation.

These models define the expected structure and validation rules for services
loaded from the inventory configuration file.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class ServiceModel(BaseModel):
    """Pydantic model for a service in the inventory."""

    id: str = Field(
        ...,
        description="Unique service identifier",
        min_length=1,
    )
    name: str = Field(
        ...,
        description="Human-readable service name",
        min_length=1,
    )
    host: str = Field(
        ...,
        description="Service host address or hostname",
        min_length=1,
    )
    port: int = Field(
        ...,
        description="Service port number",
        ge=1,
        le=65535,
    )
    source_environment: str = Field(
        ...,
        description="Source environment (e.g., legacy, prod, staging)",
        min_length=1,
    )
    target_environment: str = Field(
        ...,
        description="Target environment for migration",
        min_length=1,
    )
    health_endpoint: str = Field(
        ...,
        description="Health check endpoint path",
        min_length=1,
    )
    dependencies: List[str] = Field(
        default_factory=list,
        description="List of service IDs this service depends on",
    )
    service_type: Optional[str] = Field(
        default="application",
        description="Type of service (e.g., core, utility, infrastructure)",
    )
    criticality: Optional[str] = Field(
        default="medium",
        description="Criticality level (critical, high, medium, low)",
    )

    class Config:
        """Pydantic configuration."""
        # Allow population by field name
        populate_by_name = True
        # Use validation on assignment
        validate_assignment = True

    @field_validator("id")
    @classmethod
    def validate_service_id(cls, v: str) -> str:
        """Validate that service ID is a valid identifier."""
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Service ID must contain only alphanumeric characters, hyphens, or underscores")
        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port number is in valid range."""
        if v < 1 or v > 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("criticality")
    @classmethod
    def validate_criticality(cls, v: Optional[str]) -> Optional[str]:
        """Validate criticality level."""
        valid_levels = {"critical", "high", "medium", "low"}
        if v and v.lower() not in valid_levels:
            raise ValueError(f"Criticality must be one of {valid_levels}")
        return v.lower() if v else v

    @field_validator("dependencies")
    @classmethod
    def validate_dependencies(cls, v: List[str]) -> List[str]:
        """Validate dependencies is a list of strings."""
        if not isinstance(v, list):
            raise ValueError("Dependencies must be a list")
        if not all(isinstance(dep, str) for dep in v):
            raise ValueError("All dependencies must be strings")
        return v


class InventoryModel(BaseModel):
    """Pydantic model for the complete service inventory."""

    services: dict[str, ServiceModel] = Field(
        ...,
        description="Dictionary of services keyed by service ID",
    )

    class Config:
        """Pydantic configuration."""
        populate_by_name = True
        validate_assignment = True

    @field_validator("services")
    @classmethod
    def validate_services(cls, v: dict) -> dict:
        """Validate that services dictionary is not empty."""
        if not v:
            raise ValueError("Inventory must contain at least one service")
        return v
