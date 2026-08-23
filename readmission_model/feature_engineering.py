"""
Engineer trend features from synthetic longitudinal data and merge with main dataset.

"""
import os
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_FILE = os.path.join(BASE_DIR, "patient_data_40k.csv")
LONG_FILE = os.path.join(BASE_DIR, "synthetic_longitudinal_full.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "patient_data_enriched.csv")

df = pd.read_csv(MAIN_FILE)
long_df = pd.read_csv(LONG_FILE)
long_df["visit_date"] = pd.to_datetime(long_df["visit_date"])

feat_rows = []
for pid, g in long_df.groupby("patient_id"):
    g = g.sort_values("visit_date")
    n = len(g)

    t = (g["visit_date"] - g["visit_date"].min()).dt.days.values / 365.0
    def slope(y):
        if len(y) < 2 or np.ptp(t) == 0:
            return 0.0
        return np.polyfit(t, y, 1)[0]

    creat_slope = slope(g["creatinine"].values)
    hba1c_slope = slope(g["hba1c"].values)
    sbp_slope = slope(g["systolic_bp"].values)

    days_since_last_visit = (pd.Timestamp("2026-08-01") - g["visit_date"].max()).days
    visit_span_days = (g["visit_date"].max() - g["visit_date"].min()).days
    visit_frequency = n / max(visit_span_days, 1) * 365

    feat_rows.append({
        "patient_id": pid,
        "hist_num_visits": n,
        "hist_creatinine_slope": round(creat_slope, 4),
        "hist_hba1c_slope": round(hba1c_slope, 4),
        "hist_sbp_slope": round(sbp_slope, 4),
        "hist_days_since_last_visit": days_since_last_visit,
        "hist_visit_frequency_per_year": round(visit_frequency, 2),
        "hist_ed_visit_rate": round(g["ed_visit_flag"].mean(), 3),
        "hist_last_creatinine": g["creatinine"].iloc[-1],
        "hist_last_hba1c": g["hba1c"].iloc[-1],
        "hist_med_trend_insulin": g["on_insulin"].iloc[-1],
        "hist_med_trend_cardiac": g["on_cardiac_meds"].iloc[-1],
    })

feat_df = pd.DataFrame(feat_rows)
enriched = df.merge(feat_df, on="patient_id", how="left")

enriched["creatinine_delta_vs_history"] = enriched["creatinine"] - enriched["hist_last_creatinine"]
enriched["hba1c_delta_vs_history"] = enriched["hbA1c"] - enriched["hist_last_hba1c"]

enriched.to_csv(OUTPUT_FILE, index=False)
print("Enriched shape:", enriched.shape)
print(enriched.isnull().sum().sum(), "total nulls")
print("Saved to:", OUTPUT_FILE)
print(enriched[["patient_id","hist_num_visits","hist_creatinine_slope","hist_hba1c_slope",
                 "hist_visit_frequency_per_year","creatinine_delta_vs_history"]].head())
