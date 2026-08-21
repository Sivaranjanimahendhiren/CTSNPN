"""
Test the trained readmission_model.joblib on unseen (held-out) data.

Two modes:
  1. DEFAULT (no new file): re-creates the exact same train/test split used in
     03_train_model.py (same random_state=42) and evaluates the model on the
     held-out 20% test slice — i.e. rows the model never trained on.
  2. NEW DATA: if you have a fresh CSV of patients the model has truly never
     seen (same columns as patient_data_enriched.csv, including the true label
     'readmitted_30_days'), pass its path via --new_file and this script will
     score and evaluate on that instead.

"""
import os
import sys
import argparse
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import (roc_auc_score, average_precision_score, f1_score,
                              classification_report, confusion_matrix)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENRICHED_FILE = os.path.join(BASE_DIR, "patient_data_enriched.csv")
MODEL_FILE = os.path.join(BASE_DIR, "readmission_model.joblib")

parser = argparse.ArgumentParser()
parser.add_argument("--new_file", default=None,
                     help="Optional path to a CSV of truly new/unseen patients "
                          "(same schema as patient_data_enriched.csv, with true labels).")
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

target = "readmitted_30_days"


def prep_features(df):
    cols = {}
    for c in feature_names:
        if c in encoders:
            le = encoders[c]
            cols[c] = le.transform(df[c].astype(str)).astype("int64")
        else:
            cols[c] = df[c].values
    return pd.DataFrame(cols, index=df.index)[feature_names]


def evaluate(X, y, label):
    proba = model.predict_proba(X)[:, 1]
    pred = (proba >= 0.5).astype(int)

    print(f"\n=== Evaluation on: {label} (n={len(y)}) ===")
    print("AUC:               ", round(roc_auc_score(y, proba), 4))
    print("Average Precision: ", round(average_precision_score(y, proba), 4))
    print("F1 (thresh 0.5):   ", round(f1_score(y, pred), 4))
    print("\nClassification report:")
    print(classification_report(y, pred, digits=3))
    print("Confusion matrix:")
    print(confusion_matrix(y, pred))

    tiers = np.where(proba >= q_high, "High",
             np.where(proba >= q_med, "Medium", "Low"))
    tier_df = pd.DataFrame({"tier": tiers, "actual": y.values})
    print("\nActual readmission rate by risk tier:")
    print(tier_df.groupby("tier")["actual"].mean())
    return proba, tiers


def show_sample_io(X_raw, X_encoded, y, proba, tiers, n=10, seed=42):
    """Print a handful of rows as clearly labeled input -> output blocks,
    and also save the full sample to a CSV for easy viewing outside the terminal."""
    rng = np.random.RandomState(seed)
    idx = rng.choice(len(X_raw), size=min(n, len(X_raw)), replace=False)

    display_cols = [c for c in [
        "age", "comorbidity_index", "diabetes_flag", "heart_failure_flag", "ckd_flag",
        "copd_flag", "previous_admissions_12m", "previous_er_visits_12m",
        "prior_30_day_readmission_flag", "medication_count_at_discharge",
        "discharge_destination",
    ] if c in X_raw.columns]

    out = X_raw.iloc[idx][display_cols].copy()
    out["actual_readmitted"] = np.array(y)[idx]
    out["predicted_probability"] = np.round(np.array(proba)[idx], 3)
    out["predicted_tier"] = np.array(tiers)[idx]

    print(f"\n=== Sample input -> output ({len(idx)} random patients from this set) ===\n")
    for i, (_, row) in enumerate(out.iterrows(), start=1):
        print(f"--- Patient {i} ---")
        print("  INPUT:")
        for c in display_cols:
            print(f"    {c:35s}: {row[c]}")
        print("  OUTPUT:")
        print(f"    {'actual_readmitted':35s}: {row['actual_readmitted']}")
        print(f"    {'predicted_probability':35s}: {row['predicted_probability']}")
        print(f"    {'predicted_tier':35s}: {row['predicted_tier']}")
        print()

    sample_csv = os.path.join(BASE_DIR, "sample_input_output.csv")
    out.to_csv(sample_csv, index=False)
    print(f"Full sample also saved to: {sample_csv}")


if args.new_file:
    # ---- Mode 2: truly new/unseen file ----
    if not os.path.exists(args.new_file):
        sys.exit(f"File not found: {args.new_file}")
    new_df = pd.read_csv(args.new_file)
    if target not in new_df.columns:
        sys.exit(f"'{target}' column (true labels) not found in {args.new_file} — "
                  f"cannot evaluate without ground truth. Use score_and_classify.py "
                  f"instead if you just want predictions with no labels.")
    X_new = prep_features(new_df)
    y_new = new_df[target]
    proba, tiers = evaluate(X_new, y_new, os.path.basename(args.new_file))
    show_sample_io(new_df, X_new, y_new, proba, tiers)

else:
    # ---- Mode 1: reproduce the same held-out split used during training ----
    if not os.path.exists(ENRICHED_FILE):
        sys.exit(f"File not found: {ENRICHED_FILE}. Run 01/02 pipeline steps first.")
    df = pd.read_csv(ENRICHED_FILE)

    X_all = prep_features(df)
    y_all = df[target]

    X_train, X_test, y_train, y_test = train_test_split(
        X_all, y_all, test_size=0.2, random_state=42, stratify=y_all
    )
    df_test_raw = df.loc[X_test.index]  # original (pre-encoded) rows for readable display

    proba, tiers = evaluate(X_test, y_test, "held-out test split (same split as 03_train_model.py)")
    show_sample_io(df_test_raw, X_test, y_test, proba, tiers)

print("\nDone.")