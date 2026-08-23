"""
Unit and Integration Tests for STAGE 3:
Readmission Prediction Ingestion Service, Schema Validation, and REST API.
Validates all 18 specified test requirements and architectural isolation guards.
"""

import pytest
from pydantic import ValidationError

from adaptive_postcare.storage.database import DatabaseSessionManager
from adaptive_postcare.storage.repositories import (
    PatientRepository,
    PredictionRepository,
    CarePlanRepository,
    PatientProfileRepository,
)
from adaptive_postcare.schemas.readmission_input import InitialRiskEvent
from adaptive_postcare.services.readmission_prediction_service import ReadmissionPredictionService
from api import (
    ingest_prediction_endpoint,
    get_latest_prediction_endpoint,
    get_prediction_history_endpoint,
    prediction_service as global_api_service,
)


@pytest.fixture
def test_db():
    """Provides an isolated in-memory test database."""
    manager = DatabaseSessionManager(db_url="sqlite:///:memory:")
    manager.init_db()
    return manager


@pytest.fixture
def service(test_db):
    """Provides a fresh ReadmissionPredictionService bound to the test database."""
    return ReadmissionPredictionService(db_manager=test_db)


# =========================================================================
# 1. VALID PREDICTION IS ACCEPTED
# =========================================================================
def test_valid_prediction_accepted(service):
    res = service.ingest_prediction({
        "patient_id": "P001",
        "risk_score": 0.87,
        "risk_level": "HIGH",
        "recommended_care_days": 30,
        "model_version": "readmission-v1",
    })
    assert res["status"] == "stored"
    assert res["patient_id"] == "P001"
    assert res["risk_score"] == 0.87
    assert res["risk_level"] == "HIGH"
    assert res["recommended_care_days"] == 30
    assert res["model_version"] == "readmission-v1"
    assert res["prediction_id"] is not None


# =========================================================================
# 2. INVALID PATIENT_ID REJECTED
# =========================================================================
@pytest.mark.parametrize("bad_id", ["", "   ", None])
def test_invalid_patient_id_rejected(service, bad_id):
    with pytest.raises((ValidationError, ValueError)):
        service.ingest_prediction({
            "patient_id": bad_id,
            "risk_score": 0.5,
            "risk_level": "MEDIUM",
            "recommended_care_days": 15,
        })


# =========================================================================
# 3 & 4. RISK_SCORE BOUNDS ( < 0 or > 1 REJECTED)
# =========================================================================
@pytest.mark.parametrize("invalid_score", [-0.01, -0.5, -5.0, 1.01, 1.5, 99.0])
def test_invalid_risk_score_rejected(service, invalid_score):
    with pytest.raises((ValidationError, ValueError)):
        service.ingest_prediction({
            "patient_id": "P_SCORE_INV",
            "risk_score": invalid_score,
            "risk_level": "HIGH",
            "recommended_care_days": 30,
        })


# =========================================================================
# 5. INVALID RISK_LEVEL REJECTED
# =========================================================================
@pytest.mark.parametrize("bad_level", ["EXTREME", "MODERATE", "VERY_HIGH", "UNKNOWN", ""])
def test_invalid_risk_level_rejected(service, bad_level):
    with pytest.raises((ValidationError, ValueError)):
        service.ingest_prediction({
            "patient_id": "P_LEVEL_INV",
            "risk_score": 0.6,
            "risk_level": bad_level,
            "recommended_care_days": 20,
        })


# =========================================================================
# 6 & 7. RECOMMENDED_CARE_DAYS BOUNDS (<= 0 REJECTED)
# =========================================================================
@pytest.mark.parametrize("bad_days", [0, -1, -5, -30])
def test_invalid_care_duration_rejected(service, bad_days):
    with pytest.raises((ValidationError, ValueError)):
        service.ingest_prediction({
            "patient_id": "P_DAYS_INV",
            "risk_score": 0.4,
            "risk_level": "MEDIUM",
            "recommended_care_days": bad_days,
        })


# =========================================================================
# 8, 9, 10. ARBITRARY LEVEL + DURATION COMBINATIONS ACCEPTED
# =========================================================================
def test_high_risk_custom_duration_accepted(service):
    """Case 8: HIGH risk with non-standard 20 days accepted."""
    res = service.ingest_prediction({
        "patient_id": "P004",
        "risk_score": 0.74,
        "risk_level": "HIGH",
        "recommended_care_days": 20,
        "model_version": "readmission-v1",
    })
    assert res["risk_level"] == "HIGH"
    assert res["recommended_care_days"] == 20


def test_medium_risk_custom_duration_accepted(service):
    """Case 9: MEDIUM risk with non-standard 14 days accepted."""
    res = service.ingest_prediction({
        "patient_id": "P005",
        "risk_score": 0.48,
        "risk_level": "MEDIUM",
        "recommended_care_days": 14,
        "model_version": "readmission-v1",
    })
    assert res["risk_level"] == "MEDIUM"
    assert res["recommended_care_days"] == 14


def test_low_risk_custom_duration_accepted(service):
    """Case 10: LOW risk with 10 days accepted."""
    res = service.ingest_prediction({
        "patient_id": "P006",
        "risk_score": 0.21,
        "risk_level": "LOW",
        "recommended_care_days": 10,
        "model_version": "readmission-v1",
    })
    assert res["risk_level"] == "LOW"
    assert res["recommended_care_days"] == 10


# =========================================================================
# 11, 12, 13. MULTIPLE PREDICTIONS, LATEST QUERY, & HISTORY PRESERVED
# =========================================================================
def test_multiple_predictions_and_history_preserved(service):
    """Cases 11, 12, 13: Multiple predictions for P001 are preserved in order."""
    # Prediction 1: Initial estimate (MEDIUM, 15 days)
    res1 = service.ingest_prediction({
        "patient_id": "P001",
        "risk_score": 0.62,
        "risk_level": "MEDIUM",
        "recommended_care_days": 15,
        "model_version": "readmission-v1",
    })
    assert res1["risk_score"] == 0.62

    # Prediction 2: Updated estimate (HIGH, 30 days)
    res2 = service.ingest_prediction({
        "patient_id": "P001",
        "risk_score": 0.87,
        "risk_level": "HIGH",
        "recommended_care_days": 30,
        "model_version": "readmission-v2",
    })
    assert res2["risk_score"] == 0.87

    # Query latest prediction -> must be prediction 2
    latest = service.get_latest_prediction("P001")
    assert latest is not None
    assert latest["risk_score"] == 0.87
    assert latest["risk_level"] == "HIGH"
    assert latest["recommended_care_days"] == 30
    assert latest["model_version"] == "readmission-v2"

    # Query full history -> must contain both records
    history = service.get_prediction_history("P001")
    assert len(history) == 2
    assert history[0]["risk_score"] == 0.62
    assert history[0]["model_version"] == "readmission-v1"
    assert history[1]["risk_score"] == 0.87
    assert history[1]["model_version"] == "readmission-v2"


# =========================================================================
# 14. MODEL VERSIONING STORED
# =========================================================================
def test_model_version_stored(service):
    """Case 14: Model versions (v1, v2, v2.1) are accurately stored."""
    service.ingest_prediction({
        "patient_id": "P_VERS",
        "risk_score": 0.35,
        "risk_level": "LOW",
        "recommended_care_days": 10,
        "model_version": "readmission-rf-v2.1",
    })
    latest = service.get_latest_prediction("P_VERS")
    assert latest["model_version"] == "readmission-rf-v2.1"


# =========================================================================
# 15. PREDICTION INGESTION DOES NOT CREATE CARE PLANS
# =========================================================================
def test_prediction_ingestion_does_not_create_care_plan(service, test_db):
    """Case 15: Ingesting prediction leaves care_plans table empty."""
    service.ingest_prediction({
        "patient_id": "P_NO_PLAN",
        "risk_score": 0.85,
        "risk_level": "HIGH",
        "recommended_care_days": 30,
    })

    with test_db.session_scope() as sess:
        care_plan_repo = CarePlanRepository(sess)
        active_plan = care_plan_repo.get_active_care_plan("P_NO_PLAN")
        assert active_plan is None
        all_plans = care_plan_repo.list_patient_care_plans("P_NO_PLAN")
        assert len(all_plans) == 0


# =========================================================================
# 16. PREDICTION INGESTION DOES NOT INVOKE LANGGRAPH
# =========================================================================
def test_prediction_ingestion_does_not_invoke_langgraph(service, monkeypatch):
    """Case 16: Verifies that LangGraph execution functions are not invoked."""
    called = []

    def fake_observe(state):
        called.append("observe")
        return {}

    monkeypatch.setattr("adaptive_postcare.orchestrator.observe_node", fake_observe)

    service.ingest_prediction({
        "patient_id": "P_NO_GRAPH",
        "risk_score": 0.55,
        "risk_level": "MEDIUM",
        "recommended_care_days": 15,
    })

    assert len(called) == 0, "LangGraph observe_node was unexpectedly called during prediction ingestion!"


# =========================================================================
# 17. PREDICTION INGESTION DOES NOT CHANGE POST-CARE STATUS
# =========================================================================
def test_prediction_ingestion_does_not_change_lifecycle_status(service, test_db):
    """Case 17: Pre-existing hospital lifecycle status (e.g. ADMITTED) is not changed to active post-care."""
    # Pre-set patient status to ADMITTED
    with test_db.session_scope() as sess:
        p_repo = PatientRepository(sess)
        p_repo.create_patient("P_STATUS_CHECK")
        prof_repo = PatientProfileRepository(sess)
        prof_repo.create_or_update_profile(patient_id="P_STATUS_CHECK", care_status="ADMITTED")

    # Ingest prediction
    service.ingest_prediction({
        "patient_id": "P_STATUS_CHECK",
        "risk_score": 0.88,
        "risk_level": "HIGH",
        "recommended_care_days": 30,
    })

    # Status must still be ADMITTED
    with test_db.session_scope() as sess:
        prof_repo = PatientProfileRepository(sess)
        prof = prof_repo.get_profile("P_STATUS_CHECK")
        assert prof.care_status == "ADMITTED", f"Expected ADMITTED, got {prof.care_status}"


# =========================================================================
# 18. REST API ENDPOINTS VERIFIED (POST /api/predictions & GET)
# =========================================================================
def test_api_endpoints_ingestion_and_retrieval(test_db):
    """Case 18: Tests FastAPI route handlers for prediction ingestion and history."""
    global_api_service.db = test_db

    # Ingest prediction via endpoint
    req_payload = InitialRiskEvent(
        patient_id="P_API_01",
        risk_score=0.91,
        risk_level="HIGH",
        recommended_care_days=30,
        model_version="readmission-v1",
    )
    post_res = ingest_prediction_endpoint(req_payload)
    assert post_res["status"] == "stored"
    assert post_res["patient_id"] == "P_API_01"
    assert post_res["risk_score"] == 0.91

    # Retrieve latest prediction via endpoint
    latest_data = get_latest_prediction_endpoint("P_API_01")
    assert latest_data["patient_id"] == "P_API_01"
    assert latest_data["risk_score"] == 0.91

    # Retrieve prediction history via endpoint
    hist_data = get_prediction_history_endpoint("P_API_01")
    assert hist_data["patient_id"] == "P_API_01"
    assert hist_data["total_count"] == 1
