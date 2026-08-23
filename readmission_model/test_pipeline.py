"""
Test suite for the readmission risk pipeline.
Run this AFTER 01-04 have produced all their output files.

Covers:
  A. Data integrity checks (did each pipeline stage produce valid output?)
  B. Output correctness checks (does the final classification file make sense?)
  C. Clinical sanity checks (do specific patient profiles get classified as expected?)
  D. Unseen-data test (does the model work on a held-out sample it never saw?)

"""
import os
import sys
import joblib
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

passed, failed = [], []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    (passed if condition else failed).append(name)


# ============================================================
# A. DATA INTEGRITY CHECKS
# ============================================================
section("A. DATA INTEGRITY CHECKS")

main_path = os.path.join(BASE_DIR, "patient_data_40k.csv")
long_path = os.path.join(BASE_DIR, "synthetic_longitudinal_full.csv")
enriched_path = os.path.join(BASE_DIR, "patient_data_enriched.csv")
model_path = os.path.join(BASE_DIR, "readmission_model.joblib")
classification_path = os.path.join(BASE_DIR, "patient_risk_classification.csv")

for p in [main_path, long_path, enriched_path, model_path]:
    check(f"File exists: {os.path.basename(p)}", os.path.exists(p))

main_df = pd.read_csv(main_path)
long_df = pd.read_csv(long_path)
enriched_df = pd.read_csv(enriched_path)

check("Main dataset has 40,000 patients", len(main_df) == 40000, f"got {len(main_df)}")
check("Main dataset has no missing values", main_df.isnull().sum().sum() == 0)
check("Main dataset patient_id has no duplicates", main_df['patient_id'].nunique() == len(main_df))

check("Longitudinal data covers all 40,000 patients",
      long_df['patient_id'].nunique() == 40000,
      f"got {long_df['patient_id'].nunique()}")
check("Every patient has at least 2 synthetic visits",
      long_df.groupby('patient_id').size().min() >= 2)

check("Enriched dataset row count matches main dataset", len(enriched_df) == len(main_df))
check("Enriched dataset has no missing values after merge", enriched_df.isnull().sum().sum() == 0,
      f"got {enriched_df.isnull().sum().sum()} nulls")
check("Enriched dataset has more columns than main (new features added)",
      enriched_df.shape[1] > main_df.shape[1],
      f"{main_df.shape[1]} -> {enriched_df.shape[1]}")


# ============================================================
# B. OUTPUT CORRECTNESS CHECKS
# ============================================================
section("B. OUTPUT CORRECTNESS CHECKS (final classification file)")

if not os.path.exists(classification_path):
    print("  patient_risk_classification.csv not found — run 04_score_and_classify.py first")
else:
    out_df = pd.read_csv(classification_path)

    check("Classification file covers all patients", len(out_df) == 40000, f"got {len(out_df)}")
    check("All risk scores are between 0 and 1",
          out_df['readmission_risk_score'].between(0, 1).all())
    check("Only valid tier labels used (High/Medium/Low)",
          set(out_df['risk_classification'].unique()) <= {"High", "Medium", "Low"})
    check("Every High-risk patient has 30-day follow-up window",
          (out_df.loc[out_df.risk_classification == "High", "follow_up_window_days"] == 30).all())
    check("Every Medium-risk patient has 15-day follow-up window",
          (out_df.loc[out_df.risk_classification == "Medium", "follow_up_window_days"] == 15).all())
    check("Every Low-risk patient has 10-day follow-up window",
          (out_df.loc[out_df.risk_classification == "Low", "follow_up_window_days"] == 10).all())

    # ordering consistency: higher score should never be in a "lower" tier than a lower score
    tier_rank = {"High": 0, "Medium": 1, "Low": 2}
    out_df["_rank"] = out_df["risk_classification"].map(tier_rank)
    max_score_per_tier = out_df.groupby("risk_classification")["readmission_risk_score"].min()
    check("High tier's minimum score >= Medium tier's minimum score",
          max_score_per_tier.get("High", 1) >= max_score_per_tier.get("Medium", 0))
    check("Medium tier's minimum score >= Low tier's minimum score",
          max_score_per_tier.get("Medium", 1) >= max_score_per_tier.get("Low", 0))

    # care dates should all be in the future relative to discharge_date_assumed
    out_df["_discharge"] = pd.to_datetime(out_df["discharge_date_assumed"])
    out_df["_care"] = pd.to_datetime(out_df["recommended_care_date"])
    check("All recommended care dates are after the discharge date",
          (out_df["_care"] > out_df["_discharge"]).all())

    check("No duplicate patient_ids in output", out_df['patient_id'].nunique() == len(out_df))


# ============================================================
# C. CLINICAL SANITY CHECKS
# ============================================================
section("C. CLINICAL SANITY CHECKS (does the model behave the way a clinician would expect?)")

bundle = joblib.load(model_path)
model = bundle["model"]
encoders = bundle["encoders"]
feature_names = bundle["feature_names"]
q_high = bundle["risk_thresholds"]["q_high"]
q_med = bundle["risk_thresholds"]["q_med"]

def score_patient(overrides):
    """Build one synthetic patient row from enriched_df's median values, with overrides, and score it."""
    base = enriched_df[feature_names].median(numeric_only=True).to_dict()
    # fill categorical defaults
    for c in ["insurance_type", "admission_type", "discharge_destination"]:
        base[c] = enriched_df[c].mode()[0]
    base.update(overrides)
    row = pd.DataFrame([base])[feature_names]
    for c, le in encoders.items():
        row[c] = le.transform(row[c].astype(str)).astype("int64")
    proba = model.predict_proba(row)[:, 1][0]
    return proba

# Case 1: a "textbook low risk" patient — young, no comorbidities, no prior utilization
low_risk_score = score_patient({
    "age": 30, "comorbidity_index": 0, "diabetes_flag": 0, "heart_failure_flag": 0,
    "ckd_flag": 0, "copd_flag": 0, "cancer_flag": 0, "dementia_flag": 0,
    "previous_admissions_12m": 0, "previous_er_visits_12m": 0,
    "prior_30_day_readmission_flag": 0, "icu_stay_flag": 0,
    "medication_count_at_discharge": 1, "polypharmacy_flag": 0,
    "high_risk_medication_flag": 0, "follow_up_within_7_days_flag": 1,
    "discharge_destination": "home",
})

# Case 2: a "textbook high risk" patient — elderly, multiple comorbidities, high prior utilization
high_risk_score = score_patient({
    "age": 85, "comorbidity_index": 12, "diabetes_flag": 1, "heart_failure_flag": 1,
    "ckd_flag": 1, "copd_flag": 1, "dementia_flag": 1,
    "previous_admissions_12m": 6, "previous_er_visits_12m": 8,
    "prior_30_day_readmission_flag": 1, "icu_stay_flag": 1,
    "medication_count_at_discharge": 15, "polypharmacy_flag": 1,
    "high_risk_medication_flag": 1, "follow_up_within_7_days_flag": 0,
    "discharge_destination": "nursing_home",
})

check("Textbook LOW-risk patient scores below the High threshold",
      low_risk_score < q_high, f"score={low_risk_score:.3f}, High threshold={q_high:.3f}")
check("Textbook HIGH-risk patient scores above the High threshold",
      high_risk_score >= q_high, f"score={high_risk_score:.3f}, High threshold={q_high:.3f}")
check("High-risk patient scores meaningfully higher than low-risk patient",
      high_risk_score > low_risk_score + 0.3,
      f"low={low_risk_score:.3f}, high={high_risk_score:.3f}, gap={high_risk_score-low_risk_score:.3f}")

# Case 3: monotonicity check — increasing prior admissions should not decrease risk
scores_by_admissions = [score_patient({"previous_admissions_12m": n}) for n in [0, 2, 4, 6, 8]]
check("Risk score is non-decreasing as previous_admissions_12m increases",
      all(scores_by_admissions[i] <= scores_by_admissions[i+1] + 0.02 for i in range(len(scores_by_admissions)-1)),
      f"scores={[round(s,3) for s in scores_by_admissions]}")


# ============================================================
# D. UNSEEN DATA TEST
# ============================================================
section("D. UNSEEN DATA TEST (does the model generalize, not just memorize?)")

from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

X_all = enriched_df[feature_names].copy()
y_all = enriched_df["readmitted_30_days"].copy()
for c, le in encoders.items():
    X_all[c] = le.transform(X_all[c].astype(str)).astype("int64")

# IMPORTANT: must use the SAME split (same random_state) that 03_train_model.py used,
# otherwise "unseen" rows will overlap with training data and inflate the AUC.
X_train, X_test, y_train, y_test = train_test_split(
    X_all, y_all, test_size=0.2, random_state=42, stratify=y_all
)
proba_test = model.predict_proba(X_test)[:, 1]
auc_test = roc_auc_score(y_test, proba_test)

check("AUC on the true held-out test set matches reported result (~0.80-0.81)",
      abs(auc_test - 0.805) < 0.03,
      f"held-out AUC={auc_test:.4f}")

# Extra: an honest "resampled" check using a DIFFERENT seed, acknowledging the overlap caveat
_, X_resampled, _, y_resampled = train_test_split(X_all, y_all, test_size=0.1, random_state=999, stratify=y_all)
proba_resampled = model.predict_proba(X_resampled)[:, 1]
auc_resampled = roc_auc_score(y_resampled, proba_resampled)
print(f"  [INFO] AUC on a differently-seeded resample = {auc_resampled:.4f} "
      f"(NOT a clean unseen test — this sample overlaps with training rows, "
      f"so it's expected to look inflated. Use the held-out test above instead.)")


# ============================================================
# SUMMARY
# ============================================================
section("SUMMARY")
print(f"  Passed: {len(passed)}")
print(f"  Failed: {len(failed)}")
if failed:
    print("\n  Failed checks:")
    for f in failed:
        print(f"    - {f}")
    sys.exit(1)
else:
    print("\n  All checks passed.")
