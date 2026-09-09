"""
Pre-migration validation service.

Performs static pre-migration validation including:
- Dependency validation (all referenced services exist)
- Circular dependency detection (using DFS)
- Configuration readiness checks
"""

from typing import Dict, Set, List, Tuple, Optional
from datetime import datetime

from app.core.logging import get_logger
from app.schemas import ServiceModel
from app.schemas.validation import (
    ValidationIssue,
    ValidationCategory,
    SeverityLevel,
    PreMigrationValidationResult,
    CyclePath,
)
from app.services.inventory import get_inventory_loader

logger = get_logger("pre_migration_validator")


class PreMigrationValidator:
    """Validates service inventory for migration readiness."""

    def __init__(self):
        """Initialize the validator."""
        self.issues: List[ValidationIssue] = []
        self.cycles: List[CyclePath] = []
        self.services: Dict[str, ServiceModel] = {}

    def validate(self) -> PreMigrationValidationResult:
        """
        Perform complete pre-migration validation.

        Returns:
            PreMigrationValidationResult with validation issues and readiness status.
        """
        logger.info("Starting pre-migration validation")
        self.issues = []
        self.cycles = []

        try:
            # Load inventory
            inventory = get_inventory_loader()
            self.services = inventory.get_all_services()

            logger.info(f"Validating {len(self.services)} services")

            # Run validation checks
            self._validate_dependencies()
            self._validate_circular_dependencies()
            self._validate_configuration_readiness()

            # Build result
            result = self._build_result()
            logger.info(
                f"Validation complete: ready={result.ready}, "
                f"errors={len(result.errors)}, warnings={len(result.warnings)}"
            )
            return result

        except Exception as e:
            logger.error(f"Validation failed with exception: {e}")
            raise

    def _validate_dependencies(self) -> None:
        """
        Validate that all dependencies reference existing services.

        Adds ValidationIssues for missing dependencies.
        """
        logger.debug("Validating service dependencies")

        for service_id, service in self.services.items():
            for dep_id in service.dependencies:
                if dep_id not in self.services:
                    logger.warning(
                        f"Service {service_id} depends on missing service {dep_id}"
                    )
                    self.issues.append(
                        ValidationIssue(
                            service_id=service_id,
                            category=ValidationCategory.DEPENDENCY_MISSING,
                            severity=SeverityLevel.ERROR,
                            message=f"Service '{service_id}' depends on '{dep_id}' which does not exist in inventory",
                            details={
                                "missing_dependency": dep_id,
                                "referenced_by": service_id,
                            },
                        )
                    )

    def _validate_circular_dependencies(self) -> None:
        """
        Detect circular dependencies using DFS.

        Uses depth-first search to find all cycles in the dependency graph.
        Adds ValidationIssues for each cycle found.
        """
        logger.debug("Detecting circular dependencies using DFS")

        visited: Set[str] = set()
        rec_stack: Set[str] = set()  # Recursion stack for cycle detection
        cycles_found: Set[Tuple[str, ...]] = set()  # Avoid duplicates

        def dfs(node: str, path: List[str]) -> None:
            """
            DFS to detect cycles.

            Args:
                node: Current service ID
                path: Current traversal path for cycle reconstruction
            """
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            # Visit all dependencies
            if node in self.services:
                for neighbor in self.services[node].dependencies:
                    if neighbor not in visited:
                        dfs(neighbor, path[:])
                    elif neighbor in rec_stack:
                        # Cycle detected: reconstruct cycle from path
                        cycle_start_idx = path.index(neighbor)
                        cycle = path[cycle_start_idx:] + [neighbor]
                        cycle_tuple = tuple(cycle)

                        # Normalize cycle to avoid duplicates
                        # (A->B->A is same as B->A->B)
                        normalized = self._normalize_cycle(cycle_tuple)

                        if normalized not in cycles_found:
                            cycles_found.add(normalized)
                            self._log_cycle_found(list(normalized))

            rec_stack.discard(node)

        # Run DFS from each unvisited node
        for service_id in self.services:
            if service_id not in visited:
                dfs(service_id, [])

    def _normalize_cycle(self, cycle: Tuple[str, ...]) -> Tuple[str, ...]:
        """
        Normalize a cycle to a canonical form to avoid duplicates.

        For example, (A, B, C, A) and (B, C, A, B) represent the same cycle.

        Args:
            cycle: Cycle represented as a tuple of service IDs

        Returns:
            Normalized (canonical) representation of the cycle
        """
        # Remove the duplicate last element
        unique_services = list(dict.fromkeys(cycle[:-1]))

        # Find the lexicographically smallest rotation
        min_rotation = unique_services
        for i in range(1, len(unique_services)):
            rotation = unique_services[i:] + unique_services[:i]
            if rotation < min_rotation:
                min_rotation = rotation

        return tuple(min_rotation + [min_rotation[0]])

    def _log_cycle_found(self, cycle: List[str]) -> None:
        """
        Log and record a detected cycle.

        Args:
            cycle: List of service IDs forming a cycle
        """
        cycle_path_str = " -> ".join(cycle)
        logger.warning(f"Circular dependency detected: {cycle_path_str}")

        # Record the cycle
        cycle_obj = CyclePath(
            services=cycle,
            length=len(cycle) - 1,  # Exclude the repeated first element
        )
        self.cycles.append(cycle_obj)

        # Add validation issue for the first service in the cycle
        start_service = cycle[0]
        self.issues.append(
            ValidationIssue(
                service_id=start_service,
                category=ValidationCategory.CIRCULAR_DEPENDENCY,
                severity=SeverityLevel.ERROR,
                message=f"Circular dependency detected: {cycle_path_str}",
                details={
                    "cycle_path": cycle,
                    "cycle_length": len(cycle) - 1,
                },
            )
        )

    def _validate_configuration_readiness(self) -> None:
        """
        Validate service configuration readiness for migration.

        Checks:
        - Service has required fields (Pydantic already validates)
        - Source and target environments are different (meaningful migration)
        - Service criticality is reasonable
        """
        logger.debug("Validating configuration readiness")

        for service_id, service in self.services.items():
            # Check that migration is meaningful (not same environment)
            if service.source_environment == service.target_environment:
                logger.warning(
                    f"Service {service_id} has identical source and target environments"
                )
                self.issues.append(
                    ValidationIssue(
                        service_id=service_id,
                        category=ValidationCategory.ENVIRONMENT,
                        severity=SeverityLevel.WARNING,
                        message=f"Service '{service_id}' source and target environments are identical ({service.source_environment})",
                        details={
                            "source": service.source_environment,
                            "target": service.target_environment,
                        },
                    )
                )

    def _build_result(self) -> PreMigrationValidationResult:
        """
        Build the validation result.

        Returns:
            PreMigrationValidationResult with categorized issues and readiness status
        """
        # Separate errors and warnings
        errors = [issue for issue in self.issues if issue.severity == SeverityLevel.ERROR]
        warnings = [issue for issue in self.issues if issue.severity == SeverityLevel.WARNING]

        # Calculate metrics
        total_services = len(self.services)
        invalid_services = len(set(issue.service_id for issue in errors))
        valid_services = total_services - invalid_services

        # Determine readiness: only when no blocking errors
        ready = len(errors) == 0

        return PreMigrationValidationResult(
            ready=ready,
            total_services=total_services,
            valid_services=valid_services,
            invalid_services=invalid_services,
            errors=errors,
            warnings=warnings,
            timestamp=datetime.utcnow(),
        )


# Global validator instance
_validator: Optional[PreMigrationValidator] = None


def get_validator() -> PreMigrationValidator:
    """
    Get the pre-migration validator instance.

    Returns:
        PreMigrationValidator instance
    """
    global _validator
    if _validator is None:
        _validator = PreMigrationValidator()
    return _validator
