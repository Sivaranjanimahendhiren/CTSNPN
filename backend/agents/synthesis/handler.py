"""
CTS-NPN Research Synthesis Agent
================================

Purpose
-------
Transforms curated evidence produced by the Research, CMS and Evidence
agents into an evidence-grounded research document.

Architecture
------------
Planner
   ↓
Research + CMS
   ↓
Evidence
   ↓
Synthesis
   ↓
Critic
   ↓
Publication / Delivery

Important Design Principle
--------------------------
This agent DOES NOT perform independent research.

It only synthesizes evidence already collected upstream.

Responsibilities
----------------
1. Consume structured evidence.
2. Normalize and deterministically assign source identifiers.
3. Preserve provenance and source traceability.
4. Distinguish observed evidence from interpretation.
5. Generate evidence-grounded research prose.
6. Prevent unsupported quantitative claims.
7. Validate generated citation identifiers.
8. Produce Markdown research output.
9. Produce professional PDF using report_template.pdf.
10. Repeat the template background on every generated PDF page.
11. Persist artifacts to S3.
12. Return deterministic metadata to downstream Critic/Publication agents.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import boto3

from reportlab.lib.enums import (
    TA_CENTER,
    TA_JUSTIFY,
    TA_LEFT,
)

from reportlab.lib.styles import (
    ParagraphStyle,
    getSampleStyleSheet,
)

from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from pypdf import PdfReader, PdfWriter

from backend.common.aws import (
    bedrock,
    get_json,
    put_json,
    put_text,
    update_run,
)

from backend.common.config import (
    MODEL,
    REPORTS_BUCKET,
    RESEARCH_BUCKET,
)

from backend.common.security import (
    clean_text,
    validate_content,
)


# ============================================================================
# LOGGING
# ============================================================================

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ============================================================================
# AWS
# ============================================================================

s3_client = boto3.client("s3")


# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_TEMPLATE_PATHS = [
    os.environ.get("REPORT_TEMPLATE_PATH", ""),
    "/var/task/report_template.pdf",
    "/opt/report_template.pdf",
    os.path.join(os.getcwd(), "report_template.pdf"),
]

TEMPLATE_S3_BUCKET = os.environ.get(
    "REPORT_TEMPLATE_S3_BUCKET",
    "",
)

TEMPLATE_S3_KEY = os.environ.get(
    "REPORT_TEMPLATE_S3_KEY",
    "report_template.pdf",
)


def _env_float(
    name: str,
    default: float,
) -> float:

    try:
        return float(
            os.environ.get(
                name,
                str(default),
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


MARGIN_LEFT = _env_float(
    "REPORT_TEMPLATE_MARGIN_LEFT",
    54,
)

MARGIN_RIGHT = _env_float(
    "REPORT_TEMPLATE_MARGIN_RIGHT",
    54,
)

MARGIN_TOP = _env_float(
    "REPORT_TEMPLATE_MARGIN_TOP",
    72,
)

MARGIN_BOTTOM = _env_float(
    "REPORT_TEMPLATE_MARGIN_BOTTOM",
    60,
)


try:

    MAX_EVIDENCE_CONTEXT_CHARS = int(
        os.environ.get(
            "SYNTHESIS_MAX_EVIDENCE_CHARS",
            "45000",
        )
    )

except (
    TypeError,
    ValueError,
):

    MAX_EVIDENCE_CONTEXT_CHARS = 45000


try:

    MAX_SOURCES = int(
        os.environ.get(
            "SYNTHESIS_MAX_SOURCES",
            "80",
        )
    )

except (
    TypeError,
    ValueError,
):

    MAX_SOURCES = 80


DEFAULT_REPORT_SECTIONS = [
    "Executive Summary",
    "Research Question and Scope",
    "Methodology",
    "Evidence Base",
    "Research Findings",
    "CMS Findings",
    "ED Utilization Interpretation",
    "Navigation Opportunities",
    "Quantitative Metrics",
    "Limitations",
    "Conclusion",
]


# ============================================================================
# LAMBDA ENTRY POINT
# ============================================================================

def lambda_handler(
    event: Dict[str, Any],
    context: Any,
) -> Dict[str, Any]:

    event = event or {}

    run_id = str(
        event.get(
            "run_id",
            "unknown",
        )
    )

    try:

        update_run(
            run_id,
            "SYNTHESIZING",
        )

        logger.info(
            "Starting synthesis agent for run_id=%s",
            run_id,
        )

        question = clean_text(
            str(
                event.get(
                    "question",
                    "",
                )
            )
        )

        plan = event.get(
            "plan",
            {},
        )

        if not isinstance(
            plan,
            dict,
        ):
            plan = {}

        # ------------------------------------------------------------------
        # Evidence acquisition
        # ------------------------------------------------------------------

        raw_evidence = _obtain_evidence(
            event,
            run_id,
        )

        # ------------------------------------------------------------------
        # Normalize evidence and assign deterministic source IDs
        # ------------------------------------------------------------------

        normalized = _normalize_evidence(
            raw_evidence,
            event,
        )

        logger.info(
            "Normalized evidence statistics: %s",
            normalized["statistics"],
        )

        # ------------------------------------------------------------------
        # Generate research document
        # ------------------------------------------------------------------

        research_document = _generate_research_document(
            run_id=run_id,
            question=question,
            plan=plan,
            evidence=normalized,
        )

        if not research_document:
            raise RuntimeError(
                "Synthesis agent generated an empty document."
            )

        # ------------------------------------------------------------------
        # Security/content validation
        # ------------------------------------------------------------------

        validate_content(
            research_document,
        )

        # ------------------------------------------------------------------
        # Structural + citation validation
        # ------------------------------------------------------------------

        document_quality = _validate_generated_document(
            research_document,
            normalized,
        )

        if not document_quality["valid"]:

            logger.warning(
                "Document validation warnings: %s",
                document_quality["checks"],
            )

        # ------------------------------------------------------------------
        # Store Markdown
        # ------------------------------------------------------------------

        markdown_key = (
            f"{run_id}/research_report.md"
        )

        if REPORTS_BUCKET:

            put_text(
                REPORTS_BUCKET,
                markdown_key,
                research_document,
            )

        # ------------------------------------------------------------------
        # Generate PDF
        # ------------------------------------------------------------------

        pdf_bytes, pdf_metadata = _render_report_pdf(
            research_document,
            run_id,
            normalized,
        )

        pdf_key = (
            f"{run_id}/research_report.pdf"
        )

        if REPORTS_BUCKET:

            s3_client.put_object(
                Bucket=REPORTS_BUCKET,
                Key=pdf_key,
                Body=pdf_bytes,
                ContentType="application/pdf",
                Metadata={
                    "run-id": run_id,
                    "generator": "cts-npn-synthesis-agent",
                    "template": "report_template.pdf",
                },
            )

        # ------------------------------------------------------------------
        # Deterministic metadata
        # ------------------------------------------------------------------

        synthesis_metadata_key = (
            f"{run_id}/synthesis_metadata.json"
        )

        artifact_metadata = {
            "run_id": run_id,
            "generated_at": _utc_now(),
            "generator": "cts-npn-synthesis-agent",
            "markdown_key": markdown_key,
            "pdf_key": pdf_key,
            "pdf": pdf_metadata,
            "document_quality": document_quality,
            "evidence_statistics": normalized["statistics"],
            "evidence_quality": normalized["quality"],
            "source_registry": normalized["source_registry"],
        }

        if REPORTS_BUCKET:

            put_json(
                REPORTS_BUCKET,
                synthesis_metadata_key,
                artifact_metadata,
            )

        # ------------------------------------------------------------------
        # Update orchestration state
        # ------------------------------------------------------------------

        update_run(
            run_id,
            "SYNTHESIS_COMPLETE",
            pdf_key=pdf_key,
            markdown_key=markdown_key,
            evidence_quality=normalized["quality"],
        )

        logger.info(
            "Synthesis completed successfully: %s",
            run_id,
        )

        return {
            "run_id": run_id,
            "status": "COMPLETE",
            "report": research_document,
            "research_report": research_document,
            "pdf_key": pdf_key,
            "markdown_key": markdown_key,
            "synthesis_metadata_key": synthesis_metadata_key,
            "pdf_metadata": pdf_metadata,
            "document_quality": document_quality,
            "evidence_statistics": normalized["statistics"],
            "evidence_quality": normalized["quality"],
            "source_registry": normalized["source_registry"],
        }

    except Exception as exc:

        error_msg = (
            f"Synthesis agent error: "
            f"{type(exc).__name__}: {str(exc)}"
        )

        logger.exception(
            "Synthesis failure for run_id=%s",
            run_id,
        )

        try:

            update_run(
                run_id,
                "SYNTHESIS_FAILED",
                error=error_msg,
            )

        except Exception:

            logger.exception(
                "Unable to update run after synthesis failure."
            )

        return {
            "run_id": run_id,
            "status": "FAILED",
            "error": error_msg,
        }


# ============================================================================
# EVIDENCE ACQUISITION
# ============================================================================

def _obtain_evidence(
    event: Dict[str, Any],
    run_id: str,
) -> Dict[str, Any]:

    evidence = event.get(
        "evidence",
        {},
    )

    if isinstance(
        evidence,
        dict,
    ) and evidence:

        return evidence

    # ----------------------------------------------------------------------
    # Evidence Agent artifact
    # ----------------------------------------------------------------------

    if RESEARCH_BUCKET:

        key = (
            f"{run_id}/organized_evidence.json"
        )

        try:

            loaded = get_json(
                RESEARCH_BUCKET,
                key,
            )

            if loaded:

                logger.info(
                    "Loaded Evidence Agent artifact from "
                    "s3://%s/%s",
                    RESEARCH_BUCKET,
                    key,
                )

                return loaded

        except Exception as exc:

            logger.warning(
                "Unable to retrieve organized evidence: %s",
                exc,
            )

    # ----------------------------------------------------------------------
    # Backward compatibility
    # ----------------------------------------------------------------------

    return {
        "run_id": run_id,

        "research_papers": event.get(
            "arxiv",
            event.get(
                "research_papers",
                [],
            ),
        ),

        "regulatory_filings": event.get(
            "sec",
            event.get(
                "regulatory_filings",
                [],
            ),
        ),

        "health_data": event.get(
            "cdc",
            event.get(
                "health_data",
                [],
            ),
        ),

        "cms_findings": event.get(
            "cms_findings",
            event.get(
                "cms",
                [],
            ),
        ),

        "citations": event.get(
            "citations",
            [],
        ),
    }


# ============================================================================
# EVIDENCE NORMALIZATION
# ============================================================================

def _normalize_evidence(
    evidence: Dict[str, Any],
    event: Dict[str, Any],
) -> Dict[str, Any]:

    if not isinstance(
        evidence,
        dict,
    ):
        evidence = {}

    papers = _dict_records(
        evidence.get(
            "research_papers",
            evidence.get(
                "arxiv",
                [],
            ),
        )
    )

    filings = _dict_records(
        evidence.get(
            "regulatory_filings",
            evidence.get(
                "sec",
                [],
            ),
        )
    )

    health_data = _dict_records(
        evidence.get(
            "health_data",
            evidence.get(
                "cdc",
                [],
            ),
        )
    )

    cms_data = _dict_records(
        evidence.get(
            "cms_findings",
            evidence.get(
                "cms",
                [],
            ),
        )
    )

    citations = _dict_records(
        evidence.get(
            "citations",
            [],
        )
    )

    # ----------------------------------------------------------------------
    # Build complete source registry
    # ----------------------------------------------------------------------

    citations = _complete_citations(
        citations,
        papers,
        filings,
        health_data,
        cms_data,
    )

    # ----------------------------------------------------------------------
    # Deterministic source IDs
    # ----------------------------------------------------------------------

    source_registry = {}

    for index, citation in enumerate(
        citations[:MAX_SOURCES],
        start=1,
    ):

        source_id = f"S{index}"

        citation["source_id"] = source_id

        source_registry[source_id] = {
            "title": citation.get(
                "title",
                "Untitled source",
            ),
            "url": citation.get(
                "url",
                "",
            ),
            "source": citation.get(
                "source",
                "Unknown",
            ),
            "date": citation.get(
                "date",
                "",
            ),
            "authors": citation.get(
                "authors",
                [],
            ),
        }

    # ----------------------------------------------------------------------
    # Statistics
    # ----------------------------------------------------------------------

    statistics = {
        "research_papers": len(papers),
        "regulatory_filings": len(filings),
        "health_data_records": len(health_data),
        "cms_records": len(cms_data),
        "citations": min(
            len(citations),
            MAX_SOURCES,
        ),
        "total_evidence_items": (
            len(papers)
            + len(filings)
            + len(health_data)
            + len(cms_data)
        ),
    }

    quality = _calculate_evidence_quality(
        papers,
        filings,
        health_data,
        cms_data,
        citations,
    )

    return {
        "research_papers": papers[:MAX_SOURCES],
        "regulatory_filings": filings[:MAX_SOURCES],
        "health_data": health_data[:MAX_SOURCES],
        "cms_findings": cms_data[:MAX_SOURCES],
        "citations": citations[:MAX_SOURCES],
        "source_registry": source_registry,
        "statistics": statistics,
        "quality": quality,
    }


def _dict_records(
    value: Any,
) -> List[Dict[str, Any]]:

    if not isinstance(
        value,
        list,
    ):
        return []

    return [
        item
        for item in value
        if isinstance(
            item,
            dict,
        )
    ]


# ============================================================================
# CITATION COMPLETION
# ============================================================================

def _complete_citations(
    citations: List[Dict[str, Any]],
    papers: List[Dict[str, Any]],
    filings: List[Dict[str, Any]],
    health_data: List[Dict[str, Any]],
    cms_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:

    output = list(citations)

    existing_urls = {
        str(
            item.get(
                "url",
                "",
            )
        ).strip()
        for item in output
        if item.get("url")
    }

    def add_source(
        title: str,
        url: str,
        source: str,
        date: str = "",
        authors: Any = None,
    ) -> None:

        url = str(
            url or ""
        ).strip()

        if not url:
            return

        if url in existing_urls:
            return

        output.append(
            {
                "title": title or "Untitled source",
                "url": url,
                "source": source,
                "date": date,
                "authors": (
                    authors
                    if authors is not None
                    else []
                ),
            }
        )

        existing_urls.add(url)

    # ----------------------------------------------------------------------
    # Research
    # ----------------------------------------------------------------------

    for paper in papers:

        add_source(
            paper.get(
                "title",
                "Research paper",
            ),
            paper.get(
                "url",
                paper.get(
                    "pdf_url",
                    "",
                ),
            ),
            "arXiv",
            paper.get(
                "published_date",
                paper.get(
                    "date",
                    "",
                ),
            ),
            paper.get(
                "authors",
                [],
            ),
        )

    # ----------------------------------------------------------------------
    # SEC
    # ----------------------------------------------------------------------

    for filing in filings:

        company = filing.get(
            "company",
            "Unknown company",
        )

        filing_type = filing.get(
            "filing_type",
            "SEC filing",
        )

        add_source(
            f"{company} {filing_type}",
            filing.get(
                "url",
                "",
            ),
            "SEC EDGAR",
            filing.get(
                "date",
                "",
            ),
        )

    # ----------------------------------------------------------------------
    # CDC
    # ----------------------------------------------------------------------

    for record in health_data:

        add_source(
            record.get(
                "title",
                record.get(
                    "indicator",
                    "CDC PLACES dataset",
                ),
            ),
            record.get(
                "url",
                "",
            ),
            "CDC PLACES",
            record.get(
                "date",
                "",
            ),
        )

    # ----------------------------------------------------------------------
    # CMS
    # ----------------------------------------------------------------------

    for record in cms_data:

        add_source(
            record.get(
                "title",
                record.get(
                    "dataset",
                    "CMS data",
                ),
            ),
            record.get(
                "url",
                "",
            ),
            "CMS",
            record.get(
                "date",
                record.get(
                    "performance_year",
                    "",
                ),
            ),
        )

    return output


# ============================================================================
# EVIDENCE QUALITY
# ============================================================================

def _calculate_evidence_quality(
    papers: List[Dict[str, Any]],
    filings: List[Dict[str, Any]],
    health_data: List[Dict[str, Any]],
    cms_data: List[Dict[str, Any]],
    citations: List[Dict[str, Any]],
) -> Dict[str, Any]:

    groups = [
        papers,
        filings,
        health_data,
        cms_data,
    ]

    populated_groups = sum(
        1
        for group in groups
        if group
    )

    source_diversity = min(
        populated_groups / 4,
        1.0,
    )

    total_items = sum(
        len(group)
        for group in groups
    )

    source_volume = min(
        total_items / 40,
        1.0,
    )

    citation_coverage = min(
        len(citations)
        / max(total_items, 1),
        1.0,
    )

    all_items = (
        papers
        + filings
        + health_data
        + cms_data
    )

    metadata_fields = 0
    metadata_present = 0

    for item in all_items:

        for field in (
            "title",
            "url",
            "date",
            "source",
        ):

            metadata_fields += 1

            if item.get(field):
                metadata_present += 1

    metadata_completeness = (
        metadata_present / metadata_fields
        if metadata_fields
        else 0.0
    )

    weighted_score = (
        source_diversity * 0.25
        + source_volume * 0.15
        + citation_coverage * 0.25
        + metadata_completeness * 0.20
        + source_diversity * 0.15
    )

    return {
        "score": round(
            weighted_score,
            4,
        ),
        "score_percent": round(
            weighted_score * 100,
            2,
        ),
        "interpretation": (
            "Provenance/source-coverage indicator only; "
            "not scientific validity, causal validity, "
            "or model accuracy."
        ),
    }


# ============================================================================
# EVIDENCE CONTEXT
# ============================================================================

def _build_evidence_context(
    evidence: Dict[str, Any],
) -> str:

    """
    Build evidence context without cutting a serialized JSON object
    in the middle.

    Sources are included individually so truncation never produces
    malformed JSON.
    """

    payload = {
        "statistics": evidence["statistics"],
        "quality": evidence["quality"],
        "source_registry": evidence["source_registry"],
    }

    blocks = [
        json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        )
    ]

    categories = [
        (
            "research_papers",
            evidence["research_papers"],
        ),
        (
            "regulatory_filings",
            evidence["regulatory_filings"],
        ),
        (
            "health_data",
            evidence["health_data"],
        ),
        (
            "cms_findings",
            evidence["cms_findings"],
        ),
    ]

    for category, records in categories:

        blocks.append(
            f"\n\n### {category}\n"
        )

        for record in records:

            serialized = json.dumps(
                record,
                ensure_ascii=False,
                default=str,
            )

            candidate = (
                "\n"
                + serialized
            )

            current_length = sum(
                len(block)
                for block in blocks
            )

            if (
                current_length
                + len(candidate)
                > MAX_EVIDENCE_CONTEXT_CHARS
            ):

                logger.warning(
                    "Evidence context limit reached."
                )

                return "".join(
                    blocks
                )

            blocks.append(
                candidate
            )

    return "".join(
        blocks
    )


# ============================================================================
# SOURCE REGISTRY FOR PROMPT
# ============================================================================

def _format_source_registry(
    source_registry: Dict[str, Any],
) -> str:

    if not source_registry:
        return "No verified sources available."

    lines = []

    for source_id, source in source_registry.items():

        lines.append(
            f"{source_id}: "
            f"{source.get('title', 'Untitled')} | "
            f"{source.get('source', 'Unknown')} | "
            f"{source.get('date', '')} | "
            f"{source.get('url', '')}"
        )

    return "\n".join(lines)


# ============================================================================
# RESEARCH DOCUMENT GENERATION
# ============================================================================

def _generate_research_document(
    run_id: str,
    question: str,
    plan: Dict[str, Any],
    evidence: Dict[str, Any],
) -> str:

    evidence_context = _build_evidence_context(
        evidence
    )

    sections = plan.get(
        "report_sections",
        DEFAULT_REPORT_SECTIONS,
    )

    if not isinstance(
        sections,
        list,
    ) or not sections:

        sections = DEFAULT_REPORT_SECTIONS

    sections_text = "\n".join(
        f"{index + 1}. {section}"
        for index, section in enumerate(
            sections
        )
    )

    metrics = plan.get(
        "metrics",
        [],
    )

    source_registry_text = _format_source_registry(
        evidence["source_registry"]
    )

    prompt = f"""
You are the Senior Research Scientist and Principal Research Writer
for CTS-NPN.

CTS-NPN combines:

USE CASE 7
Avoidable Emergency Department Utilization Navigator

with

USE CASE 12
Multi-Agent Research-to-Report Analyst Assistant.

Your task is to synthesize ONLY the evidence supplied below into a
professional research report.

You are NOT a search agent.

You are NOT allowed to invent evidence.

You are NOT allowed to browse for additional evidence.

You are NOT allowed to assume facts that are not contained in the
supplied evidence.

====================================================================
RESEARCH QUESTION
====================================================================

{question}

====================================================================
RUN ID
====================================================================

{run_id}

====================================================================
RESEARCH PLAN
====================================================================

{json.dumps(plan, indent=2, ensure_ascii=False, default=str)}

====================================================================
REQUIRED SECTIONS
====================================================================

{sections_text}

====================================================================
TARGET METRICS
====================================================================

{json.dumps(metrics, ensure_ascii=False, default=str)}

====================================================================
VERIFIED SOURCE REGISTRY
====================================================================

{source_registry_text}

IMPORTANT:
The source registry above is authoritative.

Only these source identifiers may be used:

{", ".join(evidence["source_registry"].keys()) or "NONE"}

Never create another source identifier.

====================================================================
EVIDENCE
====================================================================

{evidence_context}

====================================================================
STRICT EVIDENCE RULES
====================================================================

1. Use ONLY the supplied evidence.

2. Never invent:
   - statistics
   - percentages
   - rates
   - sample sizes
   - confidence intervals
   - p-values
   - effect sizes
   - financial estimates
   - prevalence
   - model accuracy
   - dataset coverage
   - causal relationships.

3. Every quantitative claim must be directly supported by supplied
   evidence.

4. When performing a calculation, both numerator and denominator must
   be explicitly available.

5. If a requested metric cannot be calculated, write:

   "Not estimable from the currently available evidence."

6. Never manufacture missing values.

7. Distinguish the following:

   OBSERVED
   Directly reported by the source.

   DERIVED
   Mathematically calculated from supplied observations.

   INTERPRETED
   Analytical interpretation of observed or derived evidence.

   RECOMMENDED
   Proposed operational action.

8. Do not convert correlation into causation.

9. Do not imply that an ED visit is medically unnecessary merely because
   another setting may be cheaper.

10. Genuine emergencies must never be discouraged, delayed, denied,
    or redirected solely for cost reasons.

11. Navigation opportunities must be framed as conditional alternatives
    for clinically appropriate circumstances.

12. Every material factual claim should contain a valid source identifier
    whenever the supplied evidence supports one.

13. Source identifiers MUST be selected only from the verified source
    registry.

14. Never write [S99], [S100], [S999], or any source ID not present in
    the registry.

15. Do not cite a source merely because it is topically related.

16. Do not fabricate citations.

17. If a statement is analytical interpretation rather than directly
    observed evidence, clearly label it as interpretation.

18. Avoid unsupported certainty.

Do not use phrases such as:

   "studies prove"
   "research proves"
   "definitively"
   "guarantees"
   "always"
   "never"

unless the supplied evidence itself genuinely establishes the statement.

====================================================================
SOURCE-SPECIFIC RULES
====================================================================

RESEARCH PAPERS

When available, discuss:

- research question
- study design
- population
- dataset
- principal finding
- limitations
- relevance to CTS-NPN

CMS

When available, identify:

- CMS dataset
- performance period
- population/unit
- measured variable
- observed finding
- analytical relevance
- limitations

CDC

When available, identify:

- indicator
- geography
- measurement period
- observed value
- interpretation
- limitation

SEC EDGAR

Use SEC evidence only when it materially contributes to the research
question.

Do NOT force SEC evidence into a healthcare-utilization analysis merely
because SEC data exists.

====================================================================
QUANTITATIVE REPORTING
====================================================================

When sufficient numerical data exist:

Numerator:
...

Denominator:
...

Unit:
...

Period:
...

Formula:
...

Result:
...

Only calculate values when the required inputs are explicitly present.

====================================================================
NAVIGATION SAFETY
====================================================================

The report must never recommend denying emergency care.

Use language such as:

"when clinically appropriate"

"for non-emergent circumstances"

"subject to clinical assessment"

"as an alternative navigation option"

"where symptoms do not indicate an emergency"

Do not use:

"avoid the emergency department"

"prevent the patient from going to the ED"

"deny ED access"

"block emergency visits"

====================================================================
OUTPUT
====================================================================

Return ONLY Markdown.

Use exactly:

# CTS-NPN Research Report

## Executive Summary

## Research Question and Scope

## Methodology

## Evidence Base

## Research Findings

## CMS Findings

## ED Utilization Interpretation

## Navigation Opportunities

## Quantitative Metrics

## Limitations

## Conclusion

## References

## Report Metadata

The References section MUST use the exact verified source identifiers
from the registry.

Example:

[S1] Source title — Source organization — Date — URL

Do not create new source IDs.

The Report Metadata section MUST contain:

- Run ID
- Generation timestamp
- Evidence item count
- Research paper count
- CMS record count
- CDC/health record count
- SEC filing count
- Citation count
- Evidence coverage score

The evidence coverage score is only a provenance/source-coverage
indicator. It is NOT scientific validity, causal validity, or model
accuracy.

====================================================================
BEGIN SYNTHESIS
====================================================================
"""

    raw = bedrock(
        prompt,
        max_tokens=7000,
        temperature=0.10,
    )

    document = str(
        raw or ""
    ).strip()

    if not document:

        raise RuntimeError(
            "Bedrock returned an empty research document."
        )

    document = _strip_markdown_code_fence(
        document
    )

    document = _repair_report_structure(
        document,
        run_id,
        evidence,
    )

    # ----------------------------------------------------------------------
    # Deterministic citation repair
    # ----------------------------------------------------------------------

    document = _validate_and_repair_citation_ids(
        document,
        evidence,
    )

    return document


# ============================================================================
# MARKDOWN CLEANING
# ============================================================================

def _strip_markdown_code_fence(
    document: str,
) -> str:

    document = document.strip()

    document = re.sub(
        r"^```(?:markdown|md)?\s*",
        "",
        document,
        flags=re.IGNORECASE,
    )

    document = re.sub(
        r"\s*```\s*$",
        "",
        document,
    )

    return document.strip()


# ============================================================================
# REPORT STRUCTURE REPAIR
# ============================================================================

def _repair_report_structure(
    report: str,
    run_id: str,
    evidence: Dict[str, Any],
) -> str:

    report = report.strip()

    if not report.startswith(
        "# CTS-NPN Research Report"
    ):

        report = (
            "# CTS-NPN Research Report\n\n"
            + report
        )

    if "## References" not in report:

        report += (
            "\n\n## References\n\n"
        )

        report += _format_source_reference_block(
            evidence.get(
                "citations",
                [],
            )
        )

    if "## Report Metadata" not in report:

        stats = evidence["statistics"]

        report += f"""

## Report Metadata

- **Run ID:** {run_id}
- **Generation timestamp:** {_utc_now()}
- **Evidence item count:** {stats["total_evidence_items"]}
- **Research paper count:** {stats["research_papers"]}
- **CMS record count:** {stats["cms_records"]}
- **CDC/health record count:** {stats["health_data_records"]}
- **SEC filing count:** {stats["regulatory_filings"]}
- **Citation count:** {stats["citations"]}
- **Evidence coverage score:** {evidence["quality"]["score_percent"]:.2f}%

The evidence coverage score is a provenance and source-coverage indicator.
It is not a measure of scientific truth, causal validity, or model accuracy.
"""

    return report.strip()


# ============================================================================
# CITATION VALIDATION
# ============================================================================

def _validate_and_repair_citation_ids(
    report: str,
    evidence: Dict[str, Any],
) -> str:

    valid_ids = set(
        evidence.get(
            "source_registry",
            {},
        ).keys()
    )

    if not valid_ids:

        return re.sub(
            r"\[S\d+\]",
            "",
            report,
        )

    # ----------------------------------------------------------------------
    # Remove invalid citation identifiers.
    # ----------------------------------------------------------------------

    def replace_invalid(
        match: re.Match,
    ) -> str:

        marker = match.group(0)

        if marker in valid_ids:
            return marker

        logger.warning(
            "Removing invalid citation marker: %s",
            marker,
        )

        return ""

    report = re.sub(
        r"\[S\d+\]",
        replace_invalid,
        report,
    )

    return report


# ============================================================================
# REFERENCES
# ============================================================================

def _format_source_reference_block(
    citations: List[Dict[str, Any]],
) -> str:

    lines = []

    for index, citation in enumerate(
        citations[:MAX_SOURCES],
        start=1,
    ):

        source_id = f"S{index}"

        title = citation.get(
            "title",
            "Untitled source",
        )

        source = citation.get(
            "source",
            "Unknown source",
        )

        date = citation.get(
            "date",
            "",
        )

        url = citation.get(
            "url",
            "",
        )

        authors = citation.get(
            "authors",
            [],
        )

        if isinstance(
            authors,
            list,
        ):

            author_text = ", ".join(
                str(author)
                for author in authors[:5]
            )

        else:

            author_text = str(
                authors or ""
            )

        line = (
            f"[{source_id}] "
            f"**{title}** — {source}"
        )

        if author_text:

            line += (
                f". Authors: {author_text}"
            )

        if date:

            line += (
                f". Date: {date}"
            )

        if url:

            line += (
                f". {url}"
            )

        lines.append(line)

    if not lines:

        return (
            "No verified sources were available."
        )

    return "\n\n".join(
        lines
    )


# ============================================================================
# DOCUMENT VALIDATION
# ============================================================================

def _validate_generated_document(
    report: str,
    evidence: Dict[str, Any],
) -> Dict[str, Any]:

    checks = []
    valid = True

    # ----------------------------------------------------------------------
    # Length
    # ----------------------------------------------------------------------

    if len(report) >= 1200:

        checks.append(
            "Research document length is acceptable."
        )

    else:

        valid = False

        checks.append(
            "Research document is unexpectedly short."
        )

    # ----------------------------------------------------------------------
    # Required sections
    # ----------------------------------------------------------------------

    required_sections = [
        "## Executive Summary",
        "## Research Question and Scope",
        "## Methodology",
        "## Evidence Base",
        "## Research Findings",
        "## CMS Findings",
        "## ED Utilization Interpretation",
        "## Navigation Opportunities",
        "## Quantitative Metrics",
        "## Limitations",
        "## Conclusion",
        "## References",
        "## Report Metadata",
    ]

    for section in required_sections:

        if section in report:

            checks.append(
                f"Required section present: {section}"
            )

        else:

            valid = False

            checks.append(
                f"Missing required section: {section}"
            )

    # ----------------------------------------------------------------------
    # Citation validation
    # ----------------------------------------------------------------------

    source_registry = evidence.get(
        "source_registry",
        {},
    )

    valid_ids = set(
        source_registry.keys()
    )

    markers = re.findall(
        r"\[S\d+\]",
        report,
    )

    invalid_markers = [
        marker
        for marker in markers
        if marker not in valid_ids
    ]

    if invalid_markers:

        valid = False

        checks.append(
            "Invalid citation identifiers: "
            + ", ".join(
                sorted(
                    set(
                        invalid_markers
                    )
                )
            )
        )

    else:

        checks.append(
            "All citation identifiers are valid."
        )

    unique_markers = set(
        markers
    )

    if valid_ids:

        if unique_markers:

            checks.append(
                f"Valid citation markers used: "
                f"{len(unique_markers)}"
            )

        else:

            valid = False

            checks.append(
                "No citation markers detected."
            )

    else:

        checks.append(
            "No verified source registry available."
        )

    # ----------------------------------------------------------------------
    # Over-certainty
    # ----------------------------------------------------------------------

    unsupported_terms = [
        "proves",
        "guarantees",
        "definitively",
        "100% accurate",
        "always",
        "never",
    ]

    found = []

    lower_report = report.lower()

    for term in unsupported_terms:

        if term in lower_report:

            found.append(
                term
            )

    if found:

        checks.append(
            "Potentially over-strong language detected: "
            + ", ".join(found)
        )

    else:

        checks.append(
            "No obvious over-certainty terms detected."
        )

    return {
        "valid": valid,
        "checks": checks,
        "citation_markers": len(markers),
        "unique_citation_markers": len(
            unique_markers
        ),
        "verified_sources": len(
            valid_ids
        ),
        "invalid_citation_markers": sorted(
            set(
                invalid_markers
            )
        ),
    }


# ============================================================================
# TEMPLATE PDF
# ============================================================================

def _load_template_pdf() -> bytes:

    checked = []

    for path in DEFAULT_TEMPLATE_PATHS:

        if not path:
            continue

        normalized = os.path.abspath(
            path
        )

        checked.append(
            normalized
        )

        if os.path.isfile(
            normalized
        ):

            logger.info(
                "Using report template: %s",
                normalized,
            )

            with open(
                normalized,
                "rb",
            ) as fh:

                return fh.read()

    # ----------------------------------------------------------------------
    # S3 fallback
    # ----------------------------------------------------------------------

    if TEMPLATE_S3_BUCKET:

        try:

            logger.info(
                "Loading template from s3://%s/%s",
                TEMPLATE_S3_BUCKET,
                TEMPLATE_S3_KEY,
            )

            response = s3_client.get_object(
                Bucket=TEMPLATE_S3_BUCKET,
                Key=TEMPLATE_S3_KEY,
            )

            return response["Body"].read()

        except Exception as exc:

            logger.warning(
                "Unable to load S3 template: %s",
                exc,
            )

    raise FileNotFoundError(
        "report_template.pdf was not found. "
        "Checked: "
        + ", ".join(checked)
        + ". Configure REPORT_TEMPLATE_PATH or "
          "REPORT_TEMPLATE_S3_BUCKET + "
          "REPORT_TEMPLATE_S3_KEY."
    )


# ============================================================================
# PDF RENDERING
# ============================================================================

def _render_report_pdf(
    markdown_report: str,
    run_id: str,
    evidence: Dict[str, Any],
) -> Tuple[bytes, Dict[str, Any]]:

    template_bytes = _load_template_pdf()

    template_reader = PdfReader(
        io.BytesIO(
            template_bytes
        )
    )

    if not template_reader.pages:

        raise RuntimeError(
            "report_template.pdf contains no pages."
        )

    template_page = template_reader.pages[0]

    page_width = float(
        template_page.mediabox.width
    )

    page_height = float(
        template_page.mediabox.height
    )

    overlay_bytes = _build_pdf_overlay(
        markdown_report,
        run_id,
        evidence,
        page_width,
        page_height,
    )

    overlay_reader = PdfReader(
        io.BytesIO(
            overlay_bytes
        )
    )

    if not overlay_reader.pages:

        raise RuntimeError(
            "Generated PDF overlay contains no pages."
        )

    writer = PdfWriter()

    # ----------------------------------------------------------------------
    # Every generated page receives the template background.
    # ----------------------------------------------------------------------

    for generated_page in overlay_reader.pages:

        background_reader = PdfReader(
            io.BytesIO(
                template_bytes
            )
        )

        background = background_reader.pages[0]

        generated_page.mediabox = (
            background.mediabox
        )

        background.merge_page(
            generated_page
        )

        writer.add_page(
            background
        )

    output = io.BytesIO()

    writer.write(
        output
    )

    pdf_bytes = output.getvalue()

    metadata = {
        "template": "report_template.pdf",
        "template_pages": len(
            template_reader.pages
        ),
        "generated_pages": len(
            overlay_reader.pages
        ),
        "page_width_points": page_width,
        "page_height_points": page_height,
        "margin_left_points": MARGIN_LEFT,
        "margin_right_points": MARGIN_RIGHT,
        "margin_top_points": MARGIN_TOP,
        "margin_bottom_points": MARGIN_BOTTOM,
        "bytes": len(pdf_bytes),
    }

    return (
        pdf_bytes,
        metadata,
    )


# ============================================================================
# PDF OVERLAY
# ============================================================================

def _build_pdf_overlay(
    markdown_report: str,
    run_id: str,
    evidence: Dict[str, Any],
    page_width: float,
    page_height: float,
) -> bytes:

    buffer = io.BytesIO()

    frame_width = (
        page_width
        - MARGIN_LEFT
        - MARGIN_RIGHT
    )

    frame_height = (
        page_height
        - MARGIN_TOP
        - MARGIN_BOTTOM
    )

    if frame_width <= 100:

        raise RuntimeError(
            "Configured PDF margins leave insufficient "
            "horizontal space."
        )

    if frame_height <= 100:

        raise RuntimeError(
            "Configured PDF margins leave insufficient "
            "vertical space."
        )

    styles = _build_pdf_styles()

    story = _markdown_to_story(
        markdown_report,
        styles,
        frame_width,
    )

    if not story:

        raise RuntimeError(
            "Unable to convert Markdown into PDF content."
        )

    doc = BaseDocTemplate(
        buffer,
        pagesize=(
            page_width,
            page_height,
        ),
        leftMargin=MARGIN_LEFT,
        rightMargin=MARGIN_RIGHT,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title="CTS-NPN Research Report",
        author="CTS-NPN Research Synthesis Agent",
        subject="Evidence-based research report",
    )

    frame = Frame(
        MARGIN_LEFT,
        MARGIN_BOTTOM,
        frame_width,
        frame_height,
        id="main",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )

    page_template = PageTemplate(
        id="research",
        frames=[frame],
    )

    doc.addPageTemplates(
        [page_template]
    )

    doc.build(
        story
    )

    return buffer.getvalue()


# ============================================================================
# PDF STYLES
# ============================================================================

def _build_pdf_styles():

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="CTS_Title",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=12,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="CTS_H1",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            alignment=TA_LEFT,
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="CTS_H2",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=14,
            alignment=TA_LEFT,
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="CTS_Body",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=12.4,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
            splitLongWords=False,
        )
    )

    styles.add(
        ParagraphStyle(
            name="CTS_Bullet",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.0,
            leading=12,
            leftIndent=12,
            firstLineIndent=-7,
            spaceAfter=3,
        )
    )

    styles.add(
        ParagraphStyle(
            name="CTS_Metadata",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9.5,
            alignment=TA_LEFT,
            spaceAfter=2,
        )
    )

    styles.add(
        ParagraphStyle(
            name="CTS_Reference",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7.7,
            leading=10,
            alignment=TA_LEFT,
            spaceAfter=4,
        )
    )

    styles.add(
        ParagraphStyle(
            name="CTS_Table",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9,
            alignment=TA_LEFT,
        )
    )

    return styles


# ============================================================================
# MARKDOWN → REPORTLAB
# ============================================================================

def _markdown_to_story(
    markdown: str,
    styles,
    frame_width: float,
):

    story = []

    lines = (
        markdown
        .replace(
            "\r\n",
            "\n",
        )
        .replace(
            "\r",
            "\n",
        )
        .split("\n")
    )

    paragraph_buffer = []

    def flush_paragraph():

        nonlocal paragraph_buffer

        if not paragraph_buffer:
            return

        text = " ".join(
            line.strip()
            for line in paragraph_buffer
            if line.strip()
        ).strip()

        paragraph_buffer = []

        if not text:
            return

        story.append(
            Paragraph(
                _escape_and_format_inline(
                    text
                ),
                styles["CTS_Body"],
            )
        )

    index = 0

    while index < len(lines):

        raw_line = lines[index]
        line = raw_line.strip()

        # ------------------------------------------------------------------
        # Empty
        # ------------------------------------------------------------------

        if not line:

            flush_paragraph()

            if story:

                story.append(
                    Spacer(
                        1,
                        3,
                    )
                )

            index += 1
            continue

        # ------------------------------------------------------------------
        # H4
        # ------------------------------------------------------------------

        if line.startswith("#### "):

            flush_paragraph()

            heading = line[5:].strip()

            story.append(
                Paragraph(
                    _escape_and_format_inline(
                        heading
                    ),
                    styles["CTS_H2"],
                )
            )

            index += 1
            continue

        # ------------------------------------------------------------------
        # H3
        # ------------------------------------------------------------------

        if line.startswith("### "):

            flush_paragraph()

            heading = line[4:].strip()

            story.append(
                Paragraph(
                    _escape_and_format_inline(
                        heading
                    ),
                    styles["CTS_H2"],
                )
            )

            index += 1
            continue

        # ------------------------------------------------------------------
        # H2
        # ------------------------------------------------------------------

        if line.startswith("## "):

            flush_paragraph()

            heading = line[3:].strip()

            story.append(
                Paragraph(
                    _escape_and_format_inline(
                        heading
                    ),
                    styles["CTS_H1"],
                )
            )

            index += 1
            continue

        # ------------------------------------------------------------------
        # H1
        # ------------------------------------------------------------------

        if line.startswith("# "):

            flush_paragraph()

            title = line[2:].strip()

            story.append(
                Paragraph(
                    _escape_and_format_inline(
                        title
                    ),
                    styles["CTS_Title"],
                )
            )

            index += 1
            continue

        # ------------------------------------------------------------------
        # Horizontal rule
        # ------------------------------------------------------------------

        if line in (
            "---",
            "***",
            "___",
        ):

            flush_paragraph()

            story.append(
                HRFlowable(
                    width="100%",
                    thickness=0.5,
                    spaceBefore=4,
                    spaceAfter=6,
                )
            )

            index += 1
            continue

        # ------------------------------------------------------------------
        # Markdown table
        # ------------------------------------------------------------------

        if (
            "|" in line
            and index + 1 < len(lines)
        ):

            next_line = lines[
                index + 1
            ].strip()

            if (
                "|" in next_line
                and re.search(
                    r"-{3,}",
                    next_line,
                )
            ):

                flush_paragraph()

                table_lines = []

                while (
                    index < len(lines)
                    and "|" in lines[index]
                ):

                    table_lines.append(
                        lines[index].strip()
                    )

                    index += 1

                table = _build_table(
                    table_lines,
                    styles,
                    frame_width,
                )

                if table is not None:

                    story.append(
                        table
                    )

                continue

        # ------------------------------------------------------------------
        # Bullet
        # ------------------------------------------------------------------

        if re.match(
            r"^[-*+]\s+",
            line,
        ):

            flush_paragraph()

            bullet_text = re.sub(
                r"^[-*+]\s+",
                "",
                line,
            ).strip()

            story.append(
                Paragraph(
                    "• "
                    + _escape_and_format_inline(
                        bullet_text
                    ),
                    styles["CTS_Bullet"],
                )
            )

            index += 1
            continue

        # ------------------------------------------------------------------
        # Numbered list
        # ------------------------------------------------------------------

        numbered = re.match(
            r"^(\d+)\.\s+(.+)$",
            line,
        )

        if numbered:

            flush_paragraph()

            number = numbered.group(1)
            text = numbered.group(2)

            story.append(
                Paragraph(
                    f"{number}. "
                    + _escape_and_format_inline(
                        text
                    ),
                    styles["CTS_Bullet"],
                )
            )

            index += 1
            continue

        # ------------------------------------------------------------------
        # References
        # ------------------------------------------------------------------

        if re.match(
            r"^\[S\d+\]",
            line,
        ):

            flush_paragraph()

            story.append(
                Paragraph(
                    _escape_and_format_inline(
                        line
                    ),
                    styles["CTS_Reference"],
                )
            )

            index += 1
            continue

        # ------------------------------------------------------------------
        # Metadata
        # ------------------------------------------------------------------

        if (
            line.startswith("**")
            and line.endswith("**")
        ):

            flush_paragraph()

            story.append(
                Paragraph(
                    _escape_and_format_inline(
                        line
                    ),
                    styles["CTS_Metadata"],
                )
            )

            index += 1
            continue

        # ------------------------------------------------------------------
        # Normal prose
        # ------------------------------------------------------------------

        paragraph_buffer.append(
            line
        )

        index += 1

    flush_paragraph()

    return story


# ============================================================================
# TABLE SUPPORT
# ============================================================================

def _build_table(
    lines: List[str],
    styles,
    frame_width: float,
):

    rows = []

    for line in lines:

        stripped = (
            line
            .strip()
            .strip("|")
        )

        cells = [
            cell.strip()
            for cell in stripped.split("|")
        ]

        # Skip Markdown separator.
        if all(
            re.fullmatch(
                r":?-+:?",
                cell,
            )
            for cell in cells
        ):
            continue

        rows.append(
            [
                Paragraph(
                    _escape_and_format_inline(
                        cell
                    ),
                    styles["CTS_Table"],
                )
                for cell in cells
            ]
        )

    if not rows:
        return None

    column_count = max(
        len(row)
        for row in rows
    )

    normalized_rows = []

    for row in rows:

        while len(row) < column_count:

            row.append(
                Paragraph(
                    "",
                    styles["CTS_Table"],
                )
            )

        normalized_rows.append(
            row
        )

    column_width = (
        frame_width
        / column_count
    )

    table = Table(
        normalized_rows,
        colWidths=[
            column_width
        ] * column_count,
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=True,
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    None,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    3,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    3,
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold",
                ),
            ]
        )
    )

    return table


# ============================================================================
# INLINE MARKDOWN
# ============================================================================

def _escape_and_format_inline(
    text: str,
) -> str:

    text = str(
        text or ""
    )

    # XML escaping required by ReportLab.
    text = (
        text
        .replace(
            "&",
            "&amp;",
        )
        .replace(
            "<",
            "&lt;",
        )
        .replace(
            ">",
            "&gt;",
        )
    )

    # Bold
    text = re.sub(
        r"\*\*(.+?)\*\*",
        r"<b>\1</b>",
        text,
    )

    # Italic
    text = re.sub(
        r"(?<!\*)\*([^*]+?)\*(?!\*)",
        r"<i>\1</i>",
        text,
    )

    # Inline code
    text = re.sub(
        r"`(.+?)`",
        r"<font name='Courier'>\1</font>",
        text,
    )

    # Markdown links
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r"<link href='\2' color='blue'>\1</link>",
        text,
    )

    # Plain URLs
    text = re.sub(
        r"(?<![\"'=])(https?://[^\s<]+)",
        r"<link href='\1' color='blue'>\1</link>",
        text,
    )

    return text


# ============================================================================
# UTILITY
# ============================================================================

def _utc_now() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()