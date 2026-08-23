"""
FastAPI REST Gateway for Adaptive Post-Care Services.
STAGE 3: Exposes Prediction Ingestion endpoints.
Does NOT activate the post-care agent or create care plans upon prediction ingestion.
"""

from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from adaptive_postcare.schemas.readmission_input import InitialRiskEvent
from adaptive_postcare.services.readmission_prediction_service import ReadmissionPredictionService

app = FastAPI(
    title="Adaptive Post-Care Readmission Prediction API",
    version="1.0.0",
    description="Receives and persists external ML readmission model predictions without activating LangGraph.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

prediction_service = ReadmissionPredictionService()


class PredictionIngestResponse(BaseModel):
    prediction_id: str
    patient_id: str
    risk_score: float
    risk_level: str
    recommended_care_days: int
    model_version: str
    status: str = "stored"


@app.post(
    "/api/predictions",
    response_model=PredictionIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest external readmission model prediction",
)
def ingest_prediction_endpoint(payload: InitialRiskEvent):
    """
    Receives and persists external readmission model outputs into PostgreSQL.
    Does NOT trigger the LangGraph post-care agent.
    """
    try:
        result = prediction_service.ingest_prediction(payload)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get(
    "/api/predictions/{patient_id}/latest",
    summary="Get latest prediction for a patient",
)
def get_latest_prediction_endpoint(patient_id: str):
    """Retrieves the most recent readmission prediction record for a patient."""
    pred = prediction_service.get_latest_prediction(patient_id)
    if not pred:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No predictions found for patient '{patient_id}'",
        )
    return pred


@app.get(
    "/api/predictions/{patient_id}/history",
    summary="Get prediction history for a patient",
)
def get_prediction_history_endpoint(patient_id: str):
    """Retrieves all historical predictions for a patient in chronological order."""
    history = prediction_service.get_prediction_history(patient_id)
    return {"patient_id": patient_id, "predictions": history, "total_count": len(history)}
