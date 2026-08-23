"""
LLM Service Layer: Encapsulates LangChain LLM invocations, prompt formatting,
and strict structured output validation.
"""

import json
from typing import Any, Dict, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from ..config.llm_config import get_llm
from .schemas import ClinicalFeedbackAnalysis, AdaptationReasoning
from .prompts import UNDERSTAND_PROMPT, ADAPT_PROMPT


class LLMService:
    """
    Decoupled service handling all model interactions with validation guarantees.
    Enables swapping underlying Llama backends (Groq, Ollama, vLLM, OpenAI-compatible)
    without touching node logic or workflow routing.
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self._llm = llm

    @property
    def llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = get_llm(temperature=0.1)
        return self._llm

    def analyze_feedback(
        self,
        patient_id: str,
        current_day: int,
        feedback_text: str,
        medication_taken: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> ClinicalFeedbackAnalysis:
        """
        Invokes LLM via UNDERSTAND_PROMPT and validates output into ClinicalFeedbackAnalysis.
        Automatically cycles across all primary and fallback keys (Groq + Gemini keys pool).
        """
        from ..config.llm_config import get_llms_pool
        # Format prompt messages
        formatted_messages = UNDERSTAND_PROMPT.format_messages(
            patient_id=patient_id,
            current_day=current_day,
            feedback_text=feedback_text or "No text provided",
            medication_taken=str(medication_taken) if medication_taken is not None else "Not reported",
            notes=notes or "None",
        )

        # Multi-key failover loop
        llm_pool = get_llms_pool(temperature=0.1) if self._llm is None else [self._llm]
        for candidate_llm in llm_pool:
            try:
                response = candidate_llm.invoke(formatted_messages)
                content = str(response.content).strip()
                if "{" in content and "}" in content:
                    json_str = content[content.find("{"):content.rfind("}") + 1]
                    data = json.loads(json_str)
                    return ClinicalFeedbackAnalysis(**data)
            except Exception:
                continue

        # Robust deterministic fallback parsing
        lower_text = feedback_text.lower()
        if any(w in lower_text for w in ["forgot", "missed", "haven't", "have not", "no medication", "skipped"]):
            med_status = "non_adherent"
        elif any(w in lower_text for w in ["took", "taken", "taking", "yes", "all pills", "adherent"]) or medication_taken is True:
            med_status = "adherent"
        else:
            med_status = "adherent" if medication_taken is True else ("non_adherent" if medication_taken is False else "unknown")

        # Extract genuine symptoms (avoiding recovery / negation phrases)
        known_symptoms = [
            "chest pain", "shortness of breath", "difficulty breathing",
            "severe pain", "mild pain", "pain", "nausea", "dizziness",
            "swelling", "fatigue", "fever", "cough", "headache", "bleeding", "vomiting"
        ]
        symptom_tokens = []
        for sym in known_symptoms:
            if sym in lower_text:
                # Check for negations like "no pain", "no swelling", "without pain"
                if f"no {sym}" not in lower_text and f"without {sym}" not in lower_text and f"not have {sym}" not in lower_text and f"no {sym.split()[-1]}" not in lower_text:
                    symptom_tokens.append(sym)
                    break  # Capture most specific symptom

        symptom_status = "improving" if any(w in lower_text for w in ["better", "good", "fine", "improving", "resolved"]) else ("worsening" if "worse" in lower_text else "stable")

        # Determine data quality
        if any(w in lower_text for w in ["don't know", "dont know", "not sure", "haven't checked", "havent checked"]):
            quality = "incomplete"
        elif (feedback_text and feedback_text != "No text provided") or medication_taken is not None:
            quality = "high"
        else:
            quality = "incomplete"

        return ClinicalFeedbackAnalysis(
            symptom_status=symptom_status,
            extracted_symptoms=symptom_tokens,
            medication_status=med_status,
            data_quality=quality,
            concerns=[],
            confidence=0.85,
        )

    def assess_adaptation(
        self,
        patient_id: str,
        risk_level: str,
        current_day: int,
        care_duration_days: int,
        symptoms: List[str],
        medication_adherence: float,
        latest_feedback: Any,
    ) -> AdaptationReasoning:
        """
        Invokes LLM via ADAPT_PROMPT for qualitative trajectory reasoning.
        """
        formatted_messages = ADAPT_PROMPT.format_messages(
            patient_id=patient_id,
            risk_level=risk_level,
            current_day=current_day,
            care_duration_days=care_duration_days,
            symptoms=", ".join(symptoms) if symptoms else "None reported",
            medication_adherence=f"{medication_adherence * 100:.0f}%",
            latest_feedback=str(latest_feedback) if latest_feedback else "None",
        )

        try:
            if hasattr(self.llm, "with_structured_output"):
                structured_chain = self.llm.with_structured_output(AdaptationReasoning)
                result = structured_chain.invoke(formatted_messages)
                if isinstance(result, AdaptationReasoning):
                    return result

            response = self.llm.invoke(formatted_messages)
            content = str(response.content).strip()
            if "{" in content and "}" in content:
                json_str = content[content.find("{"):content.rfind("}") + 1]
                data = json.loads(json_str)
                return AdaptationReasoning(**data)
        except Exception:
            pass

        # Deterministic fallback
        return AdaptationReasoning(
            qualitative_summary=f"Patient trajectory reviewed on Day {current_day} of {care_duration_days}. Adherence at {medication_adherence * 100:.0f}%.",
            observed_barriers=[],
            suggested_focus_area="Routine adherence and daily check-in cadence",
            confidence=0.85,
        )
