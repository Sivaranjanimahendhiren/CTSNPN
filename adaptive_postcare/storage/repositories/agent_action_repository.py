"""
Repository for AgentAction audit trail operations.
"""

from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from ..models import AgentAction, generate_uuid


class AgentActionRepository:
    def __init__(self, session: Session):
        self.session = session

    def record_action(
        self,
        patient_id: str,
        day: int,
        node_name: str,
        action_type: str,
        care_plan_id: Optional[str] = None,
        reason: Optional[str] = None,
        tool_name: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        action_id: Optional[str] = None,
    ) -> AgentAction:
        """Records an agent execution step in the audit trail."""
        action = AgentAction(
            action_id=action_id or generate_uuid(),
            patient_id=str(patient_id).strip(),
            care_plan_id=care_plan_id,
            day=int(day),
            node_name=str(node_name).strip(),
            action_type=str(action_type).strip().upper(),
            reason=reason,
            tool_name=tool_name,
            result=result or {},
        )
        self.session.add(action)
        self.session.commit()
        self.session.refresh(action)
        return action

    def get_patient_actions(
        self,
        patient_id: str,
        care_plan_id: Optional[str] = None,
    ) -> List[AgentAction]:
        """Retrieves audit trail actions for a patient in chronological order."""
        query = self.session.query(AgentAction).filter(AgentAction.patient_id == patient_id)
        if care_plan_id:
            query = query.filter(AgentAction.care_plan_id == care_plan_id)
        return query.order_by(AgentAction.day.asc(), AgentAction.created_at.asc()).all()
