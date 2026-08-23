"""
Schemas for Unstructured Lab Report Extraction and pgvector Storage.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExtractedBiomarker(BaseModel):
    """
    Structured biomarker data extracted from unstructured clinical text.
    """
    biomarker_name: str = Field(..., description="Standardized name of the biomarker, e.g. 'Serum Creatinine', 'Potassium'")
    value: float = Field(..., description="Discrete numeric value of the test result")
    unit: str = Field(default="", description="Unit of measurement, e.g. 'mg/dL', 'mEq/L'")
    reference_low: Optional[float] = Field(default=None, description="Lower bound of reference normal range")
    reference_high: Optional[float] = Field(default=None, description="Upper bound of reference normal range")
    status: str = Field(default="NORMAL", description="Status flag: NORMAL, ELEVATED, CRITICAL_HIGH, LOW, CRITICAL_LOW")
    raw_text: Optional[str] = Field(default=None, description="Original raw snippet extracted from the report")


class ClinicalDocumentChunk(BaseModel):
    """
    Qualitative text chunk with metadata for pgvector embedding.
    """
    chunk_id: Optional[str] = None
    patient_id: str
    doc_type: str = Field(default="LAB_IMPRESSION", description="LAB_IMPRESSION, DISCHARGE_SUMMARY, DOCTOR_NOTE")
    text_content: str
    embedding: Optional[List[float]] = None
    created_at: Optional[datetime] = None


class LabReportAnalysis(BaseModel):
    """
    Consolidated analysis combining extracted biomarkers and qualitative medical impressions.
    """
    patient_id: str
    report_title: str = "Clinical Laboratory Examination Report"
    collected_date: Optional[str] = None
    biomarkers: List[ExtractedBiomarker] = Field(default_factory=list)
    clinical_impressions: List[str] = Field(default_factory=list)
    raw_text_length: int = 0
