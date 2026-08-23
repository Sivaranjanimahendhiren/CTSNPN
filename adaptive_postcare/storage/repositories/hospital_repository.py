"""
Repository for Hospital entity operations.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from ..models import Hospital, generate_uuid


class HospitalRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_hospital(
        self,
        hospital_code: str,
        hospital_name: str,
        location: Optional[str] = None,
        is_active: bool = True,
        hospital_id: Optional[str] = None,
    ) -> Hospital:
        """Registers a new hospital facility."""
        code = str(hospital_code).strip().upper()
        name = str(hospital_name).strip()
        if not code or not name:
            raise ValueError("hospital_code and hospital_name cannot be empty")

        hospital = Hospital(
            hospital_id=hospital_id or generate_uuid(),
            hospital_code=code,
            hospital_name=name,
            location=location,
            is_active=is_active,
        )
        self.session.add(hospital)
        self.session.commit()
        self.session.refresh(hospital)
        return hospital

    def get_hospital(self, hospital_id: str) -> Optional[Hospital]:
        """Retrieves hospital by primary key hospital_id."""
        return self.session.query(Hospital).filter(Hospital.hospital_id == hospital_id).first()

    def get_by_code(self, hospital_code: str) -> Optional[Hospital]:
        """Retrieves hospital by unique hospital_code."""
        return self.session.query(Hospital).filter(Hospital.hospital_code == hospital_code.strip().upper()).first()

    def list_hospitals(self, only_active: bool = False) -> List[Hospital]:
        """Lists registered hospitals."""
        query = self.session.query(Hospital)
        if only_active:
            query = query.filter(Hospital.is_active.is_(True))
        return query.order_by(Hospital.hospital_name.asc()).all()
