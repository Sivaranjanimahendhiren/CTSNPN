"""
CTS-NPN Research Planner Agent

Purpose
-------
The Planner converts a user's research question into a structured,
auditable research protocol for the downstream CTS-NPN multi-agent
research pipeline.

Primary use cases
-----------------
Use Case 7:
    Avoidable Emergency Department (ED) Utilization Navigator

Use Case 12:
    Multi-Agent Research-to-Report Analyst Assistant

The Planner does NOT perform research itself.

It creates the protocol used by downstream agents:
    - Research Agent
    - CMS Agent
    - CDC Agent
    - SEC Agent
    - Evidence Agent
    - Synthesis Agent
    - Critic Agent
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.common.aws import bedrock, update_run
from backend.common.security import new_run_id, require_fields, clean_text


# ============================================================================
# Configuration
# ============================================================================

PLANNER_VERSION = "2.1.0"

DEFAULT_MAX_TOKENS = 5000
DEFAULT_TEMPERATURE = 0.05

MIN_RESEARCH_QUERIES = 4
MAX_RESEARCH_QUERIES = 8

MIN_CMS_QUERIES = 3
MAX_CMS_QUERIES = 8

MIN_CDC_QUERIES = 2
MAX_CDC_QUERIES = 5

MIN_SEC_QUERIES = 1
MAX_SEC_QUERIES = 4

DEFAULT_REPORT_SECTIONS = [
    "Executive Summary",
    "Research Question and Scope",
    "Population and Context",
    "Methodology",
    "Evidence Landscape",
    "Peer-Reviewed Research Evidence",
    "CMS Empirical Findings",
    "CDC Community-Level Context",
    "Healthcare Utilization Patterns",
    "Potentially Avoidable ED Utilization Signals",
    "Navigation Opportunities",
    "Quantitative Findings",
    "Evidence-to-Action Mapping",
    "Safety and Clinical Boundaries",
    "Limitations",
    "Data Quality and Uncertainty",
    "Conclusion",
    "References",
    "Metadata",
]

MANDATORY_SAFETY_CONSTRAINTS = [
    "Never discourage, delay, deny, or gatekeep genuine emergency care.",
    "Potentially avoidable ED utilization is not equivalent to medically unnecessary care.",
    "The system identifies population-level utilization patterns and must not independently diagnose individual patients.",
    "Population-level evidence must not automatically be represented as individual clinical advice.",
    "Emergency symptoms require appropriate emergency evaluation and care.",
    "Correlation must not be presented as causation.",
    "Model predictions must not be presented as clinical truth.",
    "Missing data, uncertainty, dataset limitations, and methodological limitations must be disclosed.",
    "Navigation recommendations must be framed as options and not as restrictions on emergency access.",
    "Every quantitative claim in the final report must have traceable provenance.",
]


# ============================================================================
# Lambda entry point
# ============================================================================

def lambda_handler(event, context):
    """
    Create a research protocol from the incoming research question.

    Expected input:
    {
        "run_id": "TEST002",
        "question": "What patterns are associated with potentially avoidable ED utilization?",
        "requested_by": "demo-user",
        "context": {}
    }

    Returns:
    {
        ...original event...,
        "run_id": "...",
        "plan": {...}
    }
    """

    if not isinstance(event, dict):
        raise ValueError("Lambda event must be a JSON object")

    require_fields(event, ["question"])

    run_id = event.get("run_id") or new_run_id()

    question = clean_text(str(event["question"])).strip()

    if not question:
        raise ValueError("Research question cannot be empty")

    context_data = event.get("context") or {}

    if not isinstance(context_data, dict):
        context_data = {
            "raw_context": str(context_data)
        }

    _safe_update_run(run_id, "PLANNING")

    try:
        planning_prompt = _build_planning_prompt(
            question=question,
            context_data=context_data,
        )

        raw = bedrock(
            planning_prompt,
            max_tokens=DEFAULT_MAX_TOKENS,
            temperature=DEFAULT_TEMPERATURE,
        )

        plan = _parse_model_plan(raw)

        plan = _normalize_plan(
            plan=plan,
            question=question,
            context_data=context_data,
        )

        _validate_plan(plan)

        plan["planning_timestamp_utc"] = datetime.now(
            timezone.utc
        ).isoformat()

        plan["planner_version"] = PLANNER_VERSION

        _safe_update_run(
            run_id,
            "PLAN_COMPLETE",
            plan_summary={
                "research_queries": len(plan["research_queries"]),
                "sec_queries": len(plan["sec_queries"]),
                "cms_queries": len(plan["cms_queries"]),
                "cdc_queries": len(plan["cdc_queries"]),
                "sub_questions": len(plan["sub_questions"]),
                "hypotheses": len(plan["hypotheses"]),
                "metrics": len(plan["metrics"]),
            },
        )

        return {
            **event,
            "run_id": run_id,
            "plan": plan,
        }

    except Exception as exc:
        error_message = f"Planner agent error: {str(exc)}"

        print(error_message)

        _safe_update_run(
            run_id,
            "PLANNING_FAILED",
            error=error_message,
        )

        # Deterministic fallback keeps the orchestration pipeline alive.
        fallback_plan = _fallback_plan(
            question=question,
            context_data=context_data,
        )

        return {
            **event,
            "run_id": run_id,
            "plan": fallback_plan,
            "planner_error": error_message,
        }


# ============================================================================
# Safe run-status update
# ============================================================================

def _safe_update_run(
    run_id: str,
    status: str,
    **kwargs: Any,
) -> None:
    """
    Update orchestration status without allowing a status-store failure
    to hide the actual Planner result.
    """

    try:
        update_run(
            run_id,
            status,
            **kwargs,
        )

    except Exception as exc:
        print(
            f"WARNING: update_run failed for run_id={run_id}, "
            f"status={status}: {exc}"
        )


# ============================================================================
# Prompt construction
# ============================================================================

def _build_planning_prompt(
    question: str,
    context_data: Dict[str, Any],
) -> str:
    """
    Build the research-planning prompt.

    The Planner is explicitly instructed to create a research protocol,
    not perform the research.
    """

    context_json = json.dumps(
        context_data,
        ensure_ascii=False,
        default=str,
    )

    return f"""
You are the Senior Research Methodology and Orchestration Agent
for CTS-NPN.

SYSTEM
------

CTS-NPN combines:

Use Case 7:
Avoidable Emergency Department Utilization Navigator

with

Use Case 12:
Multi-Agent Research-to-Report Analyst Assistant.

Your responsibility is to create a rigorous research protocol that
downstream agents can execute.

You are NOT the research agent.

You must NOT invent evidence, statistics, citations, datasets,
findings, or conclusions.

The final report must distinguish clearly between:

- observed facts
- reported statistics
- calculated statistics
- associations
- hypotheses
- operational recommendations
- limitations
- uncertainty

Never manufacture evidence.

Never manufacture a statistic.

Never infer causality from correlation.

Never claim that an ED visit was medically unnecessary unless the
source explicitly establishes that classification.

The system must NEVER discourage, delay, deny, or gatekeep a genuine
medical emergency.

USER RESEARCH QUESTION
----------------------

{question}

ADDITIONAL CONTEXT
------------------

{context_json}

PRIMARY SOURCE FAMILIES
-----------------------

1. PEER-REVIEWED / SCHOLARLY RESEARCH

Starting source:
arXiv API

Purpose:
- healthcare utilization research
- machine learning
- prediction
- causal inference
- evidence synthesis
- agentic AI
- uncertainty estimation
- research methodology

Important:
arXiv is a scholarly preprint source and should not automatically
be treated as equivalent to peer-reviewed evidence.

2. CMS

Use official CMS public datasets, documentation, and APIs where
available.

Potential areas:
- Medicare utilization
- Medicare Shared Savings Program
- quality measures
- provider data
- doctors and clinicians
- performance-year data
- methodology documentation
- Medicare population measures

3. CDC PLACES

Use:
- county/community health indicators
- chronic disease prevalence
- preventive health indicators
- behavioral risk indicators
- geographic context

CDC PLACES is contextual population-level evidence and must not be
treated as individual clinical evidence.

4. SEC EDGAR

Use only when relevant.

Purpose:
- healthcare company disclosures
- payer/provider strategy
- utilization trends
- financial/operational evidence

SEC evidence must NOT be treated as clinical evidence.

RESEARCH OBJECTIVE
------------------

Define the central objective in one precise statement.

PRIMARY QUESTION
----------------

Restate the user's research question as a precise analytical question.

SUB-QUESTIONS
-------------

Create 5-8 research sub-questions.

Each must address a distinct analytical dimension.

Possible dimensions:
- utilization patterns
- population characteristics
- geographic variation
- provider/access characteristics
- evidence regarding potentially avoidable utilization
- lower-acuity care alternatives
- measurable outcomes
- evidence gaps

HYPOTHESES
----------

Create 3-6 testable hypotheses.

Each hypothesis must contain:

hypothesis_id
statement
rationale
variables
expected_direction
evidence_required
falsification_condition

Do NOT represent hypotheses as facts.

POPULATION DEFINITION
---------------------

Define:

population
unit_of_analysis
inclusion_criteria
exclusion_criteria
geographic_scope
payer_scope
age_scope
clinical_scope

If unavailable, explicitly state:

"Not specified; must be determined from source data."

TIME SCOPE
----------

Define:

preferred_period
acceptable_period
temporal_comparison
reason

Prefer the most recent comparable official period available.

SOURCE STRATEGY
---------------

For each source family specify:

source
purpose
authority_level
expected_evidence
variables
query_strategy
limitations

AUTHORITY HIERARCHY
-------------------

Tier 1:
- official government datasets
- official methodology documents
- official regulatory filings

Tier 2:
- peer-reviewed research
- scholarly research

Tier 3:
- reputable institutional research

Tier 4:
- secondary sources

Secondary sources must never override primary evidence.

RESEARCH QUERIES
----------------

Create 4-8 precise scholarly research queries.

Queries must cover different dimensions.

Do not repeat the same query with minor wording changes.

SEC QUERIES
-----------

Create 1-4 SEC queries only when SEC evidence is relevant.

If SEC evidence is not relevant, return an empty array.

CMS QUERIES
-----------

Create 3-8 CMS-oriented queries.

Queries must be specific enough for a CMS data adapter.

CDC QUERIES
-----------

Create 2-5 CDC PLACES queries.

VARIABLE EXTRACTION
-------------------

Create structured variables for downstream agents.

Every variable must include:

name
definition
source
type
unit
expected_role
aggregation
interpretation

Potential variables:
- ED utilization rate
- ED visit count
- hospitalization rate
- primary care utilization
- urgent care utilization
- telehealth utilization
- follow-up rate
- chronic disease prevalence
- geographic utilization rate
- quality measure
- cost measure
- benchmark

QUANTITATIVE METRICS
--------------------

Create 8-15 metrics where justified by available data.

Each metric must contain:

metric_name
mathematical_definition
numerator
denominator
unit
interpretation
required_data
caveat

Only include metrics that can reasonably be supported by the planned
datasets.

STATISTICAL METHODS
-------------------

Specify appropriate methods.

Potential methods:
- descriptive statistics
- stratification
- trend analysis
- rate comparison
- confidence intervals
- correlation analysis
- regression
- logistic regression
- survival analysis
- propensity methods
- causal inference
- sensitivity analysis
- subgroup analysis
- model validation

Do not prescribe advanced statistical methods merely for appearance.

Only use methods justified by the available data and study design.

EVIDENCE REQUIREMENTS
---------------------

The Evidence Agent must distinguish:

direct evidence
indirect evidence
contextual evidence
methodological evidence
weak evidence
contradictory evidence
missing evidence

For every quantitative claim:

- prefer the original source
- preserve numerator
- preserve denominator
- preserve units
- preserve time period
- preserve population
- preserve geography
- preserve methodology

No number should appear in the final report without provenance.

SAFETY CONSTRAINTS
------------------

Mandatory:

1. Genuine emergencies must never be discouraged.
2. The system identifies patterns, not individual clinical diagnoses.
3. "Potentially avoidable" must never mean "medically unnecessary."
4. Recommendations must be navigation-oriented.
5. Emergency symptoms require appropriate emergency care.
6. Population-level evidence cannot automatically be applied to an individual.
7. Correlation must not be presented as causation.
8. Model predictions must not be presented as clinical truth.
9. Missing data must be disclosed.
10. Dataset limitations must be disclosed.

REPORT DESIGN
-------------

The final document must contain:

Executive Summary
Research Question and Scope
Population and Context
Methodology
Evidence Landscape
Peer-Reviewed Research Evidence
CMS Empirical Findings
CDC Community-Level Context
Healthcare Utilization Patterns
Potentially Avoidable ED Utilization Signals
Navigation Opportunities
Quantitative Findings
Evidence-to-Action Mapping
Safety and Clinical Boundaries
Limitations
Data Quality and Uncertainty
Conclusion
References
Metadata

QUALITY GATES
-------------

Define 10-15 objective quality gates.

Include where appropriate:

citation completeness
source authority
numerical provenance
denominator availability
population consistency
temporal consistency
geographic consistency
evidence triangulation
contradiction detection
uncertainty reporting
safety compliance
recommendation traceability
hallucination prevention

EXPECTED OUTPUTS
----------------

Define expected outputs for:

Research Agent
CMS Agent
CDC Agent
SEC Agent
Evidence Agent
Synthesis Agent
Critic Agent

IMPORTANT
---------

Return VALID JSON ONLY.

Do not use Markdown.

Do not add explanatory text outside JSON.

Use exactly this top-level structure:

{{
    "research_objective": "...",
    "primary_question": "...",
    "sub_questions": [],
    "hypotheses": [],
    "population_definition": {{}},
    "time_scope": {{}},
    "source_strategy": {{}},
    "research_queries": [],
    "sec_queries": [],
    "cms_queries": [],
    "cdc_queries": [],
    "variables_to_extract": [],
    "metrics": [],
    "statistical_methods": [],
    "evidence_requirements": {{}},
    "safety_constraints": [],
    "report_sections": [],
    "quality_gates": [],
    "expected_outputs": {{}}
}}
"""


# ============================================================================
# Bedrock/model output parsing
# ============================================================================

def _parse_model_plan(raw: Any) -> Dict[str, Any]:
    """
    Parse Bedrock output defensively.

    Handles:
    - plain JSON
    - Markdown JSON fences
    - explanatory text around JSON
    - Bedrock helper returning a dictionary
    - whitespace/noisy model output
    """

    if raw is None:
        raise ValueError("Planner returned empty response")

    if isinstance(raw, dict):
        if "plan" in raw and isinstance(raw["plan"], dict):
            return raw["plan"]

        return raw

    if isinstance(raw, bytes):
        response_text = raw.decode(
            "utf-8",
            errors="replace",
        ).strip()
    else:
        response_text = str(raw).strip()

    if not response_text:
        raise ValueError("Planner returned empty response")

    # Remove Markdown fences safely.
    response_text = re.sub(
        r"```(?:json)?",
        "",
        response_text,
        flags=re.IGNORECASE,
    )

    response_text = response_text.replace(
        "```",
        "",
    ).strip()

    # First attempt: entire response is JSON.
    try:
        parsed = json.loads(response_text)

        if isinstance(parsed, dict):
            return parsed

    except json.JSONDecodeError:
        pass

    # Second attempt: find the first balanced JSON object.
    json_text = _extract_json_object(response_text)

    if not json_text:
        raise ValueError(
            "Planner response does not contain a valid JSON object"
        )

    try:
        plan = json.loads(json_text)

    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Planner JSON parsing failed: {exc}"
        ) from exc

    if not isinstance(plan, dict):
        raise ValueError(
            "Planner JSON must be an object"
        )

    return plan


def _extract_json_object(text: str) -> str:
    """
    Extract the first balanced JSON object from noisy model output.

    This is more reliable than simply using:
        text.find("{")
        text.rfind("}")
    """

    start = text.find("{")

    if start == -1:
        return ""

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False

            elif char == "\\":
                escaped = True

            elif char == '"':
                in_string = False

            continue

        if char == '"':
            in_string = True

        elif char == "{":
            depth += 1

        elif char == "}":
            depth -= 1

            if depth == 0:
                return text[start:index + 1]

    return ""


# ============================================================================
# Normalization
# ============================================================================

def _normalize_plan(
    plan: Dict[str, Any],
    question: str,
    context_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Normalize model output so downstream Lambda functions receive
    predictable structures.
    """

    normalized = dict(plan)

    normalized["research_objective"] = _ensure_string(
        normalized.get("research_objective"),
        "Investigate the research question using traceable public evidence.",
    )

    normalized["primary_question"] = _ensure_string(
        normalized.get("primary_question"),
        question,
    )

    normalized["sub_questions"] = _ensure_list(
        normalized.get("sub_questions")
    )

    normalized["hypotheses"] = _ensure_list(
        normalized.get("hypotheses")
    )

    normalized["research_queries"] = _bounded_string_list(
        normalized.get("research_queries"),
        MIN_RESEARCH_QUERIES,
        MAX_RESEARCH_QUERIES,
    )

    normalized["cms_queries"] = _bounded_string_list(
        normalized.get("cms_queries"),
        MIN_CMS_QUERIES,
        MAX_CMS_QUERIES,
    )

    normalized["cdc_queries"] = _bounded_string_list(
        normalized.get("cdc_queries"),
        MIN_CDC_QUERIES,
        MAX_CDC_QUERIES,
    )

    # SEC is optional because not every healthcare research question
    # requires regulatory/company evidence.
    normalized["sec_queries"] = _bounded_string_list(
        normalized.get("sec_queries"),
        0,
        MAX_SEC_QUERIES,
    )

    normalized["variables_to_extract"] = _ensure_list(
        normalized.get("variables_to_extract")
    )

    normalized["metrics"] = _ensure_list(
        normalized.get("metrics")
    )

    normalized["statistical_methods"] = _ensure_list(
        normalized.get("statistical_methods")
    )

    normalized["safety_constraints"] = _ensure_list(
        normalized.get("safety_constraints")
    )

    normalized["quality_gates"] = _ensure_list(
        normalized.get("quality_gates")
    )

    normalized["report_sections"] = _normalize_sections(
        normalized.get("report_sections")
    )

    population = normalized.get("population_definition")

    if not isinstance(population, dict):
        population = _default_population_definition()

    normalized["population_definition"] = population

    time_scope = normalized.get("time_scope")

    if not isinstance(time_scope, dict):
        time_scope = _default_time_scope()

    normalized["time_scope"] = time_scope

    source_strategy = normalized.get("source_strategy")

    if not isinstance(source_strategy, dict):
        source_strategy = _default_source_strategy()

    normalized["source_strategy"] = source_strategy

    evidence_requirements = normalized.get(
        "evidence_requirements"
    )

    if not isinstance(evidence_requirements, dict):
        evidence_requirements = _default_evidence_requirements()

    normalized["evidence_requirements"] = evidence_requirements

    expected_outputs = normalized.get(
        "expected_outputs"
    )

    if not isinstance(expected_outputs, dict):
        expected_outputs = _default_expected_outputs()

    normalized["expected_outputs"] = expected_outputs

    # Always enforce the mandatory healthcare safety layer.
    normalized["safety_constraints"] = _merge_safety_constraints(
        normalized["safety_constraints"]
    )

    # Complete undersized research query lists deterministically.
    normalized["research_queries"] = _ensure_minimum_queries(
        normalized["research_queries"],
        [
            question,
            f"{question} systematic evidence",
            f"{question} healthcare utilization research",
            f"{question} emergency department utilization evidence",
        ],
        MAX_RESEARCH_QUERIES,
    )

    normalized["cms_queries"] = _ensure_minimum_queries(
        normalized["cms_queries"],
        [
            "Medicare emergency department utilization",
            "Medicare quality utilization measures",
            "Medicare provider utilization and quality",
        ],
        MAX_CMS_QUERIES,
    )

    normalized["cdc_queries"] = _ensure_minimum_queries(
        normalized["cdc_queries"],
        [
            "CDC PLACES chronic disease prevalence",
            "CDC PLACES preventive health indicators",
        ],
        MAX_CDC_QUERIES,
    )

    normalized["context"] = context_data

    normalized.setdefault(
        "planner_status",
        "MODEL_GENERATED",
    )

    return normalized


def _ensure_string(
    value: Any,
    default: str,
) -> str:
    if value is None:
        return default

    text_value = clean_text(
        str(value)
    ).strip()

    return text_value if text_value else default


def _ensure_list(
    value: Any,
) -> List[Any]:
    """
    Convert malformed/null model output into a predictable list.
    """

    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def _bounded_string_list(
    value: Any,
    minimum: int,
    maximum: int,
) -> List[str]:
    """
    Normalize query lists.

    minimum is retained for compatibility with the Planner
    configuration. Minimum completion is handled separately.
    """

    del minimum

    items = _ensure_list(value)

    cleaned: List[str] = []

    for item in items:

        if isinstance(item, dict):
            text_value = (
                item.get("query")
                or item.get("question")
                or item.get("text")
                or ""
            )

        else:
            text_value = str(item)

        try:
            text_value = clean_text(
                text_value
            ).strip()

        except Exception:
            text_value = str(
                text_value
            ).strip()

        if text_value and text_value not in cleaned:
            cleaned.append(text_value)

    return cleaned[:maximum]


def _ensure_minimum_queries(
    existing: List[str],
    fallback_queries: List[str],
    maximum: int,
) -> List[str]:
    """
    Complete an undersized query list without exceeding
    the configured maximum.
    """

    result = list(existing)

    for query in fallback_queries:

        if len(result) >= maximum:
            break

        query = str(query).strip()

        if query and query not in result:
            result.append(query)

    return result[:maximum]


def _merge_safety_constraints(
    model_constraints: List[Any],
) -> List[str]:
    """
    Preserve model safety constraints while guaranteeing
    mandatory CTS-NPN healthcare safeguards.
    """

    result: List[str] = []

    for item in model_constraints:

        text_value = str(item).strip()

        if text_value and text_value not in result:
            result.append(text_value)

    for item in MANDATORY_SAFETY_CONSTRAINTS:

        if item not in result:
            result.append(item)

    return result


def _normalize_sections(
    value: Any,
) -> List[str]:
    """
    Preserve a deterministic report architecture.

    Model-provided sections are retained while mandatory sections
    are always added.
    """

    sections = [
        str(section).strip()
        for section in _ensure_list(value)
        if str(section).strip()
    ]

    if not sections:
        sections = list(DEFAULT_REPORT_SECTIONS)

    for mandatory in DEFAULT_REPORT_SECTIONS:

        if mandatory not in sections:
            sections.append(mandatory)

    return sections


# ============================================================================
# Validation
# ============================================================================

def _validate_plan(
    plan: Dict[str, Any],
) -> None:
    """
    Validate the research protocol before it enters downstream agents.
    """

    required_keys = [
        "research_objective",
        "primary_question",
        "sub_questions",
        "research_queries",
        "cms_queries",
        "cdc_queries",
        "variables_to_extract",
        "metrics",
        "safety_constraints",
        "report_sections",
        "population_definition",
        "time_scope",
        "source_strategy",
        "evidence_requirements",
        "expected_outputs",
    ]

    missing = [
        key
        for key in required_keys
        if key not in plan
    ]

    if missing:
        raise ValueError(
            f"Planner output missing required fields: {missing}"
        )

    if not isinstance(
        plan["primary_question"],
        str,
    ):
        raise ValueError(
            "Primary research question must be a string"
        )

    if not plan["primary_question"].strip():
        raise ValueError(
            "Primary research question is empty"
        )

    if len(plan["research_queries"]) < MIN_RESEARCH_QUERIES:
        raise ValueError(
            "Insufficient research queries"
        )

    if len(plan["cms_queries"]) < MIN_CMS_QUERIES:
        raise ValueError(
            "Insufficient CMS queries"
        )

    if len(plan["cdc_queries"]) < MIN_CDC_QUERIES:
        raise ValueError(
            "Insufficient CDC queries"
        )

    if not plan["safety_constraints"]:
        raise ValueError(
            "Safety constraints cannot be empty"
        )

    safety_text = " ".join(
        str(item).lower()
        for item in plan["safety_constraints"]
    )

    if "emergency" not in safety_text:
        raise ValueError(
            "Planner safety protocol does not explicitly protect "
            "genuine emergencies"
        )

    if (
        "correlation" not in safety_text
        or "causation" not in safety_text
    ):
        raise ValueError(
            "Planner safety protocol must distinguish "
            "correlation from causation"
        )

    if "potentially avoidable" not in safety_text:
        raise ValueError(
            "Planner must explicitly define potentially avoidable "
            "utilization as distinct from medically unnecessary care"
        )

    if len(plan["report_sections"]) < len(DEFAULT_REPORT_SECTIONS):
        raise ValueError(
            "Planner report structure is incomplete"
        )


# ============================================================================
# Deterministic fallback
# ============================================================================

def _fallback_plan(
    question: str,
    context_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Deterministic fallback.

    This fallback deliberately contains no fabricated findings.
    """

    return {
        "planner_version": PLANNER_VERSION,
        "planner_status": "DETERMINISTIC_FALLBACK",

        "research_objective": (
            "Investigate the stated question using authoritative "
            "public evidence and clearly distinguish observed, "
            "calculated, inferred, and unsupported claims."
        ),

        "primary_question": question,

        "sub_questions": [
            "What does the existing scholarly evidence establish?",
            "What empirical evidence is available from CMS?",
            "What community-level context is available from CDC PLACES?",
            "What utilization patterns can be measured from available data?",
            "Which navigation opportunities are supported by evidence?",
            "What conclusions cannot be established from the available data?",
        ],

        "hypotheses": [
            {
                "hypothesis_id": "H1",
                "statement": (
                    "Some observed ED utilization patterns may be "
                    "associated with availability or use of lower-acuity care."
                ),
                "rationale": (
                    "Healthcare access and utilization patterns can be "
                    "investigated using public healthcare datasets."
                ),
                "variables": [
                    "ED utilization",
                    "primary care availability",
                    "urgent care availability",
                    "telehealth availability",
                ],
                "expected_direction": "To be determined empirically",
                "evidence_required": [
                    "CMS data",
                    "scholarly literature",
                ],
                "falsification_condition": (
                    "Observed data do not support the proposed association."
                ),
            },
            {
                "hypothesis_id": "H2",
                "statement": (
                    "Community-level health characteristics may be "
                    "associated with differences in observed healthcare utilization."
                ),
                "rationale": (
                    "CDC PLACES provides population-level health indicators "
                    "that can be evaluated as contextual variables."
                ),
                "variables": [
                    "ED utilization",
                    "chronic disease prevalence",
                    "preventive health indicators",
                ],
                "expected_direction": "To be determined empirically",
                "evidence_required": [
                    "CDC PLACES",
                    "CMS",
                ],
                "falsification_condition": (
                    "No consistent association is observed after appropriate analysis."
                ),
            },
            {
                "hypothesis_id": "H3",
                "statement": (
                    "Differences in healthcare utilization may vary across "
                    "geographies and population groups."
                ),
                "rationale": (
                    "Geographic and population stratification can reveal "
                    "variation that aggregate statistics may hide."
                ),
                "variables": [
                    "ED utilization",
                    "geography",
                    "population characteristics",
                ],
                "expected_direction": "To be determined empirically",
                "evidence_required": [
                    "CMS",
                    "CDC PLACES",
                ],
                "falsification_condition": (
                    "Comparable strata do not show meaningful variation."
                ),
            },
        ],

        "population_definition": _default_population_definition(),

        "time_scope": _default_time_scope(),

        "source_strategy": _default_source_strategy(),

        "research_queries": _ensure_minimum_queries(
            [],
            [
                question,
                f"{question} systematic evidence",
                f"{question} healthcare utilization research",
                f"{question} emergency department utilization evidence",
            ],
            MAX_RESEARCH_QUERIES,
        ),

        "sec_queries": [],

        "cms_queries": _ensure_minimum_queries(
            [],
            [
                "Medicare emergency department utilization",
                "Medicare Shared Savings Program quality utilization",
                "Medicare provider utilization and quality",
            ],
            MAX_CMS_QUERIES,
        ),

        "cdc_queries": _ensure_minimum_queries(
            [],
            [
                "CDC PLACES chronic disease prevalence",
                "CDC PLACES preventive health indicators",
            ],
            MAX_CDC_QUERIES,
        ),

        "variables_to_extract": [
            {
                "name": "ED utilization rate",
                "definition": (
                    "Emergency department utilization per defined population."
                ),
                "source": "CMS",
                "type": "rate",
                "unit": "source-defined population rate",
                "expected_role": "Primary utilization outcome",
                "aggregation": "geography/time/population",
                "interpretation": (
                    "Observed utilization intensity; not evidence that "
                    "individual visits were medically unnecessary."
                ),
            },
            {
                "name": "ED visit count",
                "definition": (
                    "Number of observed emergency department events."
                ),
                "source": "CMS where available",
                "type": "count",
                "unit": "events",
                "expected_role": "Utilization numerator",
                "aggregation": "geography/time/population",
                "interpretation": (
                    "Observed events in the source dataset."
                ),
            },
            {
                "name": "Chronic disease prevalence",
                "definition": (
                    "Population-level prevalence from CDC PLACES."
                ),
                "source": "CDC PLACES",
                "type": "proportion",
                "unit": "percent",
                "expected_role": "Community-level contextual variable",
                "aggregation": "geography",
                "interpretation": (
                    "Contextual population-level association only."
                ),
            },
            {
                "name": "Primary care utilization",
                "definition": (
                    "Observed primary-care utilization where supported "
                    "by the source dataset."
                ),
                "source": "CMS",
                "type": "rate/count",
                "unit": "source-defined",
                "expected_role": "Lower-acuity care comparison",
                "aggregation": "geography/time/population",
                "interpretation": (
                    "Observed utilization and not proof that primary care "
                    "was clinically appropriate for an individual ED visit."
                ),
            },
        ],

        "metrics": [
            {
                "metric_name": "Utilization Rate",
                "mathematical_definition": "(events / population) × 100",
                "numerator": "Observed utilization events",
                "denominator": "Defined population",
                "unit": "percent or source-standardized rate",
                "interpretation": "Observed utilization intensity.",
                "required_data": [
                    "events",
                    "population",
                ],
                "caveat": "Requires a valid denominator.",
            },
            {
                "metric_name": "Absolute Difference",
                "mathematical_definition": "Rate_A - Rate_B",
                "numerator": "N/A",
                "denominator": "N/A",
                "unit": "percentage points or rate units",
                "interpretation": (
                    "Difference between comparable groups."
                ),
                "required_data": [
                    "rate_a",
                    "rate_b",
                ],
                "caveat": (
                    "Groups must use comparable definitions and denominators."
                ),
            },
            {
                "metric_name": "Relative Change",
                "mathematical_definition": "((New - Old) / Old) × 100",
                "numerator": "Change in measured value",
                "denominator": "Baseline value",
                "unit": "percent",
                "interpretation": (
                    "Relative change over time or between groups."
                ),
                "required_data": [
                    "baseline",
                    "comparison",
                ],
                "caveat": "Baseline cannot be zero.",
            },
            {
                "metric_name": "Rate Ratio",
                "mathematical_definition": "Rate_A / Rate_B",
                "numerator": "Rate_A",
                "denominator": "Rate_B",
                "unit": "ratio",
                "interpretation": (
                    "Relative utilization rate between comparable groups."
                ),
                "required_data": [
                    "rate_a",
                    "rate_b",
                ],
                "caveat": (
                    "Requires comparable definitions and a non-zero denominator."
                ),
            },
            {
                "metric_name": "Correlation",
                "mathematical_definition": (
                    "Pearson or Spearman correlation as justified"
                ),
                "numerator": "N/A",
                "denominator": "N/A",
                "unit": "correlation coefficient",
                "interpretation": (
                    "Measures association and does not establish causality."
                ),
                "required_data": [
                    "paired observations",
                ],
                "caveat": (
                    "Correlation must not be interpreted as causal evidence."
                ),
            },
            {
                "metric_name": "Confidence Interval",
                "mathematical_definition": (
                    "Method appropriate to the estimated parameter"
                ),
                "numerator": "N/A",
                "denominator": "N/A",
                "unit": "same scale as estimate",
                "interpretation": (
                    "Quantifies statistical uncertainty when assumptions are satisfied."
                ),
                "required_data": [
                    "estimate",
                    "sample information",
                ],
                "caveat": (
                    "Method must match the statistic and study design."
                ),
            },
            {
                "metric_name": "Sensitivity",
                "mathematical_definition": "TP / (TP + FN)",
                "numerator": "True positives",
                "denominator": "Actual positives",
                "unit": "proportion or percent",
                "interpretation": (
                    "Ability of a classifier to identify positive cases."
                ),
                "required_data": [
                    "TP",
                    "FN",
                ],
                "caveat": (
                    "Only applicable when a valid reference classification exists."
                ),
            },
            {
                "metric_name": "Specificity",
                "mathematical_definition": "TN / (TN + FP)",
                "numerator": "True negatives",
                "denominator": "Actual negatives",
                "unit": "proportion or percent",
                "interpretation": (
                    "Ability of a classifier to identify negative cases."
                ),
                "required_data": [
                    "TN",
                    "FP",
                ],
                "caveat": (
                    "Requires a valid reference classification."
                ),
            },
            {
                "metric_name": "AUC",
                "mathematical_definition": (
                    "Area under the ROC curve"
                ),
                "numerator": "N/A",
                "denominator": "N/A",
                "unit": "0-1",
                "interpretation": (
                    "Discrimination performance of a binary classifier."
                ),
                "required_data": [
                    "predicted scores",
                    "reference labels",
                ],
                "caveat": (
                    "Does not establish clinical utility or causality."
                ),
            },
            {
                "metric_name": "MAE",
                "mathematical_definition": (
                    "mean(|actual - predicted|)"
                ),
                "numerator": "Sum of absolute prediction errors",
                "denominator": "Number of observations",
                "unit": "target variable units",
                "interpretation": (
                    "Average magnitude of prediction error."
                ),
                "required_data": [
                    "actual values",
                    "predicted values",
                ],
                "caveat": (
                    "Applicable to continuous prediction tasks."
                ),
            },
        ],

        "statistical_methods": [
            "descriptive statistics",
            "stratification",
            "trend analysis",
            "rate comparison",
            "confidence intervals where justified",
            "sensitivity analysis",
        ],

        "evidence_requirements": _default_evidence_requirements(),

        "safety_constraints": list(
            MANDATORY_SAFETY_CONSTRAINTS
        ),

        "report_sections": list(
            DEFAULT_REPORT_SECTIONS
        ),

        "quality_gates": [
            "citation completeness",
            "source authority",
            "numerical provenance",
            "denominator availability",
            "population consistency",
            "temporal consistency",
            "geographic consistency",
            "evidence triangulation",
            "contradiction detection",
            "uncertainty reporting",
            "safety compliance",
            "recommendation traceability",
            "hallucination prevention",
        ],

        "expected_outputs": _default_expected_outputs(),

        "context": context_data,

        "fallback": True,
    }


# ============================================================================
# Default research structures
# ============================================================================

def _default_population_definition() -> Dict[str, Any]:
    return {
        "population": (
            "US Medicare population where supported by source data"
        ),
        "unit_of_analysis": (
            "To be determined from the selected dataset"
        ),
        "inclusion_criteria": [
            "Records meeting the source dataset definition"
        ],
        "exclusion_criteria": [
            "Records excluded by the source methodology"
        ],
        "geographic_scope": (
            "United States or source-supported geography"
        ),
        "payer_scope": (
            "Medicare where applicable"
        ),
        "age_scope": "Source-defined",
        "clinical_scope": (
            "Emergency department utilization and related "
            "navigation context"
        ),
    }


def _default_time_scope() -> Dict[str, Any]:
    return {
        "preferred_period": (
            "Most recent comparable period available"
        ),
        "acceptable_period": (
            "Earlier periods when necessary for valid trend analysis"
        ),
        "temporal_comparison": (
            "Year-over-year where definitions and methodology remain comparable"
        ),
        "reason": (
            "Recent comparable official data should be preferred while "
            "preserving historical context where methodologically valid."
        ),
    }


def _default_source_strategy() -> Dict[str, Any]:
    return {
        "arxiv": {
            "purpose": "Scholarly and methodological research",
            "authority_level": (
                "Scholarly preprint/research source"
            ),
            "expected_evidence": [
                "methods",
                "models",
                "experimental findings",
                "research context",
            ],
            "limitations": [
                "May not be peer-reviewed",
                "Study quality must be evaluated individually",
            ],
        },

        "cms": {
            "purpose": (
                "Primary empirical healthcare evidence"
            ),
            "authority_level": (
                "Official government data"
            ),
            "expected_evidence": [
                "utilization",
                "quality",
                "provider",
                "Medicare performance",
            ],
            "limitations": [
                "Dataset definitions and coverage vary",
                "Administrative data may not contain all clinical context",
            ],
        },

        "cdc_places": {
            "purpose": (
                "Population and community-level context"
            ),
            "authority_level": (
                "Official government data"
            ),
            "expected_evidence": [
                "health indicators",
                "chronic disease prevalence",
                "preventive health context",
            ],
            "limitations": [
                "Population-level data",
                "Not individual clinical evidence",
            ],
        },

        "sec": {
            "purpose": (
                "Public corporate/regulatory context where relevant"
            ),
            "authority_level": (
                "Official regulatory filings"
            ),
            "expected_evidence": [
                "reported business metrics",
                "strategy",
                "operational context",
            ],
            "limitations": [
                "Corporate reporting is not clinical evidence",
                "Use only when relevant to the research question",
            ],
        },
    }


def _default_evidence_requirements() -> Dict[str, Any]:
    return {
        "minimum_primary_sources": 3,

        "quantitative_claim_rule": (
            "Every quantitative claim must retain source, period, "
            "population, geography, numerator, denominator, and unit "
            "whenever available."
        ),

        "evidence_classes": [
            "direct",
            "indirect",
            "contextual",
            "methodological",
            "weak",
            "contradictory",
            "insufficient",
            "missing",
        ],

        "causal_claim_rule": (
            "Causal claims require explicit causal evidence and "
            "must not be inferred from observational association."
        ),

        "uncertainty_rule": (
            "Uncertainty, missingness, sampling limitations, "
            "measurement limitations, and dataset methodology "
            "must be reported."
        ),

        "citation_rule": (
            "Every material factual or quantitative claim must be "
            "traceable to an evidence object or source."
        ),
    }


def _default_expected_outputs() -> Dict[str, Any]:
    return {
        "research_agent": [
            "scholarly sources",
            "study metadata",
            "quantitative findings",
            "methodological findings",
            "limitations",
        ],

        "cms_agent": [
            "official CMS records",
            "dataset metadata",
            "field definitions",
            "aggregated findings",
            "source provenance",
        ],

        "cdc_agent": [
            "CDC PLACES indicators",
            "geographic context",
            "indicator definitions",
            "source provenance",
        ],

        "sec_agent": [
            "relevant filings",
            "filing metadata",
            "reported quantitative facts",
            "source provenance",
        ],

        "evidence_agent": [
            "normalized evidence objects",
            "claim-to-source mappings",
            "quantitative evidence",
            "contradiction flags",
            "evidence quality assessment",
        ],

        "synthesis_agent": [
            "research narrative",
            "quantitative findings",
            "evidence-supported conclusions",
            "uncertainty",
            "recommendations",
        ],

        "critic_agent": [
            "citation validation",
            "numerical validation",
            "claim validation",
            "safety validation",
            "methodology validation",
            "publication decision",
        ],
    }