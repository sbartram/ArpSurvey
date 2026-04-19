# Telescope Online/Offline Management UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Telescopes" page with online/offline toggle badges so the user can mark individual scopes as active or inactive, immediately affecting which telescopes the comparison engine considers.

**Architecture:** New Flask blueprint (`telescopes`) with two routes: a GET for the full page and a PATCH for the HTMX toggle. A row partial template (`telescope_row.html`) is shared between the full-page render and the toggle response, following the same pattern as `status_badge.html` in the targets blueprint. Two CSS classes are added for the offline badge and dimmed rows.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, HTMX, pytest with SQLite in-memory

**Spec:** `docs/superpowers/specs/2026-04-18-telescope-online-offline-design.md`

---

### Task 1: CSS classes for offline badge and dimmed rows

**Files:**
- Modify: `app/static/style.css:50` (after the `.skip` rule)

- [ ] **Step 1: Add two CSS rules**

Append after the `.skip{...}` line (line 50) in `style.css`:

```css
.online{color:var(--green);background:var(--green-bg)}
.offline{color:var(--red);background:var(--red-bg)}
.offline-row{opacity:0.6}
```

Note: `.online` is equivalent to `.done` but using a semantic name makes the template self-documenting.

- [ ] **Step 2: Commit**

```bash
git add app/static/style.css
git commit -m "style: add online/offline badge and dimmed row CSS classes"
```

---

### Task 2: Telescope row partial template

**Files:**
- Create: `app/templates/partials/telescope_row.html`

- [ ] **Step 1: Create the row partial**

This template renders a single `<tr>` for one telescope. It is used by both the full page and the HTMX toggle response.

```html
<tr class="{% if not telescope.active %}offline-row{% endif %}" id="tel-row-{{ telescope.id }}">
  <td style="font-weight:500">{{ telescope.telescope_id }}</td>
  <td>{{ telescope.site }}</td>
  <td>{{ "%g"|format(telescope.aperture_mm or 0) }} mm</td>
  <td>{{ "%.1f"|format(telescope.fov_arcmin or 0) }}'</td>
  <td>{{ telescope.camera_model or "—" }}</td>
  <td>{{ telescope.sensor_type or "—" }}</td>
  <td style="font-size:11px;color:var(--text2)">{{ (telescope.filters or [])|join(" ") }}</td>
  <td>
    <span class="badge {% if telescope.active %}online{% else %}offline{% endif %}"
          hx-patch="/telescopes/{{ telescope.id }}/toggle"
          hx-target="#tel-row-{{ telescope.id }}"
          hx-swap="outerHTML"
          style="cursor:pointer">
      {{ "Online" if telescope.active else "Offline" }}
    </span>
  </td>
</tr>
```

Key details:
- `hx-target` points at the `<tr>` by its `id`, and `hx-swap="outerHTML"` replaces the entire row so the `offline-row` class updates atomically with the badge.
- The partial returns a `<tr>`, so the HTMX response is a drop-in replacement for the existing row.

- [ ] **Step 2: Commit**

```bash
git add app/templates/partials/telescope_row.html
git commit -m "feat: add telescope row partial template for HTMX swap"
```

---

### Task 3: Telescopes page template

**Files:**
- Create: `app/templates/telescopes.html`

- [ ] **Step 1: Create the full page template**

```html
{% extends "base.html" %}
{% block title %}Telescopes{% endblock %}

{% block content %}
<div class="grid3">
  <div class="metric">
    <div class="lbl">Total telescopes</div>
    <div class="val">{{ total }}</div>
  </div>
  <div class="metric">
    <div class="lbl">Online</div>
    <div class="val" style="color:var(--green)">{{ online }}</div>
  </div>
  <div class="metric">
    <div class="lbl">Offline</div>
    <div class="val" style="color:var(--red)">{{ offline }}</div>
  </div>
</div>

<div class="card">
  <div class="card-title">Fleet status</div>
  {% if telescopes %}
  <div class="tbl-wrap">
    <table>
      <thead>
        <tr>
          <th>Scope</th>
          <th>Site</th>
          <th>Aperture</th>
          <th>FOV</th>
          <th>Camera</th>
          <th>Sensor</th>
          <th>Filters</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {% for telescope in telescopes %}
          {% include "partials/telescope_row.html" %}
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <div class="empty-state">No telescopes imported yet</div>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add app/templates/telescopes.html
git commit -m "feat: add telescopes page template with metrics and table"
```

---

### Task 4: Telescopes blueprint (routes)

**Files:**
- Create: `app/routes/telescopes.py`
- Modify: `app/routes/__init__.py`

- [ ] **Step 1: Create the telescopes blueprint**

```python
import re

from flask import Blueprint, render_template
from app import db
from app.models import Telescope

bp = Blueprint("telescopes", __name__)


def _natural_sort_key(tel):
    """Sort T5 before T14 by extracting the numeric part."""
    m = re.match(r"([A-Za-z]+)(\d+)", tel.telescope_id)
    if m:
        return (m.group(1), int(m.group(2)))
    return (tel.telescope_id, 0)


@bp.route("/telescopes")
def index():
    telescopes = Telescope.query.all()
    telescopes.sort(key=_natural_sort_key)
    online = sum(1 for t in telescopes if t.active)
    total = len(telescopes)
    return render_template(
        "telescopes.html",
        telescopes=telescopes,
        total=total,
        online=online,
        offline=total - online,
    )


@bp.route("/telescopes/<int:telescope_id>/toggle", methods=["PATCH"])
def toggle_active(telescope_id):
    telescope = db.session.get(Telescope, telescope_id)
    if not telescope:
        return "Not found", 404
    telescope.active = not telescope.active
    db.session.commit()
    return render_template("partials/telescope_row.html", telescope=telescope)
```

- [ ] **Step 2: Register the blueprint**

In `app/routes/__init__.py`, add the import and registration. After the `files_bp` lines, add:

```python
from app.routes.telescopes import bp as telescopes_bp
```

And in the registration block:

```python
app.register_blueprint(telescopes_bp)
```

- [ ] **Step 3: Commit**

```bash
git add app/routes/telescopes.py app/routes/__init__.py
git commit -m "feat: add telescopes blueprint with list and toggle routes"
```

---

### Task 5: Add "Telescopes" nav link

**Files:**
- Modify: `app/templates/base.html:29` (nav section)

- [ ] **Step 1: Add nav link**

In `base.html`, after the Imaging log link (line 28) and before the Progress export link (line 29), add:

```html
  <a href="/telescopes" class="{% if request.path.startswith('/telescopes') %}active{% endif %}">Telescopes</a>
```

- [ ] **Step 2: Commit**

```bash
git add app/templates/base.html
git commit -m "feat: add Telescopes nav tab to base template"
```

---

### Task 6: Tests for telescope routes

**Files:**
- Create: `tests/test_telescopes.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for telescopes routes."""

import pytest

from app import create_app, db
from app.config import Config
from app.models import Telescope


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        telescopes = [
            Telescope(telescope_id="T5", site="New Mexico Skies",
                      aperture_mm=250, fov_arcmin=60.5,
                      camera_model="FLI PL16803", sensor_type="CCD",
                      filters=["L", "R", "G", "B"], active=True),
            Telescope(telescope_id="T14", site="New Mexico Skies",
                      aperture_mm=431, fov_arcmin=28.3,
                      camera_model="FLI PL09000", sensor_type="CCD",
                      filters=["L", "R", "G", "B"], active=True),
            Telescope(telescope_id="T24", site="SSO",
                      aperture_mm=610, fov_arcmin=22.8,
                      camera_model="FLI PL09000", sensor_type="CCD",
                      filters=["L", "R", "G", "B", "Ha"], active=False),
        ]
        db.session.add_all(telescopes)
        db.session.commit()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_telescopes_page_renders(client):
    response = client.get("/telescopes")
    assert response.status_code == 200
    assert b"Fleet status" in response.data
    assert b"T5" in response.data
    assert b"T14" in response.data
    assert b"T24" in response.data


def test_telescopes_page_shows_counts(client):
    response = client.get("/telescopes")
    html = response.data.decode()
    # 3 total, 2 online, 1 offline
    assert "Total telescopes" in html
    assert "Online" in html
    assert "Offline" in html


def test_toggle_online_to_offline(client, app):
    with app.app_context():
        t5 = Telescope.query.filter_by(telescope_id="T5").first()
        assert t5.active is True
        response = client.patch(f"/telescopes/{t5.id}/toggle")
        assert response.status_code == 200
        assert b"Offline" in response.data
        assert b"offline-row" in response.data
        db.session.refresh(t5)
        assert t5.active is False


def test_toggle_offline_to_online(client, app):
    with app.app_context():
        t24 = Telescope.query.filter_by(telescope_id="T24").first()
        assert t24.active is False
        response = client.patch(f"/telescopes/{t24.id}/toggle")
        assert response.status_code == 200
        assert b"Online" in response.data
        db.session.refresh(t24)
        assert t24.active is True


def test_toggle_nonexistent_returns_404(client):
    response = client.patch("/telescopes/9999/toggle")
    assert response.status_code == 404


def test_offline_row_has_dimmed_class(client, app):
    response = client.get("/telescopes")
    html = response.data.decode()
    # T24 is offline, its row should have offline-row class
    assert "offline-row" in html


def test_natural_sort_order(client):
    """T5 should appear before T14 (natural sort, not lexicographic)."""
    response = client.get("/telescopes")
    html = response.data.decode()
    t5_pos = html.index("T5")
    t14_pos = html.index("T14")
    assert t5_pos < t14_pos
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_telescopes.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_telescopes.py
git commit -m "test: add tests for telescope list page and toggle endpoint"
```

---

### Task 7: Update backlog

**Files:**
- Modify: `docs/backlog.md:5`

- [ ] **Step 1: Mark the backlog item as done**

Change line 5 from:
```
- [ ] Add a UI feature to allow me to manually mark telescopes as online/offline
```
to:
```
- [X] Add a UI feature to allow me to manually mark telescopes as online/offline
```

- [ ] **Step 2: Commit**

```bash
git add docs/backlog.md
git commit -m "docs: mark telescope online/offline backlog item as done"
```
