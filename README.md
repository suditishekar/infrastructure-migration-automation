# Infrastructure Migration & Monitoring Automation

A Python-based infrastructure automation platform for validating service dependencies, performing health checks, orchestrating migrations, handling retries and rollback, persisting migration state, and exposing operational metrics and reports.

**Stack:** Python, FastAPI, Pydantic, SQLAlchemy, SQLite, Docker, Docker Compose, pytest, GitHub Actions

![Tests](https://github.com/suditishekar/infrastructure-migration-automation/actions/workflows/tests.yml/badge.svg)

## Overview

Infrastructure migrations can fail because of invalid configuration, dependency issues, unhealthy services, or partial migration failures.

This project implements a **validation-first migration workflow**:

```text
Service Inventory
       ↓
Pre-Migration Validation
       ↓
Dependency-Aware Ordering
       ↓
Migration Orchestrator
       ↓
Migration + Health Check
       ↓
Retry / Rollback
       ↓
SQLite Persistence
       ↓
Metrics & Reporting
```

The migration provider is intentionally simulated. The project focuses on the engineering architecture around **automation, dependency management, reliability, failure recovery, persistence, and observability**.

## Key Features

### Service Inventory
- Configuration-driven service inventory using YAML
- Pydantic validation
- Duplicate service detection
- REST APIs for service discovery

### Pre-Migration Validation
- Configuration readiness checks
- Dependency existence validation
- Circular dependency detection using DFS
- Structured errors and warnings

### Health Checks
- HTTP health probing
- Per-service timeout handling
- Healthy, unhealthy, unreachable, and timeout states
- HTTP status, latency, and error reporting

### Migration Orchestration
- Explicit migration state machine
- Dependency-aware ordering using topological sorting
- Configurable migration retries
- Post-migration health validation
- Rollback after migration or health-check failure
- Rollback failure handling
- Idempotent migrations

### Persistence & Reporting
- SQLite persistence through SQLAlchemy
- Repository abstraction for database access
- Persisted migration attempts and rollback outcomes
- Migration state survives application restarts
- Aggregate migration metrics
- Migration and failure reports

### Containerization & CI
- Dockerized FastAPI application
- Docker Compose environment with seven simulated services
- Docker network aliases matching configured legacy hostnames
- Persistent SQLite Docker volume
- 44 automated pytest tests
- GitHub Actions CI on every push and pull request

## Architecture

```text
┌─────────────────────────────────────────────┐
│                  FastAPI API                │
│              REST Endpoints                 │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│                Service Layer                │
│                                             │
│ Inventory                                    │
│ Pre-Migration Validator                     │
│ Health Check Service                        │
│ Migration Orderer                           │
│ Migration Orchestrator                     │
│ Metrics / Reporting                        │
└──────────────┬────────────────┬─────────────┘
               │                │
        ┌──────▼──────┐  ┌──────▼───────────┐
        │   Schemas   │  │    Repository    │
        │  Pydantic   │  │                  │
        └─────────────┘  └────────┬─────────┘
                                  │
                           ┌──────▼──────┐
                           │   SQLite    │
                           │ SQLAlchemy  │
                           └─────────────┘
```

### Migration State Flow

```text
discovered
    ↓
validating
    ↓
ready
    ↓
migrating
    ↓
health_check
    ↓
completed

failure
    ↓
retry
    ↓
max attempts reached
    ↓
rollback
    ↓
rolled_back / migration_failed
```

## Dependency Management

Services form a directed dependency graph.

Before migration:

1. Dependencies are validated.
2. Circular dependencies are detected using DFS.
3. A topological ordering is calculated.
4. Direct dependencies must be completed before a service can migrate.

Example:

```text
auth-service ──────────────┐
                           ↓
database-service ──────► payment-service
                           ↓
                      reporting-service
```

This prevents a service from being migrated before the services it depends on are ready.

## Failure Handling

A failed migration follows a controlled recovery workflow:

```text
Migration Attempt
       ↓
    Failure
       ↓
     Retry
       ↓
  Max Attempts
       ↓
    Rollback
       ↓
Persist Outcome
       ↓
Failure Report
```

The system preserves migration attempts, errors, and rollback outcomes so failures remain observable after the workflow completes.

## Failure Injection

Deterministic failure injection is available for demonstrations and local testing:

```bash
SIMULATE_MIGRATION_FAILURES=payment-service
SIMULATE_ROLLBACK_FAILURES=payment-service
SIMULATE_HEALTH_CHECK_FAILURES=payment-service
```

Multiple services can be supplied as comma-separated IDs.

## API

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Application health |
| GET | `/api/services` | List services |
| GET | `/api/services/{service_id}` | Service details |
| POST | `/api/validation/pre-migration` | Validate migration readiness |
| POST | `/api/health/check` | Run service health checks |
| POST | `/api/migrations/{service_id}` | Start/retrieve migration |
| GET | `/api/migrations` | List persisted migrations |
| GET | `/api/migrations/{migration_id}` | Migration details |
| GET | `/api/metrics` | Migration metrics |
| GET | `/api/reports/migrations` | Migration report |
| GET | `/api/reports/failures` | Failure report |

Interactive API documentation:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Project Structure

```text
.
├── app/
│   ├── api/
│   ├── core/
│   ├── database/
│   ├── schemas/
│   └── services/
├── config/
│   └── services.yaml
├── simulated_services/
├── tests/
├── .github/
│   └── workflows/
│       └── tests.yml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
└── README.md
```

## Technology Stack

| Technology | Purpose |
|---|---|
| Python 3.11+ | Application and automation logic |
| FastAPI | REST API |
| Pydantic | Validation and schemas |
| PyYAML | Service configuration |
| SQLAlchemy | ORM / persistence layer |
| SQLite | Migration state storage |
| Docker | Containerization |
| Docker Compose | Local service environment |
| pytest | Automated testing |
| GitHub Actions | Continuous integration |

## Running Locally

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
pip install -r requirements.txt
```

Start the application:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open:

`http://localhost:8000/docs`

> The configured legacy service hostnames are intended for the Docker Compose environment. Outside Docker, the real HTTP health-check endpoint will report the simulated services as unreachable.

## Running with Docker

Start the complete environment:

```bash
docker compose up --build
```

This starts the FastAPI application and seven lightweight simulated HTTP services.

Open:

`http://localhost:8000/docs`

Stop the environment:

```bash
docker compose down
```

Remove containers and the persisted database volume:

```bash
docker compose down -v
```

## Running Tests

Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

Run:

```bash
pytest
```

The suite contains **44 tests** and runs completely offline.

Coverage includes:

- Configuration and dependency validation
- Circular dependency detection
- Dependency-aware ordering
- Health-check behavior
- Migration success and failure
- Retries and rollback
- Rollback failure handling
- Idempotency
- Database persistence
- Metrics and reporting
- API success and error cases

GitHub Actions runs the same test suite automatically on pushes and pull requests.

## Design Decisions

### Configuration-Driven Inventory
Service metadata is defined in YAML rather than hardcoded into application logic.

### Validation Before Execution
Migration execution is gated by configuration and dependency validation.

### Dependency-Aware Orchestration
Topological ordering ensures dependencies are migrated before dependent services.

### Pluggable Providers
Migration and health-check behavior are abstracted so simulated implementations can be replaced with real infrastructure providers.

### Repository Pattern
Database access is isolated behind a repository layer, keeping persistence concerns separate from orchestration logic.

### Idempotency
Already-completed migrations are returned without executing the migration again.

### Failure Recovery
Retries and rollback are explicit workflow states, with outcomes persisted for reporting.

## Scope

This project demonstrates the architecture and reliability patterns behind infrastructure migration automation.

The migration provider is simulated and does **not** make real cloud infrastructure changes.

The included Docker services are lightweight HTTP stubs used to provide deterministic health endpoints for the application.

## Status

**Complete**

- Service inventory & configuration
- Pre-migration validation
- Active health checks
- Migration orchestration
- Retry & rollback handling
- SQLite persistence
- Metrics & reporting
- Docker & Docker Compose
- Automated testing
- GitHub Actions CI

## License

This project is intended as a software engineering portfolio project.
