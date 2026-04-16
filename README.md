# Arp Catalog iTelescope Project

A toolkit for systematically imaging all 338 objects in Halton Arp's *Atlas of Peculiar Galaxies* using the [iTelescope.net](https://www.itelescope.net) remote telescope network. Includes ACP plan generation, moon avoidance scheduling, nightly session planning, and a standalone browser-based dashboard for tracking progress.

---

## Project overview

The workflow runs in three stages:

```
Data files  ──►  Python scripts  ──►  ACP plan files (.txt)
                      │
                      └──►  arp_project.html  (local dashboard)
```

1. **Plan generation** — `arp_acp_generator.py` reads the seasonal target list and telescope specs, assigns each target to the best telescope, and outputs ready-to-upload ACP plan files with duration and cost estimates.
2. **Moon scheduling** — `arp_moon_calendar.py` calculates imaging risk for every target over a 60–90 day window and writes the result to `arp_moon_data.json`, which the dashboard uses for its moon calendar tab.
3. **Nightly planning** — `arp_session_planner.py` computes which targets are observable on a given night at a given site, applies moon avoidance, sorts by transit time, and generates a nightly ACP plan.
4. **Dashboard** — `arp_project.html` is a standalone local app (no server needed) that combines all of the above into tabs for session planning, visibility windows, the moon calendar, an imaging log, and a progress export.

---

## Requirements

```bash
pip install pandas openpyxl xlrd ephem
```

| Package | Purpose |
| --- | --- |
| `pandas` | Reading Excel and TSV data files |
| `openpyxl` | Reading `.xlsx` files |
| `xlrd` | Reading the legacy `.xls` catalog file |
| `ephem` | Astronomical calculations (rise/set times, moon position, separation) |

Python 3.9 or later is recommended.

---

## File reference

### Data files

#### `Arp_Seasonal_Plan.xlsx`
The primary planning spreadsheet. Contains all 338 Arp targets organized into seasonal batches based on right ascension, with telescope recommendations, filter strategies, and a status column. This is the main input file for all three Python scripts.

**Sheets:**

| Sheet | Contents |
| --- | --- |
| Season Overview | Summary of seasonal RA ranges and target counts |
| Spring (Now) | 149 targets, RA 8h–14h |
| Summer | 58 targets, RA 14h–20h |
| Autumn | 83 targets, RA 20h–2h |
| Winter | 48 targets, RA 2h–8h |
| All Objects | All 338 targets in one sheet, sorted by RA |

**Columns in each season sheet:**

| Column | Description |
| --- | --- |
| Arp # | Arp catalog number (1–338) |
| Common Name | Primary galaxy name or group designation |
| RA (J2000) | Right ascension in HH MM SS format |
| Dec (J2000) | Declination in +DD MM.m format |
| Size (arcmin) | Angular size of the Arp field in arcminutes |
| Best Site | Recommended iTelescope observatory or observatories |
| Filter Strategy | `LRGB` for larger/brighter targets, `Luminance` for compact ones |
| Notable / Notes | Special imaging notes |
| Status | Blank by default; track progress here or in the dashboard |

The seasonal groupings and filter strategy assignments are based on angular size, declination, and observatory site compatibility. Targets larger than about 7 arcminutes are assigned LRGB; smaller targets default to Luminance-only to reduce session time and cost.

---

#### `itelescopesystems.xlsx`
Telescope specifications and imaging rate data downloaded from the iTelescope community Google Sheet and billing rate list. Used by the ACP generator and session planner to assign telescopes and estimate costs.

**Sheets:**

| Sheet | Contents |
| --- | --- |
| Telescopes | Hardware specs for all 24 active telescopes |
| Imaging Rates | Points-per-minute billing rates for all plan tiers |

**Key columns in Telescopes sheet:**

| Column | Description |
| --- | --- |
| Telescope | Telescope ID (T2, T5, T11, etc.) |
| Platform | Observatory name |
| Aperture (mm) | Primary mirror or lens diameter |
| Focal Length (mm) | Effective focal length |
| FOV X / FOV Y (arcmins) | Field of view in arcminutes |
| Resolution (arcsec/pixel) | Plate scale |
| Filters | Available filter set |
| Camera | Camera model |

**Imaging Rates sheet** contains session billing rates (points per minute of wall-clock time) and exposure billing rates (points per minute of shutter-open time) for each telescope across five plan tiers: Plan-40, Plan-90, Plan-160, Plan-290, Plan-490. The number refers to the monthly membership cost in USD; higher plans have lower per-minute rates.

> **Note:** iTelescope rates and telescope availability change periodically. Download a fresh copy of the telescope specs from the iTelescope Discord community Google Sheet and replace this file when rates or fleet composition change.

---

#### `Arp_Catalogue.xls`
A local copy of Arp catalog data with basic properties for all 338 objects: magnitude, angular size, morphological type, coordinates, and redshift. Used as a reference; the seasonal plan is derived from this data.

---

#### `asu.tsv`
A VizieR catalog export (catalog VII/192, Arp's Peculiar Galaxies, Webb 1996) downloaded from [vizier.cds.unistra.fr](https://vizier.cds.unistra.fr). Contains 338 primary entries plus individual galaxy entries for multi-component Arp objects. Useful for cross-referencing coordinates, finding component galaxies within an Arp group, and looking up Simbad/NED links.

Columns: `Arp`, `Name`, `RAJ2000`, `DEJ2000`, `Size`, `Orient` (orientation of Arp's original photo), `fl_245`/`fl_ST6`/`fl_ST5` (original focal lengths from Arp's observations), `APG`, `Simbad`, `NED`.

To refresh from VizieR, use the URL embedded in the file header.

---

#### `arp_moon_data.json`
Pre-computed moon avoidance data generated by `arp_moon_calendar.py`. Contains nightly imaging risk assessments for all 338 targets over the calculation window.

**Top-level structure:**

| Key | Description |
| --- | --- |
| `generated` | ISO date this file was created |
| `days` | Number of days covered |
| `next_new` | Date of the next new moon after generation |
| `next_full` | Date of the next full moon after generation |
| `phase_cal` | List of `{d, p}` dicts — date and moon phase % for each night |
| `targets` | List of per-target risk windows (see below) |

**Per-target structure:**

| Key | Description |
| --- | --- |
| `arp` | Arp catalog number |
| `name` | Common name |
| `obs` | Primary observatory used for the calculation |
| `good_days` | Number of Good-rated nights in the window |
| `next_good` | ISO date of next Good night |
| `next_avoid` | ISO date of next Avoid night |
| `windows` | List of `{d, p, s, r}` dicts — date, moon phase %, separation °, risk code (G/M/A) |

**Risk thresholds** used for the G/M/A classification:

| Moon phase | Minimum separation | Good threshold |
| --- | --- | --- |
| < 25% | 20° | 40° |
| 25–50% | 40° | 60° |
| 50–75% | 60° | 80° |
| > 75% | 90° | 110° |

This file should be regenerated every 60–90 days to stay current.

---

#### `Arp_Spring_All.xlsx`
A supplementary spreadsheet with expanded data for all Spring-season targets, used during seasonal planning. Contains the same core columns as the seasonal plan sheets with additional planning notes.

---

### Python scripts

#### `arp_acp_generator.py`
Reads the seasonal plan and telescope specs, matches each target to the best available telescope, and writes ACP-format observing plan files ready to upload to iTelescope.

**Usage:**
```bash
python arp_acp_generator.py [options]
```

**Options:**

| Option | Default | Description |
| --- | --- | --- |
| `--season` | `Spring` | Which season to generate plans for: `Spring`, `Summer`, `Autumn`, `Winter`, or `All` |
| `--telescope` | auto | Force a specific telescope (e.g. `T17`). Omit to auto-assign by target size and site |
| `--output-dir` | `acp_plans/` | Directory to write plan files into |
| `--targets-per-plan` | `5` | Number of targets per `.txt` plan file |
| `--exposure` | `300` | Sub-exposure duration in seconds. Must be one of: 60, 120, 180, 300, 600 |
| `--count` | `6` | Number of sub-exposures per filter for the Luminance or base filter |
| `--binning` | `1` | CCD binning factor: 1 or 2 |
| `--repeat` | `1` | ACP `#REPEAT` value — number of full plan loops |
| `--plan-tier` | `Plan-40` | Membership plan tier for cost estimation |

**Examples:**
```bash
# Spring season, auto-assign telescopes, 5 targets per plan (default settings)
python arp_acp_generator.py --season Spring

# All seasons at once
python arp_acp_generator.py --season All

# Spain only, 3 targets per plan, shorter exposures
python arp_acp_generator.py --season Summer --telescope T17 --targets-per-plan 3 --exposure 180

# Cost estimate at Plan-160 tier
python arp_acp_generator.py --season Autumn --plan-tier Plan-160
```

**Outputs:**
- One `.txt` ACP plan file per batch, named `Arp_{Season}_{Telescope}_batch{NN}.txt`
- A `plan_summary_{Season}.csv` with every plan's targets, duration estimate, and point cost for both session and exposure billing modes

**Telescope assignment logic** uses four size tiers, with site preference applied within each tier:

| Target size | Preferred telescopes |
| --- | --- |
| < 3.0' | T17, T32, T21, T11, T25 |
| 3.0–7.0' | T11, T21, T26, T30, T17 |
| 7.0–20.0' | T5, T20, T26, T71, T75 |
| > 20.0' | T14, T8, T70, T80 |

The first telescope in each tier whose FOV accommodates the target with a 1.5× margin is selected.

**Cost estimation** uses the formula:
```
session_cost  = (exposure_time + overhead) / 60  ×  rate_per_min
exposure_cost = exposure_time / 60  ×  rate_per_min
```
where overhead is 180 seconds per target (slew + plate-solve + guider settle) plus a 300-second session startup overhead. These constants can be adjusted at the top of the script.

**ACP plan format** — each plan file opens with a comment header followed by standard iTelescope ACP directives:
```
; ============================================================
; Arp Catalog Observing Plan
; Plan Name    : Arp_Spring_T17_batch01
; Telescope    : T17
; Season       : Spring
; Targets      : 5
; Generated    : Arp ACP Generator
;
; Imaging time    : 2h 30m  (shutter-open only)
; Total duration  : 2h 50m  (imaging + slew/overhead)
; Est. Cost (Plan-40)
;   Session billing : ~11730 pts
;   Exposure billing: ~20250 pts
;
; Upload to iTelescope via: My Observing Plans > Upload File
; Note: Plans are telescope-specific — upload to T17 only
; ============================================================

#BillingMethod Session

#repeat 1

; --- Arp 1: NGC 2857  (size: 5.2') ---
#count 6
#interval 300
#binning 1
#filter Luminance
Arp001_NGC_2857	9.410556	49.356667

; --- Arp 268: Holmberg II  (size: 10.4') --- LRGB example
#count 6,3,3,3
#interval 300,300,300,300
#binning 1,1,1,1
#filter Luminance,Red,Green,Blue
Arp268_Holmberg_II	8.318333	70.713333

#shutdown
```

The format matches iTelescope's own Plan Generator output: lowercase directives, comma-separated multi-filter parameters for LRGB targets, and tab-separated coordinates in decimal hours (RA) and decimal degrees (Dec). `#BillingMethod Session` and `#shutdown` are required by iTelescope.

The header distinguishes **imaging time** (pure shutter-open time) from **total duration** (imaging plus slew and overhead). The nightly session planner uses the same format and also includes estimated total cost.

---

#### `arp_moon_calendar.py`
Calculates nightly moon phase, moon-target angular separation, and imaging risk for every Arp target at each target's recommended observatory over a configurable window. Writes the result to a JSON file used by the dashboard.

**Usage:**
```bash
python arp_moon_calendar.py [options]
```

**Options:**

| Option | Default | Description |
| --- | --- | --- |
| `--days` | `90` | Number of days to calculate forward from today |
| `--output` | `arp_moon_data.json` | Output JSON filename |

**Examples:**
```bash
# Standard 90-day window
python arp_moon_calendar.py

# 60-day window, custom output name
python arp_moon_calendar.py --days 60 --output moon_data_jun.json
```

**How it works:** For each target, the script initialises an `ephem.Observer` at the target's primary observatory (derived from the Best Site column), then steps through each day computing moon phase and angular separation between the moon and the target at local midnight. Risk is classified using the phase-dependent thresholds described in the `arp_moon_data.json` section above.

**Refresh schedule:** Run this script every 60–90 days so the dashboard moon calendar stays current. Processing 338 targets over 90 days takes about 30–60 seconds.

---

#### `arp_session_planner.py`
Given a date and observatory, computes which Arp targets are observable that night — above the minimum elevation, within a dark sky window, compatible with the site — applies moon avoidance filtering, sorts targets by transit time for optimal imaging order, and outputs both a nightly ACP plan and a JSON summary.

**Usage:**
```bash
python arp_session_planner.py [options]
```

**Options:**

| Option | Default | Description |
| --- | --- | --- |
| `--date` | today | Observing date in `YYYY-MM-DD` format |
| `--site` | `New Mexico` | Observatory: `New Mexico`, `Spain`, `Australia`, or `Chile` |
| `--min-hours` | `1.5` | Minimum observable hours to include a target |
| `--min-el` | site default | Override minimum elevation in degrees |
| `--plan-tier` | `Plan-40` | Membership plan tier for cost estimates |
| `--output-dir` | `session_plans/` | Directory for output files |
| `--moon-ok-only` | off | When set, excludes all targets with an Avoid moon rating |

**Examples:**
```bash
# Tonight at New Mexico (default)
python arp_session_planner.py

# Specific date at Spain, exclude moon-avoid targets
python arp_session_planner.py --date 2026-05-10 --site Spain --moon-ok-only

# New Mexico, only targets with 3+ observable hours
python arp_session_planner.py --min-hours 3

# Australia, custom elevation limit
python arp_session_planner.py --site Australia --min-el 30
```

**How it works:** The script finds astronomical twilight (sun at −18°) using the `ephem` library to establish the dark window, then for each compatible Arp target:
1. Calculates altitude at evening and morning twilight
2. Finds the observable window (above minimum elevation and within dark time)
3. Evaluates moon phase and angular separation at the target's transit time
4. Assigns risk rating (Good / Marginal / Avoid)
5. Assigns best telescope and estimates session cost

Targets are sorted by transit time, which gives an optimal ordering for sequential imaging — earlier-transiting targets are imaged while they are rising and near their best altitude, and the sequence naturally flows through the night.

**Outputs** (written to `--output-dir`):
- `Arp_Session_{Site}_{Date}.txt` — ACP plan file for the night, sorted by transit
- `session_{Site}_{Date}.json` — machine-readable summary for the dashboard

**Observatory parameters:**

| Site | Latitude | Longitude | Min elevation |
| --- | --- | --- | --- |
| New Mexico | 33.0° N | 107.0° W | 30° |
| Spain | 38.0° N | 3.5° W | 30° |
| Australia | 31.3° S | 149.1° E | 30° |
| Chile | 30.0° S | 70.7° W | 30° |

---

### Dashboard app

#### `arp_project.html`
A fully self-contained local web application. All 338 target coordinates, moon avoidance data, telescope specs, and application code are embedded directly in the file. Open it in any modern browser — no internet connection, server, or additional software required.

**Tabs:**

| Tab | Description |
| --- | --- |
| Overview | Season progress bars, 30-day moon availability strip, re-image queue |
| Tonight's plan | Live session computation for any date and site — click any row to update target status; generate and download ACP plan |
| Visibility | Graphical night-window bars for all computed targets, sortable by transit time, observable hours, or Arp number |
| Moon calendar | 60-day risk strip for all 338 targets, filterable by tonight's risk rating |
| Imaging log | Record individual sessions with date, telescope, exposure, filter strategy, quality rating, and notes |
| Progress export | Season breakdown, CSV export, ACP target list, status export |

**Persistence:** Status updates and imaging log entries are saved to browser `localStorage` automatically. Data persists between sessions as long as the same browser profile is used. Export CSVs periodically as a backup.

**The session planner tab** runs a full spherical astronomy calculation in the browser using an embedded astronomy engine (no external libraries). It computes dark windows, target rise/set/transit times, moon phase and separation, and risk ratings for every compatible target in real time when you click "Compute session". Computation takes a few seconds for a full night's targets.

**Updating moon data:** The moon calendar tab uses data embedded at build time. To update it, run `arp_moon_calendar.py` to generate a fresh `arp_moon_data.json`, then rebuild `arp_project.html` by re-running the build script (or ask Claude to regenerate it with the new data embedded).

---

## Typical workflow

### Before each season

```bash
# 1. Generate ACP plans for the upcoming season
python arp_acp_generator.py --season Spring --output-dir acp_plans/spring/

# 2. Refresh moon avoidance data
python arp_moon_calendar.py --days 90 --output arp_moon_data.json

# 3. Review the plan_summary CSV to check cost and duration
#    Open acp_plans/spring/plan_summary_Spring.csv
```

### Before each observing session

```bash
# Compute tonight's observable targets at New Mexico
python arp_session_planner.py --site "New Mexico" --min-hours 2 --moon-ok-only

# Review output in session_plans/
# Upload the generated .txt plan file to iTelescope via My Observing Plans
```

### After imaging

1. Open `arp_project.html` in a browser
2. Go to the **Imaging log** tab
3. Enter the Arp number, date, telescope, exposure, filter strategy, and quality rating
4. The target's status automatically updates to Done
5. Any entry rated ≤ 2 stars appears in the re-image queue on the Overview tab

---

## Cost estimation notes

iTelescope charges in points. The scripts estimate costs using **session billing** (points per minute of wall-clock time) as the primary metric, since this is the most conservative estimate. Exposure billing (points per minute of shutter-open time only) is shown alongside it in the plan summary CSV for comparison.

Default exposure settings (6 × 300s Luminance, or 6L + 3R + 3G + 3B × 300s for LRGB) are reasonable starting points. Adjust `--count` and `--exposure` to suit your quality requirements and point budget.

Per-target overhead is estimated at 180 seconds (slew + plate-solve + guider settle) and a 300-second session startup overhead. These are conservative estimates; actual overheads vary by telescope and target spacing. Both constants are defined at the top of `arp_acp_generator.py` and `arp_session_planner.py` and can be adjusted.

---

## Data sources

- **Arp catalog coordinates:** VizieR catalog VII/192 (Arp's Peculiar Galaxies, Webb 1996), downloaded from [vizier.cds.unistra.fr](https://vizier.cds.unistra.fr)
- **Telescope specifications:** iTelescope community Google Sheet maintained via the [iTelescope Discord](https://discord.gg/bKsFE8TBhH)
- **Imaging rates:** [itelescope.net/session-vs-exposure-pricing](https://www.itelescope.net/session-vs-exposure-pricing)
- **Moon calculations:** Python `ephem` library

---

## Notes on ACP plan format

iTelescope uses a customised version of ACP (Astronomer's Control Program). Key differences from generic ACP:

- `#PLATESOLVE` — forces plate-solving on every image; FITS headers will contain solved WCS data
- `#TIFF` — additionally saves a 16-bit TIFF alongside the FITS file
- `#EXPRESS` — disables autoguiding and pointing updates (use with caution)
- `#DEFOCUS` — slight defocus, sometimes used for photometry

Supported calibration exposure durations are **60, 120, 180, 300, and 600 seconds**. The scripts default to 300s. Using other values means calibration frames won't be available from iTelescope's library.

Plans are telescope-specific — a plan uploaded to T17 will not appear on T11. Each telescope needs its own copy of any plan you want to run on it.

Full ACP directive reference: [support.itelescope.net](https://support.itelescope.net/support/solutions/articles/143037)

**Minimum elevation:** iTelescope enforces a hard minimum of 15° but recommends imaging at 45° or above for best results. The scripts use 30° as the default, which avoids poor atmospheric conditions at low altitude while keeping most targets accessible. Override per-session with `--min-el`. Maximum sub-exposure duration is 600 seconds.

**Plan directives reference** — full list of supported directives from the iTelescope planner:

| Directive | Default | Description |
| --- | --- | --- |
| `#BillingMethod Session` | always added | Charge per minute of wall-clock session time |
| `#RESUME` | always added | Allow plan restart from where it stopped if interrupted by weather |
| `#repeat N` | `3` | Cycle through the full plan N times; use with low per-filter counts for weather resilience |
| `#DITHER` | off (`--dither`) | Small positional changes between exposures to reduce noise |
| `#TIFF` | off (`--tiff`) | Also save images as 16-bit TIFF alongside FITS |
| `#FORCESTARTUP` + `#NOADAPTIVE` | off (`--no-adaptive`) | Focus once at start, disable periodic adaptive refocusing |
| `#PLATESOLVE` | off | Plate-solve all images — very slow, triggers session billing |
| `#SKIPPREVIEWS` | off | Skip JPEG preview creation |
| `#FIRSTLAST` | off | Only create previews for first and last images in a sequence |
| `#LARGEPREVIEWS` | off | Large high-resolution previews — triggers session billing |
| `#NORAW` | off | Deliver calibrated images only, skip raw FITS |
| `#NOCAL` | off | Deliver raw images only, skip calibrated FITS |
| `#VPHOT` | off | Send calibrated FITS to VPhot server (AAVSO members only) |
| `#EXPRESS` | off | Skip focus, guiding and centering — use with caution |
| `#DEFOCUS` | off | Slight defocus for photometry applications |

**Output files:** Each imaging request produces a raw 16-bit FITS file, a calibrated FITS file (bias, dark, and flat applied), and a JPEG preview. `#TIFF` adds a 16-bit TIFF. `#VPHOT` sends the calibrated FITS to the VPhot server for variable star photometry.
