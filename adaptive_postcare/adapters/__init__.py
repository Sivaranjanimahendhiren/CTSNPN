"""
Hospital Event Adapter Layer.
Bridges external hospital EHR/event streams and PostgreSQL storage with the MultiPatientOrchestrator.
"""

from .hospital_adapter import HospitalEventAdapter

__all__ = ["HospitalEventAdapter"]
