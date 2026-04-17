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
│   ├── config.py                # Config class (DATABASE_URL, SECRET_KEY, UPLOAD_MAX_SIZE)
│   ├── models.py                # SQLAlchemy models
│   ├── routes/
│   │   ├── __init__.py          # Blueprint registration
│   │   ├── overview.py          # GET / — dashboard overview
│   │   ├── planner.py           # GET /planner, POST /planner/compute, POST /planner/generate-acp
│   │   ├── visibility.py        # GET /visibility
│   │   ├── moon.py              # GET /moon, POST /moon/regenerate
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
| session_rate | float | | Points per session |
| exposure_rate | float | | Points per minute |
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

### generated_plans

Stored ACP plan files.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | serial | PK | |
| filename | varchar(200) | NOT NULL | e.g. "Arp_Spring_T17_001.txt" |
| plan_type | varchar(20) | NOT NULL | "acp" or "session" |
| content | text | NOT NULL | Full plan text |
| season | varchar(20) | | |
| telescope_id | varchar(10) | | |
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
| `/planner/compute` | POST | Planner results table | "Compute session" button |
| `/planner/generate-acp` | POST | ACP preview + download link | "Generate ACP plan" button |
| `/targets/<id>/status` | PATCH | Updated status badge | Click on status cell |
| `/visibility/filter` | GET | Filtered visibility table | Filter/sort controls |
| `/moon/regenerate` | POST | Refreshed moon page content | "Regenerate" button |
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
- `dark_window(observer, date)` → `(evening_twilight_ms, morning_twilight_ms)`
- `target_visibility(ra_h, dec_deg, observer, eve_ms, morn_ms)` → `{rise_ms, set_ms, transit_ms, hours}`
- `alt_at_time(ra_h, dec_deg, observer, time_ms)` → altitude in degrees
- `moon_info(ra_h, dec_deg, observer)` → `{phase_pct, separation_deg, risk}`

### acp.py
- `assign_telescope(size_arcmin, site_key, telescopes_df)` → telescope_id
- `build_plan(targets, telescope, params)` → `{filename, content, duration_secs, cost_points}`
- `params`: exposure, count, repeat, plan_tier, binning

### session.py
- `compute_session(date, site_key, targets, min_hours, moon_filter)` → list of observable target dicts
- `generate_session_plan(observable_targets, telescope, params)` → plan text

### moon_calendar.py
- `compute_moon_data(targets, days, site_key)` → list of `{target_id, night_date, phase, separation, risk}`
- Bulk computation, writes to `moon_data` table

### ned.py
- `fetch_ned_coords(arp_number, name)` → `{ra_hours, dec_degrees}` or None
- `fetch_all_ned_coords(targets)` → list of results (with rate limiting)

### importer.py
- `import_seasonal_plan(file_path, db_session)` → import summary
- `import_telescopes(file_path, db_session)` → import summary
- `import_ned_coords(file_path, db_session)` → import summary
- All use upsert semantics (INSERT ON CONFLICT UPDATE)

## Docker Compose (Local Development)

```yaml
version: "3.8"

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://arp:arp_dev@db:5432/arpsurvey
      SECRET_KEY: dev-secret-key-not-for-production
      FLASK_ENV: development
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./app:/app/app          # Live reload during development
      - ./migrations:/app/migrations

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

# Deploy
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
python scripts/migrate_data.py --database-url postgresql://...
```

**Steps:**
1. Read `Arp_Seasonal_Plan.xlsx` per-season sheets to determine season membership
2. Read "All Objects" sheet via `load_targets()` for full target data
3. Parse RA/Dec via existing `parse_ra()`/`parse_dec()` functions
4. Insert into `targets` table (upsert by arp_number)
5. Read `arp_ned_coords.csv` via `load_ned_coords()` — update NED columns
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
```

### Dev dependencies (not in Docker image)

```
pytest>=8.0
astroquery>=0.4   # Only for NED coord fetching
```

## Testing Strategy

- Existing pure-function tests continue to pass (they test `arp_common.py` which is unchanged)
- New tests for the service layer: mock the DB, test computation logic
- New tests for routes: Flask test client, test that pages render and HTMX endpoints return correct fragments
- Migration script has a dry-run mode for testing

## Out of Scope

- Authentication / multi-user (single-user personal tool)
- TLS (local network only)
- Horizontal scaling (single replica)
- Persistent volumes (all state in PostgreSQL)
- CI/CD pipeline
- WebSocket / real-time updates (HTMX polling is sufficient for long-running ops)
