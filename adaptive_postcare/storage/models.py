"""
SQLAlchemy ORM models for PostgreSQL persistence layer:
1. Hospital (hospitals)
2. Patient (patients)
3. ReadmissionPrediction (readmission_predictions)
4. HospitalEvent (hospital_events)
5. PatientProfile (patient_profiles)
6. CarePlan (care_plans)
7. PatientFeedback (patient_feedback)
8. AgentAction (agent_actions)
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    CheckConstraint,
    Text,
)
from sqlalchemy.orm import relationship
from .database import Base


def generate_uuid() -> str:
    """Generates standard UUID4 string."""
    return str(uuid.uuid4())


class Hospital(Base):
    """TABLE 1: hospitals"""
    __tablename__ = "hospitals"

    hospital_id = Column(String(64), primary_key=True, default=generate_uuid)
    hospital_code = Column(String(64), unique=True, nullable=False, index=True)
    hospital_name = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    events = relationship("HospitalEvent", back_populates="hospital", cascade="all, delete-orphan")
    profiles = relationship("PatientProfile", back_populates="current_hospital")


class Patient(Base):
    """TABLE 2: patients"""
    __tablename__ = "patients"

    patient_id = Column(String(64), primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    predictions = relationship("ReadmissionPrediction", back_populates="patient", cascade="all, delete-orphan")
    events = relationship("HospitalEvent", back_populates="patient", cascade="all, delete-orphan")
    profile = relationship("PatientProfile", back_populates="patient", uselist=False, cascade="all, delete-orphan")
    care_plans = relationship("CarePlan", back_populates="patient", cascade="all, delete-orphan")
    feedbacks = relationship("PatientFeedback", back_populates="patient", cascade="all, delete-orphan")
    actions = relationship("AgentAction", back_populates="patient", cascade="all, delete-orphan")
    schedules = relationship("MonitoringSchedule", back_populates="patient", cascade="all, delete-orphan")


class ReadmissionPrediction(Base):
    """TABLE 3: readmission_predictions"""
    __tablename__ = "readmission_predictions"
    __table_args__ = (
        CheckConstraint("risk_score >= 0.0 AND risk_score <= 1.0", name="chk_risk_score_range"),
        CheckConstraint("recommended_care_days >= 1", name="chk_recommended_care_days_positive"),
    )

    prediction_id = Column(String(64), primary_key=True, default=generate_uuid)
    patient_id = Column(String(64), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    risk_score = Column(Float, nullable=False)
    risk_level = Column(String(32), nullable=False)
    recommended_care_days = Column(Integer, nullable=False)
    model_version = Column(String(64), default="1.0.0", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    patient = relationship("Patient", back_populates="predictions")
    care_plans = relationship("CarePlan", back_populates="prediction")


class HospitalEvent(Base):
    """TABLE 4: hospital_events"""
    __tablename__ = "hospital_events"

    event_id = Column(String(64), primary_key=True, default=generate_uuid)
    patient_id = Column(String(64), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    hospital_id = Column(String(64), ForeignKey("hospitals.hospital_id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    event_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    patient = relationship("Patient", back_populates="events")
    hospital = relationship("Hospital", back_populates="events")


class PatientProfile(Base):
    """TABLE 5: patient_profiles"""
    __tablename__ = "patient_profiles"

    patient_id = Column(String(64), ForeignKey("patients.patient_id", ondelete="CASCADE"), primary_key=True)
    current_hospital_id = Column(String(64), ForeignKey("hospitals.hospital_id", ondelete="SET NULL"), nullable=True)
    care_status = Column(String(32), default="ADMITTED", nullable=False)  # ADMITTED, DISCHARGED, POST_CARE_ACTIVE, READMITTED, CARE_COMPLETED, PAUSED
    admission_id = Column(String(64), nullable=True)
    admitted_at = Column(DateTime, nullable=True)
    discharged_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    patient = relationship("Patient", back_populates="profile")
    current_hospital = relationship("Hospital", back_populates="profiles")


class CarePlan(Base):
    """TABLE 6: care_plans"""
    __tablename__ = "care_plans"
    __table_args__ = (
        CheckConstraint("duration_days >= 1", name="chk_duration_days_positive"),
        CheckConstraint("current_day >= 0", name="chk_current_day_non_negative"),
    )

    care_plan_id = Column(String(64), primary_key=True, default=generate_uuid)
    patient_id = Column(String(64), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    prediction_id = Column(String(64), ForeignKey("readmission_predictions.prediction_id", ondelete="SET NULL"), nullable=True)
    start_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    duration_days = Column(Integer, nullable=False)  # Sourced from recommended_care_days (10, 14, 15, 20, 30, etc.)
    current_day = Column(Integer, default=0, nullable=False)
    status = Column(String(32), default="INITIALIZED", nullable=False)
    monitoring_frequency = Column(String(32), default="DAILY", nullable=False)
    plan_data = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    patient = relationship("Patient", back_populates="care_plans")
    prediction = relationship("ReadmissionPrediction", back_populates="care_plans")
    feedbacks = relationship("PatientFeedback", back_populates="care_plan")
    actions = relationship("AgentAction", back_populates="care_plan")
    schedules = relationship("MonitoringSchedule", back_populates="care_plan")


class PatientFeedback(Base):
    """TABLE 7: patient_feedback"""
    __tablename__ = "patient_feedback"

    feedback_id = Column(String(64), primary_key=True, default=generate_uuid)
    patient_id = Column(String(64), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    care_plan_id = Column(String(64), ForeignKey("care_plans.care_plan_id", ondelete="SET NULL"), nullable=True)
    day = Column(Integer, nullable=False)
    feedback_type = Column(String(64), default="DAILY_CHECKIN", nullable=False)
    raw_feedback = Column(Text, nullable=True)
    structured_feedback = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    patient = relationship("Patient", back_populates="feedbacks")
    care_plan = relationship("CarePlan", back_populates="feedbacks")


class AgentAction(Base):
    """TABLE 8: agent_actions"""
    __tablename__ = "agent_actions"

    action_id = Column(String(64), primary_key=True, default=generate_uuid)
    patient_id = Column(String(64), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    care_plan_id = Column(String(64), ForeignKey("care_plans.care_plan_id", ondelete="SET NULL"), nullable=True)
    day = Column(Integer, nullable=False)
    node_name = Column(String(64), nullable=False)
    action_type = Column(String(64), nullable=False)
    reason = Column(Text, nullable=True)
    tool_name = Column(String(64), nullable=True)
    result = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    patient = relationship("Patient", back_populates="actions")
    care_plan = relationship("CarePlan", back_populates="actions")


class MonitoringSchedule(Base):
    """TABLE 9: monitoring_schedules"""
    __tablename__ = "monitoring_schedules"

    schedule_id = Column(String(64), primary_key=True, default=generate_uuid)
    patient_id = Column(String(64), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    care_plan_id = Column(String(64), ForeignKey("care_plans.care_plan_id", ondelete="SET NULL"), nullable=True, index=True)
    care_day = Column(Integer, nullable=False)
    scheduled_at = Column(DateTime, nullable=False)
    frequency = Column(String(64), default="DAILY", nullable=False)
    status = Column(String(32), default="SCHEDULED", nullable=False, index=True)  # SCHEDULED, COMPLETED, MISSED, CANCELLED
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    patient = relationship("Patient", back_populates="schedules")
    care_plan = relationship("CarePlan", back_populates="schedules")


class PatientConversation(Base):
    """TABLE 10: patient_conversations - Persistent dialogue messages history"""
    __tablename__ = "patient_conversations"

    message_id = Column(String(64), primary_key=True, default=generate_uuid)
    chat_id = Column(String(64), nullable=False, index=True)
    patient_id = Column(String(64), ForeignKey("patients.patient_id", ondelete="SET NULL"), nullable=True, index=True)
    role = Column(String(32), nullable=False)  # 'patient', 'assistant', 'system'
    message_text = Column(Text, nullable=False)
    channel = Column(String(32), default="TELEGRAM", nullable=False)  # 'TELEGRAM', 'TERMINAL', 'WEB'
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    patient = relationship("Patient", backref="conversations")
