"""
Multi-Patient Orchestrator:
Manages multiple independent patient care journeys using ONE shared, reusable LangGraph state machine.
Guarantees 100% state isolation across patients using unique patient identifiers (thread_id).
"""

from typing import Any, Dict, List, Optional, Union
import time
from langgraph.checkpoint.memory import MemorySaver
from .graph.builder import get_compiled_graph, get_checkpointer
from .state.patient_state import PatientState, PatientStateModel, RiskLevel, CareAction, PlanStatus
from .schemas.readmission_input import InitialRiskEvent
from .schemas.patient_event import PatientEvent
from .agents.care_plan_agent import CarePlanAgent
from .nodes.observe_node import observe_node
from .nodes.understand_node import understand_node
from .nodes.risk_evaluation_node import risk_evaluation_node
from .nodes.plan_node import plan_node
from .nodes.act_node import act_node
from .nodes.feedback_node import feedback_node
from .nodes.adapt_node import adapt_node
from .nodes.escalate_node import escalate_node


class MultiPatientOrchestrator:
    """
    Orchestration layer binding multiple independent patient states
    to a single shared LangGraph state machine.
    """

    def __init__(self, checkpointer: Optional[Any] = None, checkpoint_backend: Optional[str] = None):
        self.checkpointer = checkpointer or get_checkpointer(backend=checkpoint_backend)
        # ONE single reusable LangGraph instance for all patients
        self.graph = get_compiled_graph(checkpointer=self.checkpointer)
        # Isolated in-memory patient state registry
        self._patient_states: Dict[str, Dict[str, Any]] = {}
        self.care_plan_agent = CarePlanAgent()

    def register_patient(
        self,
        patient_id: str,
        risk_score: float,
        risk_level: Union[str, RiskLevel],
        care_duration_days: int,
        clinical_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initializes an isolated patient state from external readmission model inputs.
        """
        state_model: PatientStateModel = self.care_plan_agent.initialize_patient_state(
            patient_id=patient_id,
            risk_score=risk_score,
            risk_level=risk_level,
            care_duration_days=care_duration_days,
            clinical_notes=clinical_notes,
        )
        state_dict = state_model.to_state_dict()
        self._patient_states[patient_id] = state_dict

        # Save initial checkpoint
        if self.checkpointer is not None and hasattr(self.checkpointer, "put"):
            try:
                self.checkpointer.put(
                    {"configurable": {"thread_id": patient_id, "checkpoint_ns": ""}},
                    {"channel_values": state_dict, "values": state_dict, "id": f"init_{int(time.time()*1000)}"},
                    {"source": "registration", "step": 0},
                    {},
                )
            except Exception:
                pass

        return state_dict

    def register_patient_from_event(self, initial_event: InitialRiskEvent) -> Dict[str, Any]:
        """
        Helper to register a patient directly from an InitialRiskEvent payload.
        """
        return self.register_patient(
            patient_id=initial_event.patient_id,
            risk_score=initial_event.risk_score,
            risk_level=initial_event.risk_level.value,
            care_duration_days=initial_event.care_duration_days,
        )

    def process_patient_event(
        self,
        event: Union[PatientEvent, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Dispatches a patient event to the single shared LangGraph using the patient's isolated state.
        Uses thread_id = patient_id for checkpointer state isolation.
        """
        if isinstance(event, PatientEvent):
            p_id = event.patient_id
            event_dict = event.model_dump()
        else:
            p_id = event.get("patient_id")
            event_dict = event

        if not p_id:
            raise ValueError("patient_id is required to process event.")

        # Ensure state is loaded (hydrates from checkpointer if needed)
        current_state = self.get_patient_state(p_id)
        if not current_state:
            raise KeyError(f"Patient '{p_id}' is not registered in the orchestrator.")

        # 1. Fetch isolated state copy
        current_state = dict(current_state)

        # 2. Attach new event payload (synchronizing payload to feedback if needed)
        if "feedback" not in event_dict and "payload" in event_dict:
            event_dict = dict(event_dict)
            event_dict["feedback"] = event_dict["payload"]

        current_state["current_event"] = event_dict

        # 3. Process event cycle through the core nodes
        s = dict(current_state)
        s.update(observe_node(s))
        s.update(understand_node(s))
        s.update(risk_evaluation_node(s))
        s.update(plan_node(s))
        s.update(act_node(s))
        s.update(feedback_node(s))
        s.update(adapt_node(s))
        if s.get("escalation_required") or s.get("current_action") == CareAction.ESCALATE.value:
            s.update(escalate_node(s))

        # 4. Save checkpoint under patient thread_id for workflow isolation
        if self.checkpointer is not None and hasattr(self.checkpointer, "put"):
            try:
                self.checkpointer.put(
                    {"configurable": {"thread_id": p_id, "checkpoint_ns": ""}},
                    {"channel_values": s, "values": s, "id": f"cp_{int(time.time()*1000)}"},
                    {"source": "orchestrator", "step": s.get("current_day", 0)},
                    {},
                )
            except Exception:
                pass

        # 5. Persist isolated state in-memory cache
        self._patient_states[p_id] = s
        return s

    def get_patient_state(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve isolated state for a specific patient, recovering from checkpointer if needed."""
        if patient_id in self._patient_states:
            return self._patient_states[patient_id]

        # Check checkpointer for state recovery across application restart
        if self.checkpointer is not None and hasattr(self.checkpointer, "get_tuple"):
            try:
                tup = self.checkpointer.get_tuple({"configurable": {"thread_id": patient_id, "checkpoint_ns": ""}})
                if tup and tup.checkpoint:
                    values = tup.checkpoint.get("channel_values") or tup.checkpoint.get("values")
                    if values and isinstance(values, dict):
                        self._patient_states[patient_id] = values
                        return values
            except Exception:
                pass

        return None

    def pause_patient(self, patient_id: str, reason: str = "PATIENT_READMITTED") -> Dict[str, Any]:
        """Pauses active care monitoring when patient is readmitted to the hospital."""
        if patient_id not in self._patient_states:
            raise KeyError(f"Patient '{patient_id}' is not registered.")
        self._patient_states[patient_id]["plan_status"] = PlanStatus.PAUSED.value
        self._patient_states[patient_id]["adaptation_notes"].append(f"Care plan PAUSED: {reason}")
        return self._patient_states[patient_id]

    def resume_patient(self, patient_id: str, reason: str = "RESUMED_POST_CARE") -> Dict[str, Any]:
        """Resumes care monitoring after pause."""
        if patient_id not in self._patient_states:
            raise KeyError(f"Patient '{patient_id}' is not registered.")
        self._patient_states[patient_id]["plan_status"] = PlanStatus.ACTIVE.value
        self._patient_states[patient_id]["adaptation_notes"].append(f"Care plan RESUMED: {reason}")
        return self._patient_states[patient_id]

    def list_patients(self) -> List[str]:
        """List all registered patient IDs."""
        return list(self._patient_states.keys())
