"""
Score all patients and output the final classification: risk tier + care follow-up date.

Assumption: no discharge_date column exists in the source data, so discharge date
is assumed = RUN_DATE below. In production, replace with each patient's real
discharge date (per-row, not a single constant).

"""
import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "patient_data_enriched.csv")
MODEL_FILE = os.path.join(BASE_DIR, "readmission_model.joblib")
OUTPUT_FILE = os.path.join(BASE_DIR, "patient_risk_classification.csv")

RUN_DATE = datetime.today()  # assumed discharge date; swap for real discharge_date in production

bundle = joblib.load(MODEL_FILE)
model = bundle["model"]
encoders = bundle["encoders"]
feature_names = bundle["feature_names"]
q_high = bundle["risk_thresholds"]["q_high"]
q_med = bundle["risk_thresholds"]["q_med"]

df = pd.read_csv(INPUT_FILE)

X = df[feature_names].copy()
for c, le in encoders.items():
    encoded = le.transform(X[c]).astype("int64")
    X[c] = pd.Series(encoded, index=X.index)

proba = model.predict_proba(X)[:, 1]

def classify(p):
    if p >= q_high:
        return "High", 30
    elif p >= q_med:
        return "Medium", 15
    else:
        return "Low", 10

tiers, follow_up_days = zip(*[classify(p) for p in proba])

output = pd.DataFrame({
    "patient_id": df["patient_id"],
    "readmission_risk_score": np.round(proba, 4),
    "risk_classification": tiers,
    "follow_up_window_days": follow_up_days,
})
output["recommended_care_date"] = [
    (RUN_DATE + timedelta(days=int(d))).strftime("%Y-%m-%d") for d in output["follow_up_window_days"]
]
output["discharge_date_assumed"] = RUN_DATE.strftime("%Y-%m-%d")

tier_order = {"High": 0, "Medium": 1, "Low": 2}
output["_sort"] = output["risk_classification"].map(tier_order)
output = output.sort_values(["_sort", "readmission_risk_score"], ascending=[True, False]).drop(columns="_sort")

output.to_csv(OUTPUT_FILE, index=False)

print("Total patients scored:", len(output))
print("\nClassification counts:")
print(output["risk_classification"].value_counts())
print("\nSaved to:", OUTPUT_FILE)
print("\nSample output:")
print(output.head(10).to_string(index=False))
