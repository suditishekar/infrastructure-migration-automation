"""
Focused tests for Phase 3 migration API route error-mapping behavior.

Route coroutine functions are called directly with asyncio.run (they are
plain async functions) rather than through a full FastAPI TestClient, so
no additional test-client dependency (httpx/pytest-asyncio) is required.
The orchestrator is faked at the route's call site so these tests exercise
only the route's own error-handling contract.
"""

import asyncio

import pytest
from fastapi import HTTPException

from app.api.routes import get_migration, list_migrations, migrate_service
from app.core.exceptions import ServiceNotFoundError
from app.schemas.migration import MigrationRecord, MigrationState


def make_record(service_id="auth-service", state=MigrationState.COMPLETED):
    return MigrationRecord(
        migration_id=f"mig-{service_id}",
        service_id=service_id,
        service_name=f"{service_id} name",
        state=state,
        max_attempts=1,
    )


class FakeOrchestrator:
    """Stand-in for MigrationOrchestrator, controllable per test."""

    def __init__(self, migrate_result=None, migrate_exception=None, migrations=None):
        self._migrate_result = migrate_result
        self._migrate_exception = migrate_exception
        self._migrations = migrations or {}

    def migrate_service(self, service_id):
        if self._migrate_exception:
            raise self._migrate_exception
        return self._migrate_result

    def get_migration(self, migration_id):
        return self._migrations.get(migration_id)

    def list_migrations(self):
        return list(self._migrations.values())


def test_migrate_unknown_service_returns_404(monkeypatch):
    fake = FakeOrchestrator(
        migrate_exception=ServiceNotFoundError("Service 'does-not-exist' not found in inventory")
    )
    monkeypatch.setattr("app.api.routes.get_migration_orchestrator", lambda: fake)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(migrate_service("does-not-exist"))

    assert exc_info.value.status_code == 404


def test_get_migration_unknown_id_returns_404(monkeypatch):
    fake = FakeOrchestrator(migrations={})
    monkeypatch.setattr("app.api.routes.get_migration_orchestrator", lambda: fake)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_migration("mig-does-not-exist"))

    assert exc_info.value.status_code == 404


def test_migrate_success_returns_record_unchanged(monkeypatch):
    """Existing successful migration API behavior (200 + the record) is unchanged."""
    record = make_record(state=MigrationState.COMPLETED)
    fake = FakeOrchestrator(migrate_result=record)
    monkeypatch.setattr("app.api.routes.get_migration_orchestrator", lambda: fake)

    result = asyncio.run(migrate_service("auth-service"))

    assert result is record
    assert result.state == MigrationState.COMPLETED


def test_list_migrations_returns_all_records(monkeypatch):
    record = make_record()
    fake = FakeOrchestrator(migrations={record.migration_id: record})
    monkeypatch.setattr("app.api.routes.get_migration_orchestrator", lambda: fake)

    result = asyncio.run(list_migrations())

    assert result["total"] == 1
    assert result["migrations"][0]["migration_id"] == record.migration_id


def test_get_migration_found_returns_record(monkeypatch):
    record = make_record()
    fake = FakeOrchestrator(migrations={record.migration_id: record})
    monkeypatch.setattr("app.api.routes.get_migration_orchestrator", lambda: fake)

    result = asyncio.run(get_migration(record.migration_id))

    assert result["migration"]["migration_id"] == record.migration_id
