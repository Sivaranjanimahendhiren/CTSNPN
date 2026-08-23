"""
Repository for Patient entity operations.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from ..models import Patient


class PatientRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_patient(self, patient_id: str) -> Patient:
        """Creates a new patient record."""
        p_id = str(patient_id).strip()
        if not p_id:
            raise ValueError("patient_id cannot be empty")
        
        patient = Patient(patient_id=p_id)
        self.session.add(patient)
        self.session.commit()
        self.session.refresh(patient)
        return patient

    def get_patient(self, patient_id: str) -> Optional[Patient]:
        """Retrieves patient by patient_id."""
        return self.session.query(Patient).filter(Patient.patient_id == patient_id).first()

    def exists(self, patient_id: str) -> bool:
        """Checks if a patient exists."""
        return self.session.query(Patient.patient_id).filter(Patient.patient_id == patient_id).first() is not None

    def list_patients(self) -> List[Patient]:
        """Lists all registered patients."""
        return self.session.query(Patient).order_by(Patient.created_at.desc()).all()
