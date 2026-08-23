"""
Node 2: Understand
Responsibility:
- Use LangChain + Llama-compatible LLM to interpret patient check-in responses
- Convert natural language feedback into validated structured information (ClinicalFeedbackAnalysis)
- The LLM does NOT directly modify PatientState, does NOT decide routing, and does NOT invent thresholds
"""

from typing import Any, Dict, List, Optional
from ..state.patient_state import PatientState
from ..llm.service import LLMService
from ..llm.schemas import ClinicalFeedbackAnalysis

NO_SYMPTOM_TOKENS = {
    "none", "no", "nil", "n/a", "nothing", "improving", "fine", "good", "all good", "feeling fine", "resolved"
}


def understand_node(state: PatientState) -> Dict[str, Any]:
    """
    Step 2: Understand
    Interprets natural-language feedback and updates structured state (symptoms, adherence).
    Validates LLM output into ClinicalFeedbackAnalysis before applying state diff.
    """
    event = state.get("current_event") or {}
    feedback_data = event.get("feedback") or {}
    patient_id = state.get("patient_id", "UNKNOWN")
    current_day = state.get("current_day", 0)

    current_symptoms = list(state.get("symptoms", []))
    current_adherence = state.get("medication_adherence", 1.0)
    feedback_history = state.get("feedback_history", [])

    # 1. Parse feedback fields
    feedback_text = ""
    medication_taken_flag: Optional[bool] = None
    notes: Optional[str] = None

    if isinstance(feedback_data, dict):
        raw_symptom = feedback_data.get("symptoms")
        if isinstance(raw_symptom, str):
            feedback_text = raw_symptom
        elif isinstance(raw_symptom, list) and raw_symptom:
            feedback_text = ", ".join(str(s) for s in raw_symptom if str(s).strip())

        raw_msg = feedback_data.get("raw_text") or feedback_data.get("text") or feedback_data.get("notes")
        if raw_msg and not feedback_text:
            feedback_text = str(raw_msg)
        elif not feedback_text and raw_symptom is not None:
            feedback_text = "No symptoms reported"

        medication_taken_flag = feedback_data.get("medication_taken")
        notes = feedback_data.get("notes")
    elif isinstance(feedback_data, str):
        feedback_text = feedback_data

    # If feedback indicates symptoms resolved / none, clear existing symptoms
    if feedback_text.strip().lower() in NO_SYMPTOM_TOKENS or feedback_text == "No symptoms reported":
        current_symptoms = []

    # 2. Invoke LLM Service for structured feedback analysis
    llm_service = LLMService()
    analysis: ClinicalFeedbackAnalysis = llm_service.analyze_feedback(
        patient_id=patient_id,
        current_day=current_day,
        feedback_text=feedback_text,
        medication_taken=medication_taken_flag,
        notes=notes,
    )

    # 3. Extract and filter symptoms
    new_symptoms = [
        s for s in analysis.extracted_symptoms
        if s.strip().lower() not in NO_SYMPTOM_TOKENS
    ]

    # If recovery is improving/resolved or new report specifies no symptoms, update active symptoms
    if analysis.symptom_status in ("improving", "resolved", "none") or not new_symptoms:
        combined_symptoms = new_symptoms
    else:
        combined_symptoms = list(dict.fromkeys(current_symptoms + new_symptoms))

    # 4. Calculate updated medication adherence rate
    if medication_taken_flag is False or analysis.medication_status == "non_adherent":
        total_reports = max(len(feedback_history) + 1, 1)
        taken_count = round(current_adherence * (total_reports - 1))
        updated_adherence = max(0.0, min(1.0, round(taken_count / total_reports, 2)))
    elif medication_taken_flag is True or analysis.medication_status == "adherent":
        total_reports = max(len(feedback_history) + 1, 1)
        taken_count = round(current_adherence * (total_reports - 1)) + 1
        updated_adherence = max(0.0, min(1.0, round(taken_count / total_reports, 2)))
    else:
        updated_adherence = current_adherence

    # 5. Data quality adjustment based on extraction
    obs_quality = state.get("data_quality", "GOOD")
    if obs_quality in ("POOR", "DEGRADED", "INCOMPLETE"):
        data_quality = obs_quality
    elif analysis.data_quality in ("incomplete", "low", "poor"):
        data_quality = "INCOMPLETE"
    else:
        data_quality = "GOOD"

    return {
        "symptoms": combined_symptoms,
        "medication_adherence": updated_adherence,
        "data_quality": data_quality,
        "latest_feedback": analysis.model_dump(),
    }
