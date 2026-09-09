"""
Tests for the Phase 2A configuration-readiness failure case handled during
inventory loading: missing required service configuration fields.

Uses a temporary YAML fixture written to tmp_path; config/services.yaml is
never touched.
"""

import pytest

from app.core.exceptions import InventoryValidationError
from app.services.inventory import InventoryLoader
from app.services.pre_migration_validator import PreMigrationValidator

# Missing the required 'host' field.
INVALID_SERVICE_YAML = """
services:
  broken-service:
    id: broken-service
    name: Broken Service
    port: 8080
    source_environment: legacy
    target_environment: modern
    health_endpoint: /health
    dependencies: []
"""


def test_missing_required_field_raises_validation_error(tmp_path):
    config_file = tmp_path / "services.yaml"
    config_file.write_text(INVALID_SERVICE_YAML, encoding="utf-8")

    loader = InventoryLoader(inventory_path=config_file)

    with pytest.raises(InventoryValidationError):
        loader.load()


def test_missing_required_configuration_blocks_pre_migration_validation(monkeypatch, tmp_path):
    """
    Required fields (host, port, etc.) are enforced by Pydantic when the
    inventory loads, so a ServiceModel missing one can never exist in
    memory for the validator to see. Missing configuration therefore
    surfaces as a structured InventoryValidationError raised before a
    PreMigrationValidationResult can be built, rather than as a
    ready=False entry inside one. This confirms the pipeline fails closed
    (never reports readiness) for invalid configuration.
    """
    config_file = tmp_path / "services.yaml"
    config_file.write_text(INVALID_SERVICE_YAML, encoding="utf-8")
    broken_loader = InventoryLoader(inventory_path=config_file)

    def load_and_return():
        # Mirrors the real get_inventory_loader(), which always calls
        # load() before handing back the loader.
        broken_loader.load()
        return broken_loader

    monkeypatch.setattr(
        "app.services.pre_migration_validator.get_inventory_loader",
        load_and_return,
    )

    with pytest.raises(InventoryValidationError):
        PreMigrationValidator().validate()
