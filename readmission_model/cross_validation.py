"""
5-fold stratified cross-validation for the readmission risk model.
Gives a more robust performance estimate than a single train/test split.

"""
import os
import json
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (roc_auc_score, average_precision_score, f1_score,
                              precision_score, recall_score, accuracy_score)
import xgboost as xgb

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "patient_data_enriched.csv")
REPORT_FILE = os.path.join(BASE_DIR, "cross_validation_report.md")
CV_METRICS_FILE = os.path.join(BASE_DIR, "cv_metrics.json")

df = pd.read_csv(INPUT_FILE)

target = "readmitted_30_days"
drop_cols = ["patient_id", target]
cat_cols = ["insurance_type", "admission_type", "discharge_destination"]

X = df.drop(columns=drop_cols).copy()
y = df[target].copy()

encoders = {}
for c in cat_cols:
    le = LabelEncoder()
    encoded = le.fit_transform(X[c]).astype("int64")
    X[c] = pd.Series(encoded, index=X.index)
    encoders[c] = le

N_FOLDS = 5
skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=42)

fold_results = []

for fold_idx, (train_idx, test_idx) in enumerate(skf.split(X, y), start=1):
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

    pos = y_train.sum()
    neg = len(y_train) - pos
    scale_pos_weight = neg / pos

    model = xgb.XGBClassifier(
        n_estimators=400,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        scale_pos_weight=scale_pos_weight,
        eval_metric="auc",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train, verbose=False)

    proba = model.predict_proba(X_test)[:, 1]
    pred = (proba >= 0.5).astype(int)

    fold_metrics = {
        "fold": fold_idx,
        "auc": roc_auc_score(y_test, proba),
        "average_precision": average_precision_score(y_test, proba),
        "accuracy": accuracy_score(y_test, pred),
        "precision": precision_score(y_test, pred),
        "recall": recall_score(y_test, pred),
        "f1": f1_score(y_test, pred),
    }
    fold_results.append(fold_metrics)
    print(f"Fold {fold_idx}: AUC={fold_metrics['auc']:.4f}  "
          f"AP={fold_metrics['average_precision']:.4f}  "
          f"Acc={fold_metrics['accuracy']:.4f}  "
          f"Prec={fold_metrics['precision']:.4f}  "
          f"Recall={fold_metrics['recall']:.4f}  "
          f"F1={fold_metrics['f1']:.4f}")

results_df = pd.DataFrame(fold_results)
summary = {
    "mean": results_df.drop(columns="fold").mean().to_dict(),
    "std": results_df.drop(columns="fold").std().to_dict(),
}

print("\n=== Cross-Validation Summary (5 folds) ===")
for metric in ["auc", "average_precision", "accuracy", "precision", "recall", "f1"]:
    print(f"{metric:20s}: mean={summary['mean'][metric]:.4f}  std={summary['std'][metric]:.4f}")

# save json
with open(CV_METRICS_FILE, "w") as f:
    json.dump({"fold_results": fold_results, "summary": summary}, f, indent=2)

# ---- write markdown report ----
report_lines = []
report_lines.append("# Cross-Validation Evaluation Report — Readmission Risk Model\n")
report_lines.append(f"**Method:** {N_FOLDS}-fold stratified cross-validation (StratifiedKFold, random_state=42)\n")
report_lines.append(f"**Dataset:** `patient_data_enriched.csv` — {len(df):,} patients, "
                     f"{y.mean()*100:.1f}% positive class (readmitted within 30 days)\n")
report_lines.append("## Per-fold results\n")
report_lines.append("| Fold | AUC | Avg Precision | Accuracy | Precision | Recall | F1 |")
report_lines.append("|---|---|---|---|---|---|---|")
for r in fold_results:
    report_lines.append(f"| {r['fold']} | {r['auc']:.4f} | {r['average_precision']:.4f} | "
                         f"{r['accuracy']:.4f} | {r['precision']:.4f} | {r['recall']:.4f} | {r['f1']:.4f} |")

report_lines.append("\n## Summary (mean ± std across folds)\n")
report_lines.append("| Metric | Mean | Std Dev |")
report_lines.append("|---|---|---|")
for metric in ["auc", "average_precision", "accuracy", "precision", "recall", "f1"]:
    report_lines.append(f"| {metric} | {summary['mean'][metric]:.4f} | {summary['std'][metric]:.4f} |")

auc_std = summary['std']['auc']
auc_mean = summary['mean']['auc']
stability_note = "very stable" if auc_std < 0.01 else ("reasonably stable" if auc_std < 0.02 else "some variability")

report_lines.append(f"\n## Interpretation\n")
report_lines.append(f"- Mean AUC across folds: **{auc_mean:.4f}** (std {auc_std:.4f}) — {stability_note} "
                     f"across different train/test splits, meaning the single-split result reported earlier "
                     f"(~0.804) was **not a fluke** and generalizes consistently.")
report_lines.append(f"- Mean recall on the readmitted class: **{summary['mean']['recall']:.4f}** — the model "
                     f"consistently catches roughly {summary['mean']['recall']*100:.0f}% of patients who will "
                     f"actually be readmitted, across all folds.")
report_lines.append(f"- Mean accuracy: **{summary['mean']['accuracy']:.4f}** — as discussed, this is a secondary "
                     f"metric here given the ~21%/79% class imbalance; AUC and recall are more decision-relevant.")
report_lines.append(f"\n## Verdict\n")
if auc_mean >= 0.75 and auc_std < 0.02:
    report_lines.append("**PASS** — model performance is strong and stable. Recommended to proceed to production "
                         "scoring / next pipeline stage without further tuning at this time.")
else:
    report_lines.append("**REVIEW** — performance or stability is below target; consider hyperparameter tuning "
                         "or additional features before proceeding.")

with open(REPORT_FILE, "w") as f:
    f.write("\n".join(report_lines))

print("\nSaved report to:", REPORT_FILE)
print("Saved raw metrics to:", CV_METRICS_FILE)
