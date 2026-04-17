# ArpSurvey Server Application Design

**Date:** 2026-04-17
**Status:** Draft
**Author:** Scott Bartram + Claude

## Summary

Transform the ArpSurvey CLI toolkit and static HTML dashboard into a Flask-based server application deployed in a local k3s Kubernetes cluster. The app provides a browser UI with full parity to the existing `arp_project.html` dashboard, plus the ability to run pipeline tools (ACP plan generation, session planning, moon calendar computation) and upload/download files — all from the browser. Data moves from flat files + browser localStorage to a PostgreSQL database.

## Decisions

- **Framework:** Flask + SQLAlchemy + Jinja2 + HTMX
- **Database:** PostgreSQL (existing instance in the k3s cluster)
- **Frontend:** Server-rendered HTML with HTMX for interactivity — no JavaScript framework
- **Container:** Single Docker image, Gunicorn, deployed as a k8s Deployment
- **Networking:** MetalLB LoadBalancer service (direct LAN IP, no ingress controller, no TLS)
- **Local dev:** docker-compose with PostgreSQL for testing outside k8s
- **Scope:** Full dashboard parity from day one
- **Migration:** One-time script reusing existing data loaders from `arp_common.py`

## Project Structure

```
ArpSurvey/
├── app/
│   ├── __init__.py              # Flask app factory (create_app)
│   ├── config.py                # Config class (DATABASE_URL, SECRET_KEY, MAX_CONTENT_LENGTH)
│   ├── models.py                # SQLAlchemy models
│   ├── routes/
│   │   ├── __init__.py          # Blueprint registration
│   │   ├── overview.py          # GET / — dashboard overview
│   │   ├── targets.py           # PATCH /targets/<id>/status, POST /import/localstorage
│   │   ├── planner.py           # GET /planner, POST /planner/compute, POST /planner/generate-acp
│   │   ├── visibility.py        # GET /visibility
│   │   ├── moon.py              # GET /moon, POST /moon/regenerate, GET /moon/status
│   │   ├── log.py               # GET /log, POST /log, DELETE /log/<id>, GET /log/export
│   │   ├── export.py            # GET /export, GET /export/csv, GET /export/targets, GET /export/status-json
│   │   ├── generator.py         # GET /generator, POST /generator/run — ACP batch generation
│   │   ├── files.py             # GET /files, POST /files/upload, GET /files/plans/<id>/download
│   │   └── health.py            # GET /health — readiness probe
│   ├── services/
│   │   ├── __init__.py
│   │   ├── astronomy.py         # ephem wrappers: dark window, alt/az, target visibility
│   │   ├── acp.py               # ACP plan generation logic (extracted from arp_acp_generator.py)
│   │   ├── session.py           # Session planner logic (extracted from arp_session_planner.py)
│   │   ├── moon_calendar.py     # Moon calendar computation (extracted from arp_moon_calendar.py)
│   │   ├── ned.py               # NED coordinate fetching (extracted from arp_ned_coords.py)
│   │   └── importer.py          # Excel/CSV parsing → DB import
│   ├── static/
│   │   └── style.css            # Styles extracted from arp_project.html
│   └── templates/
│       ├── base.html            # Layout: nav bar, HTMX script tag, flash messages
│       ├── overview.html        # Overview dashboard
│       ├── planner.html         # Tonight's plan
│       ├── visibility.html      # Visibility windows
│       ├── moon.html            # Moon calendar
│       ├── log.html             # Imaging log
│       ├── export.html          # Progress export
│       ├── generator.html       # ACP batch generator
│       ├── files.html           # File upload/download hub
│       └── partials/            # HTMX response fragments
│           ├── planner_table.html
│           ├── visibility_table.html
│           ├── moon_strips.html
│           ├── log_table.html
│           ├── log_stats.html
│           ├── plan_list.html
│           └── upload_result.html
├── scripts/
│   └── migrate_data.py          # One-time flat-file → DB migration
├── migrations/                  # Alembic migration directory
├── tests/                       # Existing tests + new server tests
├── k8s/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── secret.yaml.template
├── docker-compose.yml           # Local dev: app + PostgreSQL
├── Dockerfile
├── requirements.txt
├── alembic.ini
├── arp_common.py                # Preserved — still used by CLI scripts and migration
├── arp_acp_generator.py         # Preserved — CLI still works
├── arp_session_planner.py       # Preserved
├── arp_moon_calendar.py         # Preserved
└── arp_ned_coords.py            # Preserved
```

## Database Schema

### targets

The 338 Arp catalog objects. Combines data from `Arp_Seasonal_Plan.xlsx` and `arp_ned_coords.csv`.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | serial | PK | |
| arp_number | integer | UNIQUE NOT NULL | 1–338 |
| name | varchar(120) | | e.g. "NGC 2857" |
| ra_hours | float | NOT NULL | Decimal hours (parsed from catalog) |
| dec_degrees | float | NOT NULL | Decimal degrees (parsed from catalog) |
| ra_catalog | varchar(30) | | Original RA string from Excel |
| dec_catalog | varchar(30) | | Original Dec string from Excel |
| ned_ra_hours | float | | NULL if no NED data |
| ned_dec_degrees | float | | NULL if no NED data |
| ned_name | varchar(120) | | Canonical NED object name, NULL if no NED data |
| size_arcmin | float | | Angular size |
| season | varchar(20) | NOT NULL | Spring, Summer, Autumn, Winter |
| best_site | varchar(40) | | e.g. "New Mexico / Spain" |
| filter_strategy | varchar(20) | | LRGB or Luminance |
| status | varchar(20) | NOT NULL DEFAULT 'Pending' | Pending/Scheduled/Done/Skip |
| notes | text | | Target-level notes |

### telescopes

Telescope specs from `itelescopesystems.xlsx`.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | serial | PK | |
| telescope_id | varchar(10) | UNIQUE NOT NULL | e.g. "T17" |
| site | varchar(30) | NOT NULL | Observatory name |
| fov_arcmin | float | | Field of view |
| resolution | float | | Arcsec/pixel |
| filters | varchar[] | | Available filter names |
| aperture_mm | float | | |

### telescope_rates

Billing rates per plan tier.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | serial | PK | |
| telescope_id | integer | FK → telescopes.id | |
| plan_tier | varchar(20) | NOT NULL | Plan-40, Plan-90, etc. |
| session_rate | float | | Points per minute (session billing) |
| exposure_rate | float | | Points per minute (exposure billing) |
| | | UNIQUE(telescope_id, plan_tier) | |

### imaging_log

Observation records. Replaces browser localStorage `arp_log`.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | serial | PK | |
| target_id | integer | FK → targets.id, NOT NULL | |
| date_imaged | date | NOT NULL | |
| telescope_id | integer | FK → telescopes.id | |
| filter_strategy | varchar(20) | | |
| exposure_minutes | float | | |
| quality | integer | CHECK(1–5) | Star rating |
| notes | text | | |
| created_at | timestamp | NOT NULL DEFAULT now() | |

### moon_data

Pre-computed moon risk cache. Regenerated on demand.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | serial | PK | |
| target_id | integer | FK → targets.id, NOT NULL | |
| night_date | date | NOT NULL | |
| phase_pct | float | | Moon illumination % |
| separation_deg | float | | Moon–target angular separation |
| risk | varchar(1) | NOT NULL | G, M, or A |
| | | UNIQUE(target_id, night_date) | |

Index on `(night_date, risk)` for dashboard queries that filter by date + risk level.

### moon_calendar_runs

Metadata for each moon calendar computation (global phase data, generation info).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | serial | PK | |
| status | varchar(20) | NOT NULL DEFAULT 'computing' | "computing" or "complete" |
| generated_at | timestamp | NOT NULL | When the computation ran |
| days | integer | NOT NULL | Number of days computed |
| site_key | varchar(30) | NOT NULL | Observatory used |
| start_date | date | NOT NULL | First night in the range |
| phase_calendar | jsonb | NOT NULL | Daily global moon phase `[{date, phase_pct}]` |
| next_new_moon | date | | |
| next_full_moon | date | | |

Only the most recent row is used by the dashboard. Older rows are retained for reference.

### session_results

Cached results from the last session planner computation. Allows the Visibility page to display data without recomputation.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | serial | PK | |
| computed_at | timestamp | NOT NULL | |
| site_key | varchar(30) | NOT NULL | |
| date_local | date | NOT NULL | Night of observation |
| eve_twilight | timestamp | NOT NULL | Evening astronomical twilight |
| morn_twilight | timestamp | NOT NULL | Morning astronomical twilight |
| results | jsonb | NOT NULL | Full array of observable target dicts |

The Visibility page reads the most recent `session_results` row. A new row is inserted each time `POST /planner/compute` runs.

### generated_plans

Stored ACP plan files.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | serial | PK | |
| filename | varchar(200) | NOT NULL | e.g. "Arp_Spring_T17_001.txt" |
| plan_type | varchar(20) | NOT NULL | "acp" or "session" |
| content | text | NOT NULL | Full plan text |
| season | varchar(20) | | |
| telescope_id | integer | FK → telescopes.id | |
| metadata | jsonb | | Generation parameters |
| created_at | timestamp | NOT NULL DEFAULT now() | |

## Routes

### Page Routes (full page load)

| Route | Method | Page | Description |
|-------|--------|------|-------------|
| `/` | GET | Overview | Dashboard metrics, season progress, moon strip, re-image queue |
| `/planner` | GET | Tonight's Plan | Session planning form + results table |
| `/visibility` | GET | Visibility | Visibility windows from last computed session |
| `/moon` | GET | Moon Calendar | Moon risk strips, metrics, bar chart |
| `/log` | GET | Imaging Log | Log form + log table |
| `/export` | GET | Progress Export | Summary stats + download buttons |
| `/generator` | GET | ACP Generator | Batch ACP plan generation (season, telescope, params) |
| `/files` | GET | Files | Upload hub + plan download list |
| `/health` | GET | — | Returns 200 + DB check (for k8s readiness probe) |

### HTMX Fragment Routes (return partial HTML)

| Route | Method | Returns | Trigger |
|-------|--------|---------|---------|
| `/planner/compute` | POST | Planner results table | "Compute session" button. Form params: `date` (YYYY-MM-DD), `site` (observatory key), `min_hours` (int), `moon_filter` ("" / "GM" / "G") |
| `/planner/generate-acp` | POST | ACP preview + download link | "Generate ACP plan" button |
| `/targets/<id>/status` | PATCH | Updated status badge | Click on status cell (in `routes/targets.py`) |
| `/visibility/filter` | GET | Filtered visibility table | Filter/sort controls |
| `/moon/regenerate` | POST | "Computing..." indicator | "Regenerate" button (starts background computation) |
| `/moon/status` | GET | Moon page content or "computing..." | HTMX poll (every 3s while computation runs) |
| `/moon/filter` | GET | Filtered moon strips | Filter controls |
| `/log` | POST | Updated log table + stats | "Save observation" button |
| `/log/<id>` | DELETE | Updated log table | Delete button on row |
| `/log/export` | GET | — | CSV file download |
| `/generator/run` | POST | Generation results + plan links | "Generate" button |
| `/files/upload` | POST | Import result summary | File upload form |
| `/files/plans/<id>/download` | GET | — | .txt file download |
| `/files/plans` | GET | Filtered plan list | Filter controls |
| `/export/csv` | GET | — | CSV file download |
| `/export/targets` | GET | — | CSV file download |
| `/export/status-json` | GET | — | JSON file download |
| `/import/localstorage` | POST | Import result summary | One-time localStorage migration (in `routes/targets.py`) |

### Upload → Import Flow

1. User uploads `.xlsx` or `.csv` via drag-and-drop or file picker on `/files`
2. Server validates file extension and size (max 10MB)
3. Based on detected file type:
   - `Arp_Seasonal_Plan.xlsx` → re-imports all target data (upsert by arp_number)
   - `itelescopesystems.xlsx` → re-imports telescopes + rates (upsert by telescope_id)
   - `arp_ned_coords.csv` → updates NED coordinate columns on matching targets
4. HTMX returns a result summary fragment showing rows imported/updated/skipped

## Service Layer

Each service module extracts the core computation logic from its corresponding CLI script. The CLI scripts remain functional but will eventually become thin wrappers.

### astronomy.py
- `build_observer(site_key, date)` → configured `ephem.Observer`
- `dark_window(observer, date)` → `(evening_twilight: datetime, morning_twilight: datetime)`
- `target_visibility(ra_h, dec_deg, observer, eve_dt, morn_dt)` → `{rise: datetime, set: datetime, transit: datetime, hours: float}`
- `alt_at_time(ra_h, dec_deg, observer, dt)` → altitude in degrees
- `moon_info(ra_h, dec_deg, observer)` → `{phase_pct, separation_deg, risk}`

All time values use Python `datetime` objects (UTC). The service converts to/from `ephem.Date` internally.

### acp.py
- `assign_telescope(size_arcmin, site_key, telescopes_df, preferred_telescope=None)` → telescope_id
  - When `preferred_telescope` is given, uses it if the target fits the FOV; otherwise falls back to tier-based assignment
  - Performs actual FOV fit check (target size < telescope FOV), matching `arp_acp_generator.py` behavior
- `build_plan(targets, telescope, params)` → `{filename, content, duration_secs, cost_points}`
- `params`: exposure, count, repeat, plan_tier, binning
  - LRGB counts are dynamically computed from `count` (e.g., `[count, max(1, count//2), ...]`), matching the existing `arp_acp_generator.py` logic — not using the static `LRGB_COUNTS` constant

### session.py
- `compute_session(date, site_key, targets, min_hours, moon_filter)` → list of observable target dicts
- `generate_session_plan(observable_targets, telescope, params)` → plan text

### moon_calendar.py
- `compute_moon_data(targets, days, site_key)` → list of `{target_id, night_date, phase, separation, risk}`
- Bulk computation, writes to `moon_data` table and inserts a `moon_calendar_runs` metadata row
- `POST /moon/regenerate` accepts an optional `days` parameter (default 90)
- Computation takes ~25 seconds for 338 targets × 90 days — runs in a background thread. The route inserts a `moon_calendar_runs` row with a `status` column set to `"computing"` and returns immediately with a "computing..." indicator. The background thread updates the row to `status="complete"` when done. The moon page uses HTMX polling (`hx-trigger="every 3s"`) against `GET /moon/status` to check the `moon_calendar_runs` row status — this is safe across multiple Gunicorn workers since the state is in the database, not in-process memory.

### ned.py
- `fetch_ned_coords(arp_number, name)` → `{ra_hours, dec_degrees}` or None
- `fetch_all_ned_coords(targets)` → list of results (with rate limiting)

### importer.py
- `import_seasonal_plan(file_path, db_session)` → import summary
- `import_telescopes(file_path, db_session)` → import summary
- `import_ned_coords(file_path, db_session)` → import summary
- All use upsert semantics (INSERT ON CONFLICT UPDATE)

## Dockerfile

```dockerfile
# Build stage — install dependencies
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage
FROM python:3.12-slim
WORKDIR /app

COPY --from=builder /install /usr/local
COPY app/ app/
COPY scripts/ scripts/
COPY migrations/ migrations/
COPY arp_common.py .
COPY alembic.ini .

# Data files needed by migration script and importer service
COPY Arp_Seasonal_Plan.xlsx .
COPY itelescopesystems.xlsx .
COPY arp_ned_coords.csv .
COPY arp_moon_data.json .
COPY asu.tsv .

RUN useradd -r appuser
USER appuser

EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "app:create_app()"]
```

Notes:
- Python 3.12 (latest stable with broad wheel support)
- Data files are baked in for the initial migration; after that, data lives in PostgreSQL and new files are uploaded through the web UI
- 2 Gunicorn workers — plenty for single-user
- Non-root user for security

## Docker Compose (Local Development)

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://arp:arp_dev@db:5432/arpsurvey
      SECRET_KEY: dev-secret-key-not-for-production
      FLASK_DEBUG: "1"
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./app:/app/app                          # Live reload during development
      - ./migrations:/app/migrations
      - ./scripts:/app/scripts
      - ./arp_common.py:/app/arp_common.py      # Shared module
      - ./Arp_Seasonal_Plan.xlsx:/app/Arp_Seasonal_Plan.xlsx
      - ./itelescopesystems.xlsx:/app/itelescopesystems.xlsx
      - ./arp_ned_coords.csv:/app/arp_ned_coords.csv
      - ./arp_moon_data.json:/app/arp_moon_data.json

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: arp
      POSTGRES_PASSWORD: arp_dev
      POSTGRES_DB: arpsurvey
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U arp -d arpsurvey"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

Usage:
```bash
# Start services
docker-compose up -d

# Run migrations
docker-compose exec app alembic upgrade head

# Run one-time data migration
docker-compose exec app python scripts/migrate_data.py

# Access at http://localhost:8000
```

## Kubernetes Deployment

### deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: arp-survey
  labels:
    app: arp-survey
spec:
  replicas: 1
  selector:
    matchLabels:
      app: arp-survey
  template:
    metadata:
      labels:
        app: arp-survey
    spec:
      initContainers:
      - name: migrate
        image: arp-survey:latest
        command: ["alembic", "upgrade", "head"]
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: arp-survey-secrets
              key: database-url
      containers:
      - name: arp-survey
        image: arp-survey:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: arp-survey-secrets
              key: database-url
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: arp-survey-secrets
              key: flask-secret-key
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 30
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

### service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: arp-survey
spec:
  type: LoadBalancer
  selector:
    app: arp-survey
  ports:
  - port: 80
    targetPort: 8000
    protocol: TCP
```

### secret.yaml.template

**Important:** `k8s/secret.yaml` (the filled-in copy) must be added to `.gitignore` to prevent committing credentials.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: arp-survey-secrets
type: Opaque
stringData:
  database-url: "postgresql://user:pass@postgres-service:5432/arpsurvey"
  flask-secret-key: "CHANGE-ME-to-random-string"
```

### Build and deploy

```bash
# Build and import image into k3s
docker build -t arp-survey:latest .
docker save arp-survey:latest | sudo k3s ctr images import -

# Deploy (copy secret template and edit with real values first)
# cp k8s/secret.yaml.template k8s/secret.yaml && $EDITOR k8s/secret.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# Verify
kubectl get pods -l app=arp-survey
kubectl get svc arp-survey    # MetalLB assigns LAN IP

# One-time data migration (after first deploy)
kubectl exec deploy/arp-survey -- python scripts/migrate_data.py
```

## Data Migration

### Script: `scripts/migrate_data.py`

Reads existing flat files and populates PostgreSQL. Reuses data loaders from `arp_common.py`.

**Invocation:**
```bash
# Full migration
python scripts/migrate_data.py --database-url postgresql://...

# Dry run — parses everything, validates, prints summary, then rolls back
python scripts/migrate_data.py --database-url postgresql://... --dry-run
```

**Steps:**
1. Read `Arp_Seasonal_Plan.xlsx` per-season sheets to determine season membership
2. Read "All Objects" sheet via `load_targets()` for full target data
3. Parse RA/Dec via existing `parse_ra()`/`parse_dec()` functions — these return decimal hours and decimal degrees respectively, matching `targets.ra_hours` and `targets.dec_degrees`. Do NOT use `parse_catalog_coords()` which converts RA to degrees.
4. Insert into `targets` table (upsert by arp_number)
5. Read `arp_ned_coords.csv` directly via `pandas.read_csv()` (not `load_ned_coords()`, which discards `ned_name`) — update `ned_ra_hours`, `ned_dec_degrees`, and `ned_name` columns on matching target rows
6. Read `itelescopesystems.xlsx` via `load_telescopes()` — insert into `telescopes`
7. Read imaging rates via `load_rates()` — insert into `telescope_rates`
8. Read `arp_moon_data.json` — bulk insert into `moon_data`

**Properties:**
- Idempotent: uses `INSERT ... ON CONFLICT DO UPDATE`
- Prints summary with row counts per table
- Validates expected row counts (338 targets, etc.)

### localStorage Migration

A one-time convenience endpoint `POST /import/localstorage` accepts JSON pasted from browser dev console:
- `arp_st` (status dict) → updates `targets.status`
- `arp_log` (log array) → inserts into `imaging_log`

## Dependencies

### requirements.txt

```
flask>=3.0
flask-sqlalchemy>=3.1
sqlalchemy>=2.0
psycopg2-binary>=2.9
alembic>=1.13
gunicorn>=22.0
pandas>=2.2
openpyxl>=3.1
ephem>=4.1
astroquery>=0.4   # NED coordinate fetching (pulls in astropy)
```

### Dev dependencies (not in Docker image)

```
pytest>=8.0
```

## Testing Strategy

- Existing pure-function tests continue to pass (they test `arp_common.py` which is unchanged)
- New tests for the service layer: mock the DB, test computation logic
- New tests for routes: Flask test client, test that pages render and HTMX endpoints return correct fragments
- Migration script supports `--dry-run` flag: runs all parsing and validation, prints the summary, then rolls back the transaction without committing

## Migration Notes: moon_data JSON key mapping

The `arp_moon_data.json` file uses compact keys (`d`, `p`, `s`, `r` for date/phase/separation/risk) and identifies targets by `arp` number. The migration script must:
1. Look up `target_id` by joining on `targets.arp_number`
2. Map `d` → `night_date`, `p` → `phase_pct`, `s` → `separation_deg`, `r` → `risk`
3. Extract global metadata (`generated`, `days`, `next_new`, `next_full`, `phase_cal`) into a `moon_calendar_runs` row

## Deprecation: arp_project.html

Once the server app reaches full parity, `arp_project.html` is deprecated. It should be moved to `docs/legacy/` and a note added to README.md directing users to the server app. During the transition period, both can coexist, but `arp_project.html` will not be updated — it reads from `arp_moon_data.json` and browser localStorage, neither of which the server app writes to.

## Out of Scope

- Authentication / multi-user (single-user personal tool)
- TLS (local network only)
- Horizontal scaling (single replica)
- Persistent volumes (all state in PostgreSQL)
- CI/CD pipeline
- WebSocket / real-time updates (HTMX polling is sufficient for long-running ops like moon regeneration)
