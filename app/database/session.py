"""
Database engine/session setup for Phase 4 persistence.

Uses SQLite by default via settings.DATABASE_URL (same env-var-driven
configuration convention as every other setting in app.core.config).
Table creation is idempotent and safe to call multiple times.
"""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.database.models import Base


def create_sqlite_engine(database_url: str) -> Engine:
    """
    Create a SQLAlchemy engine for a SQLite URL.

    Uses StaticPool for in-memory databases so every session created from
    the engine shares the same connection - otherwise each connection
    would see its own empty, independent in-memory database. This also
    lets tests build isolated, disposable in-memory databases.
    """
    connect_args = {"check_same_thread": False}
    pool_kwargs = {"poolclass": StaticPool} if ":memory:" in database_url else {}
    return create_engine(database_url, connect_args=connect_args, **pool_kwargs)


# Global engine/session factory backing the application's configured database.
engine = create_sqlite_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db(bind_engine: Engine = None) -> None:
    """
    Create all tables if they do not already exist.

    Args:
        bind_engine: Engine to create tables against. Defaults to the
                     module-level `engine` bound to settings.DATABASE_URL.
    """
    Base.metadata.create_all(bind=bind_engine or engine)
