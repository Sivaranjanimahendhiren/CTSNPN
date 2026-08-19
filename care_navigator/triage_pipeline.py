"""
Triage Navigator - Full Inference Pipeline (simplified)
==========================================================
Two stages, not three:

  Patient intake
       |
  Model 1: hybrid safety gate + care_recommendation classifier
       |   (predicts across all 5 classes: ED, Telehealth, Urgent_Care,
       |    PCP_Appointment, Care_Management -- with the rule-based
       |    override guaranteeing critical patients land on ED)
       v
  Care center recommender (this file's job)
       |   (matches the predicted care type + patient zip to a ranked
       |    shortlist of real facilities)
       v
  Final care plan

There is no separate "care navigation" model anymore -- Model 1 already
predicts the full 5-class care_recommendation directly, so a second model
re-predicting a subset of that would just be redundant.
"""

import pandas as pd
import numpy as np
import pickle
from care_center_recommender import recommend_care_centers


def _prep_features(row, feature_columns):
    """Recreate Model 1's feature engineering for a single patient record
    (a pandas Series)."""
    d = row.to_dict()

    d["age"] = 2010 - (d["BENE_BIRTH_DT"] // 10000)
    d["is_male"] = 1 if d["BENE_SEX_IDENT_CD"] == 1 else 0
    for col in ["SP_CHF", "SP_CHRNKIDN", "SP_CNCR", "SP_COPD",
                "SP_DIABETES", "SP_ISCHMCHT", "SP_STRKETIA"]:
        d[col] = 1 if d[col] == 1 else 0

    d["spo2_home"] = d["spo2_home"] if pd.notna(d.get("spo2_home")) else 98.0
    d["temperature_home"] = d["temperature_home"] if pd.notna(d.get("temperature_home")) else 36.8
    d["heart_rate_home"] = d["heart_rate_home"] if pd.notna(d.get("heart_rate_home")) else 75.0

    symptom = d.pop("primary_symptom")
    onset = d.pop("symptom_onset")
    for col in feature_columns:
        if col.startswith("primary_symptom_"):
            d[col] = 1 if col == f"primary_symptom_{symptom}" else 0
        elif col.startswith("symptom_onset_"):
            d[col] = 1 if col == f"symptom_onset_{onset}" else 0

    for junk in ["BENE_BIRTH_DT", "BENE_SEX_IDENT_CD", "DESYNPUF_ID",
                 "needs_ed", "care_recommendation", "patient_zip"]:
        d.pop(junk, None)

    return pd.DataFrame([{c: d.get(c, 0) for c in feature_columns}])


def rule_based_critical_flag(row):
    """Same hard safety rules used inside Model 1's training-time override.
    Re-applied at inference time so a single bad model prediction can never
    downgrade a genuinely critical patient."""
    age = 2010 - (row["BENE_BIRTH_DT"] // 10000)
    spo2 = row["spo2_home"] if pd.notna(row["spo2_home"]) else 98.0
    temp = row["temperature_home"] if pd.notna(row["temperature_home"]) else 36.8
    hr = row["heart_rate_home"] if pd.notna(row["heart_rate_home"]) else 75.0

    crit_cardiac = (
        row["primary_symptom"] == "chest_pain"
        and row["symptom_onset"] == "sudden"
        and (row["SP_ISCHMCHT"] == 1 or row["SP_CHF"] == 1)
    )
    severe_chest = row["primary_symptom"] == "chest_pain" and row["pain_level"] >= 8.5
    hypoxia = spo2 < 90
    sepsis = row["primary_symptom"] == "fever" and row["SP_CNCR"] == 1
    extreme_vitals = temp >= 39.5 or hr >= 135
    elderly_abdomen = (
        row["primary_symptom"] == "abdominal_pain"
        and row["symptom_onset"] == "sudden"
        and age >= 72
        and row["pain_level"] >= 7.0
    )

    return bool(crit_cardiac or severe_chest or hypoxia or sepsis
                or extreme_vitals or elderly_abdomen)


def route_patient(patient_row, model_artifacts):
    """
    patient_row: pandas Series with raw intake fields.
    model_artifacts: dict loaded from triage_navigator_model.pkl (Model 1).
    Returns (recommendation: str, reason: str)
    """
    if rule_based_critical_flag(patient_row):
        return "ED", "Routed by clinical safety rule (bypasses ML model)."

    model = model_artifacts["model"]
    encoder = model_artifacts["label_encoder"]
    feature_columns = model_artifacts["feature_columns"]

    X = _prep_features(patient_row, feature_columns)
    pred_idx = model.predict(X)[0]
    recommendation = encoder.inverse_transform([pred_idx])[0]
    return recommendation, "Routed by Model 1 (care_recommendation classifier)."


def route_and_recommend_facility(patient_row, model_artifacts,
                                  facility_directory, quality_scores, cahps_scores):
    """
    Full pipeline: Model 1 (safety + care_recommendation) -> facility match.
    Requires patient_row to include a 'patient_zip' field.
    """
    recommendation, reason = route_patient(patient_row, model_artifacts)

    patient_zip = patient_row.get("patient_zip")
    if patient_zip is None:
        return recommendation, reason, [], "No patient_zip available -- cannot locate facilities."

    facilities = recommend_care_centers(
        patient_zip, recommendation, facility_directory, quality_scores, cahps_scores
    )
    facility_note = None if facilities else "No matching facilities found within range."
    return recommendation, reason, facilities, facility_note


if __name__ == "__main__":
    from facility_data_demo import FACILITY_DIRECTORY, QUALITY_SCORES, CAHPS_SCORES

    df = pd.read_csv("triage_navigator_dataset_with_zip.csv", dtype={"patient_zip": str})

    with open("triage_navigator_model.pkl", "rb") as f:
        model_artifacts = pickle.load(f)

    sample = df.sample(5, random_state=1)
    for _, row in sample.iterrows():
        rec, reason, facilities, note = route_and_recommend_facility(
            row, model_artifacts, FACILITY_DIRECTORY, QUALITY_SCORES, CAHPS_SCORES
        )
        print(f"\nPatient {row['DESYNPUF_ID']} (zip {row['patient_zip']}): "
              f"symptom={row['primary_symptom']}, onset={row['symptom_onset']}, "
              f"pain={row['pain_level']}")
        print(f"  -> {rec} ({reason})")
        if facilities:
            for f in facilities:
                print(f"     - {f['facility_name']} ({f['city']}, {f['state']}) "
                      f"| {f['distance_miles']} mi | quality {f['quality_score']} "
                      f"| rank_score {f['rank_score']}")
        elif note:
            print(f"     {note}")
