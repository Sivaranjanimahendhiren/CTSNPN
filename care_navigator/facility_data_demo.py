"""
DEMO facility datasets.
=========================
These mirror the EXACT column schemas you listed for the real CMS files.
Replace these with your actual uploaded files -- the recommender script
(care_center_recommender.py) reads them by these same column names, so
as long as the real files match this schema, no code changes are needed
beyond pointing at the real CSV paths.
"""

import pandas as pd

# ---------------------------------------------------------------------
# DAC_NationalDownloadableFile -- the only file with real geography.
# One row per clinician; a facility can have many rows (many providers).
# ---------------------------------------------------------------------
_dac_rows = [
    # NPI, Ind_PAC_ID, Last, First, pri_spec, Telehlth, Facility Name, org_pac_id, City/Town, State, ZIP Code
    (1000000001, "P001", "Nguyen", "Anh", "Family Medicine", "Y", "Riverside Family Health", "ORG001", "New York", "NY", "10001"),
    (1000000002, "P002", "Patel", "Raj", "Internal Medicine", "Y", "Riverside Family Health", "ORG001", "New York", "NY", "10001"),
    (1000000003, "P003", "Garcia", "Maria", "Urgent Care Medicine", "N", "CityCare Urgent Care - Midtown", "ORG002", "New York", "NY", "10001"),
    (1000000004, "P004", "Kim", "Soo", "Family Medicine", "N", "Hoboken Community Clinic", "ORG003", "Hoboken", "NJ", "07030"),
    (1000000005, "P005", "Smith", "John", "Urgent Care Medicine", "N", "Hoboken Urgent Care", "ORG004", "Hoboken", "NJ", "07030"),
    (1000000006, "P006", "Lopez", "Ana", "Geriatric Medicine", "Y", "Metro Care Management Group", "ORG005", "Philadelphia", "PA", "19104"),
    (1000000007, "P007", "Johnson", "Emily", "Family Medicine", "Y", "Boston Primary Partners", "ORG006", "Boston", "MA", "02115"),
    (1000000008, "P008", "Brown", "Michael", "Urgent Care Medicine", "N", "Chicago Loop Urgent Care", "ORG007", "Chicago", "IL", "60601"),
    (1000000009, "P009", "Davis", "Sarah", "Internal Medicine", "N", "Lincoln Park Primary Care", "ORG008", "Chicago", "IL", "60614"),
    (1000000010, "P010", "Wilson", "David", "Family Medicine", "Y", "Detroit Family Health", "ORG009", "Detroit", "MI", "48226"),
    (1000000011, "P011", "Martinez", "Laura", "Urgent Care Medicine", "N", "Atlanta Urgent Care Center", "ORG010", "Atlanta", "GA", "30303"),
    (1000000012, "P012", "Anderson", "James", "Family Medicine", "N", "Miami Primary Health", "ORG011", "Miami", "FL", "33101"),
    (1000000013, "P013", "Taylor", "Linda", "Geriatric Medicine", "N", "Dallas Care Coordination", "ORG012", "Dallas", "TX", "75201"),
    (1000000014, "P014", "Thomas", "Robert", "Family Medicine", "Y", "Houston Family Clinic", "ORG013", "Houston", "TX", "77030"),
    (1000000015, "P015", "Hernandez", "Carlos", "Urgent Care Medicine", "N", "Austin Urgent Care", "ORG014", "Austin", "TX", "78701"),
    (1000000016, "P016", "Moore", "Karen", "Internal Medicine", "Y", "Phoenix Primary Care Group", "ORG015", "Phoenix", "AZ", "85004"),
    (1000000017, "P017", "Jackson", "Steven", "Family Medicine", "N", "Denver Community Health", "ORG016", "Denver", "CO", "80202"),
    (1000000018, "P018", "Martin", "Nancy", "Urgent Care Medicine", "N", "LA Urgent Care Downtown", "ORG017", "Los Angeles", "CA", "90001"),
    (1000000019, "P019", "Lee", "Grace", "Family Medicine", "Y", "SF Bay Primary Health", "ORG018", "San Francisco", "CA", "94103"),
    (1000000020, "P020", "White", "Paul", "Geriatric Medicine", "Y", "Seattle Care Management Center", "ORG019", "Seattle", "WA", "98104"),
    # Emergency departments -- used for showing the nearest ED even though
    # ED routing itself bypasses the ML model and specialty filtering.
    (1000000021, "P021", "Osei", "Kwame", "Emergency Medicine", "N", "St. Vincent's Hospital ED", "ORG020", "New York", "NY", "10001"),
    (1000000022, "P022", "Reyes", "Elena", "Emergency Medicine", "N", "Hoboken General Hospital ED", "ORG021", "Hoboken", "NJ", "07030"),
    (1000000023, "P023", "Chen", "Wei", "Emergency Medicine", "N", "Penn Presbyterian ED", "ORG022", "Philadelphia", "PA", "19104"),
    (1000000024, "P024", "Okafor", "Ada", "Emergency Medicine", "N", "Mass General ED", "ORG023", "Boston", "MA", "02115"),
]
FACILITY_DIRECTORY = pd.DataFrame(_dac_rows, columns=[
    "NPI", "Ind_PAC_ID", "Provider Last Name", "Provider First Name",
    "pri_spec", "Telehlth", "Facility Name", "org_pac_id",
    "City/Town", "State", "ZIP Code",
])
FACILITY_DIRECTORY = FACILITY_DIRECTORY.astype({"ZIP Code": str})

# ---------------------------------------------------------------------
# ec_score_file -- clinician-level MIPS quality score, joins on NPI
# ---------------------------------------------------------------------
_score_rows = [(npi, 60 + (i * 3) % 40) for i, npi in enumerate(FACILITY_DIRECTORY["NPI"])]
QUALITY_SCORES = pd.DataFrame(_score_rows, columns=["NPI", "final_MIPS_score"])

# ---------------------------------------------------------------------
# grp_public_reporting_cahps -- patient experience score, joins on org_pac_id
# ---------------------------------------------------------------------
_cahps_rows = [
    (org, "CAHPS_OVERALL_RATING", round(3.2 + (i % 5) * 0.35, 1), 150 + i * 10)
    for i, org in enumerate(FACILITY_DIRECTORY["org_pac_id"].unique())
]
CAHPS_SCORES = pd.DataFrame(_cahps_rows, columns=[
    "org_PAC_ID", "measure_cd", "prf_rate", "patient_count"
])
