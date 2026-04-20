# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python toolkit for systematically imaging all 338 objects in Halton Arp's *Atlas of Peculiar Galaxies* using iTelescope.net remote telescopes. Two interfaces: **CLI scripts** (original pipeline) and a **Flask server app** (on `feature/server-app` branch) with browser UI, PostgreSQL, and k8s deployment.

## Commands

```bash
# === Server App (feature/server-app branch) ===
# Start local dev environment
docker-compose up -d

# Run Alembic migrations
PYTHONPATH=. DATABASE_URL=postgresql://arp:arp_dev@localhost:5432/arpsurvey .venv/bin/alembic upgrade head

# Run data migration (one-time, populates DB from flat files)
PYTHONPATH=. DATABASE_URL=postgresql://arp:arp_dev@localhost:5432/arpsurvey .venv/bin/python scripts/migrate_data.py

# Import telescope CCD specs and target magnitudes
PYTHONPATH=. DATABASE_URL=postgresql://arp:arp_dev@localhost:5432/arpsurvey .venv/bin/python scripts/import_telescope_specs.py

# === CLI Tools (original, still functional) ===
# Install dependencies
pip install pandas openpyxl xlrd ephem

# For NED coordinate fetching (one-time setup)
pip install astroquery

# For running the test suite
pip install pytest

# Generate ACP plans for a season
python arp_acp_generator.py --season Spring
python arp_acp_generator.py --season All

# Generate moon avoidance data (run every 60-90 days)
python arp_moon_calendar.py --days 90

# Compute tonight's observable targets
python arp_session_planner.py --site "New Mexico" --moon-ok-only

# Fetch NED coordinates (one-time, ~3-5 min, 338 HTTP requests)
python arp_ned_coords.py
```

The scripts are standalone CLI tools run individually. A pytest suite lives in `tests/`.

### Testing

```bash
# Run the full suite (use .venv/bin/ — Python 3.14 in venv)
.venv/bin/pytest tests/

# Or with PYTHONPATH for app imports
PYTHONPATH=. .venv/bin/pytest tests/ -v

# Run a single file
.venv/bin/pytest tests/test_arp_common.py -v

# Run a single test by name pattern
.venv/bin/pytest tests/ -k "moon_risk" -v
```

Tests cover pure functions in all 5 modules plus data loaders. Astronomy-heavy code (dark window, target visibility, moon info at transit) is not tested — those wrap `ephem` directly. Tests run against the real data files in the repo.

## Architecture

### Three-stage pipeline
1. **`arp_acp_generator.py`** — Reads `Arp_Seasonal_Plan.xlsx` + `itelescopesystems.xlsx`, assigns targets to telescopes by size tier, outputs ACP plan `.txt` files + cost summary CSV to `acp_plans/`.
2. **`arp_moon_calendar.py`** — Computes nightly moon phase/separation/risk for all 338 targets using `ephem`, writes `arp_moon_data.json` (consumed by dashboard).
3. **`arp_session_planner.py`** — For a given date+site, finds observable targets above min elevation during dark window, applies moon avoidance, sorts by transit time, outputs ACP plan + JSON to `session_plans/`.

### Shared module (`arp_common.py`)
All shared constants, data loaders, coordinate utilities, and moon risk classification live in `arp_common.py`, imported by all four scripts. The module must live alongside the scripts (uses `Path(__file__).parent` as `DATA_DIR`).

- **Constants:** `OBSERVATORIES`, `SITE_MAP` (list values — use `[0]` for primary site), `SITE_TELESCOPES`, `TELESCOPE_TIERS`, `PLAN_TIERS`, `SEASON_SHEETS`, `PHASE_THRESHOLDS`, `GOOD_MARGIN`, imaging defaults (`LRGB_FILTERS`, `LUM_FILTERS`, `LRGB_COUNTS`, `LUM_COUNTS`, `INTERVAL`), overhead estimates (`OVERHEAD_PER_TARGET_SECS`, `OVERHEAD_SESSION_SECS`).
- **Data loaders:** `load_targets(sheet_name="All Objects")`, `load_telescopes()`, `load_rates()` (returns nested `{tel: {"session": {...}, "exposure": {...}}}`), `load_ned_coords()`.
- **Coordinate utilities:** `parse_ra()`, `parse_dec()`, `sanitize_name()`, `parse_catalog_coords()`.
- **Moon risk:** `moon_risk(phase, sep)` returns short codes `"G"`/`"M"`/`"A"`. Use `RISK_LABELS` dict (`{"G": "Good", ...}`) for display.
- **NED coordinates:** `arp_ned_coords.csv` is auto-detected and preferred over catalog coords when present.

### Key constants (top of each script)
- `OVERHEAD_PER_TARGET_SECS = 180` (slew + plate-solve + settle)
- `OVERHEAD_SESSION_SECS = 300` (roof open + startup)
- Valid exposure durations: 60, 120, 180, 300, 600 seconds (must match iTelescope calibration library)
- Default imaging: 2L per repeat × 3 repeats (Luminance) or 2L+1R+1G+1B per repeat × 3 repeats (LRGB)

### Server App Architecture (feature/server-app)

Flask + SQLAlchemy + Jinja2 + HTMX. All state in PostgreSQL (no localStorage).

- **`app/__init__.py`** — Flask app factory (`create_app`), `db = SQLAlchemy()`
- **`app/models.py`** — 8 SQLAlchemy models: Target, Telescope, TelescopeRate, ImagingLog, MoonData, MoonCalendarRun, SessionResult, GeneratedPlan
- **`app/routes/`** — Flask blueprints (overview, planner, visibility, moon, log, export, generator, files, targets, telescopes, health)
- **`app/services/`** — Business logic extracted from CLI scripts (astronomy, acp, session, moon_calendar, importer, ned, snr)
- **`app/services/telescope_match.py`** — `compare_telescopes()` evaluates all active telescopes for a target; `evaluate_telescope()` computes visibility, SNR, FOV fit, cost, and composite score. Only queries `active=True` telescopes. `best_telescope_for_target()` scores only active telescopes at a specific site — used by the session planner for per-target telescope assignment. The legacy `assign_telescope()` in `acp.py` (size-tier lookup) is fallback only.
- **`app/routes/targets.py`** — Status badge cycle (`/targets/<id>/status`) and telescope selection from compare view (`/targets/<id>/select-telescope`). `preferred_telescope` stored on Target model, used by ACP generation.
- **`app/routes/telescopes.py`** — Telescope fleet management page (`/telescopes`) and online/offline toggle (`PATCH /telescopes/<id>/toggle`). Toggle uses HTMX out-of-band swap (`hx-swap-oob`) to update both the row and the summary metric cards atomically.
- **`app/templates/`** — Jinja2 templates extending `base.html`; `partials/` for HTMX fragments
- **`scripts/`** — Data migration and import scripts
- **`migrations/`** — Alembic schema migrations

Key patterns:
- HTMX for interactivity (no JS framework). Partials return HTML fragments.
- `hx-swap-oob="true"` for multi-element updates from a single HTMX response (e.g., telescope toggle updates both row and metrics).
- `hx-include` gathers filter values from sibling controls.
- Background computation (moon calendar) uses `threading.Thread` with DB status flag for cross-worker safety.
- Tests use SQLite in-memory (`SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"`). Use `db.JSON` not `db.ARRAY` for portability.
- Gunicorn with `--reload` in docker-compose for dev. Without it, Python changes need `docker-compose restart app`.

### Gotchas
- `parse_ra()` returns decimal hours, `parse_catalog_coords()` returns RA in degrees — don't mix them
- `arp_moon_data.json` uses compact keys (`d`, `p`, `s`, `r`) — normalize to (`date`, `phase_pct`, etc.) when importing
- Never fabricate SRI integrity hashes — compute with: `curl -s <url> | openssl dgst -sha384 -binary | openssl base64 -A`
- ACP filenames: single target = `{name}-{telescope}-{date}.txt`, multi = `arp-session-{telescope}-{date}.txt`
- Telescope data requires two imports: `importer.py` (xlsx → site/fov/rates) and `import_telescope_specs.py` (csv → CCD specs/filters/aperture/resolution). Both needed for complete records.
- `import_telescope_specs.py` can run in-container (k8s exec) or locally — `itelescopes.csv` is baked into the Docker image
- Billing rates from `load_rates()` / `itelescopesystems.xlsx` are **points per hour**, not per minute
- `SessionResult.results` is a snapshot — target status changes in DB are not reflected. Always look up current `Target.status` from the DB when making decisions based on status.
- HTMX silently ignores 5xx responses (no swap occurs). Debug "nothing happens" with `docker-compose logs app --tail=40`
- Session planner filters targets by `best_site` via `SITE_MAP`; compare view evaluates all telescopes at all sites regardless

### Dashboard (`arp_project.html`)
A self-contained ~150KB HTML file with embedded data, coordinates, and astronomy engine. No server or external dependencies. Uses browser `localStorage` for persistence. Moon data must be re-embedded when `arp_moon_data.json` is regenerated.

### Data files
- **`Arp_Seasonal_Plan.xlsx`** — Primary input: 338 targets across season sheets (Spring/Summer/Autumn/Winter/All Objects) with RA, Dec, size, site, filter strategy.
- **`itelescopesystems.xlsx`** — Telescope specs (FOV, resolution, filters) and billing rates across 5 plan tiers.
- **`asu.tsv`** — VizieR catalog VII/192 reference data (includes V-band magnitudes).
- **`itelescopes.csv`** — Extended telescope specs with CCD camera details (pixel size, QE, full well). Source: [iTelescope Systems Google Sheet](https://docs.google.com/spreadsheets/d/1jZWkkjewOuyNC9YzQ8y2d0pO1e4T7EBeysmQMPBVSOk/edit?usp=sharing). Used by `import_telescope_specs.py`.
  - Note: column `Aperature (mm)` is a typo in the source data (should be "Aperture"); code references the typo
  - Location groupings are in separator rows (e.g. "Utah Desert Remote Observatory (MPC U94)") between telescope entries
- **`arp_ned_coords.csv`** — High-precision NED coordinates (generated by `arp_ned_coords.py`).

### ACP plan format
Plans use iTelescope's ACP dialect: `#BillingMethod Session`, `#repeat`, `#count`, `#interval`, `#binning`, `#filter` directives, tab-separated target lines with decimal-hours RA and decimal-degrees Dec, ending with `#shutdown`. Plans are telescope-specific.

This URL is a good reference for ACP used by iTelescope - [How do I write my own scripts or plans to control the telescopes?](https://support.itelescope.net/support/solutions/articles/143037-how-do-i-write-my-own-scripts-or-plans-to-control-the-telescopes-)

### K8s Deployment

- Cluster: 4-node k3s (arm64), MetalLB for LoadBalancer IPs
- Registry: `registry.bartram.org` (no auth, Let's Encrypt TLS)
- DB: PostgreSQL in `postgres` namespace (`postgresql.postgres.svc.cluster.local`), app DB = `arpsurvey`, user = `arp`
- App namespace: `arp-survey`, service IP: `192.168.44.208`
- Docker build: must use `--platform linux/arm64 --provenance=false` (arm64 nodes, provenance causes manifest list issues with containerd)
- Dockerfile uses `USER 1000` (numeric UID required for `runAsNonRoot` securityContext)
- Init container runs `alembic upgrade head`; data population via `kubectl exec ... python scripts/migrate_data.py` then `import_telescope_specs.py`
- `PYTHONPATH=/app` must be set in k8s container env for Alembic and app imports
