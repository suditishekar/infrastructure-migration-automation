"""
FastAPI application factory and startup/shutdown handlers.

This module creates and configures the FastAPI application instance,
sets up middleware, initializes services, and defines lifecycle events.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.api.routes import router as api_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.database.session import init_db
from app.services.inventory import initialize_inventory

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context manager.

    Handles startup and shutdown events for the FastAPI application.
    """
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    try:
        initialize_inventory()
        logger.info("Inventory initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize inventory: {e}")
        raise

    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.APP_NAME}")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    # Setup logging
    setup_logging()
    logger.info(f"Initializing {settings.APP_NAME}")

    # Create FastAPI app
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Configuration-driven service inventory and management system for infrastructure migration. Phase 1 focuses on service metadata loading, validation, and REST API access.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Include API routes
    app.include_router(api_router, prefix="/api", tags=["api"])

    # Custom exception handlers (can be extended later)
    @app.get("/", tags=["root"])
    async def root() -> dict:
        """Root endpoint."""
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "docs": "/docs",
        }

    logger.info(f"FastAPI application configured successfully")
    return app


# Create the application instance
app = create_app()
