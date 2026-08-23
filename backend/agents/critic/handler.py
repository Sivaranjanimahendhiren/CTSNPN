"""
CTS-NPN Research Critic Agent
=============================

Purpose
-------
Independent quality-assurance and peer-review gate for the
CTS-NPN research-to-report pipeline.

This agent does NOT rewrite the research report.
It evaluates whether the generated report is:

1. Structurally complete
2. Evidence-grounded
3. Citation-complete
4. Citation-consistent
5. Methodologically transparent
6. Numerically responsible
7. Appropriately qualified
8. Safe for healthcare research communication
9. Free from obvious unsupported claims
10. Suitable for publication or downstream rendering
"""

import json
import re
from collections import Counter
from urllib.parse import urlparse

from backend.common.aws import put_text, update_run
from backend.common.config import REPORTS_BUCKET
from backend.common.security import validate_content, validate_citations
from backend.common.citations import extract_citations_from_text


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

MIN_REPORT_LENGTH = 900
MIN_CITATIONS = 3

REQUIRED_RESEARCH_CONCEPTS = {
    "executive_summary": [
        "executive summary",
        "summary",
        "abstract",
        "overview",
    ],
    "research_question": [
        "research question",
        "objective",
        "purpose",
        "research objective",
    ],
    "methodology": [
        "methodology",
        "methods",
        "approach",
        "research method",
    ],
    "evidence": [
        "evidence",
        "findings",
        "results",
        "analysis",
    ],
    "limitations": [
        "limitations",
        "limitation",
        "caveats",
        "constraints",
    ],
    "references": [
        "references",
        "sources",
        "bibliography",
    ],
}

# Domains particularly useful for CTS-NPN Use Case 7 + 12.
TRUSTED_RESEARCH_DOMAINS = {
    "arxiv.org",
    "sec.gov",
    "data.cms.gov",
    "cms.gov",
    "cdc.gov",
    "nih.gov",
    "ncbi.nlm.nih.gov",
    "pubmed.ncbi.nlm.nih.gov",
    "hhs.gov",
    "healthcare.gov",
    "medicare.gov",
}

SUPPORTED_URL_SCHEMES = {"http", "https"}

UNCERTAINTY_TERMS = [
    "may",
    "might",
    "could",
    "suggests",
    "suggest",
    "associated with",
    "potentially",
    "likely",
    "possibly",
    "evidence indicates",
    "evidence suggests",
    "appears",
    "preliminary",
    "cannot establish causality",
    "observational",
    "limited evidence",
]

ABSOLUTE_TERMS = [
    "always",
    "never",
    "all",
    "none",
    "guaranteed",
    "proves",
    "definitively",
    "certainly",
    "obviously",
]

# These represent individualized medical instructions rather than
# legitimate research discussion.
DIRECT_MEDICAL_ADVICE_PATTERNS = [
    r"\byou should take\b",
    r"\byou should start\b",
    r"\byou should stop\b",
    r"\byou need to take\b",
    r"\byou need treatment\b",
    r"\bseek treatment immediately\b",
    r"\bchange your medication\b",
    r"\bstop taking your medication\b",
    r"\bstart taking\b",
    r"\bprescribe\b",
    r"\bprescription for you\b",
    r"\bdiagnose you\b",
    r"\byour diagnosis is\b",
]

SUSPICIOUS_CITATION_PATTERNS = [
    r"source:\s*none",
    r"citation:\s*none",
    r"according to an unnamed",
    r"according to a confidential",
    r"internal source",
    r"private database",
]

# Quantitative claims that should normally have evidence nearby.
NUMERIC_CLAIM_PATTERN = re.compile(
    r"""
    (
        \b\d+(?:\.\d+)?\s*%
        |
        \$\s?\d+(?:,\d{3})*(?:\.\d+)?
        |
        \b\d+(?:\.\d+)?\s*(?:million|billion|thousand)
        |
        \b\d+(?:\.\d+)?\s*(?:days?|years?|months?)
        |
        \b\d+(?:\.\d+)?\s*(?:patients?|members?|visits?|claims?)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


# ---------------------------------------------------------------------------
# MAIN LAMBDA ENTRYPOINT
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    Execute the independent research-quality review.

    The function is intentionally defensive so the Critic can still
    return a useful validation result when upstream agents provide
    incomplete data.
    """

    event = event or {}
    run_id = str(event.get("run_id", "unknown"))

    try:
        update_run(run_id, "CRITIQUING")

        report = _extract_report(event)
        citations = _extract_citations(event, report)
        evidence = _extract_evidence(event)
        metadata = _extract_metadata(event)

        # ---------------------------------------------------------------
        # Execute independent validation dimensions.
        # ---------------------------------------------------------------

        content_validation = _validate_report_content(report)

        citation_validation = _validate_citations_quality(
            citations=citations,
            report=report,
        )

        evidence_validation = _validate_evidence_grounding(
            report=report,
            citations=citations,
            evidence=evidence,
        )

        methodology_validation = _validate_methodology(
            report=report,
        )

        safety_check = _safety_check(
            report=report,
        )

        research_integrity = _validate_research_integrity(
            report=report,
            citations=citations,
            evidence=evidence,
        )

        numerical_validation = _validate_numerical_claims(
            report=report,
            citations=citations,
        )

        # ---------------------------------------------------------------
        # Calculate weighted quality score.
        # ---------------------------------------------------------------

        quality_score = _calculate_quality_score(
            content_validation,
            citation_validation,
            evidence_validation,
            methodology_validation,
            safety_check,
            research_integrity,
            numerical_validation,
        )

        # ---------------------------------------------------------------
        # Determine publication status.
        # ---------------------------------------------------------------

        overall_status = _determine_status(
            quality_score=quality_score,
            content_validation=content_validation,
            citation_validation=citation_validation,
            evidence_validation=evidence_validation,
            methodology_validation=methodology_validation,
            safety_check=safety_check,
            research_integrity=research_integrity,
        )

        revision_required = _collect_revision_requirements(
            content_validation,
            citation_validation,
            evidence_validation,
            methodology_validation,
            safety_check,
            research_integrity,
            numerical_validation,
        )

        critique = _generate_professional_critique(
            run_id=run_id,
            status=overall_status,
            quality_score=quality_score,
            content_validation=content_validation,
            citation_validation=citation_validation,
            evidence_validation=evidence_validation,
            methodology_validation=methodology_validation,
            safety_check=safety_check,
            research_integrity=research_integrity,
            numerical_validation=numerical_validation,
            revision_required=revision_required,
        )

        validation_results = {
            "run_id": run_id,
            "review_version": "2.0",
            "review_type": "independent_research_quality_assurance",
            "overall_status": overall_status,
            "quality_score": quality_score,
            "content_validation": content_validation,
            "citation_validation": citation_validation,
            "evidence_validation": evidence_validation,
            "methodology_validation": methodology_validation,
            "safety_check": safety_check,
            "research_integrity": research_integrity,
            "numerical_validation": numerical_validation,
            "revision_required": revision_required,
            "critique": critique,
            "review_metadata": {
                "citation_count": len(citations),
                "evidence_item_count": len(evidence),
                "report_characters": len(report),
                "report_words": len(report.split()),
                "trusted_domain_count": _count_trusted_domains(citations),
                "absolute_language_count": _count_terms(
                    report,
                    ABSOLUTE_TERMS,
                ),
                "uncertainty_language_count": _count_terms(
                    report,
                    UNCERTAINTY_TERMS,
                ),
                "metadata_received": bool(metadata),
            },
        }

        # ---------------------------------------------------------------
        # Persist complete peer-review result.
        # ---------------------------------------------------------------

        if REPORTS_BUCKET:
            put_text(
                REPORTS_BUCKET,
                f"{run_id}/validation_results.json",
                json.dumps(
                    validation_results,
                    indent=2,
                    ensure_ascii=False,
                ),
            )

            put_text(
                REPORTS_BUCKET,
                f"{run_id}/research_critique.md",
                critique,
            )

        update_run(
            run_id,
            "CRITIC_COMPLETE",
            validation_status=overall_status,
            quality_score=quality_score,
        )

        return {
            "run_id": run_id,
            "status": "COMPLETE",
            "validation": validation_results,
            "approved": overall_status == "APPROVED",
        }

    except Exception as exc:
        error_msg = f"Critic agent error: {str(exc)}"

        print(error_msg)

        try:
            update_run(
                run_id,
                "CRITIC_FAILED",
                error=error_msg,
            )
        except Exception:
            pass

        return {
            "run_id": run_id,
            "status": "FAILED",
            "error": error_msg,
            "approved": False,
        }


# ---------------------------------------------------------------------------
# INPUT EXTRACTION
# ---------------------------------------------------------------------------

def _extract_report(event):
    """
    Extract report text from multiple compatible upstream formats.
    """

    candidates = [
        event.get("report"),
        event.get("final_report"),
        event.get("synthesized_report"),
    ]

    synthesis = event.get("synthesis")

    if isinstance(synthesis, dict):
        candidates.extend(
            [
                synthesis.get("report"),
                synthesis.get("final_report"),
                synthesis.get("content"),
                synthesis.get("text"),
            ]
        )

    elif isinstance(synthesis, str):
        candidates.append(synthesis)

    results = event.get("results")

    if isinstance(results, dict):
        candidates.extend(
            [
                results.get("report"),
                results.get("final_report"),
                results.get("content"),
            ]
        )

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    return ""


def _extract_citations(event, report):
    """
    Extract citations from upstream agents.

    If explicit citations are missing, attempt to recover citations
    directly from the report.
    """

    citations = event.get("citations", [])

    if not citations:
        evidence = event.get("evidence", [])

        if isinstance(evidence, dict):
            citations = evidence.get("citations", [])

    if not citations:
        synthesis = event.get("synthesis")

        if isinstance(synthesis, dict):
            citations = synthesis.get("citations", [])

    if isinstance(citations, list) and citations:
        return citations

    # Last-resort citation extraction.
    try:
        extracted = extract_citations_from_text(report)

        if isinstance(extracted, list):
            return extracted

    except Exception as exc:
        print(f"Citation extraction warning: {exc}")

    return []


def _extract_evidence(event):
    """
    Extract evidence records from upstream agents.
    """

    evidence = event.get("evidence", [])

    if isinstance(evidence, dict):
        evidence = evidence.get(
            "items",
            evidence.get("evidence", []),
        )

    if not evidence:
        synthesis = event.get("synthesis")

        if isinstance(synthesis, dict):
            evidence = synthesis.get("evidence", [])

    return evidence if isinstance(evidence, list) else []


def _extract_metadata(event):
    metadata = event.get("metadata", {})

    if isinstance(metadata, dict):
        return metadata

    return {}


# ---------------------------------------------------------------------------
# CONTENT QUALITY
# ---------------------------------------------------------------------------

def _validate_report_content(report):
    """
    Validate structural and editorial completeness.
    """

    results = {
        "valid": True,
        "checks": [],
        "missing_concepts": [],
    }

    if not report:
        results["valid"] = False
        results["checks"].append(
            "CRITICAL: No report content was supplied."
        )
        return results

    report_lower = report.lower()

    # Length
    if len(report) < MIN_REPORT_LENGTH:
        results["valid"] = False
        results["checks"].append(
            f"Report is too short ({len(report)} characters; "
            f"minimum {MIN_REPORT_LENGTH})."
        )
    else:
        results["checks"].append(
            f"Report length acceptable ({len(report)} characters)."
        )

    # Word count
    word_count = len(report.split())

    if word_count < 150:
        results["valid"] = False
        results["checks"].append(
            f"Report contains only {word_count} words."
        )
    else:
        results["checks"].append(
            f"Report contains approximately {word_count} words."
        )

    # Research concepts
    for concept, variants in REQUIRED_RESEARCH_CONCEPTS.items():

        if any(variant in report_lower for variant in variants):

            results["checks"].append(
                f"Research component present: "
                f"{concept.replace('_', ' ')}."
            )

        else:

            results["valid"] = False

            results["missing_concepts"].append(
                concept
            )

            results["checks"].append(
                f"Missing research component: "
                f"{concept.replace('_', ' ')}."
            )

    # Markdown heading check
    headings = re.findall(
        r"(?m)^\s{0,3}#{1,6}\s+.+$",
        report,
    )

    if len(headings) >= 4:

        results["checks"].append(
            f"Professional section structure detected "
            f"({len(headings)} headings)."
        )

    else:

        results["checks"].append(
            "Limited section structure detected."
        )

    # Metadata
    if "metadata" in report_lower:

        results["checks"].append(
            "Metadata section detected."
        )

    else:

        results["checks"].append(
            "Metadata section not explicitly detected."
        )

    # Existing security helper
    try:

        validate_content(report)

        results["checks"].append(
            "Security/content screening passed."
        )

    except ValueError as exc:

        results["valid"] = False

        results["checks"].append(
            f"Security/content screening issue: {str(exc)}"
        )

    return results


# ---------------------------------------------------------------------------
# CITATION QUALITY
# ---------------------------------------------------------------------------

def _validate_citations_quality(citations, report):
    """
    Perform professional citation QA.
    """

    results = {
        "valid": True,
        "checks": [],
        "citation_count": len(citations),
        "invalid_citations": [],
        "duplicate_citations": [],
        "domains": [],
        "trusted_domains": [],
    }

    # Minimum citation count
    if len(citations) < MIN_CITATIONS:

        results["valid"] = False

        results["checks"].append(
            f"Insufficient citations ({len(citations)}; "
            f"minimum {MIN_CITATIONS})."
        )

    else:

        results["checks"].append(
            f"Citation count acceptable ({len(citations)})."
        )

    # Existing project validation
    try:

        validate_citations(citations)

        results["checks"].append(
            "Citation schema validation passed."
        )

    except ValueError as exc:

        results["valid"] = False

        results["checks"].append(
            f"Citation schema validation failed: {str(exc)}"
        )

    urls = []

    for index, citation in enumerate(citations):

        if not isinstance(citation, dict):

            results["valid"] = False

            results["invalid_citations"].append(index)

            results["checks"].append(
                f"Citation {index + 1} is not a structured object."
            )

            continue

        url = str(
            citation.get("url", "")
        ).strip()

        if not url:

            results["valid"] = False

            results["invalid_citations"].append(index)

            results["checks"].append(
                f"Citation {index + 1} has no URL."
            )

            continue

        urls.append(url)

        parsed = urlparse(url)

        if (
            parsed.scheme.lower() not in SUPPORTED_URL_SCHEMES
            or not parsed.netloc
        ):

            results["valid"] = False

            results["invalid_citations"].append(index)

            results["checks"].append(
                f"Citation {index + 1} contains an invalid URL."
            )

            continue

        domain = _normalize_domain(parsed.netloc)

        results["domains"].append(domain)

    # Duplicate URLs
    duplicate_urls = [
        url
        for url, count in Counter(urls).items()
        if count > 1
    ]

    if duplicate_urls:

        results["duplicate_citations"] = duplicate_urls

        results["checks"].append(
            f"{len(duplicate_urls)} duplicate citation URL(s) detected."
        )

    else:

        results["checks"].append(
            "No duplicate citation URLs detected."
        )

    # Source diversity
    unique_domains = sorted(
        set(results["domains"])
    )

    results["checks"].append(
        f"Sources span {len(unique_domains)} unique domain(s)."
    )

    # Trusted domain coverage
    trusted_domains = [
        domain
        for domain in unique_domains
        if _is_trusted_domain(domain)
    ]

    results["trusted_domains"] = trusted_domains

    if trusted_domains:

        results["checks"].append(
            "Authoritative/public-sector or recognized research "
            f"sources detected: {len(trusted_domains)} domain(s)."
        )

    else:

        results["checks"].append(
            "No recognized authoritative research domain detected."
        )

    # Citation linkage
    referenced = 0

    report_lower = report.lower()

    for citation in citations:

        if not isinstance(citation, dict):
            continue

        url = str(
            citation.get("url", "")
        ).strip()

        title = str(
            citation.get("title", "")
        ).strip()

        source = str(
            citation.get("source", "")
        ).strip()

        if url and url in report:

            referenced += 1

        elif title and title.lower() in report_lower:

            referenced += 1

        elif source and source.lower() in report_lower:

            referenced += 1

    results["referenced_citations"] = referenced

    if citations:

        linkage_ratio = referenced / len(citations)

        if linkage_ratio >= 0.5:

            results["checks"].append(
                f"Citation linkage acceptable "
                f"({referenced}/{len(citations)})."
            )

        else:

            results["valid"] = False

            results["checks"].append(
                f"Insufficient citation linkage "
                f"({referenced}/{len(citations)})."
            )

    return results


# ---------------------------------------------------------------------------
# EVIDENCE GROUNDING
# ---------------------------------------------------------------------------

def _validate_evidence_grounding(report, citations, evidence):
    """
    Evaluate whether the report appears to be grounded in retrieved
    evidence.
    """

    results = {
        "valid": True,
        "checks": [],
        "evidence_count": len(evidence),
    }

    if not evidence:

        results["valid"] = False

        results["checks"].append(
            "No structured evidence records supplied by the Evidence agent."
        )

    else:

        results["checks"].append(
            f"Structured evidence supplied "
            f"({len(evidence)} item(s))."
        )

    report_lower = report.lower()

    evidence_markers = [
        "according to",
        "the study",
        "the dataset",
        "the analysis",
        "cms data",
        "cdc data",
        "arxiv",
        "sec filing",
        "research indicates",
        "evidence suggests",
        "results show",
        "findings indicate",
    ]

    marker_count = sum(
        report_lower.count(marker)
        for marker in evidence_markers
    )

    if marker_count >= 2:

        results["checks"].append(
            f"Evidence-attribution language detected "
            f"({marker_count} references)."
        )

    else:

        results["checks"].append(
            "Limited explicit evidence-attribution language."
        )

    # Suspicious citation language
    suspicious = []

    for pattern in SUSPICIOUS_CITATION_PATTERNS:

        if re.search(
            pattern,
            report,
            re.IGNORECASE,
        ):

            suspicious.append(pattern)

    if suspicious:

        results["valid"] = False

        results["checks"].append(
            "Potentially unsupported citation language detected."
        )

    else:

        results["checks"].append(
            "No obvious fabricated-source language detected."
        )

    # Substantive report requires grounding.
    if len(report) > 2000 and not citations and not evidence:

        results["valid"] = False

        results["checks"].append(
            "Substantive report contains neither citations "
            "nor structured evidence."
        )

    return results


# ---------------------------------------------------------------------------
# METHODOLOGY
# ---------------------------------------------------------------------------

def _validate_methodology(report):
    """
    Validate whether the report explains how evidence was obtained,
    interpreted, and limited.
    """

    results = {
        "valid": True,
        "checks": [],
    }

    text = report.lower()

    methodology_terms = [
        "methodology",
        "methods",
        "data source",
        "data sources",
        "search strategy",
        "retrieval",
        "selection criteria",
        "inclusion criteria",
        "analysis approach",
    ]

    found = [
        term
        for term in methodology_terms
        if term in text
    ]

    if len(found) >= 2:

        results["checks"].append(
            "Research methodology/data acquisition is described."
        )

    else:

        results["valid"] = False

        results["checks"].append(
            "Methodology or evidence acquisition process "
            "is insufficiently described."
        )

    limitation_terms = [
        "limitations",
        "limitation",
        "caveat",
        "observational",
        "correlation",
        "causation",
        "cannot establish",
        "data quality",
        "coverage limitation",
    ]

    limitation_count = sum(
        text.count(term)
        for term in limitation_terms
    )

    if limitation_count >= 1:

        results["checks"].append(
            "At least one limitation/caveat is acknowledged."
        )

    else:

        results["valid"] = False

        results["checks"].append(
            "No explicit limitation/caveat discussion detected."
        )

    return results


# ---------------------------------------------------------------------------
# SAFETY
# ---------------------------------------------------------------------------

def _safety_check(report):
    """
    Healthcare-aware safety review.

    Research terminology such as diagnosis, treatment, medication,
    prescription, or patient is not automatically unsafe.

    The Critic escalates only when the report appears to provide
    individualized medical instructions.
    """

    results = {
        "safe": True,
        "checks": [],
        "risk_level": "LOW",
    }

    advice_matches = []

    for pattern in DIRECT_MEDICAL_ADVICE_PATTERNS:

        matches = re.findall(
            pattern,
            report,
            re.IGNORECASE,
        )

        if matches:
            advice_matches.extend(matches)

    if advice_matches:

        results["safe"] = False
        results["risk_level"] = "HIGH"

        results["checks"].append(
            "Potential individualized medical advice detected."
        )

        results["advice_patterns_detected"] = advice_matches

    else:

        results["checks"].append(
            "No clear individualized medical instruction detected."
        )

    # Research terminology is explicitly allowed.
    research_terms = [
        "diagnosis",
        "treatment",
        "prescription",
        "medication",
        "clinical",
        "patient",
    ]

    research_term_count = sum(
        report.lower().count(term)
        for term in research_terms
    )

    if research_term_count:

        results["checks"].append(
            f"Healthcare terminology present in research context "
            f"({research_term_count} occurrence(s)); not automatically "
            "treated as unsafe."
        )

    # Absolute language review.
    absolute_count = _count_terms(
        report,
        ABSOLUTE_TERMS,
    )

    if absolute_count > 10:

        results["risk_level"] = "MEDIUM"

        results["checks"].append(
            f"High absolute-language frequency "
            f"({absolute_count}). Claims should be qualified "
            "where appropriate."
        )

    else:

        results["checks"].append(
            f"Absolute-language frequency acceptable "
            f"({absolute_count})."
        )

    # Strong recommendation language.
    directive_patterns = [
        r"\bmust immediately\b",
        r"\bshould definitely\b",
        r"\bguaranteed to\b",
        r"\bwill prevent\b",
    ]

    directive_count = sum(
        len(
            re.findall(
                pattern,
                report,
                re.IGNORECASE,
            )
        )
        for pattern in directive_patterns
    )

    if directive_count > 3:

        results["risk_level"] = "MEDIUM"

        results["checks"].append(
            f"Strong directive language detected "
            f"({directive_count})."
        )

    else:

        results["checks"].append(
            "Strong directive language limited."
        )

    return results


# ---------------------------------------------------------------------------
# RESEARCH INTEGRITY
# ---------------------------------------------------------------------------

def _validate_research_integrity(
    report,
    citations,
    evidence,
):
    """
    Review characteristics normally expected in professional
    research documentation.
    """

    results = {
        "valid": True,
        "checks": [],
        "risk_flags": [],
    }

    text = report.lower()

    # Causality
    causal_terms = [
        "causes",
        "caused",
        "leads to",
        "results in",
        "drives",
        "proves",
    ]

    causal_count = sum(
        text.count(term)
        for term in causal_terms
    )

    uncertainty_count = _count_terms(
        report,
        UNCERTAINTY_TERMS,
    )

    if causal_count > 0 and uncertainty_count == 0:

        results["risk_flags"].append(
            "causal_language_without_qualifying_language"
        )

        results["checks"].append(
            "Causal language detected without clear uncertainty "
            "or qualification."
        )

    else:

        results["checks"].append(
            "Causal interpretation appears appropriately qualified."
        )

    # Unsupported assertions
    unsupported_patterns = [
        r"\bthe best\b",
        r"\bthe only\b",
        r"\bproven solution\b",
        r"\bguaranteed\b",
        r"\bcompletely eliminates\b",
    ]

    unsupported_count = sum(
        len(
            re.findall(
                pattern,
                report,
                re.IGNORECASE,
            )
        )
        for pattern in unsupported_patterns
    )

    if unsupported_count:

        results["risk_flags"].append(
            "potentially_overstated_claims"
        )

        results["checks"].append(
            f"Potentially overstated claim language detected "
            f"({unsupported_count})."
        )

    else:

        results["checks"].append(
            "No obvious exaggerated-claim patterns detected."
        )

    # Evidence/citation presence
    if len(report) > 1500 and not citations:

        results["valid"] = False

        results["risk_flags"].append(
            "substantive_report_without_citations"
        )

        results["checks"].append(
            "Substantive research report has no citation set."
        )

    if len(report) > 1500 and not evidence:

        results["risk_flags"].append(
            "missing_structured_evidence"
        )

        results["checks"].append(
            "No structured evidence objects supplied."
        )

    return results


# ---------------------------------------------------------------------------
# NUMERICAL CLAIM VALIDATION
# ---------------------------------------------------------------------------

def _validate_numerical_claims(report, citations):
    """
    Detect quantitative claims and determine whether the report appears
    to provide nearby attribution.

    This is a heuristic review, not mathematical verification.
    """

    results = {
        "valid": True,
        "checks": [],
        "numeric_claim_count": 0,
        "unattributed_numeric_claims": 0,
    }

    matches = list(
        NUMERIC_CLAIM_PATTERN.finditer(report)
    )

    results["numeric_claim_count"] = len(matches)

    if not matches:

        results["checks"].append(
            "No major quantitative claims detected."
        )

        return results

    results["checks"].append(
        f"Detected {len(matches)} quantitative claim(s) "
        "requiring evidence review."
    )

    unattributed = 0

    for match in matches:

        start = max(
            0,
            match.start() - 180,
        )

        end = min(
            len(report),
            match.end() + 180,
        )

        context = report[
            start:end
        ].lower()

        has_attribution = any(
            marker in context
            for marker in [
                "according to",
                "cms",
                "cdc",
                "arxiv",
                "sec",
                "study",
                "dataset",
                "source",
                "table",
                "figure",
                "analysis",
                "research",
            ]
        )

        if not has_attribution:
            unattributed += 1

    results["unattributed_numeric_claims"] = unattributed

    if unattributed:

        results["valid"] = False

        results["checks"].append(
            f"{unattributed} quantitative claim(s) appear to lack "
            "nearby attribution."
        )

    else:

        results["checks"].append(
            "Quantitative claims appear to have nearby "
            "evidence attribution."
        )

    return results


# ---------------------------------------------------------------------------
# QUALITY SCORE
# ---------------------------------------------------------------------------

def _calculate_quality_score(
    content,
    citations,
    evidence,
    methodology,
    safety,
    integrity,
    numerical,
):
    """
    Weighted research-quality score.

    Content       20%
    Citations     20%
    Evidence      20%
    Methodology   15%
    Safety        15%
    Integrity      5%
    Numerics       5%
    """

    score = 0.0

    score += 20 if content["valid"] else 8
    score += 20 if citations["valid"] else 8
    score += 20 if evidence["valid"] else 8
    score += 15 if methodology["valid"] else 7
    score += 15 if safety["safe"] else 0
    score += 5 if integrity["valid"] else 2
    score += 5 if numerical["valid"] else 2

    return int(
        round(
            max(
                0,
                min(
                    100,
                    score,
                ),
            )
        )
    )


# ---------------------------------------------------------------------------
# STATUS DECISION
# ---------------------------------------------------------------------------

def _determine_status(
    quality_score,
    content_validation,
    citation_validation,
    evidence_validation,
    methodology_validation,
    safety_check,
    research_integrity,
):
    """
    Determine final publication status.

    Safety failures remain hard gates.
    """

    if not safety_check["safe"]:
        return "REJECTED"

    if quality_score >= 85:

        if (
            content_validation["valid"]
            and citation_validation["valid"]
            and evidence_validation["valid"]
            and methodology_validation["valid"]
        ):
            return "APPROVED"

    if quality_score >= 70:
        return "NEEDS_REVISION"

    return "NEEDS_REVISION"


# ---------------------------------------------------------------------------
# REVISION REQUIREMENTS
# ---------------------------------------------------------------------------

def _collect_revision_requirements(*validations):
    """
    Convert QA findings into concrete instructions for the Synthesis
    or future Revision agent.
    """

    requirements = []

    content = validations[0]
    citations = validations[1]
    evidence = validations[2]
    methodology = validations[3]
    safety = validations[4]
    integrity = validations[5]
    numerical = validations[6]

    if not content["valid"]:

        requirements.append(
            "Strengthen report structure and ensure executive summary, "
            "research objective, evidence/findings, methodology, "
            "limitations, and references are explicitly represented."
        )

    if not citations["valid"]:

        requirements.append(
            "Improve citation completeness, source diversity, URL validity, "
            "and citation-to-claim linkage."
        )

    if not evidence["valid"]:

        requirements.append(
            "Ensure substantive findings are directly grounded in "
            "retrieved evidence records."
        )

    if not methodology["valid"]:

        requirements.append(
            "Document the research methodology, data sources, retrieval "
            "strategy, analytical approach, and limitations."
        )

    if not safety["safe"]:

        requirements.append(
            "Remove individualized medical instructions and keep healthcare "
            "recommendations at the research/system level."
        )

    if not integrity["valid"]:

        requirements.append(
            "Reduce unsupported causal or absolute claims and explicitly "
            "distinguish association from causation."
        )

    if not numerical["valid"]:

        requirements.append(
            "Add source attribution for quantitative claims, percentages, "
            "counts, financial figures, and other numerical statements."
        )

    return requirements


# ---------------------------------------------------------------------------
# PROFESSIONAL CRITIQUE
# ---------------------------------------------------------------------------

def _generate_professional_critique(
    run_id,
    status,
    quality_score,
    content_validation,
    citation_validation,
    evidence_validation,
    methodology_validation,
    safety_check,
    research_integrity,
    numerical_validation,
    revision_required,
):
    """
    Produce an auditable peer-review document.
    """

    lines = []

    lines.append(
        f"# Research Quality Review — {run_id}"
    )

    lines.append("")

    lines.append(
        "## 1. Review Determination"
    )

    lines.append("")

    lines.append(
        f"**Overall status:** {status}"
    )

    lines.append(
        f"**Research quality score:** {quality_score}/100"
    )

    lines.append(
        "**Review type:** Independent pre-publication QA"
    )

    lines.append("")

    # ---------------------------------------------------------------
    # Content
    # ---------------------------------------------------------------

    lines.append(
        "## 2. Editorial and Structural Assessment"
    )

    lines.append("")

    for check in content_validation["checks"]:
        lines.append(f"- {check}")

    lines.append("")

    # ---------------------------------------------------------------
    # Citations
    # ---------------------------------------------------------------

    lines.append(
        "## 3. Citation and Source Assessment"
    )

    lines.append("")

    lines.append(
        f"- Citation count: "
        f"{citation_validation.get('citation_count', 0)}"
    )

    lines.append(
        f"- Referenced citations: "
        f"{citation_validation.get('referenced_citations', 0)}"
    )

    for check in citation_validation["checks"]:
        lines.append(f"- {check}")

    lines.append("")

    # ---------------------------------------------------------------
    # Evidence
    # ---------------------------------------------------------------

    lines.append(
        "## 4. Evidence-Grounding Assessment"
    )

    lines.append("")

    for check in evidence_validation["checks"]:
        lines.append(f"- {check}")

    lines.append("")

    # ---------------------------------------------------------------
    # Methodology
    # ---------------------------------------------------------------

    lines.append(
        "## 5. Methodological Assessment"
    )

    lines.append("")

    for check in methodology_validation["checks"]:
        lines.append(f"- {check}")

    lines.append("")

    # ---------------------------------------------------------------
    # Safety
    # ---------------------------------------------------------------

    lines.append(
        "## 6. Healthcare Safety Assessment"
    )

    lines.append("")

    lines.append(
        f"- Risk level: "
        f"{safety_check.get('risk_level', 'UNKNOWN')}"
    )

    for check in safety_check["checks"]:
        lines.append(f"- {check}")

    lines.append("")

    # ---------------------------------------------------------------
    # Research Integrity
    # ---------------------------------------------------------------

    lines.append(
        "## 7. Research Integrity Assessment"
    )

    lines.append("")

    for check in research_integrity["checks"]:
        lines.append(f"- {check}")

    lines.append("")

    # ---------------------------------------------------------------
    # Numerical Claims
    # ---------------------------------------------------------------

    lines.append(
        "## 8. Quantitative-Claim Assessment"
    )

    lines.append("")

    lines.append(
        f"- Quantitative claims detected: "
        f"{numerical_validation.get('numeric_claim_count', 0)}"
    )

    lines.append(
        f"- Potentially unattributed quantitative claims: "
        f"{numerical_validation.get('unattributed_numeric_claims', 0)}"
    )

    for check in numerical_validation["checks"]:
        lines.append(f"- {check}")

    lines.append("")

    # ---------------------------------------------------------------
    # Required Revisions
    # ---------------------------------------------------------------

    lines.append(
        "## 9. Required Revisions"
    )

    lines.append("")

    if revision_required:

        for index, requirement in enumerate(
            revision_required,
            start=1,
        ):
            lines.append(
                f"{index}. {requirement}"
            )

    else:

        lines.append(
            "No mandatory revisions identified. The report satisfies "
            "the current automated research-quality gate."
        )

    lines.append("")

    # ---------------------------------------------------------------
    # Publication Recommendation
    # ---------------------------------------------------------------

    lines.append(
        "## 10. Publication Recommendation"
    )

    lines.append("")

    if status == "APPROVED":

        lines.append(
            "The report has passed the automated pre-publication "
            "quality gate and is suitable for downstream report rendering."
        )

    elif status == "NEEDS_REVISION":

        lines.append(
            "The report demonstrates substantial research content "
            "but requires targeted revision before publication."
        )

    else:

        lines.append(
            "The report must not proceed to publication until the "
            "identified safety or integrity issues have been resolved."
        )

    lines.append("")

    # ---------------------------------------------------------------
    # Reviewer Note
    # ---------------------------------------------------------------

    lines.append(
        "## 11. Reviewer Note"
    )

    lines.append("")

    lines.append(
        "This assessment is an automated research-quality control layer. "
        "It evaluates structural completeness, evidence grounding, "
        "citation integrity, methodological transparency, quantitative "
        "claim attribution, research language, and healthcare safety. "
        "It does not constitute independent verification of every factual "
        "claim and should not be represented as human peer review."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# UTILITIES
# ---------------------------------------------------------------------------

def _count_terms(text, terms):
    """
    Count occurrences of a list of terms.
    """

    text_lower = text.lower()

    count = 0

    for term in terms:
        count += text_lower.count(
            term.lower()
        )

    return count


def _normalize_domain(netloc):
    """
    Normalize a URL hostname.

    Examples:
        www.cms.gov       -> cms.gov
        CMS.GOV           -> cms.gov
        cms.gov:443       -> cms.gov
    """

    domain = str(netloc).strip().lower()

    # Remove port.
    domain = domain.split(":")[0]

    # Remove leading www.
    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def _is_trusted_domain(domain):
    """
    Check whether a normalized domain belongs to the trusted
    research/public-sector domain list.
    """

    domain = _normalize_domain(domain)

    for trusted in TRUSTED_RESEARCH_DOMAINS:

        if (
            domain == trusted
            or domain.endswith("." + trusted)
        ):
            return True

    return False


def _count_trusted_domains(citations):
    """
    Count recognized authoritative domains represented in citations.
    """

    domains = set()

    for citation in citations:

        if not isinstance(citation, dict):
            continue

        url = str(
            citation.get("url", "")
        ).strip()

        if not url:
            continue

        try:

            parsed = urlparse(url)

            if (
                parsed.scheme.lower()
                not in SUPPORTED_URL_SCHEMES
            ):
                continue

            if not parsed.netloc:
                continue

            domain = _normalize_domain(
                parsed.netloc
            )

            if _is_trusted_domain(domain):
                domains.add(domain)

        except Exception:
            continue

    return len(domains)