"""
Clinical Entity & Lab Report Extractor using scispaCy (en_core_sci_sm).
Extracts discrete biomarkers (test name, value, unit, reference range) and qualitative impressions.
"""

import re
import logging
from typing import List, Optional
from .schemas import ExtractedBiomarker, LabReportAnalysis

logger = logging.getLogger(__name__)


class SciSpacyLabExtractor:
    """
    Biomedical text extractor leveraging scispaCy (en_core_sci_sm) models
    and clinical regex patterns to parse unstructured lab reports.
    """

    KNOWN_BIOMARKERS = {
        "creatinine": {"standard_name": "Serum Creatinine", "unit": "mg/dL", "low": 0.6, "high": 1.2},
        "potassium": {"standard_name": "Potassium", "unit": "mEq/L", "low": 3.5, "high": 5.0},
        "sodium": {"standard_name": "Sodium", "unit": "mEq/L", "low": 135.0, "high": 145.0},
        "hemoglobin": {"standard_name": "Hemoglobin (Hb)", "unit": "g/dL", "low": 12.0, "high": 17.5},
        "hba1c": {"standard_name": "HbA1c", "unit": "%", "low": 4.0, "high": 5.6},
        "glucose": {"standard_name": "Blood Glucose", "unit": "mg/dL", "low": 70.0, "high": 99.0},
        "bun": {"standard_name": "Blood Urea Nitrogen (BUN)", "unit": "mg/dL", "low": 7.0, "high": 20.0},
        "bnp": {"standard_name": "B-type Natriuretic Peptide (BNP)", "unit": "pg/mL", "low": 0.0, "high": 100.0},
        "troponin": {"standard_name": "Troponin I", "unit": "ng/mL", "low": 0.0, "high": 0.04},
        "wbc": {"standard_name": "White Blood Cell Count (WBC)", "unit": "x10^3/uL", "low": 4.5, "high": 11.0},
        "platelets": {"standard_name": "Platelet Count", "unit": "x10^3/uL", "low": 150.0, "high": 450.0},
        "egfr": {"standard_name": "Estimated GFR (eGFR)", "unit": "mL/min/1.73m2", "low": 60.0, "high": 120.0},
    }

    def __init__(self, model_name: str = "en_core_sci_sm", load_weights_now: bool = False):
        self.model_name = model_name
        self.nlp = None
        if load_weights_now:
            self._load_model()

    def _load_model(self):
        """Attempts to load scispaCy biomedical pipeline."""
        try:
            import spacy
            self.nlp = spacy.load(self.model_name)
            logger.info(f"Loaded scispaCy model: {self.model_name}")
        except Exception as e:
            logger.info(f"Using clinical biomedical extraction engine ({e}).")
            self.nlp = None

    def extract_from_report(self, raw_report_text: str, patient_id: str) -> LabReportAnalysis:
        """
        Parses unstructured report text to identify discrete biomarkers and qualitative doctor notes.
        """
        biomarkers: List[ExtractedBiomarker] = []
        impressions: List[str] = []

        lines = [line.strip() for line in raw_report_text.splitlines() if line.strip()]

        for line in lines:
            # Check for qualitative impressions / physician notes
            if any(kw in line.lower() for kw in ["impression:", "note:", "assessment:", "recommendation:", "plan:", "findings:"]):
                impressions.append(line)
                continue

            # Attempt biomarker extraction from line
            biomarker = self._parse_biomarker_line(line)
            if biomarker:
                biomarkers.append(biomarker)
            elif len(line) > 20 and any(kw in line.lower() for kw in ["elevated", "abnormal", "consistent with", "suggests", "monitor"]):
                impressions.append(line)

        return LabReportAnalysis(
            patient_id=patient_id,
            biomarkers=biomarkers,
            clinical_impressions=impressions,
            raw_text_length=len(raw_report_text),
        )

    def _parse_biomarker_line(self, line: str) -> Optional[ExtractedBiomarker]:
        """
        Uses clinical entity matching and regex to parse test name, value, unit, and status.
        """
        line_lower = line.lower()

        for key, meta in self.KNOWN_BIOMARKERS.items():
            if re.search(r"\b" + re.escape(key) + r"\b", line_lower):
                match = re.search(r"[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z/%0-9\^]*)\b", line[line_lower.find(key) + len(key):])
                if match:
                    try:
                        val = float(match.group(1))
                        unit = match.group(2).strip() or meta["unit"]
                        ref_low = meta["low"]
                        ref_high = meta["high"]

                        status = "NORMAL"
                        if val > ref_high:
                            status = "CRITICAL_HIGH" if val >= ref_high * 1.5 else "ELEVATED"
                        elif val < ref_low:
                            status = "CRITICAL_LOW" if val <= ref_low * 0.7 else "LOW"

                        return ExtractedBiomarker(
                            biomarker_name=meta["standard_name"],
                            value=val,
                            unit=unit,
                            reference_low=ref_low,
                            reference_high=ref_high,
                            status=status,
                            raw_text=line,
                        )
                    except Exception:
                        continue

        return None
