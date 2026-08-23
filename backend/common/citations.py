"""
CTS-NPN Citation, Provenance and Evidence Traceability Engine
==============================================================

Purpose
-------
Provides citation management, provenance tracking, evidence traceability,
citation validation, and human-readable reference generation for the
CTS-NPN Research-to-Report multi-agent system.

Core provenance chain
---------------------

    CLAIM
       |
       v
    EVIDENCE
       |
       v
    PASSAGE / DATA RECORD
       |
       v
    SOURCE
       |
       v
    ORIGINAL PUBLIC RESOURCE

This module is designed to work with:
    - Synthesis Agent
    - Evidence Agent
    - Critic Agent
    - PDF Generator Agent
    - Step Functions
    - S3 artifact storage

Important
---------
This module NEVER invents source metadata.

If author, publication date, DOI, accession number, dataset ID,
or another field is unavailable, it remains unknown.

System timestamps such as retrieved_at are NOT publication dates.

The module also supports nested/encoded JSON content so upstream
agents can safely pass strings containing JSON without leaving
escaped JSON visible in the final report.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


# ============================================================================
# CONSTANTS
# ============================================================================

SUPPORTED_STYLES = {
    "APA",
    "MLA",
    "CHICAGO",
    "SIMPLE",
}

SOURCE_TYPES = {
    "arxiv",
    "academic_paper",
    "sec_edgar",
    "cms",
    "cdc",
    "government",
    "dataset",
    "webpage",
    "report",
    "other",
}

ATTRIBUTION_TYPES = {
    "source_reported",
    "system_calculated",
    "system_inferred",
    "analyst_interpretation",
}

MAX_DECODE_DEPTH = 8


# ============================================================================
# TIME / IDENTIFIERS
# ============================================================================

def _utc_now() -> str:
    """
    Return current UTC timestamp.

    This represents system activity, not publication date.
    """
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(value: str) -> str:
    """
    Generate deterministic SHA-256 identifier.
    """
    return hashlib.sha256(
        value.strip().lower().encode("utf-8")
    ).hexdigest()


# ============================================================================
# ROBUST JSON / TEXT DECODING
# ============================================================================

def decode_nested_value(
    value: Any,
    max_depth: int = MAX_DECODE_DEPTH,
) -> Any:
    """
    Decode nested JSON/string encoded content.

    Handles examples such as:

        '{"title":"Example"}'

        '"{\\"title\\": \\"Example\\"}"'

        bytes containing UTF-8 JSON

        dictionaries/lists containing encoded strings

    The function stops when the value is no longer JSON-encoded.

    This prevents raw escaped JSON from appearing in the final report.
    """

    current = value

    for _ in range(max_depth):

        # --------------------------------------------------------------
        # Bytes
        # --------------------------------------------------------------
        if isinstance(current, bytes):
            try:
                current = current.decode("utf-8-sig")
            except UnicodeDecodeError:
                current = current.decode(
                    "utf-8",
                    errors="replace",
                )
            continue

        # --------------------------------------------------------------
        # Strings
        # --------------------------------------------------------------
        if isinstance(current, str):
            text = current.strip()

            if not text:
                return ""

            # Try JSON decoding only when the string looks JSON-like.
            looks_json = (
                text.startswith("{")
                or text.startswith("[")
                or text.startswith('"')
            )

            if looks_json:
                try:
                    decoded = json.loads(text)

                    # Avoid infinite loops.
                    if decoded == current:
                        return current

                    current = decoded
                    continue

                except (json.JSONDecodeError, TypeError):
                    pass

            return current

        # --------------------------------------------------------------
        # Dictionaries
        # --------------------------------------------------------------
        if isinstance(current, dict):
            decoded_dict = {}

            for key, item in current.items():
                decoded_dict[key] = decode_nested_value(
                    item,
                    max_depth=max_depth,
                )

            return decoded_dict

        # --------------------------------------------------------------
        # Lists
        # --------------------------------------------------------------
        if isinstance(current, list):
            return [
                decode_nested_value(
                    item,
                    max_depth=max_depth,
                )
                for item in current
            ]

        return current

    return current


def clean_text(
    value: Any,
    max_chars: Optional[int] = None,
) -> str:
    """
    Convert arbitrary content into clean human-readable text.

    Features:
        - UTF-8 cleanup
        - nested JSON decoding
        - escaped quote cleanup
        - CRLF normalization
        - HTML entity decoding
        - optional length limiting
    """

    decoded = decode_nested_value(value)

    if decoded is None:
        return ""

    if isinstance(decoded, str):
        text = decoded
    elif isinstance(decoded, (int, float, bool)):
        text = str(decoded)
    else:
        text = json.dumps(
            decoded,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    # --------------------------------------------------------------
    # Decode common HTML entities.
    # --------------------------------------------------------------
    text = html.unescape(text)

    # --------------------------------------------------------------
    # Normalize newlines.
    # --------------------------------------------------------------
    text = (
        text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )

    # --------------------------------------------------------------
    # Remove accidental JSON string escaping.
    # --------------------------------------------------------------
    text = (
        text
        .replace('\\"', '"')
        .replace("\\/", "/")
    )

    # --------------------------------------------------------------
    # Remove zero-width characters.
    # --------------------------------------------------------------
    text = re.sub(
        r"[\u200b\u200c\u200d\ufeff]",
        "",
        text,
    )

    if max_chars is not None and len(text) > max_chars:
        text = (
            text[:max_chars]
            + "\n\n"
            "[Content truncated. Complete artifact remains available in S3.]"
        )

    return text.strip()


# ============================================================================
# SOURCE NORMALIZATION
# ============================================================================

def normalize_source(
    source: Optional[dict],
) -> dict:
    """
    Normalize source metadata into a predictable schema.

    Unknown metadata is preserved rather than fabricated.
    """

    if not source:
        return {}

    decoded = decode_nested_value(source)

    if not isinstance(decoded, dict):
        return {}

    normalized = dict(decoded)

    title = clean_text(
        normalized.get("title")
        or normalized.get("name")
        or "Unknown source"
    )

    url = clean_text(
        normalized.get("url")
        or normalized.get("source_url")
        or normalized.get("link")
        or ""
    )

    date = (
        normalized.get("date")
        or normalized.get("published_date")
        or normalized.get("publication_date")
        or normalized.get("issued")
    )

    if date is not None:
        date = clean_text(date)

    authors = normalized.get("authors", [])

    if authors is None:
        authors = []

    if isinstance(authors, str):
        authors = [
            clean_text(authors)
        ]

    if not isinstance(authors, list):
        authors = [authors]

    authors = [
        clean_text(author)
        for author in authors
        if clean_text(author)
    ]

    source_type = clean_text(
        normalized.get("source_type")
        or normalized.get("type")
        or "other"
    ).lower()

    if source_type not in SOURCE_TYPES:
        source_type = "other"

    # --------------------------------------------------------------
    # Identifiers
    # --------------------------------------------------------------

    doi = clean_text(
        normalized.get("doi")
        or normalized.get("DOI")
        or ""
    )

    arxiv_id = clean_text(
        normalized.get("arxiv_id")
        or normalized.get("arxivId")
        or ""
    )

    accession_number = clean_text(
        normalized.get("accession_number")
        or normalized.get("accession")
        or ""
    )

    dataset_id = clean_text(
        normalized.get("dataset_id")
        or normalized.get("datasetId")
        or ""
    )

    publisher = clean_text(
        normalized.get("publisher")
        or normalized.get("organization")
        or ""
    )

    retrieved_at = clean_text(
        normalized.get("retrieved_at")
        or _utc_now()
    )

    normalized["title"] = title
    normalized["url"] = url
    normalized["date"] = date or "n.d."
    normalized["authors"] = authors
    normalized["source_type"] = source_type

    normalized["doi"] = doi
    normalized["arxiv_id"] = arxiv_id
    normalized["accession_number"] = accession_number
    normalized["dataset_id"] = dataset_id
    normalized["publisher"] = publisher
    normalized["retrieved_at"] = retrieved_at

    normalized["citation_id"] = citation_identity(
        normalized
    )

    return normalized


# ============================================================================
# CITATION IDENTITY
# ============================================================================

def citation_identity(
    source: dict,
) -> str:
    """
    Generate deterministic source identity.

    Priority:

        DOI
        arXiv ID
        SEC accession number
        Dataset ID
        URL
        Title + date
    """

    doi = clean_text(
        source.get("doi")
        or source.get("DOI")
        or ""
    ).lower()

    if doi:
        basis = f"doi:{doi}"

    else:
        arxiv_id = clean_text(
            source.get("arxiv_id")
            or source.get("arxivId")
            or ""
        ).lower()

        if arxiv_id:
            basis = f"arxiv:{arxiv_id}"

        else:
            accession = clean_text(
                source.get("accession_number")
                or source.get("accession")
                or ""
            ).lower()

            if accession:
                basis = f"sec:{accession}"

            else:
                dataset_id = clean_text(
                    source.get("dataset_id")
                    or source.get("datasetId")
                    or ""
                ).lower()

                if dataset_id:
                    basis = f"dataset:{dataset_id}"

                else:
                    url = clean_text(
                        source.get("url")
                        or source.get("source_url")
                        or ""
                    ).lower()

                    if url:
                        basis = f"url:{url}"

                    else:
                        title = clean_text(
                            source.get("title")
                            or ""
                        ).lower()

                        date = clean_text(
                            source.get("date")
                            or ""
                        ).lower()

                        basis = (
                            f"title:{title}|"
                            f"date:{date}"
                        )

    return (
        "SRC-"
        + _stable_hash(basis)[:16].upper()
    )


# ============================================================================
# YEAR EXTRACTION
# ============================================================================

def _extract_year(
    date_value: Any,
) -> str:
    """
    Extract publication year without inventing one.
    """

    if not date_value:
        return "n.d."

    match = re.search(
        r"\b(19|20)\d{2}\b",
        str(date_value),
    )

    return (
        match.group(0)
        if match
        else "n.d."
    )


# ============================================================================
# AUTHOR FORMATTING
# ============================================================================

def _format_authors_apa(
    authors: List[str],
) -> str:

    if not authors:
        return "Unknown"

    if len(authors) == 1:
        return authors[0]

    if len(authors) == 2:
        return (
            f"{authors[0]} & {authors[1]}"
        )

    if len(authors) <= 20:
        return (
            ", ".join(authors[:-1])
            + f", & {authors[-1]}"
        )

    return (
        ", ".join(authors[:19])
        + ", ... "
        + authors[-1]
    )


# ============================================================================
# URL / DOI NORMALIZATION
# ============================================================================

def _doi_url(
    doi: str,
) -> str:
    """
    Convert DOI variants into a clean HTTPS URL.
    """

    doi = clean_text(doi)

    if not doi:
        return ""

    doi = re.sub(
        r"^https?://doi\.org/",
        "",
        doi,
        flags=re.IGNORECASE,
    )

    doi = re.sub(
        r"^doi:",
        "",
        doi,
        flags=re.IGNORECASE,
    )

    return (
        f"https://doi.org/{doi}"
    )


def _clean_url(
    url: str,
) -> str:

    url = clean_text(url)

    if not url:
        return ""

    return url.strip()


# ============================================================================
# CITATION FORMATTING
# ============================================================================

def format_citation(
    source: dict,
    style: str = "APA",
) -> str:
    """
    Format a normalized source citation.
    """

    normalized = normalize_source(
        source
    )

    style = clean_text(
        style or "APA"
    ).upper()

    if style not in SUPPORTED_STYLES:
        style = "APA"

    if style == "APA":
        return _format_apa(
            normalized
        )

    if style == "MLA":
        return _format_mla(
            normalized
        )

    if style == "CHICAGO":
        return _format_chicago(
            normalized
        )

    return _format_simple(
        normalized
    )


def _format_apa(
    source: dict,
) -> str:

    title = clean_text(
        source.get(
            "title",
            "Unknown source",
        )
    )

    year = _extract_year(
        source.get("date")
    )

    authors = _format_authors_apa(
        source.get("authors", [])
    )

    publisher = clean_text(
        source.get("publisher", "")
    )

    doi = clean_text(
        source.get("doi", "")
    )

    url = _clean_url(
        source.get("url", "")
    )

    result = (
        f"{authors} ({year}). "
        f"{title}."
    )

    if publisher:
        result += (
            f" {publisher}."
        )

    if doi:
        result += (
            f" {_doi_url(doi)}"
        )

    elif url:
        result += (
            f" {url}"
        )

    return result


def _format_mla(
    source: dict,
) -> str:

    title = clean_text(
        source.get(
            "title",
            "Unknown source",
        )
    )

    authors = source.get(
        "authors",
        [],
    )

    date = clean_text(
        source.get(
            "date",
            "n.d.",
        )
    )

    url = _clean_url(
        source.get("url", "")
    )

    author_str = (
        authors[0]
        if authors
        else "Unknown"
    )

    result = (
        f'{author_str}. "{title}." '
        f"{date}."
    )

    if url:
        result += (
            f" {url}"
        )

    elif source.get("doi"):
        result += (
            f" {_doi_url(source['doi'])}"
        )

    return result


def _format_chicago(
    source: dict,
) -> str:

    title = clean_text(
        source.get(
            "title",
            "Unknown source",
        )
    )

    authors = source.get(
        "authors",
        [],
    )

    date = clean_text(
        source.get(
            "date",
            "n.d.",
        )
    )

    url = _clean_url(
        source.get("url", "")
    )

    author_str = (
        ", ".join(authors)
        if authors
        else "Unknown"
    )

    result = (
        f'{author_str}. "{title}." '
        f"{date}."
    )

    if url:
        result += (
            f" {url}"
        )

    elif source.get("doi"):
        result += (
            f" {_doi_url(source['doi'])}"
        )

    return result


def _format_simple(
    source: dict,
) -> str:

    title = clean_text(
        source.get(
            "title",
            "Unknown source",
        )
    )

    date = clean_text(
        source.get(
            "date",
            "n.d.",
        )
    )

    url = _clean_url(
        source.get("url", "")
    )

    result = (
        f"{title} ({date})"
    )

    if url:
        result += (
            f" - {url}"
        )

    elif source.get("doi"):
        result += (
            f" - {_doi_url(source['doi'])}"
        )

    return result


# ============================================================================
# CITATION REGISTRATION
# ============================================================================

def add_citation(
    citations_list: Optional[list],
    source: dict,
) -> list:
    """
    Add a citation while preserving provenance and preventing duplicates.
    """

    if citations_list is None:
        citations_list = []

    normalized = normalize_source(
        source
    )

    if not normalized:
        return citations_list

    citation_id = normalized.get(
        "citation_id"
    )

    for existing in citations_list:

        existing_normalized = (
            normalize_source(existing)
        )

        if (
            existing_normalized.get(
                "citation_id"
            )
            == citation_id
        ):
            return citations_list

    normalized["added_at"] = _utc_now()

    citations_list.append(
        normalized
    )

    return citations_list


# ============================================================================
# MERGE CITATIONS
# ============================================================================

def merge_citations(
    citations_lists: Optional[
        List[List[dict]]
    ],
) -> List[dict]:

    merged = []
    seen = set()

    for citation_list in (
        citations_lists or []
    ):

        for source in (
            citation_list or []
        ):

            normalized = normalize_source(
                source
            )

            if not normalized:
                continue

            citation_id = normalized[
                "citation_id"
            ]

            if citation_id in seen:
                continue

            seen.add(citation_id)

            merged.append(
                normalized
            )

    return merged


# ============================================================================
# HUMAN-READABLE REFERENCES
# ============================================================================

def format_report_citations(
    sources: list,
    style: str = "APA",
) -> str:
    """
    Generate a clean human-readable References section.

    Designed specifically for insertion into the final PDF.
    """

    if not sources:
        return (
            "## References\n\n"
            "No references available.\n"
        )

    normalized = [
        normalize_source(source)
        for source in sources
        if source
    ]

    normalized = [
        source
        for source in normalized
        if source
    ]

    normalized.sort(
        key=lambda x: (
            clean_text(
                x.get("title", "")
            ).lower(),
            clean_text(
                x.get("date", "")
            ).lower(),
        )
    )

    lines = [
        "## References",
        "",
    ]

    for index, source in enumerate(
        normalized,
        start=1,
    ):

        citation = format_citation(
            source,
            style,
        )

        citation_id = source.get(
            "citation_id",
            "",
        )

        lines.append(
            f"{index}. {citation}"
        )

        if citation_id:
            lines.append(
                f"   Source ID: {citation_id}"
            )

        lines.append("")

    return "\n".join(lines).strip() + "\n"


# ============================================================================
# CITATION VALIDATION
# ============================================================================

def validate_citations(
    citations: list,
) -> bool:
    """
    Validate citation records.

    A source does NOT strictly require a URL if it has another
    strong identifier such as DOI, arXiv ID, SEC accession number,
    or dataset ID.
    """

    if not isinstance(
        citations,
        list,
    ):
        raise ValueError(
            "Citations must be a list."
        )

    for index, citation in enumerate(
        citations
    ):

        if not isinstance(
            citation,
            dict,
        ):
            raise ValueError(
                f"Citation {index} is not an object."
            )

        normalized = normalize_source(
            citation
        )

        if not normalized.get(
            "title"
        ):
            raise ValueError(
                f"Citation {index} is missing title."
            )

        has_reference = any([
            normalized.get("url"),
            normalized.get("doi"),
            normalized.get("arxiv_id"),
            normalized.get("accession_number"),
            normalized.get("dataset_id"),
        ])

        if not has_reference:
            raise ValueError(
                f"Citation {index} has no URL, DOI, "
                "arXiv ID, accession number, or dataset ID."
            )

        url = normalized.get(
            "url",
            "",
        )

        if url and not url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            raise ValueError(
                f"Citation {index} contains an invalid URL."
            )

    return True


# ============================================================================
# CITATION QUALITY
# ============================================================================

def validate_citation_quality(
    citations: list,
) -> dict:

    results = {
        "valid": True,
        "total": len(
            citations or []
        ),
        "checks": [],
        "quality_score": 0.0,
    }

    if not citations:
        results["valid"] = False
        results["checks"].append(
            "No citations supplied."
        )
        return results

    normalized = [
        normalize_source(citation)
        for citation in citations
    ]

    normalized = [
        source
        for source in normalized
        if source
    ]

    if not normalized:
        results["valid"] = False
        results["checks"].append(
            "No valid citation records."
        )
        return results

    score = 0.0

    # ------------------------------------------------------------------
    # Metadata completeness
    # ------------------------------------------------------------------

    metadata_complete = 0

    for source in normalized:

        has_title = bool(
            source.get("title")
        )

        has_reference = any([
            source.get("url"),
            source.get("doi"),
            source.get("arxiv_id"),
            source.get("accession_number"),
            source.get("dataset_id"),
        ])

        has_date = (
            source.get("date")
            not in (
                "",
                "n.d.",
                None,
            )
        )

        has_type = bool(
            source.get("source_type")
        )

        has_provenance = bool(
            source.get("retrieved_at")
        )

        completeness = sum([
            has_title,
            has_reference,
            has_date,
            has_type,
            has_provenance,
        ])

        if completeness >= 4:
            metadata_complete += 1

    metadata_ratio = (
        metadata_complete
        / len(normalized)
    )

    score += (
        metadata_ratio * 0.30
    )

    results["checks"].append(
        "Source metadata completeness: "
        f"{metadata_complete}/{len(normalized)}"
    )

    # ------------------------------------------------------------------
    # Source diversity
    # ------------------------------------------------------------------

    source_types = {
        source.get(
            "source_type"
        )
        for source in normalized
    }

    diversity_score = min(
        len(source_types) / 4,
        1.0,
    )

    score += (
        diversity_score * 0.20
    )

    results["checks"].append(
        "Evidence source diversity: "
        f"{len(source_types)} source types"
    )

    # ------------------------------------------------------------------
    # Stable identities
    # ------------------------------------------------------------------

    with_identity = sum(
        1
        for source in normalized
        if source.get(
            "citation_id"
        )
    )

    identity_ratio = (
        with_identity
        / len(normalized)
    )

    score += (
        identity_ratio * 0.20
    )

    results["checks"].append(
        "Stable citation identities: "
        f"{with_identity}/{len(normalized)}"
    )

    # ------------------------------------------------------------------
    # Strong identifiers
    # ------------------------------------------------------------------

    strong_identifier_count = sum(
        1
        for source in normalized
        if any([
            source.get("doi"),
            source.get("arxiv_id"),
            source.get("accession_number"),
            source.get("dataset_id"),
        ])
    )

    identifier_ratio = (
        strong_identifier_count
        / len(normalized)
    )

    score += (
        identifier_ratio * 0.15
    )

    results["checks"].append(
        "Primary source identifiers present: "
        f"{strong_identifier_count}/{len(normalized)}"
    )

    # ------------------------------------------------------------------
    # Valid URLs
    # ------------------------------------------------------------------

    valid_urls = sum(
        1
        for source in normalized
        if str(
            source.get("url", "")
        ).startswith(
            (
                "http://",
                "https://",
            )
        )
    )

    url_ratio = (
        valid_urls
        / len(normalized)
    )

    score += (
        url_ratio * 0.15
    )

    results["checks"].append(
        "Valid source URLs: "
        f"{valid_urls}/{len(normalized)}"
    )

    results["quality_score"] = round(
        min(score, 1.0),
        4,
    )

    if results["quality_score"] < 0.60:
        results["valid"] = False
        results["checks"].append(
            "Citation quality below publication threshold."
        )
    else:
        results["checks"].append(
            "Citation quality meets minimum threshold."
        )

    return results


# ============================================================================
# MARKDOWN / URL CITATION EXTRACTION
# ============================================================================

def extract_citations_from_text(
    text: str,
) -> List[dict]:
    """
    Extract citation-like references from report text.

    Supports:

        [Title](https://example.com)

        https://example.com

        DOI references

    Publication dates are never inferred from URLs.
    """

    text = clean_text(text)

    if not text:
        return []

    citations = []
    seen_urls = set()

    # ------------------------------------------------------------------
    # Markdown links
    # ------------------------------------------------------------------

    markdown_pattern = re.compile(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        re.IGNORECASE,
    )

    for match in markdown_pattern.finditer(
        text
    ):

        title = clean_text(
            match.group(1)
        )

        url = clean_text(
            match.group(2)
        )

        if url.lower() in seen_urls:
            continue

        seen_urls.add(
            url.lower()
        )

        citations.append(
            normalize_source({
                "title": title,
                "url": url,
                "date": "n.d.",
                "source_type": "webpage",
                "retrieved_at": _utc_now(),
            })
        )

    # ------------------------------------------------------------------
    # Raw URLs
    # ------------------------------------------------------------------

    url_pattern = re.compile(
        r"(?<![\"'=])(https?://[^\s<>\]\)]+)",
        re.IGNORECASE,
    )

    for match in url_pattern.finditer(
        text
    ):

        url = (
            match.group(1)
            .rstrip(".,;")
        )

        if url.lower() in seen_urls:
            continue

        seen_urls.add(
            url.lower()
        )

        citations.append(
            normalize_source({
                "title": url,
                "url": url,
                "date": "n.d.",
                "source_type": "webpage",
                "retrieved_at": _utc_now(),
            })
        )

    return citations


# ============================================================================
# SOURCE ID EXTRACTION
# ============================================================================

def extract_source_ids(
    text: str,
) -> List[str]:
    """
    Extract CTS-NPN source identifiers.

    Examples:

        SRC-ABC123

        Source ID: SRC-ABC123
    """

    text = clean_text(text)

    if not text:
        return []

    pattern = re.compile(
        r"\bSRC-[A-Za-z0-9]+\b",
        re.IGNORECASE,
    )

    found = pattern.findall(
        text
    )

    result = []
    seen = set()

    for source_id in found:

        normalized = source_id.upper()

        if normalized not in seen:
            seen.add(normalized)
            result.append(
                normalized
            )

    return result


# ============================================================================
# EVIDENCE MODEL
# ============================================================================

def create_evidence_reference(
    source: dict,
    *,
    evidence_id: str,
    passage: str = "",
    section: str = "",
    page: Optional[Any] = None,
    relevance_score: Optional[float] = None,
    evidence_type: str = "qualitative",
    methodology: Optional[dict] = None,
    quantitative_result: Optional[dict] = None,
    limitations: Optional[List[str]] = None,
) -> dict:
    """
    Create structured evidence record.
    """

    normalized_source = normalize_source(
        source
    )

    if relevance_score is not None:
        relevance_score = max(
            0.0,
            min(
                float(relevance_score),
                1.0,
            ),
        )

    return {
        "evidence_id": clean_text(
            evidence_id
        ),
        "citation_id": normalized_source.get(
            "citation_id"
        ),
        "source": normalized_source,
        "passage": clean_text(
            passage
        ),
        "section": clean_text(
            section
        ),
        "page": page,
        "relevance_score": relevance_score,
        "evidence_type": clean_text(
            evidence_type
            or "qualitative"
        ),
        "methodology": (
            decode_nested_value(
                methodology or {}
            )
        ),
        "quantitative_result": (
            decode_nested_value(
                quantitative_result or {}
            )
        ),
        "limitations": [
            clean_text(item)
            for item in (
                limitations or []
            )
        ],
        "created_at": _utc_now(),
    }


# ============================================================================
# CLAIM MODEL
# ============================================================================

def create_claim(
    *,
    claim_id: str,
    claim: str,
    evidence_ids: Optional[List[str]] = None,
    claim_type: str = "finding",
    confidence: Optional[float] = None,
    quantitative: Optional[dict] = None,
    attribution: str = "source_reported",
) -> dict:
    """
    Create a research claim.

    Attribution distinguishes:

        source_reported
        system_calculated
        system_inferred
        analyst_interpretation
    """

    attribution = clean_text(
        attribution
        or "source_reported"
    )

    if attribution not in ATTRIBUTION_TYPES:
        attribution = (
            "source_reported"
        )

    if confidence is not None:
        confidence = max(
            0.0,
            min(
                float(confidence),
                1.0,
            ),
        )

    return {
        "claim_id": clean_text(
            claim_id
        ),
        "claim": clean_text(
            claim
        ),
        "claim_type": clean_text(
            claim_type
        ),
        "evidence_ids": [
            clean_text(item)
            for item in (
                evidence_ids or []
            )
            if clean_text(item)
        ],
        "confidence": confidence,
        "quantitative": (
            decode_nested_value(
                quantitative or {}
            )
        ),
        "attribution": attribution,
        "created_at": _utc_now(),
    }


# ============================================================================
# CITATION COVERAGE
# ============================================================================

def calculate_citation_coverage(
    claims: list,
) -> dict:
    """
    Calculate percentage of claims having explicit evidence IDs.

    This is structural coverage only.

    It does NOT prove semantic correctness.
    """

    total = len(
        claims or []
    )

    if total == 0:
        return {
            "total_claims": 0,
            "supported_claims": 0,
            "unsupported_claims": 0,
            "coverage": 0.0,
        }

    supported = sum(
        1
        for claim in claims
        if claim.get(
            "evidence_ids"
        )
    )

    unsupported = (
        total - supported
    )

    return {
        "total_claims": total,
        "supported_claims": supported,
        "unsupported_claims": unsupported,
        "coverage": round(
            supported / total,
            4,
        ),
    }


# ============================================================================
# UNSUPPORTED CLAIM DETECTION
# ============================================================================

def find_unsupported_claims(
    claims: list,
) -> List[dict]:

    unsupported = []

    for claim in claims or []:

        if not claim.get(
            "evidence_ids"
        ):
            unsupported.append(
                claim
            )

    return unsupported


# ============================================================================
# EVIDENCE STRENGTH
# ============================================================================

def classify_evidence_strength(
    evidence: dict,
) -> str:
    """
    Heuristic evidence classification.

    STRONG:
        identifiable source
        + contextual passage
        + methodology or quantitative result

    MODERATE:
        identifiable/reputable source
        + relevant passage

    LIMITED:
        metadata without sufficient context
    """

    evidence = (
        decode_nested_value(
            evidence
        )
        if evidence
        else {}
    )

    if not isinstance(
        evidence,
        dict,
    ):
        return "LIMITED"

    source = evidence.get(
        "source",
        {},
    )

    passage = clean_text(
        evidence.get(
            "passage",
            "",
        )
    )

    methodology = (
        evidence.get(
            "methodology",
            {},
        )
        or {}
    )

    quantitative = (
        evidence.get(
            "quantitative_result",
            {},
        )
        or {}
    )

    source_type = source.get(
        "source_type",
        "other",
    )

    has_identifier = any([
        source.get("doi"),
        source.get("arxiv_id"),
        source.get("accession_number"),
        source.get("dataset_id"),
    ])

    reputable_source = source_type in {
        "government",
        "cms",
        "cdc",
        "academic_paper",
        "arxiv",
        "sec_edgar",
        "dataset",
    }

    if (
        has_identifier
        and passage
        and (
            methodology
            or quantitative
        )
    ):
        return "STRONG"

    if passage and (
        has_identifier
        or reputable_source
    ):
        return "MODERATE"

    return "LIMITED"


# ============================================================================
# QUANTITATIVE RESULT
# ============================================================================

def create_quantitative_result(
    *,
    metric: str,
    value: Any,
    unit: str = "",
    statistic: str = "",
    confidence_interval: Optional[Any] = None,
    p_value: Optional[Any] = None,
    sample_size: Optional[Any] = None,
    reported_by_source: bool = True,
    calculation_method: str = "",
) -> dict:
    """
    Normalize quantitative research result.
    """

    return {
        "metric": clean_text(
            metric
        ),
        "value": decode_nested_value(
            value
        ),
        "unit": clean_text(
            unit
        ),
        "statistic": clean_text(
            statistic
        ),
        "confidence_interval": (
            decode_nested_value(
                confidence_interval
            )
        ),
        "p_value": decode_nested_value(
            p_value
        ),
        "sample_size": decode_nested_value(
            sample_size
        ),
        "reported_by_source": bool(
            reported_by_source
        ),
        "calculation_method": clean_text(
            calculation_method
        ),
        "created_at": _utc_now(),
    }


# ============================================================================
# SOURCE PROVENANCE AUDIT
# ============================================================================

def audit_source_provenance(
    source: dict,
) -> dict:

    normalized = normalize_source(
        source
    )

    checks = {
        "title": bool(
            normalized.get("title")
        ),
        "reference": any([
            normalized.get("url"),
            normalized.get("doi"),
            normalized.get("arxiv_id"),
            normalized.get("accession_number"),
            normalized.get("dataset_id"),
        ]),
        "date": (
            normalized.get("date")
            not in (
                "",
                "n.d.",
                None,
            )
        ),
        "source_type": bool(
            normalized.get(
                "source_type"
            )
        ),
        "retrieved_at": bool(
            normalized.get(
                "retrieved_at"
            )
        ),
        "stable_identifier": any([
            normalized.get("doi"),
            normalized.get("arxiv_id"),
            normalized.get("accession_number"),
            normalized.get("dataset_id"),
            normalized.get("url"),
        ]),
    }

    passed = sum(
        1
        for value in checks.values()
        if value
    )

    return {
        "citation_id": normalized.get(
            "citation_id"
        ),
        "checks": checks,
        "score": round(
            passed / len(checks),
            4,
        ),
        "complete": (
            passed == len(checks)
        ),
    }


# ============================================================================
# CLAIM/EVIDENCE LINK VERIFICATION
# ============================================================================

def verify_claim_evidence_links(
    claims: List[dict],
    evidence: List[dict],
) -> dict:
    """
    Verify that every evidence ID referenced by a claim exists.
    """

    evidence_ids = {
        clean_text(
            item.get(
                "evidence_id",
                "",
            )
        )
        for item in (
            evidence or []
        )
    }

    valid_links = 0
    broken_links = 0
    broken_claims = []

    for claim in claims or []:

        claim_id = claim.get(
            "claim_id"
        )

        claim_evidence_ids = (
            claim.get(
                "evidence_ids"
            )
            or []
        )

        claim_broken = False

        for evidence_id in (
            claim_evidence_ids
        ):

            normalized_id = clean_text(
                evidence_id
            )

            if normalized_id not in evidence_ids:

                broken_links += 1
                claim_broken = True

            else:

                valid_links += 1

        if claim_broken:
            broken_claims.append(
                claim
            )

    return {
        "valid": (
            len(broken_claims) == 0
        ),
        "valid_links": valid_links,
        "broken_links": broken_links,
        "claims_with_broken_links": (
            broken_claims
        ),
    }


# ============================================================================
# EVIDENCE TRACEABILITY TABLE
# ============================================================================

def build_traceability_records(
    claims: Optional[List[dict]] = None,
    evidence: Optional[List[dict]] = None,
) -> List[dict]:
    """
    Build flattened claim -> evidence -> source records.

    This is particularly useful for the final PDF.
    """

    claims = claims or []
    evidence = evidence or []

    evidence_map = {}

    for item in evidence:

        evidence_id = clean_text(
            item.get(
                "evidence_id",
                "",
            )
        )

        if evidence_id:
            evidence_map[
                evidence_id
            ] = item

    records = []

    for claim in claims:

        claim_id = clean_text(
            claim.get(
                "claim_id",
                "",
            )
        )

        claim_text = clean_text(
            claim.get(
                "claim",
                "",
            )
        )

        attribution = clean_text(
            claim.get(
                "attribution",
                "source_reported",
            )
        )

        evidence_ids = (
            claim.get(
                "evidence_ids"
            )
            or []
        )

        for evidence_id in evidence_ids:

            evidence_item = (
                evidence_map.get(
                    clean_text(
                        evidence_id
                    )
                )
            )

            if not evidence_item:
                records.append({
                    "claim_id": claim_id,
                    "claim": claim_text,
                    "evidence_id": clean_text(
                        evidence_id
                    ),
                    "citation_id": "",
                    "source_title": "",
                    "source_url": "",
                    "passage": "",
                    "evidence_strength": "BROKEN_LINK",
                    "attribution": attribution,
                })
                continue

            source = normalize_source(
                evidence_item.get(
                    "source",
                    {},
                )
            )

            records.append({
                "claim_id": claim_id,
                "claim": claim_text,
                "evidence_id": clean_text(
                    evidence_id
                ),
                "citation_id": source.get(
                    "citation_id",
                    "",
                ),
                "source_title": clean_text(
                    source.get(
                        "title",
                        "",
                    )
                ),
                "source_url": clean_text(
                    source.get(
                        "url",
                        "",
                    )
                ),
                "passage": clean_text(
                    evidence_item.get(
                        "passage",
                        "",
                    )
                ),
                "evidence_strength": (
                    classify_evidence_strength(
                        evidence_item
                    )
                ),
                "attribution": attribution,
            })

    return records


# ============================================================================
# HUMAN-READABLE TRACEABILITY REPORT
# ============================================================================

def format_traceability_report(
    claims: Optional[List[dict]] = None,
    evidence: Optional[List[dict]] = None,
) -> str:
    """
    Generate a clean human-readable evidence traceability section
    suitable for the final research PDF.
    """

    records = build_traceability_records(
        claims=claims,
        evidence=evidence,
    )

    if not records:
        return (
            "## Evidence Traceability\n\n"
            "No claim-to-evidence mappings are available.\n"
        )

    lines = [
        "## Evidence Traceability",
        "",
    ]

    for index, record in enumerate(
        records,
        start=1,
    ):

        lines.append(
            f"### Trace {index}"
        )

        if record["claim"]:
            lines.append(
                f"**Claim:** {record['claim']}"
            )

        if record["attribution"]:
            lines.append(
                f"**Attribution:** {record['attribution']}"
            )

        if record["evidence_id"]:
            lines.append(
                f"**Evidence ID:** {record['evidence_id']}"
            )

        if record["citation_id"]:
            lines.append(
                f"**Source ID:** {record['citation_id']}"
            )

        if record["source_title"]:
            lines.append(
                f"**Source:** {record['source_title']}"
            )

        if record["source_url"]:
            lines.append(
                f"**URL:** {record['source_url']}"
            )

        if record["evidence_strength"]:
            lines.append(
                f"**Evidence Strength:** "
                f"{record['evidence_strength']}"
            )

        if record["passage"]:
            lines.append(
                f"**Supporting Passage:** "
                f"{record['passage']}"
            )

        lines.append("")

    return "\n".join(lines).strip() + "\n"


# ============================================================================
# CITATION MANIFEST
# ============================================================================

def create_citation_manifest(
    sources: Optional[List[dict]] = None,
    claims: Optional[List[dict]] = None,
    evidence: Optional[List[dict]] = None,
) -> dict:
    """
    Create machine-readable provenance manifest.

    Designed to be stored beside the final report in S3.
    """

    normalized_sources = merge_citations(
        [
            sources or []
        ]
    )

    claims = claims or []
    evidence = evidence or []

    coverage = calculate_citation_coverage(
        claims
    )

    link_validation = (
        verify_claim_evidence_links(
            claims,
            evidence,
        )
    )

    quality = validate_citation_quality(
        normalized_sources
    )

    return {
        "manifest_version": "2.0",
        "generated_at": _utc_now(),

        "sources": normalized_sources,

        "claims": [
            decode_nested_value(
                claim
            )
            for claim in claims
        ],

        "evidence": [
            decode_nested_value(
                item
            )
            for item in evidence
        ],

        "traceability": (
            build_traceability_records(
                claims,
                evidence,
            )
        ),

        "citation_coverage": coverage,

        "claim_evidence_link_validation": (
            link_validation
        ),

        "citation_quality": quality,

        "source_count": len(
            normalized_sources
        ),

        "claim_count": len(
            claims
        ),

        "evidence_count": len(
            evidence
        ),
    }


# ============================================================================
# CITATION LOOKUP
# ============================================================================

def get_citation_by_id(
    citations: Iterable[dict],
    citation_id: str,
) -> Optional[dict]:
    """
    Find citation by stable citation ID.
    """

    if not citation_id:
        return None

    target = clean_text(
        citation_id
    ).upper()

    for citation in (
        citations or []
    ):

        normalized = normalize_source(
            citation
        )

        if (
            clean_text(
                normalized.get(
                    "citation_id",
                    "",
                )
            ).upper()
            == target
        ):
            return normalized

    return None


def get_evidence_by_id(
    evidence_items: Iterable[dict],
    evidence_id: str,
) -> Optional[dict]:
    """
    Find evidence record by evidence ID.
    """

    if not evidence_id:
        return None

    target = clean_text(
        evidence_id
    )

    for evidence in (
        evidence_items or []
    ):

        if (
            clean_text(
                evidence.get(
                    "evidence_id",
                    "",
                )
            )
            == target
        ):
            return evidence

    return None


# ============================================================================
# PDF-SAFE TEXT
# ============================================================================

def citation_text_for_pdf(
    source: dict,
    style: str = "APA",
) -> str:
    """
    Return citation text specifically prepared for PDF rendering.

    This strips problematic HTML/JSON escaping while preserving
    the actual citation information.
    """

    citation = format_citation(
        source,
        style,
    )

    return clean_text(
        citation
    )


def references_for_pdf(
    sources: Optional[List[dict]] = None,
    style: str = "APA",
) -> List[str]:
    """
    Return references as a clean list.

    The PDF generator can turn each item into a ReportLab Paragraph.
    """

    normalized = merge_citations(
        [
            sources or []
        ]
    )

    normalized.sort(
        key=lambda x: (
            clean_text(
                x.get("title", "")
            ).lower(),
            clean_text(
                x.get("date", "")
            ).lower(),
        )
    )

    references = []

    for index, source in enumerate(
        normalized,
        start=1,
    ):

        citation = citation_text_for_pdf(
            source,
            style,
        )

        citation_id = source.get(
            "citation_id"
        )

        if citation_id:
            citation += (
                f" [Source ID: {citation_id}]"
            )

        references.append(
            f"{index}. {citation}"
        )

    return references