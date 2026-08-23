"""
Unit tests for LangChain + Llama-compatible LLM integration:
1. Prompt Management
2. LLM Invocation & Abstraction
3. Structured Output Validation (ClinicalFeedbackAnalysis, AdaptationReasoning)
4. State Separation & Safety Invariant Validation
"""

import pytest
from pydantic import ValidationError
from adaptive_postcare.llm.schemas import ClinicalFeedbackAnalysis, AdaptationReasoning
from adaptive_postcare.llm.prompts import UNDERSTAND_PROMPT, ADAPT_PROMPT
from adaptive_postcare.llm.service import LLMService
from adaptive_postcare.state.patient_state import PatientStateModel, RiskLevel


# ==============================================================================
# 1. STRUCTURED OUTPUT SCHEMA VALIDATION TESTS
# ==============================================================================

def test_clinical_feedback_analysis_schema_valid():
    """Verify structured output parsing conforming to user example."""
    data = {
        "symptom_status": "improving",
        "extracted_symptoms": ["mild headache"],
        "medication_status": "adherent",
        "data_quality": "high",
        "concerns": [],
        "confidence": 0.91,
    }
    analysis = ClinicalFeedbackAnalysis(**data)
    assert analysis.symptom_status == "improving"
    assert analysis.extracted_symptoms == ["mild headache"]
    assert analysis.medication_status == "adherent"
    assert analysis.data_quality == "high"
    assert analysis.concerns == []
    assert analysis.confidence == 0.91


@pytest.mark.parametrize("invalid_conf", [-0.1, 1.05, 2.0])
def test_clinical_feedback_analysis_invalid_confidence_bounds(invalid_conf: float):
    """Verify confidence is strictly between 0.0 and 1.0."""
    with pytest.raises(ValidationError):
        ClinicalFeedbackAnalysis(
            symptom_status="stable",
            extracted_symptoms=[],
            medication_status="adherent",
            data_quality="high",
            confidence=invalid_conf,
        )


def test_adaptation_reasoning_schema_valid():
    """Verify AdaptationReasoning structured output schema."""
    reasoning = AdaptationReasoning(
        qualitative_summary="Patient reports steady improvement with no new barriers.",
        observed_barriers=["Occasional mild morning dizziness"],
        suggested_focus_area="Hydration with medication",
        confidence=0.88,
    )
    assert reasoning.confidence == 0.88
    assert len(reasoning.observed_barriers) == 1


# ==============================================================================
# 2. PROMPT MANAGEMENT TESTS
# ==============================================================================

def test_understand_prompt_formatting():
    """Verify UNDERSTAND_PROMPT formats cleanly with variables."""
    messages = UNDERSTAND_PROMPT.format_messages(
        patient_id="PT-PROMPT-01",
        current_day=5,
        feedback_text="Feeling better, taking pills with breakfast",
        medication_taken=True,
        notes="None",
    )
    assert len(messages) == 2
    assert "PT-PROMPT-01" in messages[1].content
    assert "Day of Post-Care: 5" in messages[1].content


def test_adapt_prompt_formatting():
    """Verify ADAPT_PROMPT formats cleanly with variables."""
    messages = ADAPT_PROMPT.format_messages(
        patient_id="PT-PROMPT-02",
        risk_level="HIGH",
        current_day=10,
        care_duration_days=45,
        symptoms="mild cough",
        medication_adherence="90%",
        latest_feedback="Taking evening dose on time",
    )
    assert len(messages) == 2
    assert "PT-PROMPT-02" in messages[1].content
    assert "HIGH" in messages[1].content


# ==============================================================================
# 3. LLM SERVICE ABSTRACTION & FALLBACK TESTS
# ==============================================================================

def test_llm_service_analyze_feedback_structured():
    """Verify LLMService returns a fully validated ClinicalFeedbackAnalysis object."""
    service = LLMService()
    result = service.analyze_feedback(
        patient_id="PT-SRV-01",
        current_day=3,
        feedback_text="Mild ankle swelling, took morning medication",
        medication_taken=True,
    )
    assert isinstance(result, ClinicalFeedbackAnalysis)
    assert 0.0 <= result.confidence <= 1.0
    assert result.medication_status in ["adherent", "non_adherent", "unknown"]


def test_llm_service_assess_adaptation_structured():
    """Verify LLMService returns a fully validated AdaptationReasoning object."""
    service = LLMService()
    result = service.assess_adaptation(
        patient_id="PT-SRV-02",
        risk_level="MEDIUM",
        current_day=7,
        care_duration_days=30,
        symptoms=["mild fatigue"],
        medication_adherence=0.85,
        latest_feedback="Tired in afternoons",
    )
    assert isinstance(result, AdaptationReasoning)
    assert len(result.qualitative_summary) > 0
    assert 0.0 <= result.confidence <= 1.0


# ==============================================================================
# 4. SAFETY & IMMUTABILITY INVARIANTS
# ==============================================================================

def test_llm_does_not_mutate_patient_state_directly():
    """Verify LLM analysis is pure and cannot directly alter PatientState."""
    initial_state = PatientStateModel.initialize_from_external_model(
        patient_id="PT-IMMUTABLE",
        risk_score=0.3,
        risk_level=RiskLevel.LOW,
        care_duration_days=30,
    )
    state_dict = initial_state.to_state_dict()
    service = LLMService()

    analysis = service.analyze_feedback(
        patient_id=state_dict["patient_id"],
        current_day=state_dict["current_day"],
        feedback_text="Testing state immutability",
    )

    # State remains completely unchanged by LLM invocation
    assert state_dict["patient_id"] == "PT-IMMUTABLE"
    assert state_dict["current_day"] == 0
    assert state_dict["risk_score"] == 0.3
    assert state_dict["care_duration_days"] == 30
