"""
Score patients with the trained readmission model and classify them into
follow-up tiers:

    High    -> readmission_risk_score in top 15%  -> 30-day follow-up
    Medium  -> next 25%                            -> 15-day follow-up
    Low     -> bottom 60%                           -> 10-day follow-up

"""
import os
import sys
import argparse
import joblib
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT_FILE = os.path.join(BASE_DIR, "patient_data_enriched.csv")
MODEL_FILE = os.path.join(BASE_DIR, "readmission_model.joblib")
OUTPUT_FILE = os.path.join(BASE_DIR, "risk_tier_output.csv")

parser = argparse.ArgumentParser()
parser.add_argument("--input_file", default=DEFAULT_INPUT_FILE,
                     help="CSV of patients to score (default: patient_data_enriched.csv)")
parser.add_argument("--limit", type=int, default=None,
                     help="Only print this many rows to the terminal (full result is still saved to CSV)")
args = parser.parse_args()

# ---- load model bundle ----
if not os.path.exists(MODEL_FILE):
    sys.exit(f"Model file not found: {MODEL_FILE}. Run 03_train_model.py first.")

bundle = joblib.load(MODEL_FILE)
model = bundle["model"]
encoders = bundle["encoders"]
feature_names = bundle["feature_names"]
q_high = bundle["risk_thresholds"]["q_high"]
q_med = bundle["risk_thresholds"]["q_med"]

# ---- load patients to score ----
if not os.path.exists(args.input_file):
    sys.exit(f"Input file not found: {args.input_file}")
df = pd.read_csv(args.input_file)

missing = [c for c in feature_names if c not in df.columns]
if missing:
    sys.exit(f"Input file is missing required feature columns: {missing}")

# ---- encode categorical columns using the SAME encoders fit during training ----
cols = {}
for c in feature_names:
    if c in encoders:
        cols[c] = encoders[c].transform(df[c].astype(str)).astype("int64")
    else:
        cols[c] = df[c].values
X = pd.DataFrame(cols, index=df.index)[feature_names]

# ---- score ----
proba = model.predict_proba(X)[:, 1]


def classify(p):
    if p >= q_high:
        return "High", 30
    elif p >= q_med:
        return "Medium", 15
    else:
        return "Low", 10


tiers, follow_up_days = zip(*[classify(p) for p in proba])

result = pd.DataFrame({
    "patient_id": df["patient_id"] if "patient_id" in df.columns else np.arange(1, len(df) + 1),
    "readmission_risk_score": np.round(proba, 4),
    "risk_tier": tiers,
    "follow_up_window_days": follow_up_days,
})

tier_order = {"High": 0, "Medium": 1, "Low": 2}
result["_sort"] = result["risk_tier"].map(tier_order)
result = result.sort_values(["_sort", "readmission_risk_score"], ascending=[True, False]).drop(columns="_sort")

result.to_csv(OUTPUT_FILE, index=False)

# ---- print to terminal ----
print(f"Scored {len(result)} patients using thresholds: High >= {q_high:.3f}, Medium >= {q_med:.3f}\n")
print("Tier distribution:")
print(result["risk_tier"].value_counts().reindex(["High", "Medium", "Low"]))
print()

to_show = result.head(args.limit) if args.limit else result
for _, row in to_show.iterrows():
    print(f"Patient {row['patient_id']:<10} | score={row['readmission_risk_score']:.3f} "
          f"| tier={row['risk_tier']:<6} | follow-up in {row['follow_up_window_days']} days")

print(f"\nFull results saved to: {OUTPUT_FILE}")