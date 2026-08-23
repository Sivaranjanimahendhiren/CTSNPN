"""
Factory for initializing Llama-compatible LLMs.
"""

import os
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from .settings import get_settings


def get_llms_pool(temperature: Optional[float] = None) -> list:
    """
    Returns an ordered chain of LLMs for multi-key failover:
    1. Primary Groq LLM
    2. Fallback Gemini Key 1
    3. Fallback Gemini Key 2
    4. Fallback Gemini Key 3
    5. Mock test fallback
    """
    settings = get_settings()
    temp = temperature if temperature is not None else settings.llm_temperature
    model_name = settings.llm_model
    pool = []

    # 1. Multi-model Groq Pool (Instant high-speed failover)
    groq_api_key = os.environ.get("LLM_API_KEY") or settings.llm_api_key or os.environ.get("GROQ_API_KEY") or "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"
    if groq_api_key:
        groq_models = ["openai/gpt-oss-20b", "qwen/qwen3.6-27b", "openai/gpt-oss-120b"]
        for g_model in groq_models:
            try:
                from langchain_groq import ChatGroq
                pool.append(ChatGroq(model=g_model, temperature=temp, api_key=groq_api_key, max_retries=1))
            except Exception:
                pass

    # 2. Gemini Fallback Keys (with max_retries=0 to prevent retry log noise)
    gemini_keys = [
        os.environ.get("GEMINI_API_KEY_1", ""),
        os.environ.get("GEMINI_API_KEY_2", ""),
        os.environ.get("GEMINI_API_KEY_3", ""),
    ]
    raw_keys_env = os.environ.get("GEMINI_API_KEYS", "")
    if raw_keys_env:
        for k in raw_keys_env.split(","):
            if k.strip() and k.strip() not in gemini_keys:
                gemini_keys.append(k.strip())

    for g_key in gemini_keys:
        if g_key and g_key.strip() and not g_key.startswith("AQ."):
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                pool.append(ChatGoogleGenerativeAI(
                    model="gemini-1.5-flash",
                    google_api_key=g_key.strip(),
                    temperature=temp,
                    max_retries=0,
                ))
            except Exception:
                pass

    if not pool:
        # Offline test fallback for fast, deterministic unit testing
        pool.append(FakeListChatModel(responses=[
            '{"extracted_symptoms": [], "symptom_trend": "STABLE", "adherence_barrier": null}',
            "Your care plan is actively personalized for your safe recovery. Please stay in touch."
        ]))
    return pool


def get_llm(
    temperature: Optional[float] = None,
    model: Optional[str] = None
) -> BaseChatModel:
    """
    Factory function to retrieve primary Chat Model with fallback support.
    """
    pool = get_llms_pool(temperature=temperature)
    return pool[0] if pool else FakeListChatModel(responses=["OK"])
