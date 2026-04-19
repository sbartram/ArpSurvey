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
    magnitude = db.Column(db.Float)         # V-band magnitude from VizieR catalog
    season = db.Column(db.String(20), nullable=False)
    best_site = db.Column(db.String(40))
    filter_strategy = db.Column(db.String(20))
    status = db.Column(db.String(20), nullable=False, default="Pending")
    preferred_telescope = db.Column(db.String(10))
    notes = db.Column(db.Text)

    imaging_logs = db.relationship("ImagingLog", backref="target", lazy="dynamic")

    @property
    def best_ra(self):
        return self.ned_ra_hours if self.ned_ra_hours is not None else self.ra_hours

    @property
    def best_dec(self):
        return self.ned_dec_degrees if self.ned_dec_degrees is not None else self.dec_degrees


class Telescope(db.Model):
    __tablename__ = "telescopes"

    id = db.Column(db.Integer, primary_key=True)
    telescope_id = db.Column(db.String(10), unique=True, nullable=False)
    site = db.Column(db.String(30), nullable=False)
    fov_arcmin = db.Column(db.Float)
    resolution = db.Column(db.Float)
    filters = db.Column(db.JSON)
    aperture_mm = db.Column(db.Float)
    focal_length_mm = db.Column(db.Float)
    pixel_size_um = db.Column(db.Float)
    peak_qe = db.Column(db.Float)         # 0.0–1.0
    full_well_e = db.Column(db.Integer)
    camera_model = db.Column(db.String(80))
    sensor_model = db.Column(db.String(80))
    sensor_type = db.Column(db.String(20))  # CCD or CMOS
    read_noise_e = db.Column(db.Float)      # e-/pixel
    dark_current_e = db.Column(db.Float)    # e-/pixel/sec at operating temp
    active = db.Column(db.Boolean, nullable=False, default=True, server_default="true")

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
