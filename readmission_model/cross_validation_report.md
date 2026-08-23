# Cross-Validation Evaluation Report — Readmission Risk Model

**Method:** 5-fold stratified cross-validation (StratifiedKFold, random_state=42)

**Dataset:** `patient_data_enriched.csv` — 40,000 patients, 21.0% positive class (readmitted within 30 days)

## Per-fold results

| Fold | AUC | Avg Precision | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| 1 | 0.7942 | 0.5130 | 0.7206 | 0.4039 | 0.6979 | 0.5117 |
| 2 | 0.8028 | 0.5101 | 0.7302 | 0.4160 | 0.7064 | 0.5236 |
| 3 | 0.8096 | 0.5159 | 0.7315 | 0.4175 | 0.7064 | 0.5248 |
| 4 | 0.8032 | 0.5042 | 0.7286 | 0.4159 | 0.7242 | 0.5284 |
| 5 | 0.8090 | 0.5274 | 0.7268 | 0.4122 | 0.7088 | 0.5212 |

## Summary (mean ± std across folds)

| Metric | Mean | Std Dev |
|---|---|---|
| auc | 0.8038 | 0.0062 |
| average_precision | 0.5141 | 0.0086 |
| accuracy | 0.7276 | 0.0043 |
| precision | 0.4131 | 0.0055 |
| recall | 0.7087 | 0.0096 |
| f1 | 0.5219 | 0.0063 |

## Interpretation

- Mean AUC across folds: **0.8038** (std 0.0062) — very stable across different train/test splits, meaning the single-split result reported earlier (~0.804) was **not a fluke** and generalizes consistently.
- Mean recall on the readmitted class: **0.7087** — the model consistently catches roughly 71% of patients who will actually be readmitted, across all folds.
- Mean accuracy: **0.7276** — as discussed, this is a secondary metric here given the ~21%/79% class imbalance; AUC and recall are more decision-relevant.

## Verdict

**PASS** — model performance is strong and stable. Recommended to proceed to production scoring / next pipeline stage without further tuning at this time.