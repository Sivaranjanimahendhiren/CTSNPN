"""
Train and evaluate XGBoost readmission risk model.

"""
import os
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (roc_auc_score, classification_report,
                              confusion_matrix, average_precision_score, f1_score)
import xgboost as xgb

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "patient_data_enriched.csv")
MODEL_FILE = os.path.join(BASE_DIR, "readmission_model.joblib")
METRICS_FILE = os.path.join(BASE_DIR, "metrics.json")
IMPORTANCE_FILE = os.path.join(BASE_DIR, "feature_importance.csv")

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

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

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

model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

proba = model.predict_proba(X_test)[:, 1]
pred = (proba >= 0.5).astype(int)

auc = roc_auc_score(y_test, proba)
ap = average_precision_score(y_test, proba)
f1 = f1_score(y_test, pred)
report = classification_report(y_test, pred, digits=3)
cm = confusion_matrix(y_test, pred)

print("AUC:", round(auc, 4))
print("Average Precision:", round(ap, 4))
print("F1 (thresh 0.5):", round(f1, 4))
print(report)
print("Confusion matrix:\n", cm)

q_high = np.quantile(proba, 0.85)
q_med = np.quantile(proba, 0.60)
def tier(p):
    if p >= q_high:
        return "High (30-day follow-up)"
    elif p >= q_med:
        return "Medium (15-day follow-up)"
    else:
        return "Low (10-day follow-up)"

tiers = pd.Series(proba).apply(tier)
tier_counts = tiers.value_counts()
print("\nRisk tier distribution on test set:\n", tier_counts)

tier_df = pd.DataFrame({"tier": tiers.values, "actual": y_test.values})
tier_rates = tier_df.groupby("tier")["actual"].mean()
print("\nActual readmission rate by tier:\n", tier_rates)

importances = pd.Series(model.feature_importances_, index=X.columns).sort_values(ascending=False)
print("\nTop 15 features:\n", importances.head(15))

joblib.dump({"model": model, "encoders": encoders, "feature_names": list(X.columns),
             "risk_thresholds": {"q_high": float(q_high), "q_med": float(q_med)}},
            MODEL_FILE)

metrics = {
    "auc": auc, "average_precision": ap, "f1_at_0.5": f1,
    "n_train": len(X_train), "n_test": len(X_test),
    "positive_rate_train": float(y_train.mean()),
    "positive_rate_test": float(y_test.mean()),
    "confusion_matrix": cm.tolist(),
    "risk_tier_counts": tier_counts.to_dict(),
    "risk_tier_actual_readmit_rate": tier_rates.to_dict(),
    "top_15_features": importances.head(15).to_dict(),
}
with open(METRICS_FILE, "w") as f:
    json.dump(metrics, f, indent=2)

importances.to_csv(IMPORTANCE_FILE, header=["importance"])
print("\nSaved model to:", MODEL_FILE)
print("Saved metrics to:", METRICS_FILE)
