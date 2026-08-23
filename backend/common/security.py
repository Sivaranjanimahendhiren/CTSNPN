"""
CTS-NPN Security and Validation Utilities
=========================================

Centralized security, validation, sanitization, and audit utilities for the
CTS-NPN Research-to-Report multi-agent system.

External evidence is treated as untrusted data.

This module provides protection against:

- malformed inputs
- oversized inputs
- null-byte injection
- HTML/script injection
- JavaScript injection
- prompt-injection patterns
- unsafe URLs
- malformed citations
- duplicate citations
- excessively nested objects
- unexpected data types
- unsafe report content

This module does NOT determine whether research findings are scientifically
true. Scientific validity is handled by Evidence and Critic agents through
source provenance, corroboration, quantitative consistency checks,
citation completeness, and evidence-quality scoring.
"""

import json
import logging
import re
import uuid
from typing import Any, Dict
from urllib.parse import urlparse

from backend.common.config import ENABLE_AUDIT_LOGGING


# ============================================================================
# CONSTANTS
# ============================================================================

MAX_TEXT_LENGTH = 50_000
MAX_QUERY_LENGTH = 5_000
MAX_TITLE_LENGTH = 1_000
MAX_URL_LENGTH = 4_096
MAX_AUTHORS = 100
MAX_CITATIONS = 500
MAX_NESTING_DEPTH = 12

ALLOWED_URL_SCHEMES = {
    "http",
    "https",
    "urn",
}

# Trusted public research/data domains.
#
# This is NOT used to reject legitimate sources globally.
# It is used to identify high-confidence public evidence sources.
TRUSTED_RESEARCH_DOMAINS = {
    "arxiv.org",
    "export.arxiv.org",
    "sec.gov",
    "www.sec.gov",
    "data.sec.gov",
    "cms.gov",
    "data.cms.gov",
    "cdc.gov",
    "www.cdc.gov",
    "data.cdc.gov",
}


# ============================================================================
# LOGGING
# ============================================================================

logger = logging.getLogger("cts_npn.security")

if not logger.handlers:
    handler = logging.StreamHandler()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

logger.setLevel(logging.INFO)


# ============================================================================
# RUN IDENTIFICATION
# ============================================================================

def new_run_id() -> str:
    """
    Generate a short, human-readable run identifier.

    Returns
    -------
    str
        Eight-character uppercase hexadecimal identifier.

    Example
    -------
    A91F20BC
    """

    return str(uuid.uuid4()).replace("-", "")[:8].upper()


# ============================================================================
# REQUIRED FIELD VALIDATION
# ============================================================================

def require_fields(data: dict, fields: list) -> None:
    """
    Validate that required fields exist and contain meaningful values.

    Raises
    ------
    ValueError
        If input is invalid or a required field is missing.
    """

    if not isinstance(data, dict):
        raise ValueError("Input must be a dictionary")

    if not isinstance(fields, list):
        raise ValueError("fields must be a list")

    missing = []

    for field in fields:

        if field not in data:
            missing.append(field)
            continue

        value = data[field]

        if value is None:
            missing.append(field)
            continue

        if isinstance(value, str) and not value.strip():
            missing.append(field)
            continue

        if isinstance(value, (list, dict)) and len(value) == 0:
            missing.append(field)

    if missing:
        raise ValueError(
            "Required field(s) missing or empty: "
            + ", ".join(missing)
        )


# ============================================================================
# TEXT NORMALIZATION
# ============================================================================

def clean_text(
    text: str,
    max_length: int = MAX_TEXT_LENGTH
) -> str:
    """
    Normalize user/system text without destroying research meaning.

    This function intentionally performs conservative cleaning.

    It does NOT:
    - rewrite research findings
    - remove punctuation
    - remove URLs
    - remove mathematical notation
    - alter citations
    - summarize evidence

    It only removes unsafe control characters and normalizes whitespace.
    """

    if text is None:
        raise ValueError("Text cannot be None")

    if not isinstance(text, str):
        text = str(text)

    original_length = len(text)

    if original_length > max_length:
        raise ValueError(
            f"Text exceeds maximum length of {max_length} characters"
        )

    # Remove null bytes.
    text = text.replace("\x00", "")

    # Remove Unicode control characters except:
    # newline, carriage return, tab.
    cleaned_chars = []

    for char in text:
        code = ord(char)

        if code in (9, 10, 13):
            cleaned_chars.append(char)
            continue

        if code < 32:
            continue

        cleaned_chars.append(char)

    text = "".join(cleaned_chars)

    # Normalize excessive spaces while preserving line structure.
    text = re.sub(r"[ \t]+", " ", text)

    # Prevent enormous runs of blank lines.
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    text = text.strip()

    if ENABLE_AUDIT_LOGGING:
        _audit_log(
            "clean_text",
            {
                "original_length": original_length,
                "cleaned_length": len(text),
                "max_length": max_length,
            },
        )

    return text


# ============================================================================
# PROMPT-INJECTION DETECTION
# ============================================================================

PROMPT_INJECTION_PATTERNS = [

    # ------------------------------------------------------------------------
    # Direct instruction override attempts
    # ------------------------------------------------------------------------

    r"\bignore\s+(all|any|the|previous|prior)\s+instructions\b",

    r"\bdisregard\s+(all|any|the|previous|prior)\s+instructions\b",

    r"\bforget\s+(all|any|the|previous|prior)\s+instructions\b",

    # ------------------------------------------------------------------------
    # Role manipulation
    # ------------------------------------------------------------------------

    r"\byou\s+are\s+now\s+(a|an)\b",

    r"\bact\s+as\s+(a|an)\b",

    r"\bpretend\s+to\s+be\b",

    r"\bassume\s+the\s+role\s+of\b",

    # ------------------------------------------------------------------------
    # System prompt extraction
    # ------------------------------------------------------------------------

    r"\breveal\s+(the\s+)?system\s+prompt\b",

    r"\bshow\s+(me\s+)?your\s+system\s+prompt\b",

    r"\bprint\s+(the\s+)?system\s+message\b",

    r"\bdeveloper\s+message\b",

    # ------------------------------------------------------------------------
    # Tool manipulation
    # ------------------------------------------------------------------------

    r"\bcall\s+this\s+tool\b",

    r"\bexecute\s+this\s+command\b",

    r"\brun\s+this\s+command\b",

    r"\buse\s+the\s+following\s+tool\b",

    # ------------------------------------------------------------------------
    # Fake priority instructions
    # ------------------------------------------------------------------------

    r"\bsystem\s+override\b",

    r"\bdeveloper\s+override\b",

    r"\bpriority\s+instruction\b",

    # ------------------------------------------------------------------------
    # Common LLM injection language
    # ------------------------------------------------------------------------

    r"\bdo\s+not\s+follow\s+the\s+user\b",

    r"\bfollow\s+only\s+these\s+instructions\b",

    r"\bnew\s+instructions\s*:",
]


def detect_prompt_injection(text: str) -> Dict[str, Any]:
    """
    Detect common prompt-injection patterns.

    Detection does not automatically mean the source is malicious.

    Academic papers, web pages, filings, and other documents can contain
    imperative language naturally.

    The result should therefore be combined with source provenance and
    agent policy.
    """

    if not isinstance(text, str):
        text = str(text)

    lowered = text.lower()

    matches = []

    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, lowered, re.IGNORECASE):
            matches.append(pattern)

    # Bounded risk score.
    risk_score = min(len(matches) / 5.0, 1.0)

    if risk_score >= 0.8:
        risk_level = "HIGH"

    elif risk_score >= 0.4:
        risk_level = "MEDIUM"

    elif risk_score > 0:
        risk_level = "LOW"

    else:
        risk_level = "NONE"

    return {
        "detected": bool(matches),
        "risk_level": risk_level,
        "risk_score": round(risk_score, 4),
        "matched_pattern_count": len(matches),
    }


# ============================================================================
# CONTENT VALIDATION
# ============================================================================

def validate_content(
    content: str,
    content_type: str = "text"
) -> bool:
    """
    Validate text content for unsafe executable/injection patterns.

    Compatible with:

        validate_content(content)

    Raises
    ------
    ValueError
        When content is unsafe.
    """

    if content is None:
        raise ValueError("Content cannot be empty")

    if not isinstance(content, str):
        content = str(content)

    if not content.strip():
        raise ValueError("Content cannot be empty")

    if len(content) > MAX_TEXT_LENGTH:
        raise ValueError(
            f"Content exceeds maximum allowed size "
            f"({MAX_TEXT_LENGTH} characters)"
        )

    # ------------------------------------------------------------------------
    # HTML / SCRIPT INJECTION
    # ------------------------------------------------------------------------

    dangerous_patterns = [

        # Script elements
        r"<\s*script\b[^>]*>",

        r"</\s*script\s*>",

        # JavaScript URLs
        r"\bjavascript\s*:",

        # Data URLs that can contain executable content
        r"\bdata\s*:\s*text/html",

        # HTML event handlers
        r"\bon[a-zA-Z]+\s*=",

        # iframe/object/embed/applet execution surfaces
        r"<\s*(iframe|object|embed|applet)\b",

        # Common SVG execution vectors
        r"<\s*svg\b[^>]*on[a-zA-Z]+\s*=",

        # Null-byte injection
        r"\x00",
    ]

    for pattern in dangerous_patterns:

        if re.search(pattern, content, re.IGNORECASE):

            raise ValueError(
                f"Content contains potentially unsafe pattern: {pattern}"
            )

    # ------------------------------------------------------------------------
    # PROMPT-INJECTION CHECK
    # ------------------------------------------------------------------------

    injection_result = detect_prompt_injection(content)

    # LOW/MEDIUM are not automatically rejected because research documents
    # can legitimately contain instruction-like language.
    #
    # HIGH-risk injection is rejected at the security boundary.

    if injection_result["risk_level"] == "HIGH":
        raise ValueError(
            "Content contains high-risk prompt-injection patterns"
        )

    if ENABLE_AUDIT_LOGGING:
        _audit_log(
            "validate_content",
            {
                "content_type": content_type,
                "length": len(content),
                "prompt_injection_risk": injection_result["risk_level"],
                "valid": True,
            },
        )

    return True


# ============================================================================
# URL VALIDATION
# ============================================================================

def validate_url(
    url: str,
    require_https: bool = False
) -> bool:
    """
    Validate a citation/source URL.

    Supported schemes:
        http://
        https://
        urn:
    """

    if not isinstance(url, str):
        raise ValueError("URL must be a string")

    url = url.strip()

    if not url:
        raise ValueError("URL cannot be empty")

    if len(url) > MAX_URL_LENGTH:
        raise ValueError(
            "URL exceeds maximum allowed length"
        )

    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        raise ValueError(
            f"Unsupported URL scheme: {parsed.scheme}"
        )

    if require_https and parsed.scheme != "https":
        raise ValueError("HTTPS URL required")

    # URNs don't have a conventional hostname.
    if parsed.scheme == "urn":
        return True

    if not parsed.netloc:
        raise ValueError(
            "URL does not contain a valid host"
        )

    # Reject credential-bearing URLs.
    if parsed.username or parsed.password:
        raise ValueError(
            "URLs containing embedded credentials are not permitted"
        )

    return True


# ============================================================================
# SOURCE TRUST CLASSIFICATION
# ============================================================================

def classify_source_domain(url: str) -> str:
    """
    Classify source provenance.

    Returns:
        TRUSTED_PUBLIC
        PUBLIC_OTHER
        UNKNOWN
        INVALID
    """

    try:
        validate_url(url)

    except ValueError:
        return "INVALID"

    parsed = urlparse(url)

    if parsed.scheme == "urn":
        return "PUBLIC_OTHER"

    hostname = (parsed.hostname or "").lower()

    for domain in TRUSTED_RESEARCH_DOMAINS:

        if hostname == domain or hostname.endswith("." + domain):
            return "TRUSTED_PUBLIC"

    if parsed.scheme == "https":
        return "PUBLIC_OTHER"

    return "UNKNOWN"


# ============================================================================
# CITATION VALIDATION
# ============================================================================

def validate_citations(citations: list) -> bool:
    """
    Validate citation records.

    Required fields:
        source
        url
        title
        date

    Additional validation:
        - correct data types
        - URL validity
        - title length
        - author structure
        - duplicate URL detection
        - source provenance classification
    """

    if not isinstance(citations, list):
        raise ValueError("Citations must be a list")

    if len(citations) > MAX_CITATIONS:
        raise ValueError(
            f"Too many citations. Maximum allowed is {MAX_CITATIONS}"
        )

    required_fields = [
        "source",
        "url",
        "title",
        "date",
    ]

    seen_urls = set()

    for index, citation in enumerate(citations):

        if not isinstance(citation, dict):
            raise ValueError(
                f"Citation {index} must be a dictionary"
            )

        # --------------------------------------------------------------------
        # REQUIRED FIELDS
        # --------------------------------------------------------------------

        for field in required_fields:

            if field not in citation:
                raise ValueError(
                    f"Citation {index} missing required field: {field}"
                )

            value = citation[field]

            if value is None:
                raise ValueError(
                    f"Citation {index} has empty field: {field}"
                )

            if isinstance(value, str) and not value.strip():
                raise ValueError(
                    f"Citation {index} has empty field: {field}"
                )

        # --------------------------------------------------------------------
        # FIELD TYPE VALIDATION
        # --------------------------------------------------------------------

        if not isinstance(citation["title"], str):
            raise ValueError(
                f"Citation {index} title must be a string"
            )

        if not isinstance(citation["source"], str):
            raise ValueError(
                f"Citation {index} source must be a string"
            )

        if not isinstance(citation["date"], str):
            raise ValueError(
                f"Citation {index} date must be a string"
            )

        if len(citation["title"]) > MAX_TITLE_LENGTH:
            raise ValueError(
                f"Citation {index} title is too long"
            )

        # --------------------------------------------------------------------
        # URL VALIDATION
        # --------------------------------------------------------------------

        if not isinstance(citation["url"], str):
            raise ValueError(
                f"Citation {index} URL must be a string"
            )

        url = citation["url"].strip()

        validate_url(url)

        # --------------------------------------------------------------------
        # DUPLICATE DETECTION
        # --------------------------------------------------------------------

        normalized_url = url.rstrip("/").lower()

        if normalized_url in seen_urls:
            raise ValueError(
                f"Duplicate citation URL detected at citation {index}"
            )

        seen_urls.add(normalized_url)

        # --------------------------------------------------------------------
        # AUTHORS
        # --------------------------------------------------------------------

        authors = citation.get("authors", [])

        if authors is not None:

            if not isinstance(authors, list):
                raise ValueError(
                    f"Citation {index} authors must be a list"
                )

            if len(authors) > MAX_AUTHORS:
                raise ValueError(
                    f"Citation {index} contains too many authors"
                )

            for author in authors:

                if not isinstance(author, str):
                    raise ValueError(
                        f"Citation {index} contains invalid author"
                    )

                if len(author) > MAX_TITLE_LENGTH:
                    raise ValueError(
                        f"Citation {index} contains an author name that is too long"
                    )

    if ENABLE_AUDIT_LOGGING:
        _audit_log(
            "validate_citations",
            {
                "citation_count": len(citations),
                "valid": True,
            },
        )

    return True


# ============================================================================
# CITATION QUALITY ANALYSIS
# ============================================================================

def analyze_citation_quality(
    citations: list
) -> Dict[str, Any]:
    """
    Produce quantitative citation-quality metrics.

    Metrics:
        completeness
        trusted_source_ratio
        source_diversity
        duplicate_ratio
    """

    if not isinstance(citations, list) or not citations:

        return {
            "citation_count": 0,
            "completeness": 0.0,
            "trusted_source_ratio": 0.0,
            "source_diversity": 0,
            "duplicate_ratio": 0.0,
        }

    total = len(citations)

    complete = 0
    trusted = 0

    source_types = set()
    urls = []

    for citation in citations:

        if all(
            citation.get(field)
            for field in (
                "source",
                "url",
                "title",
                "date",
            )
        ):
            complete += 1

        classification = classify_source_domain(
            citation.get("url", "")
        )

        if classification == "TRUSTED_PUBLIC":
            trusted += 1

        source_types.add(
            citation.get("source", "unknown")
        )

        urls.append(
            citation.get("url", "")
            .rstrip("/")
            .lower()
        )

    duplicate_count = total - len(set(urls))

    return {
        "citation_count": total,
        "completeness": round(
            complete / total,
            4
        ),
        "trusted_source_ratio": round(
            trusted / total,
            4
        ),
        "source_diversity": len(source_types),
        "duplicate_ratio": round(
            duplicate_count / total,
            4
        ),
    }


# ============================================================================
# EVIDENCE OBJECT VALIDATION
# ============================================================================

def validate_evidence_object(
    evidence: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate the structural integrity of an evidence package.

    This does not judge whether a scientific claim is true.
    It verifies that evidence is structurally usable by downstream agents.
    """

    if not isinstance(evidence, dict):
        raise ValueError(
            "Evidence must be a dictionary"
        )

    result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "metrics": {},
    }

    expected_collections = [
        "research_papers",
        "regulatory_filings",
        "health_data",
        "citations",
    ]

    for collection in expected_collections:

        value = evidence.get(
            collection,
            []
        )

        if value is None:

            evidence[collection] = []

            continue

        if not isinstance(value, list):

            result["valid"] = False

            result["errors"].append(
                f"{collection} must be a list"
            )

    citations = evidence.get(
        "citations",
        []
    )

    try:

        validate_citations(citations)

    except ValueError as exc:

        result["valid"] = False

        result["errors"].append(
            str(exc)
        )

    result["metrics"] = analyze_citation_quality(
        citations
    )

    if not citations:

        result["warnings"].append(
            "Evidence package contains no citations"
        )

    if not evidence.get("research_papers"):

        result["warnings"].append(
            "No research papers were collected"
        )

    if not evidence.get("health_data"):

        result["warnings"].append(
            "No public health dataset evidence was collected"
        )

    return result


# ============================================================================
# REPORT VALIDATION
# ============================================================================

def validate_report_structure(
    report: str
) -> Dict[str, Any]:
    """
    Validate the structural completeness of a generated report.

    The function does not evaluate scientific truth.
    """

    if not isinstance(report, str):

        return {
            "valid": False,
            "checks": [
                "Report must be a string"
            ],
        }

    checks = []
    valid = True

    # ------------------------------------------------------------------------
    # LENGTH
    # ------------------------------------------------------------------------

    if len(report) < 500:

        valid = False

        checks.append(
            "Report is shorter than the minimum recommended length"
        )

    else:

        checks.append(
            "Report length acceptable"
        )

    # ------------------------------------------------------------------------
    # REQUIRED SECTIONS
    # ------------------------------------------------------------------------

    required_sections = [
        "References",
        "Metadata",
    ]

    for section in required_sections:

        if section.lower() in report.lower():

            checks.append(
                f"Required section present: {section}"
            )

        else:

            valid = False

            checks.append(
                f"Required section missing: {section}"
            )

    # ------------------------------------------------------------------------
    # HEADING DETECTION
    # ------------------------------------------------------------------------

    heading_count = len(
        re.findall(
            r"(?m)^#{1,6}\s+\S+",
            report
        )
    )

    if heading_count >= 3:

        checks.append(
            f"Structured headings detected: {heading_count}"
        )

    else:

        valid = False

        checks.append(
            "Insufficient report section structure"
        )

    return {
        "valid": valid,
        "checks": checks,
        "heading_count": heading_count,
        "character_count": len(report),
        "word_count": len(report.split()),
    }


# ============================================================================
# JSON SAFETY
# ============================================================================

def validate_json_serializable(
    value: Any
) -> bool:
    """
    Verify that an object can be safely serialized as JSON.
    """

    try:

        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
        )

        return True

    except (TypeError, ValueError) as exc:

        raise ValueError(
            f"Object is not safely JSON serializable: {exc}"
        ) from exc


# ============================================================================
# DEEP OBJECT SAFETY
# ============================================================================

def _check_nesting(
    value: Any,
    depth: int = 0
) -> None:
    """
    Protect against excessively nested objects.
    """

    if depth > MAX_NESTING_DEPTH:

        raise ValueError(
            f"Object nesting exceeds maximum depth "
            f"of {MAX_NESTING_DEPTH}"
        )

    if isinstance(value, dict):

        for key, child in value.items():

            if not isinstance(key, str):

                raise ValueError(
                    "Dictionary keys must be strings"
                )

            _check_nesting(
                child,
                depth + 1
            )

    elif isinstance(value, list):

        for child in value:

            _check_nesting(
                child,
                depth + 1
            )


def validate_data_object(
    value: Any
) -> bool:
    """
    Perform structural validation of arbitrary API data.
    """

    validate_json_serializable(value)

    _check_nesting(value)

    return True


# ============================================================================
# AUDIT LOGGING
# ============================================================================

def _audit_log(
    action: str,
    details: dict
) -> None:
    """
    Write a security/audit event.

    Do not store:
    - passwords
    - authentication tokens
    - API keys
    - complete patient/member records
    - unnecessary personally identifiable information

    Security logging must never crash the research pipeline.
    """

    if not ENABLE_AUDIT_LOGGING:
        return

    try:

        safe_details = {}

        for key, value in details.items():

            lowered = str(key).lower()

            # Prevent accidental secret logging.
            if any(
                secret_word in lowered
                for secret_word in (
                    "password",
                    "token",
                    "secret",
                    "api_key",
                    "authorization",
                )
            ):

                safe_details[key] = "[REDACTED]"

            else:

                safe_details[key] = value

        logger.info(
            "AUDIT: %s - %s",
            action,
            safe_details,
        )

    except Exception as exc:

        # Security logging must never crash the research pipeline.
        logger.warning(
            "Audit logging failed: %s",
            exc,
        )