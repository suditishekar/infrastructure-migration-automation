# Infrastructure Migration & Monitoring Automation

A Python-based infrastructure automation system for service inventory management and pre-migration validation. Designed to safely orchestrate service migration from legacy to modern cloud-native environments.

## Project Status

- **Phase 1** ✅ Complete: Service inventory & configuration management  
- **Phase 2A** ✅ Complete: Pre-migration validation (static checks)  
- **Phase 2B** ✅ Complete: Active health probing & health checks  
- **Phase 3** ✅ Complete: Core migration orchestration (simulated)  
- **Phase 4** ✅ Complete: SQLite persistence, metrics, and reporting  
- **Phase 5** ✅ Complete: Docker + simulated service containers  
- **Phase 6** ✅ Complete: Automated test suite + CI  
- **Phase 7+** (Planned): Beyond testing/CI  

## Overview

This project automates infrastructure migration with a validation-first approach. Phase 1 provides configuration-driven service inventory management. Phase 2A adds static pre-migration validation to detect configuration issues before any migration operations occur.

## Architecture: Phase 1 & 2A

```
services.yaml
      ↓
InventoryLoader (Phase 1)
  • Load YAML file
  • Parse YAML structure  
  • Validate with Pydantic
  • Detect duplicates
      ↓
PreMigrationValidator (Phase 2A)
  • Validate dependencies exist
  • Detect circular dependencies (DFS)
  • Check configuration readiness
      ↓
ValidationResult
      ↓
HealthCheckService (Phase 2B)
  • Probe each service's health endpoint over HTTP
  • Capture status, latency, and errors per service
      ↓
HealthCheckSummary
      ↓
FastAPI Routes
  • GET /api/health
  • GET /api/services
  • GET /api/services/{id}
  • POST /api/validation/pre-migration
  • POST /api/health/check
  • POST /api/migrations/{service_id}
  • GET /api/migrations
  • GET /api/migrations/{migration_id}
  • GET /api/metrics
  • GET /api/reports/migrations
  • GET /api/reports/failures
```

## Project Structure

```
app/
├── main.py                          # FastAPI application factory
├── core/
│   ├── config.py                    # Configuration management
│   ├── exceptions.py                # Custom exceptions
│   └── logging.py                   # Logging setup
├── api/
│   └── routes.py                    # REST endpoints
├── services/
│   ├── inventory.py                  # Inventory loader (Phase 1)
│   ├── pre_migration_validator.py    # Validator service (Phase 2A)
│   ├── health_check.py               # Health check service (Phase 2B)
│   ├── migration_orderer.py          # Dependency-aware ordering (Phase 3)
│   ├── migration_provider.py         # Migration/rollback + health-check abstractions (Phase 3)
│   ├── migration_orchestrator.py     # Migration orchestrator (Phase 3, persists via Phase 4 repository)
│   ├── migration_repository.py       # Migration persistence repository (Phase 4)
│   ├── metrics_service.py            # Migration metrics (Phase 4)
│   └── reporting_service.py          # Migration/failure reports (Phase 4)
├── database/
│   ├── models.py                     # SQLAlchemy ORM models (Phase 4)
│   └── session.py                    # Engine/session setup, init_db() (Phase 4)
└── schemas/
    ├── __init__.py                  # Service models (Phase 1)
    ├── validation.py                # Validation models (Phase 2A)
    ├── health.py                    # Health check models (Phase 2B)
    ├── migration.py                 # Migration models (Phase 3)
    ├── metrics.py                   # Metrics models (Phase 4)
    └── reports.py                   # Reporting models (Phase 4)

config/
└── services.yaml                    # Service inventory (unmodified since Phase 1)

simulated_services/                  # Phase 5: dependency-free HTTP stub image
├── server.py                        # Reused for all simulated containers (env-var configured)
└── Dockerfile

tests/                               # Phase 6: automated test suite (44 tests)
.github/workflows/
└── tests.yml                        # Phase 6: CI - runs pytest on push/PR
Dockerfile                            # Phase 5: production-oriented app image
docker-compose.yml                    # Phase 5: app + simulated services
.dockerignore                         # Phase 5
requirements.txt                     # Python dependencies (application runtime)
requirements-dev.txt                  # Phase 6: adds pytest for running the test suite
.gitignore                          # Git ignore
README.md                           # This file
```

## Configuration

### Environment Variables

```bash
ENVIRONMENT=development            # development, staging, production
API_HOST=127.0.0.1                # API listen address
API_PORT=8000                      # API listen port
INVENTORY_FILE=config/services.yaml # Path to services YAML
HEALTH_CHECK_TIMEOUT=5.0           # Per-service health check timeout (seconds)
MIGRATION_MAX_RETRIES=2            # Additional migration attempts after the first failure
DATABASE_URL=sqlite:///./app.db    # SQLite database location (Phase 4 persistence)
LOG_LEVEL=INFO                     # Logging level
DEBUG=true                         # Debug mode

# Phase 5: optional, tests/local development only - unset by default
SIMULATE_MIGRATION_FAILURES=       # Comma-separated service IDs: migration always fails
SIMULATE_ROLLBACK_FAILURES=        # Comma-separated service IDs: rollback always fails
SIMULATE_HEALTH_CHECK_FAILURES=    # Comma-separated service IDs: post-migration health check always fails
```

### services.yaml Format

Each service requires:

```yaml
services:
  service-id:
    id: service-id                    # Unique identifier
    name: Service Name                # Human-readable name
    host: service.internal            # Hostname/IP
    port: 8080                        # Port (1-65535)
    source_environment: legacy        # Current environment
    target_environment: modern        # Migration target
    health_endpoint: /health          # Health check path
    dependencies: [auth, db]          # Service ID dependencies
    service_type: core                # Service type
    criticality: high                 # Criticality level
```

## Phase 1: Service Inventory

### What Phase 1 Does

- Loads service metadata from `services.yaml`
- Validates services with Pydantic models
- Provides REST API for service discovery
- Detects duplicate service IDs
- Stores inventory in memory at startup

### Phase 1 API Endpoints

#### GET /api/health
```json
{
  "status": "healthy",
  "service": "infrastructure-migration",
  "version": "0.1.0"
}
```

#### GET /api/services
```json
{
  "total": 7,
  "services": [...]
}
```

#### GET /api/services/{service_id}
```json
{
  "service": {...}
}
```

### Phase 1 Limitations

- No database persistence (in-memory only)
- No health probing
- No validation of dependencies
- No migration logic
- No metrics or reporting

## Phase 2A: Pre-Migration Validation

Static pre-migration validation determines if the service inventory is ready for migration. All checks are static (no network requests or active probing).

### What Phase 2A Validates

#### 1. Configuration Readiness
- All required fields present (Pydantic validation)
- Source and target environments are different
- Ports are valid (1-65535)
- Service types are valid

#### 2. Dependency Validation
Every service dependency must reference another service in the inventory.

**Example valid dependencies**:
```yaml
payment-service:
  dependencies: [auth-service, database-service]
```

Both `auth-service` and `database-service` must exist in inventory.

**Invalid dependency error**:
```json
{
  "service_id": "payment-service",
  "category": "dependency_missing",
  "severity": "error",
  "message": "Service 'payment-service' depends on 'unknown-service' which does not exist",
  "details": {"missing_dependency": "unknown-service"}
}
```

#### 3. Circular Dependency Detection
Treats service dependencies as a **directed graph** and detects cycles using **Depth-First Search (DFS)**.

**Examples of cycles detected**:
- Direct cycle: A → A
- Simple cycle: A → B → A  
- Complex cycle: A → B → C → A

**Circular dependency error**:
```json
{
  "service_id": "payment-service",
  "category": "circular_dependency",
  "severity": "error",
  "message": "Circular dependency detected: payment-service -> auth-service -> payment-service",
  "details": {
    "cycle_path": ["payment-service", "auth-service", "payment-service"],
    "cycle_length": 2
  }
}
```

### Dependency Graph Algorithm

**DFS with Recursion Stack** for cycle detection:

1. **Visited Set**: Track services already explored
2. **Recursion Stack**: Track services in current path
3. **For each unvisited service**: Recursively explore dependencies
4. **Cycle detection**: If we visit a service on current recursion stack, cycle exists
5. **Cycle normalization**: Convert cycles to lexicographically smallest rotation to avoid duplicate reporting

**Why recursion stack matters**: 
- Visited set alone is insufficient (tracks globally explored, not current path)
- Recursion stack identifies services in current path
- If we encounter a service on recursion stack, we've found a back edge (cycle)

### Pre-Migration Validation API Endpoint

#### POST /api/validation/pre-migration

Performs static pre-migration validation of the entire inventory.

**Request**:
```
POST /api/validation/pre-migration
```

**Response - Ready for migration (200 OK)**:
```json
{
  "ready": true,
  "total_services": 7,
  "valid_services": 7,
  "invalid_services": 0,
  "errors": [],
  "warnings": [],
  "timestamp": "2026-09-01T12:34:56.789Z"
}
```

**Response - Not ready (200 OK)**:
```json
{
  "ready": false,
  "total_services": 7,
  "valid_services": 6,
  "invalid_services": 1,
  "errors": [
    {
      "service_id": "payment-service",
      "category": "dependency_missing",
      "severity": "error",
      "message": "Service 'payment-service' depends on 'unknown-service' which does not exist",
      "details": {"missing_dependency": "unknown-service"}
    }
  ],
  "warnings": [
    {
      "service_id": "reporting-service",
      "category": "environment",
      "severity": "warning",
      "message": "Service 'reporting-service' source and target environments are identical (legacy)",
      "details": {"source": "legacy", "target": "legacy"}
    }
  ],
  "timestamp": "2026-09-01T12:34:56.789Z"
}
```

### Validation Result Semantics

- **ready**: Boolean readiness status (`false` if any errors exist)
- **total_services**: Number of services in inventory
- **valid_services**: Services with no errors
- **invalid_services**: Services with at least one error
- **errors**: Blocking issues that prevent migration
- **warnings**: Non-blocking issues to review

Migration is **ready** only when errors list is empty.

### Severity Levels

- **ERROR**: Blocking issue (missing dependency, circular dependency)
- **WARNING**: Non-blocking issue (identical environments, configuration anomaly)
- **INFO**: Informational message

### Validation Categories

- **DEPENDENCY_MISSING**: Referenced dependency does not exist
- **CIRCULAR_DEPENDENCY**: Circular dependency detected
- **CONFIGURATION**: Configuration validation issue
- **ENVIRONMENT**: Environment-related issue
- **SERVICE_ID**: Service ID validation issue

### Phase 2A Files Introduced

**app/schemas/validation.py**:
- `SeverityLevel` enum: ERROR, WARNING, INFO
- `ValidationCategory` enum: Validation issue types
- `ValidationIssue`: Represents single validation problem
- `PreMigrationValidationResult`: Complete validation result with all issues
- `CyclePath`: Circular dependency path information

**app/services/pre_migration_validator.py**:
- `PreMigrationValidator` class: Performs all validation checks
- `validate()`: Main validation entry point
- `_validate_dependencies()`: Checks dependencies exist
- `_validate_circular_dependencies()`: DFS cycle detection
- `_validate_configuration_readiness()`: Configuration checks
- `_build_result()`: Constructs validation result
- `get_validator()`: Singleton access function

**app/api/routes.py** (modified):
- Added `POST /api/validation/pre-migration` endpoint
- Integrated validation service with FastAPI
- Structured error handling and logging

### Phase 2A Logging

Events logged at INFO level:
- Validation started
- Number of services being validated
- Missing dependencies discovered
- Circular dependencies detected (with cycle path)
- Configuration issues found
- Validation completed with final status

### Phase 2A Limitations

- **No network requests**: Static analysis only
- **No health checks**: Does not probe services
- **No dependency semantics**: Does not verify dependencies are correct for business logic
- **No ordering**: Does not calculate optimal migration order
- **No execution**: Does not perform migration

## Phase 2B: Health Checks

Active health probing performs real HTTP requests against each service's configured `health_endpoint`, unlike Phase 2A's static analysis.

### What Phase 2B Does

- Sends an HTTP GET to `http://{host}:{port}{health_endpoint}` for every service in the inventory
- Applies a per-service timeout (`HEALTH_CHECK_TIMEOUT`, default 5.0s)
- Classifies each service as `healthy`, `unhealthy`, `unreachable`, or `timeout`
- Captures HTTP status, latency (ms), and error details without raising on connection failures

### Health Check API Endpoint

#### POST /api/health/check

Performs active health checks across the entire service inventory.

**Response (200 OK)**:
```json
{
  "total_services": 7,
  "healthy_count": 6,
  "unhealthy_count": 1,
  "results": [
    {
      "service_id": "auth-service",
      "service_name": "Authentication & Authorization Service",
      "status": "healthy",
      "http_status": 200,
      "latency_ms": 12.4,
      "error": null,
      "checked_at": "2026-09-09T12:34:56.789Z"
    },
    {
      "service_id": "payment-service",
      "service_name": "Payment Processing Service",
      "status": "unreachable",
      "http_status": null,
      "latency_ms": null,
      "error": "[Errno 111] Connection refused",
      "checked_at": "2026-09-09T12:34:56.912Z"
    }
  ],
  "timestamp": "2026-09-09T12:34:56.912Z"
}
```

### Phase 2B Files Introduced

- `app/schemas/health.py`: `HealthStatus` enum, `ServiceHealthResult`, `HealthCheckSummary`
- `app/services/health_check.py`: `HealthCheckService` — probes services and aggregates results
- `app/api/routes.py` (modified): Added `POST /api/health/check`

### Phase 2B Limitations

- No retries, backoff, or scheduling — a single probe per service per request
- No metrics storage or historical reporting
- Assumes `http://` scheme for health endpoints

## Phase 3: Core Migration Orchestration

Coordinates the per-service migration workflow on top of Phase 2A validation and Phase 2B health checks. Infrastructure changes are **simulated only** — no real cloud/provider calls are made.

### What Phase 3 Does

- Tracks each service's migration through a state machine: `discovered → validating → ready → migrating → health_check → completed`, with failure states `validation_failed`, `migration_failed`, `health_check_failed`, and `rolled_back`
- Runs Phase 2A's `PreMigrationValidator` before migrating, and blocks migration if the service (or a dependency cycle it belongs to) has a blocking error
- Requires a service's direct dependencies to already be in the `completed` state before it can migrate (dependency-aware ordering is computed via `build_migration_order`, which reuses Phase 2A's dependency/cycle checks rather than a second implementation)
- Executes the migration through a pluggable `MigrationProvider` abstraction; the default `SimulatedMigrationProvider` is deterministic and performs no real infrastructure changes
- Retries a failed migration attempt up to `MIGRATION_MAX_RETRIES` additional times, then runs a rollback workflow; the record moves to `rolled_back` only if rollback succeeds, otherwise the failure state and rollback error are both preserved
- Is idempotent: a service already `completed` is returned as-is rather than re-migrated

### Migration API Endpoints

- `POST /api/migrations/{service_id}` — initiate (or return the existing result of) a service's migration
- `GET /api/migrations` — list all in-memory migration records
- `GET /api/migrations/{migration_id}` — get a single migration record by ID

### Phase 3 Files Introduced

- `app/schemas/migration.py`: `MigrationState` enum, `MigrationAttempt`, `RollbackInfo`, `MigrationRecord`
- `app/services/migration_orderer.py`: `build_migration_order()` — topological sort, reusing `PreMigrationValidator`'s dependency/cycle checks
- `app/services/migration_provider.py`: `MigrationProvider` abstraction and the default `SimulatedMigrationProvider`
- `app/services/migration_orchestrator.py`: `MigrationOrchestrator` — validation gate, retries, health check, rollback
- `app/api/routes.py` (modified): Added the three `/migrations` endpoints

### Phase 3 Limitations

- No real infrastructure changes — migration and rollback are simulated
- Single-service workflow only — no multi-service/whole-inventory migration run, no background workers or queues

## Phase 4: Persistence, Metrics & Reporting

Migration records and attempts are now persisted to SQLite via SQLAlchemy instead of living only in process memory, and two read-only aggregate views (metrics, reports) are derived from that persisted data.

### What Phase 4 Does

- Persists every `MigrationRecord` (including rollback outcome) and its `MigrationAttempt`s to SQLite through a `MigrationRepository` — a clean repository layer the orchestrator, metrics, and reporting services all depend on instead of touching SQL/ORM directly
- `MigrationOrchestrator` now takes an injectable `repository` (defaulting to the app-wide SQLite-backed one) and persists at each state transition; idempotency and dependency-readiness checks are based on persisted state, so they survive an application restart
- `GET /api/migrations` and `GET /api/migrations/{migration_id}` now read from the database — unchanged endpoint contracts, durable data
- `MetricsService` computes counts (total/completed/failed/rolled-back/in-progress), total attempts, success rate, and average migration duration from persisted records
- `ReportingService` builds an aggregate migration report and a failure-focused report (errors, attempts, rollback outcome) from persisted records

### Phase 4 API Endpoints

- `GET /api/metrics` — aggregate migration metrics
- `GET /api/reports/migrations` — per-migration summary report
- `GET /api/reports/failures` — failed/rolled-back migrations with attempts and rollback detail

### Phase 4 Files Introduced

- `app/database/models.py`: `MigrationRecordORM`, `MigrationAttemptORM`
- `app/database/session.py`: engine/session setup, `init_db()`
- `app/services/migration_repository.py`: `MigrationRepository` — the persistence abstraction
- `app/services/metrics_service.py`, `app/services/reporting_service.py`
- `app/schemas/metrics.py`, `app/schemas/reports.py`
- `app/services/migration_orchestrator.py` (modified): persists through `MigrationRepository` instead of in-memory dicts
- `app/main.py` (modified): calls `init_db()` on startup
- `app/api/routes.py` (modified): added the three endpoints above

### Phase 4 Limitations

- SQLite only, single file, no migrations/schema versioning tooling (e.g. Alembic)
- No authentication/authorization on the new read endpoints
- Metrics/reports are computed on read, not pre-aggregated or cached

## Phase 5: Docker + Simulated Services

Dockerizes the app and gives Phase 2B's real `HealthCheckService` something real to talk to, without changing `config/services.yaml` or the application code.

### How it's wired

- `Dockerfile` builds the FastAPI app (non-root user, `HEALTHCHECK` against `/api/health`).
- `simulated_services/` is one minimal, dependency-free HTTP stub (`server.py`, stdlib only) reused as the image for all 7 simulated containers in `docker-compose.yml`. Each container is configured via env vars (`PORT`, `HEALTH_PATH`, `SERVICE_NAME`) to match one service's port/`health_endpoint` from `services.yaml`.
- Each simulated container is given a Docker Compose **network alias** equal to that service's exact `host` value from `services.yaml` (e.g. the `auth-service` container is aliased to `legacy-auth.internal`). This makes the legacy hostnames already in `services.yaml` resolve correctly inside the Compose network — no hostnames are hard-coded into application code, and `services.yaml` did not need to change.
- The app's SQLite database is written to a named volume (`app_db_data`, mounted at `/data`, `DATABASE_URL=sqlite:////data/app.db`) so it survives container restarts.

### Failure injection (tests/local development only)

The existing deterministic `SimulatedMigrationProvider`/`SimulatedHealthChecker` failure-injection (`always_fail_service_ids`, `always_fail_rollback_service_ids`) is unchanged and still what the automated tests use directly. For manually demonstrating a failure through the running API (Docker or local `uvicorn`) without writing code or touching `services.yaml`, three optional env vars configure the default orchestrator singleton's simulated provider/checker:

```bash
SIMULATE_MIGRATION_FAILURES=payment-service       # migration attempts always fail for these service IDs
SIMULATE_ROLLBACK_FAILURES=payment-service         # rollback attempts always fail for these service IDs
SIMULATE_HEALTH_CHECK_FAILURES=payment-service     # post-migration health check always fails for these service IDs
```

Comma-separated service IDs; unset (the default) means no simulated failures. These are not exposed through any API endpoint — set them as environment variables before starting the app (or uncomment the corresponding line in `docker-compose.yml`).

### Phase 5 Limitations

- No Kubernetes, Terraform, or cloud deployment — Compose only
- Simulated containers only serve their configured health path; they do not simulate any other real service behavior (e.g. no actual Postgres/Redis/AMQP protocol)
- Failure-injection env vars affect only the default orchestrator singleton (`get_migration_orchestrator()`); they have no effect on unit tests, which construct `MigrationOrchestrator` directly

## Phase 6: Testing & CI

An automated `pytest` suite (44 tests, see `tests/`) covering the behavior introduced in Phases 1-4, plus a GitHub Actions workflow that runs it on every push/PR.

### What's covered

- **Inventory/config validation**: missing required fields, missing-config fail-closed behavior (`test_inventory_configuration.py`), dependency/circular-dependency/valid-config checks (`test_pre_migration_validator.py`)
- **Dependency ordering**: direct and transitive ordering, circular/missing-dependency errors (`test_migration_orderer.py`)
- **Health checks**: healthy/HTTP-error/unreachable/timeout responses and aggregate `check_all()` (`test_health_check.py`)
- **Migration orchestration**: successful migration, retry/failure/rollback, health-check failure/rollback, rollback failure without crashing, idempotency (including across a new orchestrator/repository instance), and Phase 2B `HealthCheckService` injection (`test_migration_orchestrator.py`)
- **Repository persistence**: save/round-trip, attempts ordering, rollback info, updates, latest-by-service lookup, survival across repository object recreation (`test_migration_repository.py`)
- **Metrics**: empty-repository zeros, mixed-outcome counts/success-rate, average-duration calculation (`test_metrics_service.py`)
- **Reports**: migration report contents/duration, failure report filtering (`test_reporting_service.py`)
- **API**: unknown-service and unknown-migration-id 404s, unchanged success passthrough, list/get endpoints (`test_migration_api.py`)

The suite is fully offline (no real network, no Docker, no dependency on `config/services.yaml`'s content) and does not modify `config/services.yaml`.

### Phase 6 Limitations

- No coverage percentage is tracked or reported — only that all 44 tests pass
- CI runs on Ubuntu with Python 3.11 only; no cross-platform or multi-version matrix
- CI does not build/run the Docker image or docker-compose stack, only the Python test suite

## Technology Stack

| Component | Purpose | Phase |
|-----------|---------|-------|
| Python 3.11+ | Core language | 1+ |
| FastAPI | REST API framework | 1+ |
| Pydantic v2 | Configuration validation | 1+ |
| PyYAML | YAML parsing | 1+ |
| Python logging | Structured logging | 1+ |
| python-dotenv | Environment variables | 1+ |
| SQLAlchemy | ORM / SQLite persistence | 4+ |
| Docker / Docker Compose | Containerized app + simulated services | 5+ |
| pytest | Automated test suite | 6+ |
| GitHub Actions | CI: runs pytest on push/PR | 6+ |

## Design Decisions

### Configuration-Driven Approach
Services defined in YAML, not hardcoded. Enables environment parity and simple service addition.

### Pydantic Validation
Type-safe validation with clear error messages, enforced at parse time.

### Singleton Inventory & Validator
Single load at startup, shared immutably across requests. Enables efficient state management.

### Layered Architecture
- API layer: HTTP concerns
- Service layer: Business logic
- Schema layer: Data validation
- Core layer: Configuration, exceptions, logging

### Dedicated Validation Service
Pre-migration validation separated from API to enable reuse by orchestrator (Phase 3).

### Static Analysis First
Pre-migration validation performs only static checks. Active health checks are Phase 2B.

### Explicit Error vs Warning Semantics
Errors block migration readiness. Warnings indicate issues to review but do not block.

## Running the Application

### Option A: Local Python / uvicorn

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

This is unchanged by Phase 5. `config/services.yaml`'s legacy hostnames (e.g. `legacy-auth.internal`) are not resolvable outside Docker, so locally: `POST /api/validation/pre-migration` and `POST /api/migrations/{id}` (simulated migration/health-check) work as before; `POST /api/health/check` (Phase 2B's real HTTP probing) will report each service unreachable, since there is nothing listening at those hostnames on your machine.

### Option B: Docker Compose (app + simulated services)

```bash
docker compose up --build
```

This builds and starts the FastAPI app plus one lightweight simulated HTTP container per service in `config/services.yaml` (see "Phase 5" below). Once up:
- Swagger UI: http://localhost:8000/docs
- `POST /api/health/check` now succeeds for real, since the simulated containers are reachable at the exact hosts/ports/paths declared in `config/services.yaml`.

Stop and remove containers with `docker compose down` (add `-v` to also drop the persisted `app_db_data` volume).

### Access Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite (`tests/`) is fully offline: the real network, Docker, and `config/services.yaml`'s content are never required — services, inventories, and repositories are constructed in-memory or against an isolated in-memory SQLite database per test. `.github/workflows/tests.yml` runs the same `pytest` command on push/PR via GitHub Actions.

## Key Concepts

### Directed Graphs & Cycle Detection
Dependency relationships form a directed graph. Cycles indicate circular dependencies that prevent migration. DFS with recursion stack efficiently detects all cycles by identifying back edges.

### Configuration Validation vs Runtime Validation
- **Configuration Validation** (Phase 2A): Static checks on YAML structure
- **Runtime Validation** (Phase 2B): Active checks on service health

### Pre-Flight Checks
Migration systems perform pre-flight validation to catch configuration errors before attempting migrations. This saves time and prevents partial/failed migrations.

### Separation of Concerns
Validation logic in service layer (not API routes) enables:
- Reuse by orchestrator (Phase 3)
- Independent testing
- Cleaner HTTP endpoint code

## Example Services

The `config/services.yaml` includes 7 example services:

- **payment-service**: Core payment processing (criticality: high)
- **reporting-service**: Analytics and reporting (criticality: medium)
- **notification-service**: Alert and notification (criticality: medium)
- **auth-service**: Authentication & authorization (criticality: high)
- **database-service**: Primary data store (criticality: critical)
- **cache-service**: Distributed cache (criticality: medium)
- **message-queue**: Event messaging (criticality: high)

## Validation Workflow

```
Service inventory loaded (Phase 1)
       ↓
Application receives POST /api/validation/pre-migration
       ↓
PreMigrationValidator.validate() called
       ↓
├─ validate_dependencies()
│   └─ For each service, check all dependencies exist
│   └─ Add ValidationIssue for missing dependencies
│
├─ validate_circular_dependencies()
│   └─ Run DFS cycle detection on dependency graph
│   └─ Add ValidationIssue for each cycle found
│
└─ validate_configuration_readiness()
    └─ For each service, check configuration is valid
    └─ Add ValidationIssue for configuration problems
       ↓
ValidationResult constructed
  • Separate errors from warnings
  • Count valid/invalid services
  • Set ready = (no errors)
       ↓
Result returned to client
```

## Future Phases

### Phase 7+: Advanced Scenarios
- Blue-green deployments
- Canary migration patterns
- Automatic rollback based on metrics

---

**Version**: 0.1.0  
**Phase 1**: Complete ✅  
**Phase 2A**: Complete ✅  
**Phase 2B**: Complete ✅  
**Phase 3**: Complete ✅  
**Phase 4**: Complete ✅  
**Phase 5**: Complete ✅  
**Phase 6**: Complete ✅  
**Next**: Phase 7 - Advanced Scenarios  
