"""
Repository for PatientProfile current lifecycle status operations.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from ..models import PatientProfile


class PatientProfileRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_or_update_profile(
        self,
        patient_id: str,
        care_status: str = "ADMITTED",
        current_hospital_id: Optional[str] = None,
        admission_id: Optional[str] = None,
        admitted_at: Optional[datetime] = None,
        discharged_at: Optional[datetime] = None,
    ) -> PatientProfile:
        """Upserts a patient profile with their current hospital/care status."""
        p_id = str(patient_id).strip()
        status_upper = str(care_status).strip().upper()
        profile = self.session.query(PatientProfile).filter(PatientProfile.patient_id == p_id).first()

        if profile:
            profile.care_status = status_upper
            if current_hospital_id is not None:
                profile.current_hospital_id = current_hospital_id
            if admission_id is not None:
                profile.admission_id = admission_id
            if admitted_at is not None:
                profile.admitted_at = admitted_at
            if discharged_at is not None:
                profile.discharged_at = discharged_at
            profile.updated_at = datetime.utcnow()
        else:
            profile = PatientProfile(
                patient_id=p_id,
                current_hospital_id=current_hospital_id,
                care_status=status_upper,
                admission_id=admission_id,
                admitted_at=admitted_at or datetime.utcnow(),
                discharged_at=discharged_at,
            )
            self.session.add(profile)

        self.session.commit()
        self.session.refresh(profile)
        return profile

    def get_profile(self, patient_id: str) -> Optional[PatientProfile]:
        """Retrieves current patient profile."""
        return self.session.query(PatientProfile).filter(PatientProfile.patient_id == patient_id).first()

    def update_status(self, patient_id: str, status: str) -> Optional[PatientProfile]:
        """Updates the care_status of an existing patient profile."""
        profile = self.get_profile(patient_id)
        if not profile:
            return None
        profile.care_status = str(status).strip().upper()
        profile.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(profile)
        return profile
