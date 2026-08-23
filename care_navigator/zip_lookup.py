"""
Zip code lookup -- loads a REAL, complete US zip code dataset instead of
a hardcoded table.

SETUP (one-time, free):
  1. Go to https://simplemaps.com/data/us-zips
  2. Download the free "Basic" database (CSV). No cost -- you'll be asked
     for an email and to agree to keep a small attribution link if you
     publish the app publicly (see their license page for exact terms).
  3. Save the file as "uszips.csv" in this same project folder.

That file has ~33,000 rows (every US zip code) with columns including:
  zip, lat, lng, city, state_id, state_name, county_name, population

This module loads it once at import time and exposes the same two
functions the rest of the code already calls -- nothing else needs to
change.
"""

import math
import pandas as pd

_ZIP_FILE = "uszips.csv"

try:
    _zips_df = pd.read_csv(_ZIP_FILE, dtype={"zip": str})
    _zips_df["zip"] = _zips_df["zip"].str.zfill(5)
    _zips_df = _zips_df.set_index("zip")
    _LOADED = True
except FileNotFoundError:
    _zips_df = None
    _LOADED = False


def _require_loaded():
    if not _LOADED:
        raise FileNotFoundError(
            f"'{_ZIP_FILE}' not found. Download the free US zip database from "
            f"https://simplemaps.com/data/us-zips and save it as '{_ZIP_FILE}' "
            f"in this project folder."
        )


def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8  # earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def distance_between_zips(zip_a, zip_b):
    _require_loaded()
    zip_a, zip_b = str(zip_a).zfill(5), str(zip_b).zfill(5)
    if zip_a not in _zips_df.index or zip_b not in _zips_df.index:
        return None
    row_a, row_b = _zips_df.loc[zip_a], _zips_df.loc[zip_b]
    return haversine_miles(row_a["lat"], row_a["lng"], row_b["lat"], row_b["lng"])


def state_for_zip(zip_code):
    _require_loaded()
    zip_code = str(zip_code).zfill(5)
    if zip_code not in _zips_df.index:
        return None
    return _zips_df.loc[zip_code, "state_id"]
