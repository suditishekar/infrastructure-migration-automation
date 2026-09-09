"""
Dependency-aware migration ordering.

Computes a migration order for a set of services such that every service's
dependencies precede it. Dependency-existence and circular-dependency
detection are delegated to Phase 2A's PreMigrationValidator (the same
DFS-based checks it already performs) instead of a second, independent
graph-validation implementation.
"""

from typing import Dict, List

from app.core.exceptions import InvalidDependencyGraphError
from app.core.logging import get_logger
from app.schemas import ServiceModel
from app.services.pre_migration_validator import PreMigrationValidator

logger = get_logger("migration_orderer")


def build_migration_order(services: Dict[str, ServiceModel]) -> List[str]:
    """
    Compute a dependency-aware migration order for the given services.

    Args:
        services: Services to order, keyed by service ID.

    Returns:
        Service IDs ordered so that every dependency precedes its dependent.

    Raises:
        InvalidDependencyGraphError: If the dependency graph has missing
            references or circular dependencies.
    """
    # Reuse PreMigrationValidator's existing dependency/cycle checks against
    # a fresh instance scoped to these services, rather than re-implementing
    # graph validation here.
    validator = PreMigrationValidator()
    validator.services = dict(services)
    validator._validate_dependencies()
    validator._validate_circular_dependencies()

    if validator.issues:
        messages = [issue.message for issue in validator.issues]
        logger.error(f"Cannot build migration order: {messages}")
        raise InvalidDependencyGraphError(
            "Service dependency graph is invalid for migration ordering: "
            + "; ".join(messages)
        )

    # Kahn's algorithm. Safe here: the checks above already confirmed the
    # dependency graph is acyclic and every reference resolves.
    in_degree = {service_id: 0 for service_id in services}
    dependents: Dict[str, List[str]] = {service_id: [] for service_id in services}

    for service_id, service in services.items():
        for dep_id in service.dependencies:
            dependents[dep_id].append(service_id)
            in_degree[service_id] += 1

    queue = sorted(sid for sid, degree in in_degree.items() if degree == 0)
    order: List[str] = []

    while queue:
        current = queue.pop(0)
        order.append(current)
        newly_ready = []
        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                newly_ready.append(dependent)
        queue = sorted(queue + newly_ready)

    if len(order) != len(services):
        # Should be unreachable: the validator checks above already ruled
        # out cycles and missing references.
        raise InvalidDependencyGraphError(
            "Unable to compute a complete migration order; unresolved dependency cycle"
        )

    logger.info(f"Computed dependency-aware migration order: {order}")
    return order
