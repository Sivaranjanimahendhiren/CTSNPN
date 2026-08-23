# Adaptive Agentic Post-Care System (Agent Layer)

An autonomous, adaptive post-discharge patient care management agent built with **LangGraph**, **LangChain**, and **Llama-compatible LLMs**.

---

## 🏛 Architecture Overview

The agent layer receives inputs from an external readmission risk model (e.g. Random Forest) and manages patient monitoring, clinical safety evaluations, adaptive care planning, and dynamic tool interactions across subsequent post-care events.

```
External Readmission Model
        ↓
Risk Score + Risk Level + Care Duration
        ↓
Adaptive Agent Layer
        ↓
PatientState
        ↓
LangGraph State Machine
        ↓
Observe → Understand → Risk Evaluation → Plan → Act → Feedback → Adapt
        ↓
Updated Patient State
        ↓
Next Patient Event
```

---

## 📁 Project Structure

```
├── adaptive_postcare/
│   ├── adapters/           # External event adapters (Hospital events)
│   ├── agents/             # Specialized LLM reasoning agents (CarePlanAgent)
│   ├── clinical_rag/       # Clinical RAG & medical knowledge retrieval
│   ├── config/             # LLM settings & environment configuration
│   ├── controllers/        # MVC Controllers for Bot & services
│   ├── edges/              # Conditional routing and graph branch decisions
│   ├── graph/              # LangGraph StateGraph builder & compiler
│   ├── llm/                # LLM factory & provider abstractions
│   ├── nodes/              # LangGraph execution nodes (Observe, Understand, Plan, etc.)
│   ├── policies/           # Deterministic clinical safety & escalation rules
│   ├── scheduling/         # Monitoring schedulers & cadence engines
│   ├── schemas/            # Pydantic schemas (Readmission inputs & patient events)
│   ├── services/           # Prediction ingestion & patient management services
│   ├── state/              # PatientState TypedDict & data definitions
│   ├── storage/            # PostgreSQL / SQLite persistence layer & PostgresSaver
│   ├── tools/              # LangChain tool definitions (alerts, meds, care plans)
│   ├── utils/              # Tracers & logging utilities
│   ├── views/              # MVC Views (Console & Telegram formatted outputs)
│   └── orchestrator.py     # Multi-patient orchestrator
├── api.py                  # FastAPI REST Gateway
├── telegram_bot.py         # Telegram AI Nurse Bot runner
├── demo_showcase.py        # End-to-end clinical workflow showcase
├── demo_clinical_rag.py    # Clinical RAG demonstration
├── .env.example            # Environment variables template
├── .gitignore              # Git ignore rules
├── requirements.txt        # Python package dependencies
└── README.md               # Project documentation
```

---

## 🚀 Quick Start

### 1. Installation

```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your API credentials:

```bash
cp .env.example .env
```

### 3. Running Services

- **FastAPI REST API:**
  ```bash
  uvicorn api:app --reload --port 8000
  ```
- **Telegram Bot:**
  ```bash
  python telegram_bot.py
  ```
- **Demo Showcase:**
  ```bash
  python demo_showcase.py
  ```

