"""
Logging configuration for the infrastructure migration system.

This module sets up structured logging with appropriate levels and handlers
for both development and production environments.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from app.core.config import settings


def setup_logging() -> None:
    """Configure logging for the application."""
    
    # Create logger
    logger = logging.getLogger("infra_migration")
    logger.setLevel(settings.LOG_LEVEL)
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Log format
    log_format = (
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    formatter = logging.Formatter(log_format)
    
    # Console handler (always enabled)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(settings.LOG_LEVEL)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (if configured)
    if settings.LOG_FILE:
        log_file = Path(settings.LOG_FILE)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(settings.LOG_LEVEL)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # Set level for uvicorn and other libraries
    logging.getLogger("uvicorn").setLevel(settings.LOG_LEVEL)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a specific module."""
    return logging.getLogger(f"infra_migration.{name}")
