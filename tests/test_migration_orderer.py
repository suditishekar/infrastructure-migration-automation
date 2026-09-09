"""
Tests for Phase 3 dependency-aware migration ordering.

build_migration_order() delegates dependency-existence and circular-
dependency detection to Phase 2A's PreMigrationValidator; these tests
operate on in-memory ServiceModel fixtures and never touch
config/services.yaml.
"""

import pytest

from app.core.exceptions import InvalidDependencyGraphError
from app.schemas import ServiceModel
from app.services.migration_orderer import build_migration_order


def make_service(service_id, dependencies=None):
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


def test_dependencies_ordered_before_dependents():
    services = {
        "auth-service": make_service("auth-service"),
        "database-service": make_service("database-service"),
        "payment-service": make_service(
            "payment-service", dependencies=["auth-service", "database-service"]
        ),
    }

    order = build_migration_order(services)

    assert set(order) == set(services)
    assert order.index("auth-service") < order.index("payment-service")
    assert order.index("database-service") < order.index("payment-service")


def test_transitive_dependencies_are_respected():
    services = {
        "database-service": make_service("database-service"),
        "auth-service": make_service("auth-service", dependencies=["database-service"]),
        "payment-service": make_service("payment-service", dependencies=["auth-service"]),
    }

    order = build_migration_order(services)

    assert order == ["database-service", "auth-service", "payment-service"]


def test_circular_dependency_raises_invalid_graph_error():
    services = {
        "service-a": make_service("service-a", dependencies=["service-b"]),
        "service-b": make_service("service-b", dependencies=["service-a"]),
    }

    with pytest.raises(InvalidDependencyGraphError):
        build_migration_order(services)


def test_missing_dependency_reference_raises_invalid_graph_error():
    services = {
        "payment-service": make_service("payment-service", dependencies=["unknown-service"]),
    }

    with pytest.raises(InvalidDependencyGraphError):
        build_migration_order(services)
