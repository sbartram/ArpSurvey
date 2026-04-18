"""
Signal-to-noise ratio estimation service.

Computes estimated SNR for imaging a target with a given telescope,
exposure parameters, and observing conditions (elevation, moon).

Uses the CCD/CMOS signal equation:
  SNR = S*t / sqrt(S*t + npix*(B*t + D*t + R^2))

Where:
  S = source signal rate (e-/s total from object)
  t = single sub-exposure time (s)
  B = sky background rate (e-/pixel/s)
  D = dark current (e-/pixel/s)
  R = read noise (e-)
  npix = number of pixels covering the object

For N sub-exposures, total SNR = single_SNR * sqrt(N).
"""

import math

# Typical sky brightness at zenith in V-band (mag/arcsec^2) per site
# Dark site ~21.5, moderate ~20.5, light-polluted ~19
SITE_SKY_BRIGHTNESS = {
    "New Mexico": 21.0,   # moderate (Mayhill area)
    "Spain": 21.0,        # moderate (rural Spain)
    "Australia": 21.5,    # dark (Siding Spring)
    "Chile": 21.5,        # dark
}

# Vega zero-point flux in V-band: photons/s/cm^2/Angstrom at mag=0
# ~3.64e-9 erg/s/cm^2/A → ~1000 photons/s/cm^2/A for V-band
VEGA_PHOTON_FLUX = 1000.0  # photons/s/cm^2/Angstrom at V=0

# Effective V-band width in Angstroms
V_BAND_WIDTH = 880.0  # ~880A effective width for Johnson V


def estimate_snr(target_mag, target_size_arcmin, telescope, site_key,
                 elevation_deg, moon_phase_pct, moon_sep_deg,
                 exposure_secs=300, n_subs=1, binning=1):
    """
    Estimate SNR for imaging a target.

    Args:
        target_mag: V-band integrated magnitude
        target_size_arcmin: target angular size (arcmin)
        telescope: Telescope model instance (with CCD specs)
        site_key: observatory name
        elevation_deg: target altitude above horizon (degrees)
        moon_phase_pct: moon illumination percentage (0-100)
        moon_sep_deg: moon-target angular separation (degrees)
        exposure_secs: single sub-exposure in seconds
        n_subs: number of sub-exposures
        binning: pixel binning factor (1 or 2)

    Returns dict: {snr_single, snr_total, signal_rate, sky_rate, noise_components}
    or None if insufficient data.
    """
    if target_mag is None or telescope.read_noise_e is None:
        return None

    # Telescope collecting area (cm^2)
    aperture_cm = (telescope.aperture_mm or 250) / 10.0
    area_cm2 = math.pi * (aperture_cm / 2) ** 2

    # Plate scale (arcsec/pixel), accounting for binning
    plate_scale = (telescope.resolution or 1.0) * binning

    # QE
    qe = telescope.peak_qe or 0.6

    # Atmospheric extinction correction
    # Airmass ~ 1/sin(elevation), extinction ~0.2 mag/airmass in V
    if elevation_deg <= 0:
        return None
    airmass = 1.0 / math.sin(math.radians(max(elevation_deg, 10)))
    extinction_mag = 0.2 * airmass  # V-band typical

    # Effective target magnitude after extinction
    effective_mag = target_mag + extinction_mag

    # Source photon rate (photons/s from entire object)
    # flux = F0 * 10^(-0.4 * mag) * bandwidth * area
    source_photons = (VEGA_PHOTON_FLUX * 10 ** (-0.4 * effective_mag)
                      * V_BAND_WIDTH * area_cm2)
    # Convert to electrons
    source_e_per_s = source_photons * qe

    # Number of pixels covering the object
    target_size_arcsec = (target_size_arcmin or 1.0) * 60.0
    target_area_arcsec2 = math.pi * (target_size_arcsec / 2) ** 2
    pixel_area_arcsec2 = plate_scale ** 2
    npix = max(1, target_area_arcsec2 / pixel_area_arcsec2)

    # Sky background
    base_sky_mag = SITE_SKY_BRIGHTNESS.get(site_key, 21.0)

    # Moon brightening: rough model
    # Full moon at 0 sep adds ~4 mag/arcsec^2, drops with separation and phase
    if moon_phase_pct > 10:
        moon_factor = (moon_phase_pct / 100.0)
        sep_factor = max(0, 1.0 - moon_sep_deg / 120.0)
        moon_brightening = 4.0 * moon_factor * sep_factor
        effective_sky_mag = base_sky_mag - moon_brightening
    else:
        effective_sky_mag = base_sky_mag

    # Sky also affected by airmass (brighter near horizon)
    effective_sky_mag -= 0.1 * (airmass - 1)

    # Sky photon rate per pixel
    sky_photons_per_arcsec2 = (VEGA_PHOTON_FLUX * 10 ** (-0.4 * effective_sky_mag)
                                * V_BAND_WIDTH * area_cm2)
    sky_e_per_pixel_per_s = sky_photons_per_arcsec2 * qe * pixel_area_arcsec2

    # Dark current and read noise
    dark = telescope.dark_current_e or 0.01
    read_noise = telescope.read_noise_e or 5.0

    # Single sub-exposure SNR (for the whole object)
    S = source_e_per_s * exposure_secs
    sky_noise = npix * sky_e_per_pixel_per_s * exposure_secs
    dark_noise = npix * dark * exposure_secs
    read_noise_total = npix * read_noise ** 2

    total_noise_variance = S + sky_noise + dark_noise + read_noise_total
    if total_noise_variance <= 0:
        return None

    snr_single = S / math.sqrt(total_noise_variance)
    snr_total = snr_single * math.sqrt(n_subs)

    return {
        "snr_single": round(snr_single, 1),
        "snr_total": round(snr_total, 1),
        "signal_e": round(S, 0),
        "sky_e_per_pix": round(sky_e_per_pixel_per_s * exposure_secs, 1),
        "airmass": round(airmass, 2),
        "effective_sky_mag": round(effective_sky_mag, 1),
    }


def snr_quality_label(snr):
    """Convert SNR to a qualitative label."""
    if snr is None:
        return "?"
    if snr >= 50:
        return "Excellent"
    if snr >= 20:
        return "Good"
    if snr >= 10:
        return "Fair"
    if snr >= 5:
        return "Poor"
    return "Very Poor"
