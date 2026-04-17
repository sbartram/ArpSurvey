# ArpSurvey Server Application Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the ArpSurvey CLI toolkit into a Flask server application with full dashboard parity, PostgreSQL persistence, and k8s deployment.

**Architecture:** Flask app factory pattern with SQLAlchemy models, blueprint-based routes, HTMX for interactivity, and a service layer extracting logic from existing CLI scripts. Data moves from flat files to PostgreSQL via a one-time migration script. Deployed as a single Docker container on k3s with MetalLB.

**Tech Stack:** Flask 3.x, SQLAlchemy 2.x, Alembic, Jinja2, HTMX, PostgreSQL 16, Gunicorn, Docker, k3s

**Spec:** `docs/superpowers/specs/2026-04-17-server-app-design.md`

---

## File Map

### New Files to Create

| File | Responsibility |
|------|---------------|
| `app/__init__.py` | Flask app factory (`create_app`) |
| `app/config.py` | Config class reading from env vars |
| `app/models.py` | All SQLAlchemy models (7 tables) |
| `app/routes/__init__.py` | Blueprint registration |
| `app/routes/health.py` | `GET /health` readiness probe |
| `app/routes/overview.py` | `GET /` dashboard overview |
| `app/routes/targets.py` | `PATCH /targets/<id>/status`, `POST /import/localstorage` |
| `app/routes/planner.py` | Session planner page + compute/generate endpoints |
| `app/routes/visibility.py` | Visibility windows page + filter |
| `app/routes/moon.py` | Moon calendar page + regenerate + status |
| `app/routes/log.py` | Imaging log CRUD + CSV export |
| `app/routes/export.py` | Progress export page + downloads |
| `app/routes/generator.py` | Batch ACP generator page + run |
| `app/routes/files.py` | File upload/download hub |
| `app/services/__init__.py` | Empty package init |
| `app/services/astronomy.py` | ephem wrappers: observer, dark window, visibility, moon info |
| `app/services/acp.py` | ACP plan generation: telescope assignment, plan building |
| `app/services/session.py` | Session planner: compute observable targets |
| `app/services/moon_calendar.py` | Moon calendar bulk computation |
| `app/services/ned.py` | NED coordinate fetching |
| `app/services/importer.py` | Excel/CSV → DB import logic |
| `app/static/style.css` | Styles extracted from `arp_project.html` |
| `app/templates/base.html` | Layout with nav, HTMX, flash messages |
| `app/templates/overview.html` | Overview dashboard |
| `app/templates/planner.html` | Tonight's plan |
| `app/templates/visibility.html` | Visibility windows |
| `app/templates/moon.html` | Moon calendar |
| `app/templates/log.html` | Imaging log |
| `app/templates/export.html` | Progress export |
| `app/templates/generator.html` | ACP batch generator |
| `app/templates/files.html` | File upload/download hub |
| `app/templates/partials/planner_table.html` | HTMX fragment: planner results |
| `app/templates/partials/visibility_table.html` | HTMX fragment: visibility results |
| `app/templates/partials/moon_strips.html` | HTMX fragment: moon risk strips |
| `app/templates/partials/log_table.html` | HTMX fragment: log entries table |
| `app/templates/partials/log_stats.html` | HTMX fragment: log statistics |
| `app/templates/partials/plan_list.html` | HTMX fragment: generated plans list |
| `app/templates/partials/upload_result.html` | HTMX fragment: upload outcome |
| `scripts/migrate_data.py` | One-time flat file → DB migration |
| `tests/test_models.py` | Model and DB tests |
| `tests/test_services_astronomy.py` | Astronomy service tests |
| `tests/test_services_acp.py` | ACP service tests |
| `tests/test_services_session.py` | Session service tests |
| `tests/test_services_importer.py` | Importer service tests |
| `tests/test_routes.py` | Route integration tests |
| `requirements.txt` | Python dependencies |
| `alembic.ini` | Alembic config |
| `migrations/env.py` | Alembic environment |
| `migrations/versions/` | Migration scripts directory |
| `Dockerfile` | Multi-stage Docker build |
| `docker-compose.yml` | Local dev: app + PostgreSQL |
| `k8s/deployment.yaml` | k8s Deployment manifest |
| `k8s/service.yaml` | k8s LoadBalancer Service |
| `k8s/secret.yaml.template` | k8s Secret template |

### Files to Modify

| File | Change |
|------|--------|
| `.gitignore` | Add `k8s/secret.yaml` |
| `pyproject.toml` | Add `app` to pythonpath for tests |

### Files NOT Modified

All existing CLI scripts (`arp_acp_generator.py`, `arp_session_planner.py`, `arp_moon_calendar.py`, `arp_ned_coords.py`, `arp_common.py`) remain untouched. The service layer extracts their logic independently.

---

## Task 1: Project Foundation — Dependencies, Config, App Factory

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/routes/__init__.py`
- Create: `app/routes/health.py`
- Create: `app/services/__init__.py`
- Modify: `.gitignore`
- Modify: `pyproject.toml`
- Test: `tests/test_app_factory.py`

- [ ] **Step 1: Create `requirements.txt`**

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
astroquery>=0.4
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: All packages install successfully

- [ ] **Step 3: Create `app/config.py`**

```python
import os


class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://arp:arp_dev@localhost:5432/arpsurvey"
    )
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-not-for-production")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB upload limit
    SQLALCHEMY_TRACK_MODIFICATIONS = False
```

- [ ] **Step 4: Create `app/__init__.py`**

```python
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app(config_class=None):
    app = Flask(__name__)

    if config_class:
        app.config.from_object(config_class)
    else:
        from app.config import Config
        app.config.from_object(Config)

    db.init_app(app)

    from app.routes import register_blueprints
    register_blueprints(app)

    return app
```

- [ ] **Step 5: Create `app/routes/__init__.py`**

```python
def register_blueprints(app):
    from app.routes.health import bp as health_bp
    app.register_blueprint(health_bp)
```

- [ ] **Step 6: Create `app/routes/health.py`**

```python
from flask import Blueprint, jsonify
from app import db

bp = Blueprint("health", __name__)


@bp.route("/health")
def health():
    try:
        db.session.execute(db.text("SELECT 1"))
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 503
```

- [ ] **Step 7: Create `app/services/__init__.py`**

```python
# Service layer package
```

- [ ] **Step 8: Update `.gitignore`**

Add this line to the existing `.gitignore`:

```
k8s/secret.yaml
```

- [ ] **Step 9: Update `pyproject.toml`**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = [".", "app"]
```

- [ ] **Step 10: Write test for app factory**

Create `tests/test_app_factory.py`:

```python
"""Tests for Flask app factory and health endpoint."""

import pytest
from app import create_app, db
from app.config import Config


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_app_creates_successfully(app):
    assert app is not None
    assert app.config["TESTING"] is True


def test_health_endpoint_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
```

- [ ] **Step 11: Run tests to verify**

Run: `pytest tests/test_app_factory.py -v`
Expected: 2 tests PASS

- [ ] **Step 12: Verify existing tests still pass**

Run: `pytest tests/test_arp_common.py tests/test_arp_acp_generator.py -v`
Expected: All existing tests PASS (nothing was modified)

- [ ] **Step 13: Commit**

```bash
git add requirements.txt app/__init__.py app/config.py app/routes/__init__.py \
  app/routes/health.py app/services/__init__.py tests/test_app_factory.py \
  .gitignore pyproject.toml
git commit -m "feat: add Flask app factory, config, health endpoint, and requirements"
```

---

## Task 2: Database Models and Alembic Migration

**Files:**
- Create: `app/models.py`
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/` (directory)
- Test: `tests/test_models.py`

- [ ] **Step 1: Create `app/models.py`**

```python
from datetime import date, datetime, timezone
from app import db


class Target(db.Model):
    __tablename__ = "targets"

    id = db.Column(db.Integer, primary_key=True)
    arp_number = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(120))
    ra_hours = db.Column(db.Float, nullable=False)
    dec_degrees = db.Column(db.Float, nullable=False)
    ra_catalog = db.Column(db.String(30))
    dec_catalog = db.Column(db.String(30))
    ned_ra_hours = db.Column(db.Float)
    ned_dec_degrees = db.Column(db.Float)
    ned_name = db.Column(db.String(120))
    size_arcmin = db.Column(db.Float)
    season = db.Column(db.String(20), nullable=False)
    best_site = db.Column(db.String(40))
    filter_strategy = db.Column(db.String(20))
    status = db.Column(db.String(20), nullable=False, default="Pending")
    notes = db.Column(db.Text)

    imaging_logs = db.relationship("ImagingLog", backref="target", lazy="dynamic")

    @property
    def best_ra(self):
        """Return NED RA if available, otherwise catalog RA."""
        return self.ned_ra_hours if self.ned_ra_hours is not None else self.ra_hours

    @property
    def best_dec(self):
        """Return NED Dec if available, otherwise catalog Dec."""
        return self.ned_dec_degrees if self.ned_dec_degrees is not None else self.dec_degrees


class Telescope(db.Model):
    __tablename__ = "telescopes"

    id = db.Column(db.Integer, primary_key=True)
    telescope_id = db.Column(db.String(10), unique=True, nullable=False)
    site = db.Column(db.String(30), nullable=False)
    fov_arcmin = db.Column(db.Float)
    resolution = db.Column(db.Float)
    filters = db.Column(db.ARRAY(db.String))
    aperture_mm = db.Column(db.Float)

    rates = db.relationship("TelescopeRate", backref="telescope", lazy="dynamic")


class TelescopeRate(db.Model):
    __tablename__ = "telescope_rates"

    id = db.Column(db.Integer, primary_key=True)
    telescope_id = db.Column(db.Integer, db.ForeignKey("telescopes.id"), nullable=False)
    plan_tier = db.Column(db.String(20), nullable=False)
    session_rate = db.Column(db.Float)
    exposure_rate = db.Column(db.Float)

    __table_args__ = (
        db.UniqueConstraint("telescope_id", "plan_tier", name="uq_telescope_plan"),
    )


class ImagingLog(db.Model):
    __tablename__ = "imaging_log"

    id = db.Column(db.Integer, primary_key=True)
    target_id = db.Column(db.Integer, db.ForeignKey("targets.id"), nullable=False)
    date_imaged = db.Column(db.Date, nullable=False)
    telescope_id = db.Column(db.Integer, db.ForeignKey("telescopes.id"))
    filter_strategy = db.Column(db.String(20))
    exposure_minutes = db.Column(db.Float)
    quality = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    telescope = db.relationship("Telescope")


class MoonData(db.Model):
    __tablename__ = "moon_data"

    id = db.Column(db.Integer, primary_key=True)
    target_id = db.Column(db.Integer, db.ForeignKey("targets.id"), nullable=False)
    night_date = db.Column(db.Date, nullable=False)
    phase_pct = db.Column(db.Float)
    separation_deg = db.Column(db.Float)
    risk = db.Column(db.String(1), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("target_id", "night_date", name="uq_moon_target_date"),
        db.Index("ix_moon_date_risk", "night_date", "risk"),
    )


class MoonCalendarRun(db.Model):
    __tablename__ = "moon_calendar_runs"

    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), nullable=False, default="computing")
    generated_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    days = db.Column(db.Integer, nullable=False)
    site_key = db.Column(db.String(30), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    phase_calendar = db.Column(db.JSON, nullable=False)
    next_new_moon = db.Column(db.Date)
    next_full_moon = db.Column(db.Date)


class SessionResult(db.Model):
    __tablename__ = "session_results"

    id = db.Column(db.Integer, primary_key=True)
    computed_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    site_key = db.Column(db.String(30), nullable=False)
    date_local = db.Column(db.Date, nullable=False)
    eve_twilight = db.Column(db.DateTime, nullable=False)
    morn_twilight = db.Column(db.DateTime, nullable=False)
    results = db.Column(db.JSON, nullable=False)


class GeneratedPlan(db.Model):
    __tablename__ = "generated_plans"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    plan_type = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    season = db.Column(db.String(20))
    telescope_id = db.Column(db.Integer, db.ForeignKey("telescopes.id"))
    metadata_ = db.Column("metadata", db.JSON)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    telescope = db.relationship("Telescope")
```

- [ ] **Step 2: Write model tests**

Create `tests/test_models.py`:

```python
"""Tests for SQLAlchemy models."""

import pytest
from datetime import date, datetime, timezone
from app import create_app, db
from app.config import Config
from app.models import (
    Target, Telescope, TelescopeRate, ImagingLog,
    MoonData, MoonCalendarRun, SessionResult, GeneratedPlan,
)


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def session(app):
    with app.app_context():
        yield db.session


def test_target_create_and_query(session):
    t = Target(arp_number=1, name="NGC 2857", ra_hours=9.37, dec_degrees=49.35,
               season="Spring", status="Pending")
    session.add(t)
    session.commit()

    result = session.query(Target).filter_by(arp_number=1).first()
    assert result.name == "NGC 2857"
    assert result.status == "Pending"


def test_target_best_ra_prefers_ned(session):
    t = Target(arp_number=1, name="Test", ra_hours=9.0, dec_degrees=49.0,
               ned_ra_hours=9.1, ned_dec_degrees=49.1, season="Spring")
    session.add(t)
    session.commit()

    assert t.best_ra == 9.1
    assert t.best_dec == 49.1


def test_target_best_ra_falls_back_to_catalog(session):
    t = Target(arp_number=2, name="Test", ra_hours=9.0, dec_degrees=49.0,
               season="Spring")
    session.add(t)
    session.commit()

    assert t.best_ra == 9.0
    assert t.best_dec == 49.0


def test_target_arp_number_unique(session):
    t1 = Target(arp_number=1, name="A", ra_hours=1.0, dec_degrees=1.0, season="Spring")
    t2 = Target(arp_number=1, name="B", ra_hours=2.0, dec_degrees=2.0, season="Spring")
    session.add(t1)
    session.commit()
    session.add(t2)
    with pytest.raises(Exception):
        session.commit()


def test_telescope_and_rate(session):
    tel = Telescope(telescope_id="T17", site="Spain", fov_arcmin=20.5)
    session.add(tel)
    session.commit()

    rate = TelescopeRate(telescope_id=tel.id, plan_tier="Plan-40",
                         session_rate=102.0, exposure_rate=85.0)
    session.add(rate)
    session.commit()

    assert tel.rates.first().plan_tier == "Plan-40"


def test_imaging_log_with_foreign_keys(session):
    target = Target(arp_number=85, name="M51", ra_hours=13.5, dec_degrees=47.2,
                    season="Spring")
    tel = Telescope(telescope_id="T11", site="New Mexico")
    session.add_all([target, tel])
    session.commit()

    log = ImagingLog(target_id=target.id, date_imaged=date(2026, 4, 15),
                     telescope_id=tel.id, filter_strategy="LRGB",
                     exposure_minutes=90, quality=4)
    session.add(log)
    session.commit()

    assert log.target.name == "M51"
    assert log.telescope.telescope_id == "T11"


def test_moon_data_unique_constraint(session):
    target = Target(arp_number=1, name="Test", ra_hours=1.0, dec_degrees=1.0,
                    season="Spring")
    session.add(target)
    session.commit()

    m1 = MoonData(target_id=target.id, night_date=date(2026, 4, 17),
                  phase_pct=45.0, separation_deg=80.0, risk="G")
    m2 = MoonData(target_id=target.id, night_date=date(2026, 4, 17),
                  phase_pct=45.0, separation_deg=80.0, risk="G")
    session.add(m1)
    session.commit()
    session.add(m2)
    with pytest.raises(Exception):
        session.commit()


def test_moon_calendar_run(session):
    run = MoonCalendarRun(
        status="computing", days=90, site_key="New Mexico",
        start_date=date(2026, 4, 17),
        phase_calendar=[{"date": "2026-04-17", "phase_pct": 45.0}],
    )
    session.add(run)
    session.commit()

    assert run.status == "computing"
    assert run.phase_calendar[0]["phase_pct"] == 45.0


def test_generated_plan(session):
    plan = GeneratedPlan(
        filename="Arp_Spring_T17_batch01.txt", plan_type="acp",
        content="; test plan\n#shutdown", season="Spring",
        metadata_={"exposure": 300, "repeat": 3},
    )
    session.add(plan)
    session.commit()

    assert plan.metadata_["exposure"] == 300
```

- [ ] **Step 3: Run model tests**

Run: `pytest tests/test_models.py -v`
Expected: All tests PASS (using SQLite in-memory for unit tests)

- [ ] **Step 4: Create `alembic.ini`**

```ini
[alembic]
script_location = migrations
sqlalchemy.url = postgresql://arp:arp_dev@localhost:5432/arpsurvey

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 5: Create `migrations/env.py`**

```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL from environment if set
db_url = os.environ.get("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

from app.models import Target, Telescope, TelescopeRate, ImagingLog, MoonData, \
    MoonCalendarRun, SessionResult, GeneratedPlan
from app import db
target_metadata = db.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 6: Create `migrations/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 7: Create `migrations/versions/` directory**

```bash
mkdir -p migrations/versions
```

- [ ] **Step 8: Commit**

```bash
git add app/models.py alembic.ini migrations/env.py migrations/script.py.mako \
  migrations/versions/.gitkeep tests/test_models.py
git commit -m "feat: add SQLAlchemy models for all 7 tables and Alembic config"
```

---

## Task 3: Docker Compose and First Migration

**Files:**
- Create: `docker-compose.yml`
- Create: `Dockerfile`

- [ ] **Step 1: Create `Dockerfile`**

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

- [ ] **Step 2: Create `docker-compose.yml`**

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
      - ./app:/app/app
      - ./migrations:/app/migrations
      - ./scripts:/app/scripts
      - ./arp_common.py:/app/arp_common.py
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

- [ ] **Step 3: Start services and generate first Alembic migration**

```bash
docker-compose up -d db
docker-compose exec db pg_isready -U arp -d arpsurvey

# Generate the initial migration from models
DATABASE_URL=postgresql://arp:arp_dev@localhost:5432/arpsurvey \
  alembic revision --autogenerate -m "initial schema"
```

Expected: Migration file created in `migrations/versions/` with all 7 tables.

- [ ] **Step 4: Apply the migration**

```bash
DATABASE_URL=postgresql://arp:arp_dev@localhost:5432/arpsurvey \
  alembic upgrade head
```

Expected: All tables created in PostgreSQL. Verify with:
```bash
docker-compose exec db psql -U arp -d arpsurvey -c "\dt"
```

- [ ] **Step 5: Build and start the full compose stack**

```bash
docker-compose up -d --build
curl http://localhost:8000/health
```

Expected: `{"status": "ok"}`

- [ ] **Step 6: Commit**

```bash
git add Dockerfile docker-compose.yml migrations/versions/
git commit -m "feat: add Dockerfile, docker-compose, and initial Alembic migration"
```

---

## Task 4: Data Migration Script

**Files:**
- Create: `scripts/migrate_data.py`
- Test: `tests/test_migration.py`

- [ ] **Step 1: Write migration test**

Create `tests/test_migration.py`:

```python
"""Tests for the data migration script."""

import pytest
from unittest.mock import patch
from app import create_app, db
from app.config import Config
from app.models import Target, Telescope, TelescopeRate


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


def test_import_targets_creates_338_rows(app):
    """Verify migration can load all 338 targets from the real Excel file."""
    from scripts.migrate_data import import_targets
    with app.app_context():
        count = import_targets(db.session)
        assert count == 338
        t = db.session.query(Target).filter_by(arp_number=85).first()
        assert t is not None
        assert t.season in ("Spring", "Summer", "Autumn", "Winter")


def test_import_telescopes(app):
    """Verify migration loads telescopes from the real Excel file."""
    from scripts.migrate_data import import_telescopes
    with app.app_context():
        count = import_telescopes(db.session)
        assert count > 0
        t17 = db.session.query(Telescope).filter_by(telescope_id="T17").first()
        assert t17 is not None
        assert t17.site is not None


def test_import_ned_coords(app):
    """Verify NED coord import updates existing targets."""
    from scripts.migrate_data import import_targets, import_ned_coords
    with app.app_context():
        import_targets(db.session)
        ned_count = import_ned_coords(db.session)
        assert ned_count > 0
        # At least some targets should have NED coords
        with_ned = db.session.query(Target).filter(
            Target.ned_ra_hours.isnot(None)
        ).count()
        assert with_ned > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_migration.py -v`
Expected: FAIL — `scripts.migrate_data` does not exist yet

- [ ] **Step 3: Create `scripts/__init__.py`**

```python
# Scripts package
```

- [ ] **Step 4: Create `scripts/migrate_data.py`**

```python
#!/usr/bin/env python3
"""
One-time migration: flat files → PostgreSQL.

Usage:
    python scripts/migrate_data.py [--database-url URL] [--dry-run]
"""

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

# Add project root to path so arp_common can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arp_common import (
    SEASON_SHEETS, SITE_TELESCOPES, PLAN_TIERS,
    load_targets, load_telescopes, load_rates,
    parse_ra, parse_dec, DATA_DIR,
)
from app import create_app, db
from app.config import Config
from app.models import (
    Target, Telescope, TelescopeRate, MoonData, MoonCalendarRun,
)


def import_targets(session):
    """Import targets from Arp_Seasonal_Plan.xlsx into the targets table."""
    # First pass: determine season for each target
    season_map = {}
    for season_name, sheet_name in SEASON_SHEETS.items():
        if season_name == "All":
            continue
        try:
            df = load_targets(sheet_name=sheet_name)
            for _, row in df.iterrows():
                arp = int(float(str(row["Arp #"]).strip()))
                season_map[arp] = season_name
        except Exception:
            continue

    # Second pass: load all targets
    df = load_targets(sheet_name="All Objects")
    count = 0

    for _, row in df.iterrows():
        arp = int(float(str(row["Arp #"]).strip()))
        name = str(row["Common Name"]).strip()
        ra_str = str(row["RA (J2000)"]).strip()
        dec_str = str(row["Dec (J2000)"]).strip()

        # Parse RA to decimal hours
        ra_parts = parse_ra(ra_str).split(":")
        ra_hours = float(ra_parts[0]) + float(ra_parts[1]) / 60
        if len(ra_parts) > 2:
            ra_hours += float(ra_parts[2]) / 3600

        # Parse Dec to decimal degrees
        dec_parsed = parse_dec(dec_str)
        sign = -1 if dec_parsed.startswith("-") else 1
        dec_parts = dec_parsed.lstrip("+-").split(":")
        dec_degrees = sign * (
            float(dec_parts[0]) + float(dec_parts[1]) / 60 + float(dec_parts[2]) / 3600
        )

        try:
            size = float(row["Size (arcmin)"])
        except (ValueError, TypeError):
            size = None

        best_site = str(row.get("Best Site", "")).strip()
        filter_strategy = str(row.get("Filter Strategy", "Luminance")).strip()
        season = season_map.get(arp, "Spring")

        existing = session.query(Target).filter_by(arp_number=arp).first()
        if existing:
            existing.name = name
            existing.ra_hours = ra_hours
            existing.dec_degrees = dec_degrees
            existing.ra_catalog = ra_str
            existing.dec_catalog = dec_str
            existing.size_arcmin = size
            existing.season = season
            existing.best_site = best_site
            existing.filter_strategy = filter_strategy
        else:
            target = Target(
                arp_number=arp, name=name, ra_hours=ra_hours, dec_degrees=dec_degrees,
                ra_catalog=ra_str, dec_catalog=dec_str, size_arcmin=size,
                season=season, best_site=best_site, filter_strategy=filter_strategy,
            )
            session.add(target)
        count += 1

    session.flush()
    return count


def import_ned_coords(session):
    """Import NED coordinates from arp_ned_coords.csv."""
    ned_path = DATA_DIR / "arp_ned_coords.csv"
    if not ned_path.exists():
        return 0

    df = pd.read_csv(ned_path)
    count = 0

    for _, row in df.iterrows():
        if row.get("source") != "NED":
            continue
        arp = int(row["arp"])
        target = session.query(Target).filter_by(arp_number=arp).first()
        if target:
            target.ned_ra_hours = float(row["ra_hours"])
            target.ned_dec_degrees = float(row["dec_deg"])
            target.ned_name = str(row.get("ned_name", "")).strip() or None
            count += 1

    session.flush()
    return count


def import_telescopes(session):
    """Import telescope specs from itelescopesystems.xlsx."""
    tels_df = load_telescopes()
    count = 0

    for tel_id, row in tels_df.iterrows():
        # Determine site from SITE_TELESCOPES
        site = "Unknown"
        for site_name, site_tels in SITE_TELESCOPES.items():
            if tel_id in site_tels:
                site = site_name
                break

        fov_x = None
        try:
            fov_x = float(row.get("FOV X (arcmins)", None))
        except (ValueError, TypeError):
            pass

        resolution = None
        try:
            resolution = float(row.get("Resolution (arcsec/px)", None))
        except (ValueError, TypeError):
            pass

        aperture = None
        try:
            aperture = float(row.get("Aperture (mm)", None))
        except (ValueError, TypeError):
            pass

        existing = session.query(Telescope).filter_by(telescope_id=tel_id).first()
        if existing:
            existing.site = site
            existing.fov_arcmin = fov_x
            existing.resolution = resolution
            existing.aperture_mm = aperture
        else:
            tel = Telescope(
                telescope_id=tel_id, site=site, fov_arcmin=fov_x,
                resolution=resolution, aperture_mm=aperture,
            )
            session.add(tel)
        count += 1

    session.flush()
    return count


def import_rates(session):
    """Import telescope imaging rates."""
    rates = load_rates()
    count = 0

    for tel_id_str, rate_data in rates.items():
        tel = session.query(Telescope).filter_by(telescope_id=tel_id_str).first()
        if not tel:
            continue

        for plan_tier in PLAN_TIERS:
            session_rate = rate_data["session"].get(plan_tier)
            exposure_rate = rate_data["exposure"].get(plan_tier)

            existing = session.query(TelescopeRate).filter_by(
                telescope_id=tel.id, plan_tier=plan_tier
            ).first()

            if existing:
                existing.session_rate = session_rate
                existing.exposure_rate = exposure_rate
            else:
                rate = TelescopeRate(
                    telescope_id=tel.id, plan_tier=plan_tier,
                    session_rate=session_rate, exposure_rate=exposure_rate,
                )
                session.add(rate)
            count += 1

    session.flush()
    return count


def import_moon_data(session):
    """Import moon data from arp_moon_data.json."""
    moon_path = DATA_DIR / "arp_moon_data.json"
    if not moon_path.exists():
        return 0, False

    with open(moon_path) as f:
        data = json.load(f)

    # Insert moon_calendar_runs metadata
    run = MoonCalendarRun(
        status="complete",
        generated_at=datetime.fromisoformat(data["generated"]).replace(
            tzinfo=timezone.utc
        ) if "T" in data.get("generated", "") else datetime.now(timezone.utc),
        days=data["days"],
        site_key="New Mexico",
        start_date=date.fromisoformat(data["generated"]),
        phase_calendar=data.get("phase_cal", []),
        next_new_moon=date.fromisoformat(data["next_new"]) if data.get("next_new") else None,
        next_full_moon=date.fromisoformat(data["next_full"]) if data.get("next_full") else None,
    )
    session.add(run)
    session.flush()

    # Build arp_number → target_id lookup
    targets = {t.arp_number: t.id for t in session.query(Target).all()}

    count = 0
    for entry in data["targets"]:
        arp = entry["arp"]
        target_id = targets.get(arp)
        if not target_id:
            continue

        for w in entry["windows"]:
            moon = MoonData(
                target_id=target_id,
                night_date=date.fromisoformat(w["d"]),
                phase_pct=w["p"],
                separation_deg=w["s"],
                risk=w["r"],
            )
            session.add(moon)
            count += 1

    session.flush()
    return count, True


def main():
    parser = argparse.ArgumentParser(description="Migrate flat files to PostgreSQL")
    parser.add_argument("--database-url", default=None,
                        help="PostgreSQL URL (or set DATABASE_URL env var)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and validate only, then rollback")
    args = parser.parse_args()

    if args.database_url:
        import os
        os.environ["DATABASE_URL"] = args.database_url

    app = create_app()

    with app.app_context():
        print("\n=== ArpSurvey Data Migration ===\n")

        target_count = import_targets(db.session)
        print(f"Targets imported:    {target_count}")

        ned_count = import_ned_coords(db.session)
        print(f"NED coords matched:  {ned_count}")

        tel_count = import_telescopes(db.session)
        print(f"Telescopes imported: {tel_count}")

        rate_count = import_rates(db.session)
        print(f"Rate entries:        {rate_count}")

        moon_count, moon_ok = import_moon_data(db.session)
        print(f"Moon data rows:      {moon_count}")

        if args.dry_run:
            db.session.rollback()
            print("\n[DRY RUN] All changes rolled back.\n")
        else:
            db.session.commit()
            print("\n[OK] Migration committed.\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run migration tests**

Run: `pytest tests/test_migration.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Run migration against docker-compose database**

```bash
docker-compose up -d db
DATABASE_URL=postgresql://arp:arp_dev@localhost:5432/arpsurvey \
  python scripts/migrate_data.py
```

Expected output:
```
=== ArpSurvey Data Migration ===

Targets imported:    338
NED coords matched:  332
Telescopes imported: ~24
Rate entries:        ~120
Moon data rows:      ~30420

[OK] Migration committed.
```

- [ ] **Step 7: Commit**

```bash
git add scripts/__init__.py scripts/migrate_data.py tests/test_migration.py
git commit -m "feat: add data migration script (flat files → PostgreSQL)"
```

---

## Task 5: Astronomy Service

**Files:**
- Create: `app/services/astronomy.py`
- Test: `tests/test_services_astronomy.py`

- [ ] **Step 1: Write astronomy service tests**

Create `tests/test_services_astronomy.py`:

```python
"""Tests for the astronomy service layer."""

import datetime
import pytest
from app.services.astronomy import build_observer, dark_window, moon_info


def test_build_observer_new_mexico():
    obs = build_observer("New Mexico", datetime.date(2026, 4, 17))
    assert obs is not None
    assert float(obs.lat) == pytest.approx(0.5759, abs=0.01)  # 33 deg in radians


def test_dark_window_returns_datetimes():
    eve, morn = dark_window("New Mexico", datetime.date(2026, 4, 17))
    assert isinstance(eve, datetime.datetime)
    assert isinstance(morn, datetime.datetime)
    assert morn > eve
    # Dark window should be roughly 8-10 hours in April
    hours = (morn - eve).total_seconds() / 3600
    assert 7 < hours < 12


def test_dark_window_spain():
    eve, morn = dark_window("Spain", datetime.date(2026, 6, 21))
    assert morn > eve
    # Summer nights in Spain are shorter
    hours = (morn - eve).total_seconds() / 3600
    assert 4 < hours < 10


def test_moon_info_returns_phase_sep_risk():
    obs = build_observer("New Mexico", datetime.date(2026, 4, 17))
    info = moon_info(13.5, 47.2, obs)  # M51 approx coords
    assert "phase_pct" in info
    assert "separation_deg" in info
    assert "risk" in info
    assert info["risk"] in ("G", "M", "A")
    assert 0 <= info["phase_pct"] <= 100
    assert 0 <= info["separation_deg"] <= 180
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_services_astronomy.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Create `app/services/astronomy.py`**

```python
"""
Astronomy service — wraps ephem for dark window, visibility, and moon calculations.

All public functions return Python datetime objects (UTC). ephem.Date conversions
are handled internally.
"""

import datetime
import math

import ephem

from arp_common import OBSERVATORIES, moon_risk as _moon_risk


def build_observer(site_key, date):
    """Build a configured ephem.Observer for a site and date."""
    cfg = OBSERVATORIES[site_key]
    observer = ephem.Observer()
    observer.lat = cfg["lat"]
    observer.lon = cfg["lon"]
    observer.elevation = cfg["elev"]
    observer.horizon = "-18"

    utc_noon = (12 - cfg["utc_offset"]) % 24
    observer.date = date.strftime(f"%Y/%m/%d {utc_noon:02d}:00:00")
    return observer


def _ephem_to_datetime(ephem_date):
    """Convert ephem.Date float to a timezone-aware UTC datetime."""
    return ephem.Date(ephem_date).datetime().replace(tzinfo=datetime.timezone.utc)


def dark_window(site_key, date):
    """
    Compute astronomical twilight boundaries for a given site and date.
    Returns (evening_twilight, morning_twilight) as UTC datetimes.
    """
    observer = build_observer(site_key, date)
    sun = ephem.Sun()

    eve_twi = observer.next_setting(sun, use_center=True)
    observer.date = eve_twi
    morn_twi = observer.next_rising(sun, use_center=True)

    return _ephem_to_datetime(eve_twi), _ephem_to_datetime(morn_twi)


def target_visibility(ra_h, dec_deg, site_key, eve_dt, morn_dt):
    """
    Compute observable window for a target during the dark window.

    Args:
        ra_h: Right ascension in decimal hours
        dec_deg: Declination in decimal degrees
        site_key: Observatory name
        eve_dt: Evening twilight (UTC datetime)
        morn_dt: Morning twilight (UTC datetime)

    Returns dict with {rise, set, transit, hours} as datetimes/float,
    or None if not observable.
    """
    cfg = OBSERVATORIES[site_key]
    observer = ephem.Observer()
    observer.lat = cfg["lat"]
    observer.lon = cfg["lon"]
    observer.elevation = cfg["elev"]
    observer.horizon = str(cfg["min_el"])

    target = ephem.FixedBody()
    # Convert decimal hours to ephem RA string
    h = int(ra_h)
    m = int((ra_h - h) * 60)
    s = ((ra_h - h) * 60 - m) * 60
    target._ra = f"{h:02d}:{m:02d}:{s:05.2f}"
    # Convert decimal degrees to ephem Dec string
    sign = "-" if dec_deg < 0 else "+"
    ad = abs(dec_deg)
    dd = int(ad)
    dm = int((ad - dd) * 60)
    ds = ((ad - dd) * 60 - dm) * 60
    target._dec = f"{sign}{dd:02d}:{dm:02d}:{ds:04.1f}"

    eve_twi = ephem.Date(eve_dt)
    morn_twi = ephem.Date(morn_dt)

    # Check altitude at twilight boundaries
    observer.date = eve_twi
    target.compute(observer)
    alt_eve = math.degrees(target.alt)

    observer.date = morn_twi
    target.compute(observer)
    alt_morn = math.degrees(target.alt)

    # Determine observable start
    if alt_eve >= cfg["min_el"]:
        obs_start = eve_twi
    else:
        observer.date = eve_twi
        try:
            rise = float(observer.next_rising(target))
            obs_start = rise if rise < morn_twi else None
        except ephem.AlwaysUpError:
            obs_start = eve_twi
        except ephem.NeverUpError:
            return None

    if obs_start is None:
        return None

    # Determine observable end
    if alt_morn >= cfg["min_el"]:
        obs_end = morn_twi
    else:
        observer.date = obs_start
        try:
            sett = float(observer.next_setting(target))
            obs_end = min(sett, float(morn_twi))
        except ephem.AlwaysUpError:
            obs_end = float(morn_twi)
        except ephem.NeverUpError:
            obs_end = float(obs_start)

    if obs_end <= obs_start:
        return None

    obs_hrs = (obs_end - float(obs_start)) * 24

    # Transit time
    observer.date = obs_start
    try:
        trans = float(observer.next_transit(target))
        if trans > float(morn_twi):
            trans = (float(obs_start) + obs_end) / 2
    except Exception:
        trans = (float(obs_start) + obs_end) / 2

    return {
        "rise": _ephem_to_datetime(obs_start),
        "set": _ephem_to_datetime(obs_end),
        "transit": _ephem_to_datetime(trans),
        "hours": round(obs_hrs, 1),
    }


def alt_at_time(ra_h, dec_deg, site_key, dt):
    """Return altitude in degrees at a specific UTC datetime."""
    cfg = OBSERVATORIES[site_key]
    observer = ephem.Observer()
    observer.lat = cfg["lat"]
    observer.lon = cfg["lon"]
    observer.elevation = cfg["elev"]
    observer.date = ephem.Date(dt)

    target = ephem.FixedBody()
    h = int(ra_h)
    m = int((ra_h - h) * 60)
    s = ((ra_h - h) * 60 - m) * 60
    target._ra = f"{h:02d}:{m:02d}:{s:05.2f}"
    sign = "-" if dec_deg < 0 else "+"
    ad = abs(dec_deg)
    dd = int(ad)
    dm = int((ad - dd) * 60)
    ds = ((ad - dd) * 60 - dm) * 60
    target._dec = f"{sign}{dd:02d}:{dm:02d}:{ds:04.1f}"

    target.compute(observer)
    return math.degrees(target.alt)


def moon_info(ra_h, dec_deg, observer):
    """
    Compute moon phase, separation, and risk for a target.

    Args:
        ra_h: RA in decimal hours
        dec_deg: Dec in decimal degrees
        observer: configured ephem.Observer (with date set)

    Returns dict: {phase_pct, separation_deg, risk}
    """
    moon = ephem.Moon()
    target = ephem.FixedBody()

    h = int(ra_h)
    m = int((ra_h - h) * 60)
    s = ((ra_h - h) * 60 - m) * 60
    target._ra = f"{h:02d}:{m:02d}:{s:05.2f}"
    sign = "-" if dec_deg < 0 else "+"
    ad = abs(dec_deg)
    dd = int(ad)
    dm = int((ad - dd) * 60)
    ds = ((ad - dd) * 60 - dm) * 60
    target._dec = f"{sign}{dd:02d}:{dm:02d}:{ds:04.1f}"

    moon.compute(observer)
    target.compute(observer)

    phase = moon.phase
    sep = math.degrees(ephem.separation(moon, target))
    risk = _moon_risk(phase, sep)

    return {
        "phase_pct": round(phase, 1),
        "separation_deg": round(sep, 1),
        "risk": risk,
    }
```

- [ ] **Step 4: Run astronomy tests**

Run: `pytest tests/test_services_astronomy.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/astronomy.py tests/test_services_astronomy.py
git commit -m "feat: add astronomy service (observer, dark window, moon info)"
```

---

## Task 6: ACP Service

**Files:**
- Create: `app/services/acp.py`
- Test: `tests/test_services_acp.py`

- [ ] **Step 1: Write ACP service tests**

Create `tests/test_services_acp.py`:

```python
"""Tests for the ACP plan generation service."""

import pytest
from app.services.acp import assign_telescope, build_plan, compute_lrgb_counts


def test_compute_lrgb_counts_default():
    counts = compute_lrgb_counts(2)
    assert counts == [2, 1, 1, 1]


def test_compute_lrgb_counts_count_4():
    counts = compute_lrgb_counts(4)
    assert counts == [4, 2, 2, 2]


def test_compute_lrgb_counts_count_1():
    counts = compute_lrgb_counts(1)
    assert counts == [1, 1, 1, 1]  # max(1, 0) = 1


def test_assign_telescope_compact_target():
    """Compact target (<3 arcmin) should get a high-res scope."""
    from arp_common import load_telescopes
    tels = load_telescopes()
    result = assign_telescope(1.5, "Spain", tels)
    assert result in ("T17", "T32", "T21", "T11", "T25")


def test_assign_telescope_preferred_override():
    from arp_common import load_telescopes
    tels = load_telescopes()
    result = assign_telescope(1.5, "Spain", tels, preferred_telescope="T20")
    assert result == "T20"


def test_assign_telescope_preferred_invalid_falls_back():
    from arp_common import load_telescopes
    tels = load_telescopes()
    result = assign_telescope(1.5, "Spain", tels, preferred_telescope="TXYZ")
    # Should fall back to tier-based assignment
    assert result in ("T17", "T32", "T21", "T11", "T25")


def test_build_plan_produces_valid_acp():
    targets = [
        {"arp": 85, "name": "M51", "ra_hours": 13.5, "dec_degrees": 47.2,
         "size_arcmin": 11.0, "filter_strategy": "LRGB"},
    ]
    params = {"exposure": 300, "count": 2, "repeat": 3,
              "plan_tier": "Plan-40", "binning": 1}
    result = build_plan(targets, "T20", "Spring", params)

    assert "filename" in result
    assert "content" in result
    assert "duration_secs" in result
    assert "cost_points" in result
    assert "#shutdown" in result["content"]
    assert "Arp085_M51" in result["content"]
    assert "#BillingMethod Session" in result["content"]
    assert "#repeat 3" in result["content"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_services_acp.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Create `app/services/acp.py`**

```python
"""
ACP plan generation service.

Extracted from arp_acp_generator.py. Generates iTelescope ACP-format
observing plans from target data.
"""

from arp_common import (
    TELESCOPE_TIERS, SITE_TELESCOPES, LRGB_FILTERS, LUM_FILTERS,
    OVERHEAD_PER_TARGET_SECS, OVERHEAD_SESSION_SECS,
    sanitize_name,
)


def compute_lrgb_counts(count):
    """Compute per-filter exposure counts for LRGB from the luminance count."""
    return [count, max(1, count // 2), max(1, count // 2), max(1, count // 2)]


def parse_fov(telescope_row):
    """Return FOV in arcminutes, or None."""
    try:
        x = float(telescope_row["FOV X (arcmins)"])
        y = float(telescope_row["FOV Y (arcmins)"])
        return min(x, y)
    except (ValueError, TypeError, KeyError):
        return None


def assign_telescope(size_arcmin, site_key, telescopes_df, preferred_telescope=None):
    """
    Determine the best telescope for a target.

    Args:
        size_arcmin: Target angular size
        site_key: Observatory site string (e.g. "New Mexico / Spain" or "Spain")
        telescopes_df: DataFrame from load_telescopes(), indexed by telescope ID
        preferred_telescope: Force a specific telescope if valid

    Returns telescope ID string.
    """
    if preferred_telescope and preferred_telescope in telescopes_df.index:
        return preferred_telescope

    # Find tier candidates
    candidates = []
    for min_s, max_s, tel_ids in TELESCOPE_TIERS:
        if min_s <= size_arcmin < max_s:
            candidates = tel_ids
            break

    # Filter by site preference
    site_preferred = []
    for sk, site_tels in SITE_TELESCOPES.items():
        if sk.lower() in site_key.lower():
            site_preferred.extend(site_tels)

    ordered = ([t for t in candidates if t in site_preferred] +
               [t for t in candidates if t not in site_preferred])

    for tel_id in ordered:
        if tel_id not in telescopes_df.index:
            continue
        fov = parse_fov(telescopes_df.loc[tel_id])
        if fov and size_arcmin * 1.5 <= fov:
            return tel_id

    # Fallback
    for tel_id in candidates:
        if tel_id in telescopes_df.index:
            return tel_id

    return "T11"


def format_duration(total_secs):
    """Return human-readable duration string."""
    h = int(total_secs // 3600)
    m = int((total_secs % 3600) // 60)
    return f"{h}h {m:02d}m" if h > 0 else f"{m}m"


def build_plan(targets, telescope_id, season, params):
    """
    Generate an ACP plan from target data.

    Args:
        targets: List of dicts with keys: arp, name, ra_hours, dec_degrees,
                 size_arcmin, filter_strategy
        telescope_id: Telescope string ID (e.g. "T20")
        season: Season name
        params: Dict with keys: exposure, count, repeat, plan_tier, binning

    Returns dict: {filename, content, duration_secs, cost_points}
    """
    exposure = params["exposure"]
    count = params["count"]
    repeat = params["repeat"]
    plan_tier = params.get("plan_tier", "Plan-40")

    lrgb_counts = compute_lrgb_counts(count)
    lum_counts = [count]

    plan_name = f"Arp_{season}_{telescope_id}_batch01"

    # Calculate duration
    exposure_secs = 0
    for t in targets:
        strategy = t.get("filter_strategy", "Luminance")
        if strategy == "LRGB":
            exposure_secs += sum(lrgb_counts) * exposure
        else:
            exposure_secs += sum(lum_counts) * exposure

    imaging_secs = exposure_secs * repeat
    target_overhead = len(targets) * OVERHEAD_PER_TARGET_SECS
    total_secs = (exposure_secs + target_overhead) * repeat + OVERHEAD_SESSION_SECS

    # Build plan text
    lines = []
    lines.append(f"; ============================================================")
    lines.append(f"; Arp Catalog Observing Plan")
    lines.append(f"; Plan Name    : {plan_name}")
    lines.append(f"; Telescope    : {telescope_id}")
    lines.append(f"; Season       : {season}")
    lines.append(f"; Targets      : {len(targets)}")
    lines.append(f"; Imaging time : {format_duration(imaging_secs)}")
    lines.append(f"; Total duration: {format_duration(total_secs)}")
    lines.append(f"; Generated    : Arp ACP Generator")
    lines.append(f"; ============================================================")
    lines.append("")
    lines.append("#BillingMethod Session")
    lines.append("#RESUME")
    lines.append("#FIRSTLAST")
    lines.append(f"#repeat {repeat}")
    lines.append("")

    for t in targets:
        arp = t["arp"]
        name = sanitize_name(f"Arp{int(arp):03d}_{t['name']}")
        ra = t["ra_hours"]
        dec = t["dec_degrees"]
        size = t.get("size_arcmin", "?")
        strategy = t.get("filter_strategy", "Luminance")

        if strategy == "LRGB":
            filters = ",".join(LRGB_FILTERS)
            counts = ",".join(str(c) for c in lrgb_counts)
            intervals = ",".join(str(exposure) for _ in lrgb_counts)
            binnings = "1,2,2,2"
        else:
            filters = LUM_FILTERS[0]
            counts = str(lum_counts[0])
            intervals = str(exposure)
            binnings = "1"

        lines.append(f"; --- Arp {arp}: {t['name']}  (size: {size}') ---")
        lines.append(f"#count {counts}")
        lines.append(f"#interval {intervals}")
        lines.append(f"#binning {binnings}")
        lines.append(f"#filter {filters}")
        lines.append(f"{name}\t{ra:.6f}\t{dec:.6f}")
        lines.append("")

    lines.append("#shutdown")

    return {
        "filename": f"{plan_name}.txt",
        "content": "\n".join(lines),
        "duration_secs": total_secs,
        "cost_points": None,  # Cost requires rate lookup from DB
    }
```

- [ ] **Step 4: Run ACP service tests**

Run: `pytest tests/test_services_acp.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/acp.py tests/test_services_acp.py
git commit -m "feat: add ACP plan generation service"
```

---

## Task 7: Session Planner and Moon Calendar Services

**Files:**
- Create: `app/services/session.py`
- Create: `app/services/moon_calendar.py`
- Test: `tests/test_services_session.py`

- [ ] **Step 1: Write session service tests**

Create `tests/test_services_session.py`:

```python
"""Tests for the session planner service."""

import datetime
import pytest
from app.services.session import compute_session


def test_compute_session_returns_observable_targets():
    targets = [
        {"arp_number": 85, "name": "M51", "ra_hours": 13.5, "dec_degrees": 47.2,
         "size_arcmin": 11.0, "filter_strategy": "LRGB", "best_site": "New Mexico / Spain"},
    ]
    results = compute_session(
        date=datetime.date(2026, 4, 17),
        site_key="New Mexico",
        targets=targets,
        min_hours=1.0,
        moon_filter="",
    )
    # M51 should be observable from NM in April
    assert len(results) >= 1
    r = results[0]
    assert r["arp"] == 85
    assert r["hours"] > 0
    assert r["moon"]["risk"] in ("G", "M", "A")


def test_compute_session_filters_by_min_hours():
    targets = [
        {"arp_number": 85, "name": "M51", "ra_hours": 13.5, "dec_degrees": 47.2,
         "size_arcmin": 11.0, "filter_strategy": "LRGB", "best_site": "New Mexico / Spain"},
    ]
    results = compute_session(
        date=datetime.date(2026, 4, 17),
        site_key="New Mexico",
        targets=targets,
        min_hours=99,  # Impossible requirement
        moon_filter="",
    )
    assert len(results) == 0


def test_compute_session_filters_by_site():
    targets = [
        {"arp_number": 1, "name": "Test", "ra_hours": 13.5, "dec_degrees": 47.2,
         "size_arcmin": 3.0, "filter_strategy": "Luminance",
         "best_site": "Australia"},
    ]
    results = compute_session(
        date=datetime.date(2026, 4, 17),
        site_key="New Mexico",
        targets=targets,
        min_hours=1.0,
        moon_filter="",
    )
    # Australia-only target should not appear for NM
    assert len(results) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_services_session.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Create `app/services/session.py`**

```python
"""
Session planner service.

Extracted from arp_session_planner.py. Computes which targets are observable
on a given night, applies moon avoidance, sorts by transit time.
"""

import datetime

from arp_common import OBSERVATORIES, SITE_MAP

from app.services.astronomy import (
    build_observer, dark_window, target_visibility, moon_info,
)
from app.services.acp import assign_telescope


def compute_session(date, site_key, targets, min_hours, moon_filter):
    """
    Compute observable targets for a given night.

    Args:
        date: observation date (datetime.date)
        site_key: observatory name (e.g. "New Mexico")
        targets: list of dicts with keys: arp_number, name, ra_hours, dec_degrees,
                 size_arcmin, filter_strategy, best_site
        min_hours: minimum observable hours
        moon_filter: "" (all), "GM" (good+marginal), "G" (good only)

    Returns list of observable target dicts sorted by transit time.
    """
    cfg = OBSERVATORIES[site_key]
    eve_dt, morn_dt = dark_window(site_key, date)

    results = []
    for t in targets:
        # Check site compatibility
        best_site = t.get("best_site", "Any site") or "Any site"
        compatible = SITE_MAP.get(best_site, ["New Mexico"])
        if site_key not in compatible:
            continue

        ra_h = t["ra_hours"]
        dec_deg = t["dec_degrees"]

        vis = target_visibility(ra_h, dec_deg, site_key, eve_dt, morn_dt)
        if not vis or vis["hours"] < min_hours:
            continue

        # Moon info at transit
        obs = build_observer(site_key, date)
        import ephem
        obs.date = ephem.Date(vis["transit"])
        mi = moon_info(ra_h, dec_deg, obs)

        # Apply moon filter
        if moon_filter == "G" and mi["risk"] != "G":
            continue
        if moon_filter == "GM" and mi["risk"] == "A":
            continue

        utc_offset = cfg["utc_offset"]

        results.append({
            "arp": t["arp_number"],
            "name": t["name"],
            "ra_hours": ra_h,
            "dec_degrees": dec_deg,
            "size_arcmin": t.get("size_arcmin"),
            "filter_strategy": t.get("filter_strategy", "Luminance"),
            "hours": vis["hours"],
            "rise": vis["rise"].isoformat(),
            "set": vis["set"].isoformat(),
            "transit": vis["transit"].isoformat(),
            "start_local": _utc_to_local_str(vis["rise"], utc_offset),
            "end_local": _utc_to_local_str(vis["set"], utc_offset),
            "transit_local": _utc_to_local_str(vis["transit"], utc_offset),
            "moon": mi,
        })

    results.sort(key=lambda r: r["transit"])
    return results


def _utc_to_local_str(utc_dt, utc_offset):
    """Convert UTC datetime to local HH:MM string."""
    local = utc_dt + datetime.timedelta(hours=utc_offset)
    return local.strftime("%H:%M")
```

- [ ] **Step 4: Create `app/services/moon_calendar.py`**

```python
"""
Moon calendar computation service.

Extracted from arp_moon_calendar.py. Computes moon phase/separation/risk
for all targets over a date range.
"""

import datetime
import math

import ephem

from arp_common import OBSERVATORIES, moon_risk


def compute_moon_data(targets, days, site_key):
    """
    Compute moon data for all targets over a date range.

    Args:
        targets: list of dicts with keys: id, arp_number, ra_hours, dec_degrees
        days: number of days to compute
        site_key: observatory name

    Returns:
        (rows, metadata) where:
            rows: list of {target_id, night_date, phase_pct, separation_deg, risk}
            metadata: {phase_calendar, next_new_moon, next_full_moon, start_date}
    """
    cfg = OBSERVATORIES[site_key]
    observer = ephem.Observer()
    observer.lat = cfg["lat"]
    observer.lon = cfg["lon"]
    observer.elevation = cfg["elev"]

    today = datetime.date.today()
    utc_hour = (24 - cfg["utc_offset"]) % 24

    # Phase calendar (global moon phase per night)
    phase_calendar = []
    moon_obj = ephem.Moon()
    for d in range(days):
        night = today + datetime.timedelta(days=d)
        observer.date = night.strftime(f"%Y/%m/%d {utc_hour:02d}:00:00")
        moon_obj.compute(observer)
        phase_calendar.append({
            "date": night.isoformat(),
            "phase_pct": round(moon_obj.phase, 1),
        })

    # Next new/full moon
    next_new = ephem.Date(
        ephem.next_new_moon(today.strftime("%Y/%m/%d"))
    ).datetime().date()
    next_full = ephem.Date(
        ephem.next_full_moon(today.strftime("%Y/%m/%d"))
    ).datetime().date()

    # Per-target, per-night rows
    rows = []
    moon = ephem.Moon()

    for t in targets:
        target = ephem.FixedBody()
        ra_h = t["ra_hours"]
        dec_deg = t["dec_degrees"]

        h = int(ra_h)
        m = int((ra_h - h) * 60)
        s = ((ra_h - h) * 60 - m) * 60
        target._ra = f"{h:02d}:{m:02d}:{s:05.2f}"

        sign = "-" if dec_deg < 0 else "+"
        ad = abs(dec_deg)
        dd = int(ad)
        dm = int((ad - dd) * 60)
        ds = ((ad - dd) * 60 - dm) * 60
        target._dec = f"{sign}{dd:02d}:{dm:02d}:{ds:04.1f}"

        for d in range(days):
            night = today + datetime.timedelta(days=d)
            observer.date = night.strftime(f"%Y/%m/%d {utc_hour:02d}:00:00")
            moon.compute(observer)
            target.compute(observer)

            phase = moon.phase
            sep = math.degrees(ephem.separation(moon, target))

            rows.append({
                "target_id": t["id"],
                "night_date": night,
                "phase_pct": round(phase, 1),
                "separation_deg": round(sep, 1),
                "risk": moon_risk(phase, sep),
            })

    metadata = {
        "phase_calendar": phase_calendar,
        "next_new_moon": next_new,
        "next_full_moon": next_full,
        "start_date": today,
    }

    return rows, metadata
```

- [ ] **Step 5: Run session service tests**

Run: `pytest tests/test_services_session.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/session.py app/services/moon_calendar.py \
  tests/test_services_session.py
git commit -m "feat: add session planner and moon calendar services"
```

---

## Task 8: Importer Service

**Files:**
- Create: `app/services/importer.py`
- Create: `app/services/ned.py`
- Test: `tests/test_services_importer.py`

- [ ] **Step 1: Write importer service tests**

Create `tests/test_services_importer.py`:

```python
"""Tests for the file import service."""

import pytest
from io import BytesIO
from app import create_app, db
from app.config import Config
from app.models import Target, Telescope
from app.services.importer import detect_file_type


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


def test_detect_seasonal_plan():
    assert detect_file_type("Arp_Seasonal_Plan.xlsx") == "seasonal_plan"


def test_detect_telescope_file():
    assert detect_file_type("itelescopesystems.xlsx") == "telescopes"


def test_detect_ned_coords():
    assert detect_file_type("arp_ned_coords.csv") == "ned_coords"


def test_detect_unknown():
    assert detect_file_type("random.txt") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_services_importer.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Create `app/services/importer.py`**

```python
"""
File import service.

Handles uploading and importing Excel/CSV files into the database.
Detection is filename-based; parsing reuses arp_common data loaders.
"""

import tempfile
from pathlib import Path

import pandas as pd

from arp_common import (
    SEASON_SHEETS, SITE_TELESCOPES, PLAN_TIERS,
    load_targets, load_telescopes, load_rates,
    parse_ra, parse_dec,
)
from app import db
from app.models import Target, Telescope, TelescopeRate


def detect_file_type(filename):
    """Detect file type from filename. Returns type string or None."""
    name = filename.lower()
    if "seasonal_plan" in name and name.endswith(".xlsx"):
        return "seasonal_plan"
    if "itelescopesystems" in name and name.endswith(".xlsx"):
        return "telescopes"
    if "ned_coords" in name and name.endswith(".csv"):
        return "ned_coords"
    return None


def import_seasonal_plan(file_storage, session):
    """
    Import target data from an uploaded Arp_Seasonal_Plan.xlsx.
    Returns summary dict: {imported, updated, errors}.
    """
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        file_storage.save(tmp)
        tmp_path = Path(tmp.name)

    try:
        # Determine seasons
        season_map = {}
        for season_name, sheet_name in SEASON_SHEETS.items():
            if season_name == "All":
                continue
            try:
                df = pd.read_excel(tmp_path, sheet_name=sheet_name, header=None)
                header_row = None
                for i, row in df.iterrows():
                    if any(str(v).strip() == "Arp #" for v in row.values):
                        header_row = i
                        break
                if header_row is not None:
                    df.columns = df.iloc[header_row]
                    df = df.iloc[header_row + 1:].reset_index(drop=True)
                    df = df.dropna(subset=["Arp #"])
                    for _, row in df.iterrows():
                        arp = int(float(str(row["Arp #"]).strip()))
                        season_map[arp] = season_name
            except Exception:
                continue

        # Load all targets
        df = pd.read_excel(tmp_path, sheet_name="All Objects", header=None)
        header_row = None
        for i, row in df.iterrows():
            if any(str(v).strip() == "Arp #" for v in row.values):
                header_row = i
                break
        df.columns = df.iloc[header_row]
        df = df.iloc[header_row + 1:].reset_index(drop=True)
        df = df.dropna(subset=["Arp #"])
        df.columns = [str(c).strip() for c in df.columns]

        imported = 0
        updated = 0

        for _, row in df.iterrows():
            arp = int(float(str(row["Arp #"]).strip()))
            name = str(row["Common Name"]).strip()
            ra_str = str(row["RA (J2000)"]).strip()
            dec_str_raw = str(row["Dec (J2000)"]).strip()

            ra_parts = parse_ra(ra_str).split(":")
            ra_hours = float(ra_parts[0]) + float(ra_parts[1]) / 60
            if len(ra_parts) > 2:
                ra_hours += float(ra_parts[2]) / 3600

            dec_parsed = parse_dec(dec_str_raw)
            sign = -1 if dec_parsed.startswith("-") else 1
            dec_parts = dec_parsed.lstrip("+-").split(":")
            dec_degrees = sign * (
                float(dec_parts[0]) + float(dec_parts[1]) / 60 + float(dec_parts[2]) / 3600
            )

            try:
                size = float(row["Size (arcmin)"])
            except (ValueError, TypeError):
                size = None

            best_site = str(row.get("Best Site", "")).strip()
            filter_strategy = str(row.get("Filter Strategy", "Luminance")).strip()
            season = season_map.get(arp, "Spring")

            existing = session.query(Target).filter_by(arp_number=arp).first()
            if existing:
                existing.name = name
                existing.ra_hours = ra_hours
                existing.dec_degrees = dec_degrees
                existing.ra_catalog = ra_str
                existing.dec_catalog = dec_str_raw
                existing.size_arcmin = size
                existing.season = season
                existing.best_site = best_site
                existing.filter_strategy = filter_strategy
                updated += 1
            else:
                target = Target(
                    arp_number=arp, name=name, ra_hours=ra_hours,
                    dec_degrees=dec_degrees, ra_catalog=ra_str,
                    dec_catalog=dec_str_raw, size_arcmin=size,
                    season=season, best_site=best_site,
                    filter_strategy=filter_strategy,
                )
                session.add(target)
                imported += 1

        session.commit()
        return {"imported": imported, "updated": updated, "errors": 0}
    finally:
        tmp_path.unlink(missing_ok=True)


def import_telescopes_file(file_storage, session):
    """Import telescope data from uploaded itelescopesystems.xlsx."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        file_storage.save(tmp)
        tmp_path = Path(tmp.name)

    try:
        tels_df = load_telescopes(filepath=str(tmp_path))
        rates_data = load_rates(filepath=str(tmp_path))
        tel_count = 0
        rate_count = 0

        for tel_id, row in tels_df.iterrows():
            site = "Unknown"
            for site_name, site_tels in SITE_TELESCOPES.items():
                if tel_id in site_tels:
                    site = site_name
                    break

            fov_x = None
            try:
                fov_x = float(row.get("FOV X (arcmins)", None))
            except (ValueError, TypeError):
                pass

            existing = session.query(Telescope).filter_by(telescope_id=tel_id).first()
            if existing:
                existing.site = site
                existing.fov_arcmin = fov_x
            else:
                tel = Telescope(telescope_id=tel_id, site=site, fov_arcmin=fov_x)
                session.add(tel)
            tel_count += 1

        session.flush()

        for tel_id_str, rate_data in rates_data.items():
            tel = session.query(Telescope).filter_by(telescope_id=tel_id_str).first()
            if not tel:
                continue
            for plan_tier in PLAN_TIERS:
                existing = session.query(TelescopeRate).filter_by(
                    telescope_id=tel.id, plan_tier=plan_tier
                ).first()
                if existing:
                    existing.session_rate = rate_data["session"].get(plan_tier)
                    existing.exposure_rate = rate_data["exposure"].get(plan_tier)
                else:
                    rate = TelescopeRate(
                        telescope_id=tel.id, plan_tier=plan_tier,
                        session_rate=rate_data["session"].get(plan_tier),
                        exposure_rate=rate_data["exposure"].get(plan_tier),
                    )
                    session.add(rate)
                rate_count += 1

        session.commit()
        return {"telescopes": tel_count, "rates": rate_count}
    finally:
        tmp_path.unlink(missing_ok=True)


def import_ned_coords_file(file_storage, session):
    """Import NED coordinates from uploaded arp_ned_coords.csv."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        file_storage.save(tmp)
        tmp_path = Path(tmp.name)

    try:
        df = pd.read_csv(tmp_path)
        count = 0

        for _, row in df.iterrows():
            if row.get("source") != "NED":
                continue
            arp = int(row["arp"])
            target = session.query(Target).filter_by(arp_number=arp).first()
            if target:
                target.ned_ra_hours = float(row["ra_hours"])
                target.ned_dec_degrees = float(row["dec_deg"])
                target.ned_name = str(row.get("ned_name", "")).strip() or None
                count += 1

        session.commit()
        return {"updated": count}
    finally:
        tmp_path.unlink(missing_ok=True)
```

- [ ] **Step 4: Create `app/services/ned.py`**

```python
"""
NED coordinate fetching service.

Extracted from arp_ned_coords.py. Provides NED lookups with rate limiting.
"""

import re
import time
import time

try:
    from astroquery.ipac.ned import Ned
    from astroquery.exceptions import RemoteServiceError
    HAS_ASTROQUERY = True
except ImportError:
    HAS_ASTROQUERY = False

from arp_common import parse_catalog_coords


def ned_query_names(raw_name, arp_num):
    """Return list of names to try querying NED with, in priority order."""
    name = raw_name.strip()
    primary = re.split(r'\s*\+\s*', name)[0].strip()
    primary = re.sub(r'\s+(comp|A|B|C)$', '', primary, flags=re.IGNORECASE).strip()

    candidates = [primary]
    if name != primary:
        candidates.append(name)
    candidates.append(f"Arp {arp_num}")

    seen = set()
    return [c for c in candidates if not (c in seen or seen.add(c))]


def fetch_ned_coords(arp_number, name, fallback_ra_deg=0.0, fallback_dec=0.0):
    """
    Query NED for a single target's coordinates.

    Returns dict: {ra_hours, dec_degrees, ned_name, source}
    """
    if not HAS_ASTROQUERY:
        return {"ra_hours": fallback_ra_deg / 15.0, "dec_degrees": fallback_dec,
                "ned_name": "", "source": "catalog"}

    candidates = ned_query_names(name, arp_number)

    for query_name in candidates:
        try:
            result = Ned.query_object(query_name)
            if result is None or len(result) == 0:
                continue
            row = result[0]
            ra_deg = float(row["RA"])
            dec_deg = float(row["DEC"])
            ned_name = str(row["Object Name"]).strip()
            return {
                "ra_hours": ra_deg / 15.0,
                "dec_degrees": dec_deg,
                "ned_name": ned_name,
                "source": "NED",
            }
        except Exception:
            continue

    return {"ra_hours": fallback_ra_deg / 15.0, "dec_degrees": fallback_dec,
            "ned_name": "", "source": "catalog"}


def fetch_all_ned_coords(targets, delay=0.5):
    """
    Fetch NED coordinates for all targets with rate limiting.

    Args:
        targets: list of dicts with keys: arp_number, name
        delay: seconds between NED queries (default 0.5)

    Returns list of dicts: [{arp_number, ra_hours, dec_degrees, ned_name, source}]
    """
    results = []
    for t in targets:
        result = fetch_ned_coords(t["arp_number"], t["name"])
        result["arp_number"] = t["arp_number"]
        results.append(result)
        if result["source"] == "NED":
            time.sleep(delay)
    return results
```

- [ ] **Step 5: Run importer tests**

Run: `pytest tests/test_services_importer.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/importer.py app/services/ned.py tests/test_services_importer.py
git commit -m "feat: add file import and NED coordinate services"
```

---

## Task 9: Base Template and Static CSS

**Files:**
- Create: `app/static/style.css`
- Create: `app/templates/base.html`

- [ ] **Step 1: Create `app/static/style.css`**

Extract styles from `arp_project.html` lines 8-93. This is the full CSS from the existing dashboard:

```css
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#ffffff;--bg2:#f5f5f3;--bg3:#ededea;
  --text:#1a1a18;--text2:#6b6b67;--text3:#9b9b96;
  --border:rgba(0,0,0,0.12);--border2:rgba(0,0,0,0.2);
  --green:#27500A;--green-bg:#EAF3DE;
  --amber:#633806;--amber-bg:#FAEEDA;
  --red:#791F1F;--red-bg:#FCEBEB;
  --blue:#0C447C;--blue-bg:#E6F1FB;
  --accent:#1D9E75;--accent-dark:#0F6E56;
  --purple:#7F77DD;
  --radius:8px;--radius-lg:12px;
}
@media(prefers-color-scheme:dark){:root{
  --bg:#1a1a18;--bg2:#242422;--bg3:#2e2e2b;
  --text:#e8e8e4;--text2:#9b9b96;--text3:#6b6b67;
  --border:rgba(255,255,255,0.1);--border2:rgba(255,255,255,0.18);
  --green:#97C459;--green-bg:#1a2e08;
  --amber:#EF9F27;--amber-bg:#2a1e06;
  --red:#F09595;--red-bg:#2a0808;
  --blue:#85B7EB;--blue-bg:#061a2a;
}}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg3);color:var(--text);font-size:14px;line-height:1.5}
.app{max-width:1400px;margin:0 auto;padding:0}
header{background:var(--bg);border-bottom:0.5px solid var(--border);padding:12px 24px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:50}
.header-title{font-size:16px;font-weight:500}
.header-sub{font-size:12px;color:var(--text2);margin-top:1px}
.header-meta{display:flex;gap:16px;align-items:center;font-size:12px;color:var(--text2)}
.nav{background:var(--bg);border-bottom:0.5px solid var(--border);display:flex;padding:0 24px;overflow-x:auto}
.nav a{padding:10px 18px;font-size:13px;text-decoration:none;color:var(--text2);border-bottom:2px solid transparent;margin-bottom:-0.5px;white-space:nowrap}
.nav a.active{color:var(--text);font-weight:500;border-bottom-color:var(--accent)}
.nav a:hover{color:var(--text)}
.main{padding:20px 24px}
.grid4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:16px}
.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:16px}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:16px}
.metric{background:var(--bg2);border-radius:var(--radius);padding:12px 16px}
.metric .lbl{font-size:11px;color:var(--text2);margin-bottom:4px;text-transform:uppercase;letter-spacing:.05em}
.metric .val{font-size:24px;font-weight:500}
.metric .sub{font-size:11px;color:var(--text3);margin-top:2px}
.card{background:var(--bg);border:0.5px solid var(--border);border-radius:var(--radius-lg);padding:16px 20px;margin-bottom:16px}
.card-title{font-size:11px;font-weight:500;color:var(--text2);margin-bottom:12px;text-transform:uppercase;letter-spacing:.05em}
.badge{display:inline-block;font-size:11px;font-weight:500;padding:2px 8px;border-radius:4px}
.G{color:var(--green);background:var(--green-bg)}
.M{color:var(--amber);background:var(--amber-bg)}
.A{color:var(--red);background:var(--red-bg)}
.done{color:var(--green);background:var(--green-bg)}
.pending{color:var(--blue);background:var(--blue-bg)}
.sched{color:var(--amber);background:var(--amber-bg)}
.skip{color:var(--text2);background:var(--bg2)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;padding:7px 10px;font-size:10px;font-weight:500;color:var(--text2);border-bottom:0.5px solid var(--border);text-transform:uppercase;letter-spacing:.05em;white-space:nowrap;background:var(--bg2)}
td{padding:7px 10px;border-bottom:0.5px solid var(--border);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--bg2)}
.filter-row{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center}
input[type=text],input[type=date],input[type=number],select,textarea{
  font-size:13px;padding:6px 10px;border-radius:var(--radius);
  border:0.5px solid var(--border2);background:var(--bg);color:var(--text);font-family:inherit}
input:focus,select:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:1px}
textarea{resize:vertical;min-height:60px}
.btn{padding:6px 14px;font-size:13px;border-radius:var(--radius);border:0.5px solid var(--border2);background:var(--bg2);color:var(--text);cursor:pointer;font-family:inherit;text-decoration:none;display:inline-block}
.btn:hover{background:var(--bg3)}
.btn-primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn-primary:hover{background:var(--accent-dark)}
.progress-bg{background:var(--border);border-radius:3px;height:5px}
.progress-fill{background:var(--accent);border-radius:3px;height:5px;transition:width .3s}
.tbl-wrap{overflow-x:auto;border-radius:var(--radius-lg);border:0.5px solid var(--border)}
.empty-state{padding:40px;text-align:center;color:var(--text3);font-size:13px}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}
.form-group label{display:block;font-size:11px;color:var(--text2);margin-bottom:4px;text-transform:uppercase;letter-spacing:.04em}
.form-group input,.form-group select,.form-group textarea{width:100%}
.strip-day{display:inline-block;width:8px;height:14px;border-radius:1px;margin:0 0.5px;vertical-align:middle}
.toast{position:fixed;bottom:20px;right:20px;background:#27500A;color:#EAF3DE;padding:9px 18px;border-radius:var(--radius);font-size:13px;opacity:0;transition:opacity .25s;pointer-events:none;z-index:999;box-shadow:0 4px 12px rgba(0,0,0,.2)}
.toast.show{opacity:1}
.htmx-indicator{display:none}
.htmx-request .htmx-indicator{display:inline}
.htmx-request.htmx-indicator{display:inline}
```

- [ ] **Step 2: Create `app/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{% block title %}Arp Catalog{% endblock %} — iTelescope Project</title>
<link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
</head>
<body>
<div class="app">

<header>
  <div>
    <div class="header-title">Arp Catalog &middot; iTelescope Project</div>
    <div class="header-sub">338 peculiar galaxies &middot; Plan-40 membership</div>
  </div>
  <div class="header-meta">
    {% block header_meta %}{% endblock %}
  </div>
</header>

<nav class="nav">
  <a href="{{ url_for('overview.index') }}" class="{% if request.endpoint == 'overview.index' %}active{% endif %}">Overview</a>
  <a href="{{ url_for('planner.index') }}" class="{% if request.endpoint and request.endpoint.startswith('planner.') %}active{% endif %}">Tonight's plan</a>
  <a href="{{ url_for('visibility.index') }}" class="{% if request.endpoint and request.endpoint.startswith('visibility.') %}active{% endif %}">Visibility</a>
  <a href="{{ url_for('moon.index') }}" class="{% if request.endpoint and request.endpoint.startswith('moon.') %}active{% endif %}">Moon calendar</a>
  <a href="{{ url_for('log.index') }}" class="{% if request.endpoint and request.endpoint.startswith('log.') %}active{% endif %}">Imaging log</a>
  <a href="{{ url_for('export.index') }}" class="{% if request.endpoint and request.endpoint.startswith('export.') %}active{% endif %}">Progress export</a>
  <a href="{{ url_for('generator.index') }}" class="{% if request.endpoint and request.endpoint.startswith('generator.') %}active{% endif %}">ACP generator</a>
  <a href="{{ url_for('files.index') }}" class="{% if request.endpoint and request.endpoint.startswith('files.') %}active{% endif %}">Files</a>
</nav>

<div class="main">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for category, message in messages %}
      <div class="card" style="border-left:3px solid var(--accent);margin-bottom:12px">
        {{ message }}
      </div>
    {% endfor %}
  {% endwith %}

  {% block content %}{% endblock %}
</div>

</div>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add app/static/style.css app/templates/base.html
git commit -m "feat: add base template with nav and extracted CSS from dashboard"
```

---

## Task 10: Overview Route and Template

**Files:**
- Create: `app/routes/overview.py`
- Create: `app/templates/overview.html`
- Modify: `app/routes/__init__.py`
- Test: `tests/test_routes.py`

- [ ] **Step 1: Create `app/routes/overview.py`**

```python
from datetime import date, timedelta

from flask import Blueprint, render_template
from sqlalchemy import func

from app import db
from app.models import Target, ImagingLog, MoonData, MoonCalendarRun

bp = Blueprint("overview", __name__)


@bp.route("/")
def index():
    total = db.session.query(func.count(Target.id)).scalar()
    done = db.session.query(func.count(Target.id)).filter(Target.status == "Done").scalar()
    remaining = total - done
    log_count = db.session.query(func.count(ImagingLog.id)).scalar()
    total_exposure = db.session.query(
        func.coalesce(func.sum(ImagingLog.exposure_minutes), 0)
    ).scalar()

    # Season progress
    seasons = db.session.query(
        Target.season,
        func.count(Target.id).label("total"),
        func.count(Target.id).filter(Target.status == "Done").label("done"),
    ).group_by(Target.season).all()

    season_progress = []
    for s in seasons:
        pct = round(s.done / s.total * 100) if s.total > 0 else 0
        season_progress.append({
            "name": s.season, "total": s.total, "done": s.done, "pct": pct
        })

    # Moon strip (next 60 days)
    today = date.today()
    moon_run = db.session.query(MoonCalendarRun).filter_by(
        status="complete"
    ).order_by(MoonCalendarRun.generated_at.desc()).first()

    phase_calendar = moon_run.phase_calendar if moon_run else []

    # Re-image queue
    reimage = db.session.query(ImagingLog).filter(
        ImagingLog.quality <= 2
    ).order_by(ImagingLog.date_imaged.desc()).limit(20).all()

    return render_template("overview.html",
        total=total, done=done, remaining=remaining,
        log_count=log_count, total_exposure=total_exposure,
        season_progress=season_progress,
        phase_calendar=phase_calendar[:60],
        reimage=reimage,
        done_pct=round(done / total * 100) if total > 0 else 0,
    )
```

- [ ] **Step 2: Create `app/templates/overview.html`**

```html
{% extends "base.html" %}
{% block title %}Overview{% endblock %}

{% block content %}
<div class="grid4">
  <div class="metric">
    <div class="lbl">Total targets</div>
    <div class="val">{{ total }}</div>
    <div class="sub">Full Arp catalog</div>
  </div>
  <div class="metric">
    <div class="lbl">Imaged</div>
    <div class="val" style="color:var(--accent)">{{ done }}</div>
    <div class="sub">{{ done_pct }}% complete</div>
  </div>
  <div class="metric">
    <div class="lbl">Remaining</div>
    <div class="val">{{ remaining }}</div>
    <div class="sub">targets to image</div>
  </div>
  <div class="metric">
    <div class="lbl">Log entries</div>
    <div class="val">{{ log_count }}</div>
    <div class="sub">{{ "%.1f"|format(total_exposure / 60) }}h total exposure</div>
  </div>
</div>

<div class="grid2">
  <div class="card">
    <div class="card-title">Season progress</div>
    {% for s in season_progress %}
    <div style="margin-bottom:10px">
      <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px">
        <span>{{ s.name }}</span>
        <span style="color:var(--text2)">{{ s.done }}/{{ s.total }}</span>
      </div>
      <div class="progress-bg">
        <div class="progress-fill" style="width:{{ s.pct }}%"></div>
      </div>
    </div>
    {% endfor %}
  </div>

  <div class="card">
    <div class="card-title">Moon calendar — next 60 days</div>
    <div style="margin-bottom:8px;line-height:1.4">
      {% for day in phase_calendar %}
        {% if day.phase_pct < 25 %}
          <span class="strip-day" style="background:#97C459" title="{{ day.date }}: {{ day.phase_pct }}%"></span>
        {% elif day.phase_pct < 75 %}
          <span class="strip-day" style="background:#EF9F27" title="{{ day.date }}: {{ day.phase_pct }}%"></span>
        {% else %}
          <span class="strip-day" style="background:#E24B4A" title="{{ day.date }}: {{ day.phase_pct }}%"></span>
        {% endif %}
      {% endfor %}
    </div>
    <div style="font-size:11px;color:var(--text3)">
      <span style="display:inline-block;width:10px;height:10px;background:#97C459;border-radius:2px;vertical-align:middle"></span> Dark
      <span style="margin-left:8px;display:inline-block;width:10px;height:10px;background:#EF9F27;border-radius:2px;vertical-align:middle"></span> Moderate
      <span style="margin-left:8px;display:inline-block;width:10px;height:10px;background:#E24B4A;border-radius:2px;vertical-align:middle"></span> Bright
    </div>
  </div>
</div>

<div class="card">
  <div class="card-title">Re-image queue (quality &le; 2&starf;)</div>
  {% if reimage %}
  <div class="tbl-wrap">
    <table>
      <thead><tr><th>Arp</th><th>Name</th><th>Date</th><th>Quality</th><th>Notes</th></tr></thead>
      <tbody>
        {% for log in reimage %}
        <tr>
          <td>{{ log.target.arp_number }}</td>
          <td>{{ log.target.name }}</td>
          <td>{{ log.date_imaged }}</td>
          <td>{{ "★" * log.quality }}{{ "☆" * (5 - log.quality) }}</td>
          <td>{{ log.notes or "" }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <div class="empty-state">No re-image candidates yet</div>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 3: Update `app/routes/__init__.py` to register overview blueprint**

```python
def register_blueprints(app):
    from app.routes.health import bp as health_bp
    from app.routes.overview import bp as overview_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(overview_bp)
```

- [ ] **Step 4: Write route test**

Create `tests/test_routes.py`:

```python
"""Tests for Flask routes."""

import pytest
from app import create_app, db
from app.config import Config
from app.models import Target


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        # Seed a target for overview
        t = Target(arp_number=1, name="Test Galaxy", ra_hours=9.0,
                   dec_degrees=49.0, season="Spring", status="Pending")
        db.session.add(t)
        db.session.commit()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_overview_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Arp Catalog" in response.data
    assert b"Total targets" in response.data


def test_overview_shows_target_count(client):
    response = client.get("/")
    assert b"1" in response.data  # 1 target seeded
```

- [ ] **Step 5: Run route tests**

Run: `pytest tests/test_routes.py -v`
Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/routes/overview.py app/routes/__init__.py \
  app/templates/overview.html tests/test_routes.py
git commit -m "feat: add overview dashboard route and template"
```

---

## Task 11: Remaining Route Stubs and Blueprint Registration

This task creates all remaining routes as minimal stubs so the nav bar links work and the app is browsable. Each route renders a basic template. Subsequent tasks will flesh out the functionality.

**Files:**
- Create: `app/routes/targets.py`
- Create: `app/routes/planner.py`
- Create: `app/routes/visibility.py`
- Create: `app/routes/moon.py`
- Create: `app/routes/log.py`
- Create: `app/routes/export.py`
- Create: `app/routes/generator.py`
- Create: `app/routes/files.py`
- Create: `app/templates/planner.html`
- Create: `app/templates/visibility.html`
- Create: `app/templates/moon.html`
- Create: `app/templates/log.html`
- Create: `app/templates/export.html`
- Create: `app/templates/generator.html`
- Create: `app/templates/files.html`
- Create: all `app/templates/partials/*.html`
- Modify: `app/routes/__init__.py`

- [ ] **Step 1: Create all route stubs**

Each route file follows the same pattern. Create them all:

`app/routes/targets.py`:
```python
from flask import Blueprint, jsonify, request
from app import db
from app.models import Target, ImagingLog

bp = Blueprint("targets", __name__)


@bp.route("/targets/<int:target_id>/status", methods=["PATCH"])
def update_status(target_id):
    target = db.session.get(Target, target_id)
    if not target:
        return "Not found", 404

    cycle = {"Pending": "Scheduled", "Scheduled": "Done", "Done": "Skip", "Skip": "Pending"}
    target.status = cycle.get(target.status, "Pending")
    db.session.commit()

    status_class = {"Pending": "pending", "Scheduled": "sched", "Done": "done", "Skip": "skip"}
    css = status_class.get(target.status, "pending")
    return f'<span class="badge {css}" hx-patch="/targets/{target_id}/status" hx-swap="outerHTML" style="cursor:pointer">{target.status}</span>'


@bp.route("/import/localstorage", methods=["POST"])
def import_localstorage():
    data = request.get_json()
    if not data:
        return "No JSON data", 400

    status_count = 0
    log_count = 0

    # Import statuses
    statuses = data.get("arp_st", {})
    for arp_str, status in statuses.items():
        target = db.session.query(Target).filter_by(arp_number=int(arp_str)).first()
        if target and status in ("Pending", "Scheduled", "Done", "Skip"):
            target.status = status
            status_count += 1

    # Import imaging log
    logs = data.get("arp_log", [])
    for entry in logs:
        target = db.session.query(Target).filter_by(arp_number=int(entry.get("arp", 0))).first()
        if target:
            log = ImagingLog(
                target_id=target.id,
                date_imaged=entry.get("date"),
                filter_strategy=entry.get("filters"),
                exposure_minutes=entry.get("exp"),
                quality=entry.get("quality", 3),
                notes=entry.get("notes", ""),
            )
            db.session.add(log)
            log_count += 1

    db.session.commit()
    return f"<div class='card'>Imported {status_count} statuses, {log_count} log entries.</div>"
```

`app/routes/planner.py`:
```python
from flask import Blueprint, render_template

bp = Blueprint("planner", __name__)


@bp.route("/planner")
def index():
    return render_template("planner.html")
```

`app/routes/visibility.py`:
```python
from flask import Blueprint, render_template

bp = Blueprint("visibility", __name__)


@bp.route("/visibility")
def index():
    return render_template("visibility.html")
```

`app/routes/moon.py`:
```python
from flask import Blueprint, render_template

bp = Blueprint("moon", __name__)


@bp.route("/moon")
def index():
    return render_template("moon.html")
```

`app/routes/log.py`:
```python
from flask import Blueprint, render_template

bp = Blueprint("log", __name__)


@bp.route("/log")
def index():
    return render_template("log.html")
```

`app/routes/export.py`:
```python
from flask import Blueprint, render_template

bp = Blueprint("export", __name__)


@bp.route("/export")
def index():
    return render_template("export.html")
```

`app/routes/generator.py`:
```python
from flask import Blueprint, render_template

bp = Blueprint("generator", __name__)


@bp.route("/generator")
def index():
    return render_template("generator.html")
```

`app/routes/files.py`:
```python
from flask import Blueprint, render_template

bp = Blueprint("files", __name__)


@bp.route("/files")
def index():
    return render_template("files.html")
```

- [ ] **Step 2: Create stub templates**

Each stub template extends base.html with a placeholder. Create all 7:

`app/templates/planner.html`:
```html
{% extends "base.html" %}
{% block title %}Tonight's Plan{% endblock %}
{% block content %}
<div class="card">
  <div class="card-title">Session planner</div>
  <div class="empty-state">Session planner — implementation pending</div>
</div>
{% endblock %}
```

`app/templates/visibility.html`:
```html
{% extends "base.html" %}
{% block title %}Visibility{% endblock %}
{% block content %}
<div class="card">
  <div class="card-title">Visibility windows</div>
  <div class="empty-state">Run "Tonight's plan" first to populate visibility data.</div>
</div>
{% endblock %}
```

`app/templates/moon.html`:
```html
{% extends "base.html" %}
{% block title %}Moon Calendar{% endblock %}
{% block content %}
<div class="card">
  <div class="card-title">Moon calendar</div>
  <div class="empty-state">Moon calendar — implementation pending</div>
</div>
{% endblock %}
```

`app/templates/log.html`:
```html
{% extends "base.html" %}
{% block title %}Imaging Log{% endblock %}
{% block content %}
<div class="card">
  <div class="card-title">Imaging log</div>
  <div class="empty-state">Imaging log — implementation pending</div>
</div>
{% endblock %}
```

`app/templates/export.html`:
```html
{% extends "base.html" %}
{% block title %}Progress Export{% endblock %}
{% block content %}
<div class="card">
  <div class="card-title">Progress export</div>
  <div class="empty-state">Progress export — implementation pending</div>
</div>
{% endblock %}
```

`app/templates/generator.html`:
```html
{% extends "base.html" %}
{% block title %}ACP Generator{% endblock %}
{% block content %}
<div class="card">
  <div class="card-title">ACP batch generator</div>
  <div class="empty-state">ACP batch generator — implementation pending</div>
</div>
{% endblock %}
```

`app/templates/files.html`:
```html
{% extends "base.html" %}
{% block title %}Files{% endblock %}
{% block content %}
<div class="card">
  <div class="card-title">File management</div>
  <div class="empty-state">File upload/download — implementation pending</div>
</div>
{% endblock %}
```

- [ ] **Step 3: Create empty partial templates**

```bash
mkdir -p app/templates/partials
```

Create each as an empty file for now (they'll be populated when their parent routes are fleshed out):

`app/templates/partials/planner_table.html`: `<!-- planner results -->`
`app/templates/partials/visibility_table.html`: `<!-- visibility results -->`
`app/templates/partials/moon_strips.html`: `<!-- moon strips -->`
`app/templates/partials/log_table.html`: `<!-- log table -->`
`app/templates/partials/log_stats.html`: `<!-- log stats -->`
`app/templates/partials/plan_list.html`: `<!-- plan list -->`
`app/templates/partials/upload_result.html`: `<!-- upload result -->`

- [ ] **Step 4: Update `app/routes/__init__.py`**

```python
def register_blueprints(app):
    from app.routes.health import bp as health_bp
    from app.routes.overview import bp as overview_bp
    from app.routes.targets import bp as targets_bp
    from app.routes.planner import bp as planner_bp
    from app.routes.visibility import bp as visibility_bp
    from app.routes.moon import bp as moon_bp
    from app.routes.log import bp as log_bp
    from app.routes.export import bp as export_bp
    from app.routes.generator import bp as generator_bp
    from app.routes.files import bp as files_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(overview_bp)
    app.register_blueprint(targets_bp)
    app.register_blueprint(planner_bp)
    app.register_blueprint(visibility_bp)
    app.register_blueprint(moon_bp)
    app.register_blueprint(log_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(generator_bp)
    app.register_blueprint(files_bp)
```

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS, no import errors

- [ ] **Step 6: Test in browser**

```bash
docker-compose up -d --build
```

Navigate to `http://localhost:8000` — all 8 nav tabs should be clickable and render their stub content.

- [ ] **Step 7: Commit**

```bash
git add app/routes/ app/templates/ 
git commit -m "feat: add all route stubs and templates with working navigation"
```

---

## Task 12: Kubernetes Manifests

**Files:**
- Create: `k8s/deployment.yaml`
- Create: `k8s/service.yaml`
- Create: `k8s/secret.yaml.template`

- [ ] **Step 1: Create `k8s/deployment.yaml`**

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

- [ ] **Step 2: Create `k8s/service.yaml`**

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

- [ ] **Step 3: Create `k8s/secret.yaml.template`**

```yaml
# IMPORTANT: Copy to k8s/secret.yaml and fill in real values.
# k8s/secret.yaml is gitignored — NEVER commit it.
apiVersion: v1
kind: Secret
metadata:
  name: arp-survey-secrets
type: Opaque
stringData:
  database-url: "postgresql://user:pass@postgres-service:5432/arpsurvey"
  flask-secret-key: "CHANGE-ME-to-random-string"
```

- [ ] **Step 4: Commit**

```bash
git add k8s/
git commit -m "feat: add k8s deployment, service, and secret template"
```

---

## Checkpoint: Browsable App with Data

At this point the application is fully browsable with working navigation, real data in PostgreSQL, docker-compose for local dev, and k8s manifests ready. The remaining tasks flesh out each page's interactive features.

**Verify:**
```bash
docker-compose up -d --build
DATABASE_URL=postgresql://arp:arp_dev@localhost:5432/arpsurvey alembic upgrade head
DATABASE_URL=postgresql://arp:arp_dev@localhost:5432/arpsurvey python scripts/migrate_data.py
curl http://localhost:8000/health
# Open http://localhost:8000 — overview should show 338 targets, season progress
```

---

## Tasks 13+: Route Feature Implementation

The remaining work implements the interactive features for each page. Each is independent and follows the same pattern: update the route to query data and call services, update the template to render forms and results, create HTMX partial templates for dynamic responses.

These tasks are **large and should each be broken into their own sub-plan** when execution begins. The ordering below reflects dependencies:

### Task 13: Imaging Log (CRUD)
- `POST /log` — create log entry, auto-set target status to "Done"
- `DELETE /log/<id>` — remove entry
- `GET /log/export` — CSV download
- Full `log.html` template with form, table, filtering, stats panel
- Partials: `log_table.html`, `log_stats.html`

### Task 14: Session Planner
- `POST /planner/compute` — run `session.compute_session()`, store result in `session_results`
- `POST /planner/generate-acp` — generate ACP plan, store in `generated_plans`
- Full `planner.html` with form (date, site, min hours, moon filter), results table, ACP preview
- Status toggling via existing `PATCH /targets/<id>/status`
- Partials: `planner_table.html`

### Task 15: Visibility Windows
- `GET /visibility` — read latest `session_results` row
- `GET /visibility/filter` — filtered/sorted HTMX response
- Full `visibility.html` with filter controls and visibility table
- Partial: `visibility_table.html`

### Task 16: Moon Calendar
- `POST /moon/regenerate` — background thread + DB status flag
- `GET /moon/status` — HTMX poll endpoint
- `GET /moon/filter` — filtered moon strips
- Full `moon.html` with metrics, bar chart, per-target strips
- Partial: `moon_strips.html`

### Task 17: ACP Batch Generator
- `POST /generator/run` — run ACP generation for a season, store plans
- Full `generator.html` with season/telescope/param form
- Result display with plan links

### Task 18: File Upload/Download
- `POST /files/upload` — detect type, run importer, return summary
- `GET /files/plans/<id>/download` — serve plan file
- `GET /files/plans` — list generated plans
- Full `files.html` with upload area and plan list
- Partials: `plan_list.html`, `upload_result.html`

### Task 19: Progress Export
- `GET /export/csv` — target status CSV
- `GET /export/targets` — target list with coords
- `GET /export/status-json` — JSON snapshot
- Full `export.html` with summary stats and download buttons

### Task 20: Final Integration
- Run full test suite
- Verify all pages render correctly with real data
- Test docker-compose end-to-end
- Build Docker image, test k8s deployment
- All existing CLI tests still pass
