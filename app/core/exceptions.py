"""
Custom exceptions for the infrastructure migration system.

This module defines domain-specific exceptions to provide clear error handling
throughout the application.
"""


class InfrastructureException(Exception):
    """Base exception for all infrastructure migration system errors."""
    pass


class InventoryException(InfrastructureException):
    """Base exception for inventory-related errors."""
    pass


class InventoryFileNotFoundError(InventoryException):
    """Raised when the inventory configuration file cannot be found."""
    pass


class InventoryParseError(InventoryException):
    """Raised when the inventory YAML file cannot be parsed."""
    pass


class InventoryValidationError(InventoryException):
    """Raised when inventory configuration fails Pydantic validation."""
    pass


class ServiceNotFoundError(InventoryException):
    """Raised when a requested service is not found in the inventory."""
    pass


class ServiceConfigurationError(InventoryException):
    """Raised when service configuration is invalid or incomplete."""
    pass


class DuplicateServiceError(InventoryException):
    """Raised when duplicate service IDs are detected in the inventory."""
    pass


class MigrationException(InfrastructureException):
    """Base exception for migration orchestration errors."""
    pass


class InvalidDependencyGraphError(MigrationException):
    """Raised when the dependency graph cannot be ordered for migration (missing or circular dependencies)."""
    pass


class MigrationExecutionError(MigrationException):
    """Raised by a migration provider when a migration attempt fails."""
    pass


class RollbackError(MigrationException):
    """Raised by a migration provider when a rollback attempt fails."""
    pass
