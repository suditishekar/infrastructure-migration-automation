"""
Service inventory loader and manager.

This module is responsible for loading, parsing, validating, and providing
access to the service inventory configuration. It acts as the bridge between
the YAML configuration and the application's business logic.
"""

from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import (
    DuplicateServiceError,
    InventoryFileNotFoundError,
    InventoryParseError,
    InventoryValidationError,
    ServiceNotFoundError,
)
from app.core.logging import get_logger
from app.schemas import InventoryModel, ServiceModel

logger = get_logger("inventory")


class InventoryLoader:
    """Loads and manages the service inventory."""

    def __init__(self, inventory_path: Optional[Path] = None):
        """
        Initialize the inventory loader.

        Args:
            inventory_path: Path to the services.yaml file.
                          Defaults to settings.INVENTORY_FILE if not provided.
        """
        self.inventory_path = inventory_path or settings.get_inventory_path()
        self._services: Dict[str, ServiceModel] = {}
        self._loaded = False

    def load(self) -> None:
        """
        Load and validate the service inventory.

        Raises:
            InventoryFileNotFoundError: If the inventory file does not exist.
            InventoryParseError: If the YAML file is malformed.
            InventoryValidationError: If the configuration fails validation.
            DuplicateServiceError: If duplicate service IDs are detected.
        """
        logger.info(f"Loading inventory from {self.inventory_path}")

        # Check file exists
        if not self.inventory_path.exists():
            logger.error(f"Inventory file not found: {self.inventory_path}")
            raise InventoryFileNotFoundError(
                f"Service inventory file not found: {self.inventory_path}"
            )

        # Parse YAML
        try:
            with open(self.inventory_path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f)
            logger.info("Inventory YAML parsed successfully")
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse inventory YAML: {e}")
            raise InventoryParseError(f"Failed to parse YAML: {e}")
        except Exception as e:
            logger.error(f"Error reading inventory file: {e}")
            raise InventoryParseError(f"Error reading inventory file: {e}")

        # Validate structure
        try:
            inventory = InventoryModel(**raw_data)
            logger.info(f"Inventory validation successful")
        except ValidationError as e:
            logger.error(f"Inventory validation failed: {e}")
            raise InventoryValidationError(
                f"Inventory configuration validation failed: {e}"
            )

        # Check for duplicates (additional check beyond Pydantic)
        service_ids = list(inventory.services.keys())
        if len(service_ids) != len(set(service_ids)):
            duplicates = [
                sid for sid in service_ids
                if service_ids.count(sid) > 1
            ]
            logger.error(f"Duplicate service IDs detected: {duplicates}")
            raise DuplicateServiceError(
                f"Duplicate service IDs found in inventory: {duplicates}"
            )

        # Store services
        self._services = inventory.services
        self._loaded = True
        logger.info(f"Inventory loaded successfully with {len(self._services)} services")

    def get_all_services(self) -> Dict[str, ServiceModel]:
        """
        Get all services from the inventory.

        Returns:
            Dictionary of all services keyed by service ID.

        Raises:
            RuntimeError: If inventory has not been loaded.
        """
        if not self._loaded:
            raise RuntimeError("Inventory has not been loaded. Call load() first.")
        return self._services.copy()

    def get_all_services_list(self) -> List[ServiceModel]:
        """
        Get all services as a list.

        Returns:
            List of all services in the inventory.

        Raises:
            RuntimeError: If inventory has not been loaded.
        """
        if not self._loaded:
            raise RuntimeError("Inventory has not been loaded. Call load() first.")
        return list(self._services.values())

    def get_service(self, service_id: str) -> ServiceModel:
        """
        Get a specific service by ID.

        Args:
            service_id: The unique service identifier.

        Returns:
            The ServiceModel for the requested service.

        Raises:
            RuntimeError: If inventory has not been loaded.
            ServiceNotFoundError: If the service does not exist in the inventory.
        """
        if not self._loaded:
            raise RuntimeError("Inventory has not been loaded. Call load() first.")

        if service_id not in self._services:
            logger.warning(f"Service not found: {service_id}")
            raise ServiceNotFoundError(
                f"Service '{service_id}' not found in inventory"
            )

        return self._services[service_id]

    def service_exists(self, service_id: str) -> bool:
        """
        Check if a service exists in the inventory.

        Args:
            service_id: The unique service identifier.

        Returns:
            True if the service exists, False otherwise.
        """
        if not self._loaded:
            return False
        return service_id in self._services

    def get_service_count(self) -> int:
        """Get the total number of services in the inventory."""
        if not self._loaded:
            return 0
        return len(self._services)


# Global inventory loader instance
_inventory_loader: Optional[InventoryLoader] = None


def get_inventory_loader() -> InventoryLoader:
    """
    Get or create the global inventory loader instance.

    This implements a simple singleton pattern for the inventory loader.

    Returns:
        The InventoryLoader instance.
    """
    global _inventory_loader
    if _inventory_loader is None:
        _inventory_loader = InventoryLoader()
        _inventory_loader.load()
    return _inventory_loader


def initialize_inventory() -> InventoryLoader:
    """
    Initialize the inventory loader.

    This function should be called during application startup.

    Returns:
        The InventoryLoader instance.

    Raises:
        InventoryFileNotFoundError: If the inventory file does not exist.
        InventoryParseError: If the YAML file is malformed.
        InventoryValidationError: If the configuration fails validation.
    """
    return get_inventory_loader()
