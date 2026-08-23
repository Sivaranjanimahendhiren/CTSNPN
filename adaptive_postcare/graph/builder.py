"""
LangGraph StateGraph builder for Adaptive Agentic Post-Care System.
Implements the 7-node pipeline with conditional routing after Adapt and multi-patient checkpointer support.
"""

from typing import Any, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from ..state.patient_state import PatientState
from ..nodes.observe_node import observe_node
from ..nodes.understand_node import understand_node
from ..nodes.risk_evaluation_node import risk_evaluation_node
from ..nodes.plan_node import plan_node
from ..nodes.act_node import act_node
from ..nodes.feedback_node import feedback_node
from ..nodes.adapt_node import adapt_node
from ..nodes.escalate_node import escalate_node
from ..edges.routing import route_after_adapt


def build_postcare_graph() -> StateGraph:
    """
    Constructs the uncompiled LangGraph StateGraph with all 7 nodes,
    dedicated escalation node, and conditional routing after Adapt.
    """
    workflow = StateGraph(PatientState)

    # 1. Register Core Nodes
    workflow.add_node("observe", observe_node)
    workflow.add_node("understand", understand_node)
    workflow.add_node("risk_evaluation", risk_evaluation_node)
    workflow.add_node("plan", plan_node)
    workflow.add_node("act", act_node)
    workflow.add_node("feedback", feedback_node)
    workflow.add_node("adapt", adapt_node)
    workflow.add_node("escalate", escalate_node)

    # 2. Wire Linear Flow from START through Adapt
    workflow.add_edge(START, "observe")
    workflow.add_edge("observe", "understand")
    workflow.add_edge("understand", "risk_evaluation")
    workflow.add_edge("risk_evaluation", "plan")
    workflow.add_edge("plan", "act")
    workflow.add_edge("act", "feedback")
    workflow.add_edge("feedback", "adapt")

    # 3. Wire Conditional Edges after Adapt
    workflow.add_conditional_edges(
        "adapt",
        route_after_adapt,
        {
            "continue": "observe",
            "increase_monitoring": "observe",
            "decrease_monitoring": "observe",
            "request_more_data": "feedback",
            "modify_care_plan": "plan",
            "escalate": "escalate",
            "complete": END,
        }
    )

    # 4. Terminal edge from Escalation node
    workflow.add_edge("escalate", END)

    return workflow


import os


def get_checkpointer(backend: Optional[str] = None) -> Any:
    """
    Factory creating a checkpointer based on configuration or explicit parameter.
    Defaults to PostgresSaver if LANGGRAPH_CHECKPOINT_BACKEND=postgres, else MemorySaver.
    """
    configured_backend = (backend or os.getenv("LANGGRAPH_CHECKPOINT_BACKEND", "memory")).lower().strip()
    if configured_backend in ("postgres", "postgresql"):
        try:
            from ..storage.postgres_saver import PostgresSaver
            return PostgresSaver()
        except Exception:
            return MemorySaver()
    return MemorySaver()


def get_compiled_graph(checkpointer: Optional[Any] = None):
    """
    Returns a compiled, executable LangGraph StateGraph instance.
    Supports PostgresSaver and MemorySaver checkpointer for thread-isolated multi-patient workflows.
    """
    graph_builder = build_postcare_graph()
    if checkpointer is not None:
        return graph_builder.compile(checkpointer=checkpointer)
    return graph_builder.compile()
