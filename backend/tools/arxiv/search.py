"""
CTS-NPN ArXiv Research Retrieval Tool
======================================

Purpose
-------
Provides research-grade retrieval from the public arXiv API.

For every retrieved paper, this module attempts to construct a structured
research-evidence record containing:

1. Bibliographic metadata
2. Abstract
3. Authors
4. arXiv identifier
5. Categories
6. Publication/update dates
7. PDF and abstract URLs
8. Search-query provenance
9. Relevance signals
10. Research-method signals
11. Quantitative-result signals
12. Limitations signals
13. Evidence passages extracted from the abstract
14. Passage context
15. Source provenance
16. Retrieval timestamp

The downstream Evidence, Critic, and Synthesis agents can therefore reason
over structured evidence rather than merely receiving a list of paper titles.

Important
---------
The arXiv Atom API provides structured metadata and abstracts. It does not
guarantee full-text article passages through the legacy query endpoint.

Therefore, this module NEVER invents full-text passages.

If full-text retrieval is unavailable, the returned record explicitly states
that the available evidence text scope is the abstract.
"""

from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from backend.common.config import MAX_RESULTS


# ============================================================================
# CONSTANTS
# ============================================================================

ARXIV_API_URL = "https://export.arxiv.org/api/query"

ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

DEFAULT_TIMEOUT = 20

# Be conservative with the public arXiv endpoint.
DEFAULT_REQUEST_DELAY = 1.0

# Maximum number of papers returned by a single invocation.
HARD_MAX_RESULTS = 100


# ============================================================================
# PUBLIC API
# ============================================================================

def search(
    query: str,
    max_results: Optional[int] = None,
    *,
    start: int = 0,
    sort_by: str = "relevance",
    sort_order: str = "descending",
    include_passages: bool = True,
) -> List[Dict[str, Any]]:
    """
    Search arXiv and return research-grade structured evidence.

    Parameters
    ----------
    query:
        Natural-language or arXiv search expression.

    max_results:
        Number of papers to retrieve.

    start:
        Pagination offset.

    sort_by:
        arXiv sorting mode.

    sort_order:
        ascending or descending.

    include_passages:
        Whether to construct evidence passages from the available
        abstract text.

    Returns
    -------
    list[dict]
        Structured paper evidence records.

    Notes
    -----
    This function is deliberately fault tolerant.

    A failed external research source must not crash the entire
    Step Functions execution.
    """

    query = _normalize_query(query)

    if not query:
        return []

    # Use application configuration when available.
    if max_results is None:
        max_results = MAX_RESULTS

    try:
        max_results = int(max_results)
    except (TypeError, ValueError):
        max_results = MAX_RESULTS

    max_results = max(
        1,
        min(max_results, HARD_MAX_RESULTS),
    )

    try:
        start = int(start)
    except (TypeError, ValueError):
        start = 0

    start = max(0, start)

    # Validate sorting options.
    allowed_sort_by = {
        "relevance",
        "lastUpdatedDate",
        "submittedDate",
    }

    allowed_sort_order = {
        "ascending",
        "descending",
    }

    if sort_by not in allowed_sort_by:
        sort_by = "relevance"

    if sort_order not in allowed_sort_order:
        sort_order = "descending"

    params = {
        "search_query": _build_search_expression(query),
        "start": start,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }

    try:
        response = requests.get(
            ARXIV_API_URL,
            params=params,
            headers={
                "User-Agent": (
                    "CTS-NPN-Research-Agent/1.0 "
                    "(research retrieval; contact administrator)"
                ),
                "Accept": "application/atom+xml",
            },
            timeout=DEFAULT_TIMEOUT,
        )

        response.raise_for_status()

        papers = _parse_feed(
            response.content,
            query=query,
            include_passages=include_passages,
        )

        return papers

    except requests.exceptions.Timeout as exc:
        print(f"[ArXiv] Request timeout: {exc}")
        return []

    except requests.exceptions.RequestException as exc:
        print(f"[ArXiv] Request failed: {exc}")
        return []

    except ET.ParseError as exc:
        print(f"[ArXiv] XML parsing failed: {exc}")
        return []

    except Exception as exc:
        print(f"[ArXiv] Unexpected retrieval error: {exc}")
        return []


def search_pages(
    query: str,
    *,
    pages: int = 2,
    page_size: Optional[int] = None,
    include_passages: bool = True,
) -> List[Dict[str, Any]]:
    """
    Retrieve multiple pages of arXiv results.

    This is useful when the planner wants broader evidence discovery
    instead of relying on the first result page.
    """

    if page_size is None:
        page_size = min(MAX_RESULTS, 20)

    try:
        page_size = int(page_size)
    except (TypeError, ValueError):
        page_size = 20

    page_size = max(
        1,
        min(page_size, HARD_MAX_RESULTS),
    )

    try:
        pages = int(pages)
    except (TypeError, ValueError):
        pages = 2

    pages = max(1, min(pages, 10))

    all_papers: List[Dict[str, Any]] = []

    for page_number in range(pages):

        start = page_number * page_size

        papers = search(
            query,
            max_results=page_size,
            start=start,
            include_passages=include_passages,
        )

        if not papers:
            break

        all_papers.extend(papers)

        # Be conservative with the public endpoint.
        if page_number < pages - 1:
            time.sleep(DEFAULT_REQUEST_DELAY)

    return _deduplicate_papers(all_papers)


# ============================================================================
# QUERY CONSTRUCTION
# ============================================================================

def _normalize_query(query: Any) -> str:
    """
    Normalize researcher-provided search text without destroying
    meaningful research terminology.
    """

    if query is None:
        return ""

    query = str(query)

    # Remove null bytes.
    query = query.replace("\x00", " ")

    # Normalize whitespace.
    query = re.sub(r"\s+", " ", query)

    return query.strip()


def _build_search_expression(query: str) -> str:
    """
    Construct an arXiv search expression.

    For natural-language questions, search across title and abstract
    rather than treating the entire question as one exact token.

    If the caller already supplied an arXiv field expression, preserve it.
    """

    lowered = query.lower()

    arxiv_field_tokens = (
        "all:",
        "ti:",
        "au:",
        "abs:",
        "cat:",
        "id:",
    )

    if any(token in lowered for token in arxiv_field_tokens):
        return query

    # Extract meaningful terms.
    tokens = re.findall(
        r"[A-Za-z0-9][A-Za-z0-9\-']+",
        query,
    )

    stopwords = {
        "what",
        "which",
        "where",
        "when",
        "why",
        "how",
        "does",
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "this",
        "that",
        "these",
        "those",
        "about",
        "using",
        "used",
        "use",
        "research",
        "study",
        "studies",
        "paper",
        "papers",
    }

    meaningful = [
        token
        for token in tokens
        if token.lower() not in stopwords
        and len(token) >= 3
    ]

    if not meaningful:
        meaningful = tokens

    # Limit expression size.
    meaningful = meaningful[:12]

    clauses = []

    for token in meaningful:

        safe = token.replace('"', "")

        clauses.append(
            f'(ti:"{safe}" OR abs:"{safe}")'
        )

    if not clauses:
        safe_query = query.replace('"', "")

        return f'all:"{safe_query}"'

    return " AND ".join(clauses)


# ============================================================================
# XML PARSING
# ============================================================================

def _parse_feed(
    xml_bytes: bytes,
    *,
    query: str,
    include_passages: bool,
) -> List[Dict[str, Any]]:
    """
    Parse an arXiv Atom feed.
    """

    root = ET.fromstring(xml_bytes)

    papers: List[Dict[str, Any]] = []

    for entry in root.findall(
        "atom:entry",
        ATOM_NS,
    ):

        paper = _parse_entry(
            entry,
            query=query,
            include_passages=include_passages,
        )

        if paper:
            papers.append(paper)

    return papers


def _parse_entry(
    entry: ET.Element,
    *,
    query: str,
    include_passages: bool,
) -> Dict[str, Any]:
    """
    Convert a single arXiv Atom entry into a structured evidence record.
    """

    title = _element_text(
        entry,
        "atom:title",
    )

    summary = _element_text(
        entry,
        "atom:summary",
    )

    published = _element_text(
        entry,
        "atom:published",
    )

    updated = _element_text(
        entry,
        "atom:updated",
    )

    arxiv_url = _element_text(
        entry,
        "atom:id",
    )

    # ------------------------------------------------------------------------
    # Authors
    # ------------------------------------------------------------------------

    authors: List[str] = []

    for author in entry.findall(
        "atom:author",
        ATOM_NS,
    ):

        name = _element_text(
            author,
            "atom:name",
        )

        if name:
            authors.append(name)

    # ------------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------------

    categories: List[str] = []

    for category in entry.findall(
        "atom:category",
        ATOM_NS,
    ):

        term = category.attrib.get("term")

        if term:
            categories.append(term)

    # ------------------------------------------------------------------------
    # Links
    # ------------------------------------------------------------------------

    links: Dict[str, str] = {}

    for link in entry.findall(
        "atom:link",
        ATOM_NS,
    ):

        href = link.attrib.get("href")
        rel = link.attrib.get("rel")
        link_type = link.attrib.get("type")

        if not href:
            continue

        if link_type == "application/pdf":
            links["pdf"] = href

        elif rel == "alternate":
            links["abstract"] = href

    # Fallback abstract URL.
    if "abstract" not in links and arxiv_url:
        links["abstract"] = arxiv_url

    # Fallback PDF URL.
    if "pdf" not in links and arxiv_url:

        identifier = _extract_arxiv_id(
            arxiv_url
        )

        if identifier:
            links["pdf"] = (
                f"https://arxiv.org/pdf/{identifier}.pdf"
            )

    identifier = _extract_arxiv_id(
        arxiv_url
    )

    # ------------------------------------------------------------------------
    # Evidence passages
    # ------------------------------------------------------------------------

    evidence_passages: List[Dict[str, Any]] = []

    if include_passages and summary:

        evidence_passages = _extract_evidence_passages(
            summary,
            query,
        )

    # ------------------------------------------------------------------------
    # Research signals
    # ------------------------------------------------------------------------

    research_signals = _extract_research_signals(
        title=title,
        abstract=summary,
    )

    # ------------------------------------------------------------------------
    # Retrieval timestamp
    # ------------------------------------------------------------------------

    retrieved_at = _utc_now()

    # ------------------------------------------------------------------------
    # Final structured record
    # ------------------------------------------------------------------------

    record: Dict[str, Any] = {

        "source": "arXiv",

        "source_type": "research_paper",

        "arxiv_id": identifier,

        "title": _clean_text(title),

        "authors": authors,

        "published_date": published,

        "updated_date": updated,

        "categories": categories,

        "url": links.get(
            "abstract",
            arxiv_url,
        ),

        "abstract_url": links.get(
            "abstract",
            arxiv_url,
        ),

        "pdf_url": links.get(
            "pdf",
            "",
        ),

        "summary": _clean_text(summary),

        "abstract": _clean_text(summary),

        "search_query": query,

        "retrieved_at": retrieved_at,

        "retrieval_method": "arxiv_atom_api",

        "evidence": {

            "available_text_scope": "abstract",

            "passages": evidence_passages,

            "research_signals": research_signals,

            "quantitative_claims": (
                _extract_quantitative_claims(summary)
            ),

            "limitations_signals": _extract_sentences(
                summary,
                [
                    "limitation",
                    "limitations",
                    "future work",
                    "future research",
                    "challenge",
                    "challenges",
                    "however",
                ],
            ),

            "methodology_signals": _extract_sentences(
                summary,
                [
                    "method",
                    "methodology",
                    "model",
                    "algorithm",
                    "dataset",
                    "data",
                    "experiment",
                    "evaluation",
                    "framework",
                    "approach",
                ],
            ),

            "outcome_signals": _extract_sentences(
                summary,
                [
                    "result",
                    "results",
                    "found",
                    "findings",
                    "improved",
                    "improvement",
                    "accuracy",
                    "performance",
                    "significant",
                    "increase",
                    "decrease",
                    "reduced",
                ],
            ),
        },

        "provenance": {

            "provider": "arXiv",

            "api_endpoint": ARXIV_API_URL,

            "query": query,

            "retrieved_at": retrieved_at,

            "retrieval_method": "arxiv_atom_api",

            "full_text_verified": False,

            "evidence_text_scope": "abstract",
        },
    }

    return record


# ============================================================================
# EVIDENCE EXTRACTION
# ============================================================================

def _extract_evidence_passages(
    abstract: str,
    query: str,
) -> List[Dict[str, Any]]:
    """
    Convert the abstract into structured evidence passages.

    This does NOT claim that the passage is a full-text quotation.

    It is explicitly labelled as an abstract passage.
    """

    sentences = _split_sentences(
        abstract
    )

    if not sentences:
        return []

    query_terms = {
        token.lower()
        for token in re.findall(
            r"[A-Za-z0-9][A-Za-z0-9\-']+",
            query,
        )
        if len(token) >= 3
    }

    scored: List[Dict[str, Any]] = []

    for index, sentence in enumerate(sentences):

        sentence_terms = {
            token.lower()
            for token in re.findall(
                r"[A-Za-z0-9][A-Za-z0-9\-']+",
                sentence,
            )
        }

        overlap = len(
            query_terms.intersection(
                sentence_terms
            )
        )

        score = overlap / max(
            len(query_terms),
            1,
        )

        # Boost sentences containing evidence-oriented terminology.
        evidence_terms = [
            "result",
            "results",
            "found",
            "accuracy",
            "performance",
            "significant",
            "dataset",
            "method",
            "evaluation",
            "improved",
            "reduced",
            "increase",
            "decrease",
            "limitation",
        ]

        evidence_hits = sum(
            1
            for term in evidence_terms
            if term in sentence.lower()
        )

        score += min(
            evidence_hits * 0.05,
            0.25,
        )

        scored.append(
            {
                "sentence_index": index,
                "text": sentence.strip(),
                "relevance_score": round(
                    min(score, 1.0),
                    4,
                ),
            }
        )

    scored.sort(
        key=lambda item: item["relevance_score"],
        reverse=True,
    )

    passages: List[Dict[str, Any]] = []

    for item in scored[:8]:

        index = item["sentence_index"]

        start = max(
            0,
            index - 1,
        )

        end = min(
            len(sentences),
            index + 2,
        )

        context = " ".join(
            sentences[start:end]
        )

        passages.append(
            {
                "passage_id": (
                    f"abstract-{index + 1}"
                ),
                "text": item["text"],
                "context": context,
                "source_scope": "abstract",
                "sentence_index": index,
                "relevance_score": item[
                    "relevance_score"
                ],
            }
        )

    return passages


def _extract_research_signals(
    *,
    title: str,
    abstract: str,
) -> Dict[str, Any]:
    """
    Detect research-oriented signals from title and abstract.

    This is keyword-based extraction only.
    It does not claim scientific interpretation.
    """

    text = (
        f"{title}. {abstract}"
    ).lower()

    signals: Dict[str, List[str]] = {

        "study_design": [],

        "data_sources": [],

        "methods": [],

        "evaluation": [],

        "population": [],

        "outcomes": [],
    }

    patterns = {

        "study_design": [
            "randomized",
            "cohort",
            "cross-sectional",
            "longitudinal",
            "retrospective",
            "prospective",
            "observational",
            "simulation",
            "case study",
            "systematic review",
            "meta-analysis",
        ],

        "data_sources": [
            "medicare",
            "claims",
            "electronic health record",
            "ehr",
            "registry",
            "survey",
            "dataset",
            "administrative data",
            "public data",
        ],

        "methods": [
            "machine learning",
            "deep learning",
            "neural network",
            "random forest",
            "gradient boosting",
            "regression",
            "classification",
            "clustering",
            "natural language processing",
            "nlp",
            "reinforcement learning",
            "transformer",
        ],

        "evaluation": [
            "accuracy",
            "precision",
            "recall",
            "f1",
            "auc",
            "auroc",
            "sensitivity",
            "specificity",
            "rmse",
            "mae",
            "r-squared",
            "confidence interval",
            "p-value",
        ],

        "population": [
            "patient",
            "patients",
            "beneficiary",
            "beneficiaries",
            "adult",
            "adults",
            "provider",
            "providers",
            "hospital",
            "hospitals",
        ],

        "outcomes": [
            "emergency department",
            "ed visit",
            "readmission",
            "hospitalization",
            "mortality",
            "cost",
            "utilization",
            "quality",
            "access",
            "telehealth",
        ],
    }

    for group, terms in patterns.items():

        for term in terms:

            if term in text:

                signals[group].append(term)

    return signals


def _extract_quantitative_claims(
    text: str,
) -> List[Dict[str, Any]]:
    """
    Detect quantitative expressions without interpreting them.

    Examples
    --------
    94%
    12.4%
    1,250 patients
    p < 0.05
    AUC 0.87
    95% CI
    """

    if not text:
        return []

    sentences = _split_sentences(
        text
    )

    patterns = [

        # Percentages.
        r"\b\d+(?:\.\d+)?\s*%",

        # Numbers, including comma-separated values.
        r"\b\d+(?:,\d{3})*(?:\.\d+)?\b",

        # P-values.
        r"\bp\s*[<>=]\s*0?\.\d+\b",

        # AUC / AUROC.
        r"\b(?:auc|auroc)\s*[=:]?\s*0?\.\d+\b",

        # Fold / times.
        r"\b\d+(?:\.\d+)?\s*(?:fold|times)\b",

        # Confidence intervals.
        r"\b95%\s*(?:CI|confidence interval)\b",
    ]

    claims: List[Dict[str, Any]] = []

    for sentence in sentences:

        matches: List[str] = []

        for pattern in patterns:

            matches.extend(
                re.findall(
                    pattern,
                    sentence,
                    re.IGNORECASE,
                )
            )

        if matches:

            claims.append(
                {
                    "sentence": sentence.strip(),

                    "values": sorted(
                        set(matches)
                    ),

                    "interpretation": (
                        "Quantitative expression detected; "
                        "no independent interpretation applied."
                    ),
                }
            )

    return claims


def _extract_sentences(
    text: str,
    keywords: List[str],
) -> List[str]:
    """
    Extract sentences containing one or more target keywords.
    """

    sentences = _split_sentences(
        text
    )

    results: List[str] = []

    for sentence in sentences:

        lower = sentence.lower()

        if any(
            keyword.lower() in lower
            for keyword in keywords
        ):

            results.append(
                sentence.strip()
            )

    return results[:10]


# ============================================================================
# HELPERS
# ============================================================================

def _split_sentences(
    text: str,
) -> List[str]:
    """
    Split text into approximate sentences.

    This is intentionally conservative and does not attempt
    full NLP sentence segmentation.
    """

    text = _clean_text(
        text
    )

    if not text:
        return []

    sentences = re.split(
        r"(?<=[.!?])\s+(?=[A-Z0-9])",
        text,
    )

    return [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
    ]


def _element_text(
    parent: ET.Element,
    path: str,
) -> str:
    """
    Safely extract text from an XML element.
    """

    element = parent.find(
        path,
        ATOM_NS,
    )

    if element is None:
        return ""

    if element.text is None:
        return ""

    return _clean_text(
        element.text
    )


def _clean_text(
    value: Any,
) -> str:
    """
    Conservative text cleaning.

    Removes null bytes and normalizes whitespace without
    altering the research meaning.
    """

    if value is None:
        return ""

    value = html.unescape(
        str(value)
    )

    value = value.replace(
        "\x00",
        "",
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def _extract_arxiv_id(
    url: str,
) -> str:
    """
    Extract an arXiv identifier from an arXiv URL.

    Supports:
        https://arxiv.org/abs/2401.12345
        https://arxiv.org/pdf/2401.12345
        https://arxiv.org/pdf/2401.12345.pdf
    """

    if not url:
        return ""

    match = re.search(
        r"arxiv\.org/(?:abs|pdf)/([^/?#]+)",
        url,
        re.IGNORECASE,
    )

    if not match:
        return ""

    identifier = match.group(1)

    # Remove .pdf if present.
    identifier = re.sub(
        r"\.pdf$",
        "",
        identifier,
        flags=re.IGNORECASE,
    )

    return identifier


def _deduplicate_papers(
    papers: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Deduplicate papers using arXiv ID, URL, or title.
    """

    unique: Dict[str, Dict[str, Any]] = {}

    for paper in papers:

        key = (
            paper.get("arxiv_id")
            or paper.get("url")
            or paper.get("title")
        )

        if key:
            unique[key] = paper

    return list(
        unique.values()
    )


def _utc_now() -> str:
    """
    Return the current UTC timestamp in ISO-8601 format.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()