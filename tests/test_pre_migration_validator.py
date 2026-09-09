"""
Tests for the Phase 2A pre-migration validator.

Covers the validator's primary failure cases: missing dependency references
and circular dependencies, plus the structured error/readiness contract.
Services are built in-memory and the inventory loader is monkeypatched, so
config/services.yaml is never read or modified.
"""

import pytest

from app.schemas import ServiceModel
from app.schemas.validation import SeverityLevel, ValidationCategory
from app.services.pre_migration_validator import PreMigrationValidator


def make_service(service_id, dependencies=None):
    """Build an in-memory ServiceModel fixture for validator tests."""
    return ServiceModel(
        id=service_id,
        name=f"{service_id} name",
        host=f"{service_id}.internal",
        port=8080,
        source_environment="legacy",
        target_environment="modern",
        health_endpoint="/health",
        dependencies=dependencies or [],
    )


class FakeInventoryLoader:
    """Stand-in for InventoryLoader exposing only what the validator uses."""

    def __init__(self, services):
        self._services = services

    def get_all_services(self):
        return dict(self._services)


def run_validation(monkeypatch, services):
    monkeypatch.setattr(
        "app.services.pre_migration_validator.get_inventory_loader",
        lambda: FakeInventoryLoader(services),
    )
    return PreMigrationValidator().validate()


def test_missing_dependency_reference_produces_structured_error(monkeypatch):
    services = {
        "payment-service": make_service("payment-service", dependencies=["unknown-service"]),
    }

    result = run_validation(monkeypatch, services)

    assert result.ready is False
    assert len(result.errors) == 1
    error = result.errors[0]
    assert error.service_id == "payment-service"
    assert error.category == ValidationCategory.DEPENDENCY_MISSING
    assert error.severity == SeverityLevel.ERROR
    assert error.details["missing_dependency"] == "unknown-service"


def test_circular_dependency_produces_structured_error(monkeypatch):
    services = {
        "service-a": make_service("service-a", dependencies=["service-b"]),
        "service-b": make_service("service-b", dependencies=["service-a"]),
    }

    result = run_validation(monkeypatch, services)

    assert result.ready is False
    circular_errors = [
        e for e in result.errors if e.category == ValidationCategory.CIRCULAR_DEPENDENCY
    ]
    assert len(circular_errors) == 1
    assert circular_errors[0].severity == SeverityLevel.ERROR
    assert "cycle_path" in circular_errors[0].details
    assert circular_errors[0].details["cycle_length"] == 2


def test_valid_configuration_remains_ready(monkeypatch):
    """Non-regression check: existing successful-validation behavior is unchanged."""
    services = {
        "auth-service": make_service("auth-service"),
        "payment-service": make_service("payment-service", dependencies=["auth-service"]),
    }

    result = run_validation(monkeypatch, services)

    assert result.ready is True
    assert result.errors == []
    assert result.total_services == 2
    assert result.valid_services == 2
    assert result.invalid_services == 0
