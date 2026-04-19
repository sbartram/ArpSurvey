# Telescope Online/Offline Management UI

**Date:** 2026-04-18
**Status:** Approved

## Summary

Add a dedicated "Telescopes" page to the Flask app that lists all telescopes with their specs and provides clickable badges to toggle each telescope's online/offline status. Offline telescopes are excluded from the telescope comparison engine (`compare_telescopes()` already filters `active=True`).

## Motivation

iTelescope scopes go offline periodically for maintenance or weather closures. Currently there's no UI to mark them offline — it requires a direct database update. This feature lets the user quickly reflect fleet status so that session planning and telescope comparisons only consider available instruments.

## Design

### New nav tab

Add "Telescopes" to the navigation bar in `base.html`, positioned after "Imaging log" and before "Progress export".

### Page layout

**Summary metrics (3-column grid):**
- Total telescopes count
- Online count (green)
- Offline count (red)

**Telescope table** inside a `.card` with `.tbl-wrap`:

| Column | Source | Notes |
|--------|--------|-------|
| Scope | `telescope_id` | Bold, e.g. "T5" |
| Site | `site` | |
| Aperture | `aperture_mm` | Formatted as "250 mm" |
| FOV | `fov_arcmin` | Formatted as "60.5'" |
| Camera | `camera_model` | |
| Sensor | `sensor_type` | "CCD" or "CMOS" |
| Filters | `filters` (JSON list) | Space-separated, muted text |
| Status | `active` | Clickable Online/Offline badge |

Rows are sorted by `telescope_id` (natural sort — T5 before T14).

**Offline row styling:** Rows for offline telescopes get `opacity: 0.6` to visually dim them.

### Online/Offline toggle

Follows the existing status badge pattern from `targets.py`:

- Clickable `<span class="badge">` with `hx-patch` to a new endpoint
- Returns a partial HTML fragment that replaces itself via `hx-swap="outerHTML"`
- Badge uses existing CSS classes: green (`done` class) for Online, red-ish/grey for Offline
- The table row's opacity should update too — achieved by swapping the entire `<tr>` rather than just the badge, so the row's class/style updates atomically

### New files

1. **`app/routes/telescopes.py`** — Blueprint with two routes:
   - `GET /telescopes` — renders full page with telescope list and counts
   - `PATCH /telescopes/<id>/toggle` — toggles `active`, returns updated `<tr>` partial

2. **`app/templates/telescopes.html`** — Full page template extending `base.html`

3. **`app/templates/partials/telescope_row.html`** — Single `<tr>` partial for HTMX swap, used by both the full page render and the toggle endpoint

### Blueprint registration

Add to `app/routes/__init__.py`:
```python
from app.routes.telescopes import bp as telescopes_bp
app.register_blueprint(telescopes_bp)
```

### Route details

**`GET /telescopes`:**
- Query all `Telescope` rows, sorted by `telescope_id` (using natural sort to handle T5 < T14)
- Compute total/online/offline counts
- Render `telescopes.html`

**`PATCH /telescopes/<int:telescope_id>/toggle`:**
- Look up telescope by primary key
- Flip `active` to `not active`
- Commit
- Return `partials/telescope_row.html` for HTMX swap

### CSS additions

One new class in `style.css`:
```css
.offline-row { opacity: 0.6 }
```

Badge styling reuses existing `.done` (green) for Online. For Offline, use a new `.offline` class similar to `.skip` but with red tones:
```css
.offline{color:var(--red);background:var(--red-bg)}
```

### No migration needed

The `active` column already exists on the `Telescope` model with `default=True` and `server_default="true"`.

## What this does NOT include

- Bulk toggle (select-all for a site) — can be added later
- Telescope editing (aperture, filters, etc.) — out of scope
- Automatic status detection from iTelescope API — no API available

## Testing

- Unit test for the toggle endpoint: verify `active` flips and response contains updated badge
- Verify the `compare_telescopes()` filtering still works correctly (it already filters `active=True`, no change needed)
