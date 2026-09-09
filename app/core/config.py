"""
Application configuration handling.

This module manages application-level settings loaded from environment variables
and configuration files. It provides a centralized configuration object used
throughout the application.
"""

import os
from pathlib import Path
from typing import Optional


class Settings:
    """Application settings configuration class."""

    # Application metadata
    APP_NAME: str = "Infrastructure Migration & Monitoring Automation"
    APP_VERSION: str = "0.1.0"
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # API Configuration
    API_HOST: str = os.getenv("API_HOST", "127.0.0.1")
    API_PORT: int = int(os.getenv("API_PORT", 8000))
    API_DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    
    # Inventory Configuration
    INVENTORY_FILE: str = os.getenv(
        "INVENTORY_FILE",
        str(Path(__file__).parent.parent.parent / "config" / "services.yaml")
    )
    
    # Health Check Configuration
    HEALTH_CHECK_TIMEOUT: float = float(os.getenv("HEALTH_CHECK_TIMEOUT", "5.0"))

    # Migration Orchestration Configuration
    MIGRATION_MAX_RETRIES: int = int(os.getenv("MIGRATION_MAX_RETRIES", "2"))

    # Simulated failure injection (tests/local development only - leave unset
    # in production). Comma-separated service IDs; consumed by
    # get_migration_orchestrator() to configure the default
    # SimulatedMigrationProvider/SimulatedHealthChecker without touching
    # config/services.yaml or writing code.
    SIMULATE_MIGRATION_FAILURES: str = os.getenv("SIMULATE_MIGRATION_FAILURES", "")
    SIMULATE_ROLLBACK_FAILURES: str = os.getenv("SIMULATE_ROLLBACK_FAILURES", "")
    SIMULATE_HEALTH_CHECK_FAILURES: str = os.getenv("SIMULATE_HEALTH_CHECK_FAILURES", "")

    # Database Configuration (placeholder for future phases)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./app.db"
    )
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: Optional[str] = os.getenv("LOG_FILE", None)
    
    @classmethod
    def get_inventory_path(cls) -> Path:
        """Get the absolute path to the inventory file."""
        return Path(cls.INVENTORY_FILE).resolve()

    @staticmethod
    def _parse_service_id_set(value: str) -> set:
        """Parse a comma-separated list of service IDs from an env var."""
        return {item.strip() for item in value.split(",") if item.strip()}

    @classmethod
    def get_simulated_migration_failure_ids(cls) -> set:
        """Service IDs that should deterministically fail migration (SIMULATE_MIGRATION_FAILURES)."""
        return cls._parse_service_id_set(cls.SIMULATE_MIGRATION_FAILURES)

    @classmethod
    def get_simulated_rollback_failure_ids(cls) -> set:
        """Service IDs that should deterministically fail rollback (SIMULATE_ROLLBACK_FAILURES)."""
        return cls._parse_service_id_set(cls.SIMULATE_ROLLBACK_FAILURES)

    @classmethod
    def get_simulated_health_check_failure_ids(cls) -> set:
        """Service IDs that should deterministically fail the post-migration health check (SIMULATE_HEALTH_CHECK_FAILURES)."""
        return cls._parse_service_id_set(cls.SIMULATE_HEALTH_CHECK_FAILURES)

    @classmethod
    def is_development(cls) -> bool:
        """Check if running in development environment."""
        return cls.ENVIRONMENT.lower() in ("dev", "development", "local")
    
    @classmethod
    def is_production(cls) -> bool:
        """Check if running in production environment."""
        return cls.ENVIRONMENT.lower() == "production"


# Global settings instance
settings = Settings()
