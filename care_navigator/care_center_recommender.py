"""
Stage 3: Care Center Recommender
==================================
Takes the output of the Stage 2 care navigation model (Telehealth /
Urgent_Care / PCP_Appointment / Care_Management / ED) plus the patient's
zip code, and returns a ranked shortlist of real facilities.

Data sources (real files should match these exact column schemas):
  - DAC_NationalDownloadableFile  -> facility name, specialty, ZIP, telehealth flag
  - ec_score_file                 -> clinician-level MIPS quality score
  - grp_public_reporting_cahps    -> facility-level patient experience score

Join keys: NPI (clinician-level) and org_pac_id (facility/group-level).
Geography: patient_zip vs facility "ZIP Code", distance via a zip
centroid gazetteer (see zip_geo_demo.py -- swap for a real Census/HUD
ZCTA gazetteer in production).

NOTE: This script runs against the DEMO data in facility_data_demo.py and
zip_geo_demo.py. Swap the loader functions at the bottom for pd.read_csv()
calls against your real uploaded files once they're available -- the
matching/ranking logic does not need to change as long as column names
match what's documented above.
"""

import pandas as pd
from zip_lookup import distance_between_zips, state_for_zip

# Map each care navigation recommendation to the specialty/facility type
# we should search for in the facility directory. Extend this as your
# specialty taxonomy grows (e.g. splitting "Family Medicine" vs
# "Internal Medicine" by chronic condition mix).
CARE_TYPE_TO_SPECIALTY = {
    "PCP_Appointment": ["Family Medicine", "Internal Medicine"],
    "Urgent_Care": ["Urgent Care Medicine"],
    "Telehealth": ["Family Medicine", "Internal Medicine"],  # filtered further by Telehlth == 'Y'
    "Care_Management": ["Geriatric Medicine"],
    "ED": ["Emergency Medicine"],
}

# EDs are time-critical: widen the search radius so we always surface the
# nearest one rather than coming back empty in sparser regions.
ED_MAX_RADIUS_MILES = 60

MAX_RADIUS_MILES = 30
TOP_N = 3


def _quality_component(row, quality_scores, cahps_scores):
    """Blend clinician MIPS score + facility CAHPS patient-experience score
    into a single 0-100 quality signal. Missing data doesn't disqualify a
    facility -- it just doesn't boost it."""
    mips = quality_scores.loc[quality_scores["NPI"] == row["NPI"], "final_MIPS_score"]
    mips_val = float(mips.iloc[0]) if len(mips) else 50.0

    cahps = cahps_scores.loc[cahps_scores["org_PAC_ID"] == row["org_pac_id"], "prf_rate"]
    cahps_val = float(cahps.iloc[0]) * 20 if len(cahps) else 50.0  # scale 1-5 star to 0-100

    return round(0.6 * mips_val + 0.4 * cahps_val, 1)


def recommend_care_centers(patient_zip, care_recommendation,
                            facility_directory, quality_scores, cahps_scores,
                            top_n=TOP_N, max_radius_miles=MAX_RADIUS_MILES):
    """
    Returns a ranked list of dicts: facility name, distance, quality score,
    address city/state, telehealth availability.
    """
    candidates = facility_directory.copy()

    specialties = CARE_TYPE_TO_SPECIALTY.get(care_recommendation)
    if specialties is not None:
        candidates = candidates[candidates["pri_spec"].isin(specialties)]

    if care_recommendation == "Telehealth":
        # Prefer providers who actually offer telehealth; fall back to
        # in-person if none are within radius (handled after distance filter)
        telehealth_candidates = candidates[candidates["Telehlth"] == "Y"]
        if len(telehealth_candidates) > 0:
            candidates = telehealth_candidates

    if len(candidates) == 0:
        return []

    candidates = candidates.copy()
    candidates.loc[:, "distance_miles"] = candidates["ZIP Code"].apply(
        lambda z: distance_between_zips(patient_zip, z)
    )

    if care_recommendation == "Telehealth":
        # Physical distance is irrelevant for a virtual visit -- what
        # matters is that the clinician is licensed to practice in the
        # patient's state. Distance is kept only for display/tiebreak
        # (e.g. same-day in-person follow-up convenience).
        patient_state = state_for_zip(patient_zip)
        candidates = candidates[candidates["State"] == patient_state]
    else:
        radius = ED_MAX_RADIUS_MILES if care_recommendation == "ED" else max_radius_miles
        candidates = candidates.dropna(subset=["distance_miles"])
        candidates = candidates[candidates["distance_miles"] <= radius]

    if len(candidates) == 0:
        return []

    # Quality blend
    candidates = candidates.copy()
    candidates.loc[:, "quality_score"] = candidates.apply(
        lambda r: _quality_component(r, quality_scores, cahps_scores), axis=1
    )

    # Rank: distance is primary (closer is better, esp. for Urgent_Care/ED),
    # quality is the tiebreaker within a reasonable distance band.
    candidates.loc[:, "rank_score"] = candidates["distance_miles"] - (candidates["quality_score"] / 20.0)
    candidates = candidates.sort_values("rank_score")

    results = []
    seen_facilities = set()
    for _, row in candidates.iterrows():
        if row["Facility Name"] in seen_facilities:
            continue  # one recommendation per facility, not per clinician
        seen_facilities.add(row["Facility Name"])
        results.append({
            "facility_name": row["Facility Name"],
            "specialty": row["pri_spec"],
            "city": row["City/Town"],
            "state": row["State"],
            "zip": row["ZIP Code"],
            "distance_miles": round(row["distance_miles"], 1),
            "quality_score": row["quality_score"],
            "rank_score": round(row["rank_score"], 2),
            "telehealth_available": row["Telehlth"] == "Y",
        })
        if len(results) >= top_n:
            break

    return results


if __name__ == "__main__":
    from facility_data_demo import FACILITY_DIRECTORY, QUALITY_SCORES, CAHPS_SCORES

    demo_cases = [
        ("10001", "PCP_Appointment"),
        ("07030", "Urgent_Care"),
        ("19104", "Care_Management"),
        ("90001", "Telehealth"),
    ]

    for zip_code, care_type in demo_cases:
        print(f"\nPatient zip {zip_code}, recommended: {care_type}")
        recs = recommend_care_centers(zip_code, care_type, FACILITY_DIRECTORY,
                                       QUALITY_SCORES, CAHPS_SCORES)
        if not recs:
            print(f"  No matching facilities within {MAX_RADIUS_MILES} miles.")
        for r in recs:
            print(f"  - {r['facility_name']} ({r['city']}, {r['state']}) "
                  f"| {r['distance_miles']} mi | quality {r['quality_score']} "
                  f"| rank_score {r['rank_score']} | telehealth={r['telehealth_available']}")
