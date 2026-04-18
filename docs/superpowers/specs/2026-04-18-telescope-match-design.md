# Telescope Match — Design Spec

**Date:** 2026-04-18
**Feature:** Telescope comparison and ranking for a specific Arp target on a given date
**App:** Flask server app (feature/server-app branch, now merged to main)

## Overview

Add a "Compare Telescopes" action to the session planner. When the user clicks it on a target row, the planner results area swaps (via HTMX) to show a ranked comparison of all telescopes, scored by imaging quality and efficiency for that target on that night. Excluded telescopes (below horizon, missing filters, FOV too small) appear greyed out at the bottom with a reason.

## Decisions

| Decision | Choice | Notes |
|----------|--------|-------|
| Entry point | Session planner target rows | "Compare" button per row |
| UI approach | HTMX area swap (Approach C) | Swaps `#planner-results`; back button restores target list |
| Ranking | Composite score (0–100) + all metrics sortable | Default sort by score; columns individually sortable |
| Excluded telescopes | Shown greyed out at bottom | With disqualification reason |
| Billing tier | Default Plan-40 | Single constant, easy to change |
| SNR target | Default 30, user-adjustable | Input in comparison header, re-fetches on change |
| Standalone page | Not in initial scope | Can be added later |

## Metrics

Computed per telescope for a given target + date:

| Metric | Computation | Notes |
|--------|-------------|-------|
| Peak elevation (deg) | `ephem` — target transit at telescope site | Higher = less airmass |
| Hours above min elevation | `ephem` — dark window intersected with target visibility (>30 deg) | |
| Airmass at transit | `1 / cos(zenith_angle)` from peak elevation | |
| Moon risk | Existing `moon_risk(phase, sep)` | G/M/A badge |
| Target size in pixels | `target_size_arcmin * 60 / telescope.resolution` | |
| FOV fill (%) | `target_size_arcmin / min(fov_x, fov_y) * 100` | Sweet spot ~10-60%; >100% = clipped |
| SNR (single sub) | Existing `estimate_snr()` with actual elevation + moon state | |
| Time to target SNR | `n_subs = ceil((snr_target / snr_single) ** 2)`; time = `n_subs * exposure_secs` | Direct calculation, no iteration |
| Estimated cost (points) | `time_to_snr_minutes * exposure_rate` using Plan-40 tier | Exposure rate, not session rate |
| Filter match | Telescope filters vs target `filter_strategy` | Boolean — feeds disqualification |

## Composite Quality Score

Weighted sum of min-max normalized metrics across the viable telescope set (0–100):

| Factor | Weight | Direction |
|--------|--------|-----------|
| Time to SNR | 35% | Lower is better |
| FOV fit | 20% | Optimal 10-60%; penalize below and above |
| Hours observable | 20% | Higher is better |
| Peak elevation | 15% | Higher is better |
| Cost | 10% | Lower is better |

Normalization is relative to the result set (best telescope anchors at 100 per axis), not absolute scales.

## Disqualification Reasons

A telescope is excluded (greyed out, no composite score) if any of:

- Target never above 30 deg during dark window at that site
- Target angular size exceeds telescope FOV
- Telescope lacks filters required by the target's filter strategy
- No target magnitude data available for SNR calculation

## Service Layer

### New file: `app/services/telescope_match.py`

**Constants:**

```python
DEFAULT_SNR_TARGET = 30
DEFAULT_PLAN_TIER = "Plan-40"
DEFAULT_MIN_ELEVATION = 30
SCORE_WEIGHTS = {
    "time_to_snr": 0.35,
    "fov_fit": 0.20,
    "hours": 0.20,
    "elevation": 0.15,
    "cost": 0.10,
}
```

**`evaluate_telescope(target, telescope, date, site_key, moon_info, snr_target=30, plan_tier="Plan-40")`**

- Computes all metrics for one target+telescope+date combination
- Returns dict with all metric values plus `disqualified: bool` and `disqualification_reason: str | None`
- Calls existing `estimate_snr()` and `ephem` for per-telescope visibility

**`compare_telescopes(target, date, snr_target=30, plan_tier="Plan-40")`**

- Iterates all telescopes from the DB
- Calls `evaluate_telescope()` for each
- Computes composite score for viable telescopes
- Returns `{"viable": [...], "excluded": [...]}` — viable sorted by score descending, excluded sorted alphabetically

No Flask or template dependencies — pure computation, testable in isolation.

## Route

### `GET /planner/compare` (added to `app/routes/planner.py`)

**Query parameters:**

| Param | Required | Default | Notes |
|-------|----------|---------|-------|
| `arp` | Yes | — | Arp number |
| `date` | Yes | — | Observation date (from planner context) |
| `site` | Yes | — | Observatory site (from planner context) |
| `snr_target` | No | 30 | User-adjustable SNR goal |
| `sort` | No | `score` | Column to sort by |
| `dir` | No | `desc` | Sort direction |

**Returns:** `partials/telescope_compare.html` (HTMX partial)

## UI

### Trigger (in `partials/planner_rows.html`)

Add a "Compare" button on each target row:

```html
<button hx-get="/planner/compare?arp={{ t.arp }}&date={{ date }}&site={{ site }}"
        hx-target="#planner-results"
        hx-swap="innerHTML">
  Compare
</button>
```

### Comparison View (`partials/telescope_compare.html`)

```
+-----------------------------------------------------+
| <- Back to targets    Arp 123 - NGC 1234             |
|                       V mag: 12.3 | Size: 2.1'      |
|                       SNR target: [30 ___] [Update]  |
+-----------------------------------------------------+
| Score|Telescope|Site|Elev|Hours|Airmass|Pixels|FOV%  |
|      |         |    |    |     |       |      |      |
|      |  ... sortable columns ...           Moon|     |
|      |         |    |    |     |       |SNR  |Cost   |
+-----------------------------------------------------+
| -- Excluded ---------------------------------------- |
| T18  | Australia | Target below 30 deg               |
| T30  | Spain     | Missing R filter                  |
+-----------------------------------------------------+
```

**Key interactions:**

- **Back button:** `hx-get="/planner/filter"` with `hx-include="#planner-filters"` restores the target list with active filters preserved
- **SNR target input:** `hx-get="/planner/compare"` with `hx-trigger="change"` re-fetches with new SNR target
- **Column sorting:** `hx-get` on column headers with `sort` and `dir` params; server-side sort
- **Score display:** Color-coded badge (green >70, yellow 40-70, red <40)
- **Excluded section:** Below horizontal rule, greyed out, reason shown in place of score

## Testing

### New file: `tests/test_telescope_match.py`

Uses same patterns as existing tests: real data files, SQLite in-memory DB.

| Test | What it verifies |
|------|-----------------|
| `test_evaluate_telescope_viable` | Known good target+telescope returns all metrics, `disqualified=False` |
| `test_evaluate_telescope_below_horizon` | Target that never rises above 30 deg -> disqualified with "elevation" reason |
| `test_evaluate_telescope_fov_clipped` | Target larger than FOV -> disqualified with "FOV" reason |
| `test_evaluate_telescope_missing_filters` | LRGB target on Lum-only scope -> disqualified with "filter" reason |
| `test_time_to_snr_calculation` | `n_subs = ceil((snr_target / snr_single) ** 2)` produces correct result |
| `test_fov_fill_ratio` | Pixel size and fill % math correct for known values |
| `test_composite_score_ordering` | Clearly better telescope scores higher |
| `test_composite_score_normalization` | All scores within 0-100 |
| `test_compare_telescopes_splits_viable_and_excluded` | Both lists present, excluded have no score |
| `test_compare_telescopes_custom_snr_target` | Different SNR target changes time/cost but not elevation/hours |

## Files Changed

| File | Change |
|------|--------|
| `app/services/telescope_match.py` | **New** — core comparison logic |
| `app/routes/planner.py` | Add `GET /planner/compare` route |
| `app/templates/partials/telescope_compare.html` | **New** — comparison view partial |
| `app/templates/partials/planner_rows.html` | Add "Compare" button per row |
| `tests/test_telescope_match.py` | **New** — unit tests |

No model changes. No migrations. No changes to existing services.
