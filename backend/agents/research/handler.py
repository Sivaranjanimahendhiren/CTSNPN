"""
CTS-NPN Research Agent
======================

Purpose
-------
Professional research acquisition and evidence extraction agent for the
CTS-NPN Use Case 7 + Use Case 12 workflow.

IMPORTANT PAYLOAD RULE
----------------------
The complete research payload is persisted to S3.

The Lambda return value is intentionally SMALL so that AWS Step Functions
never receives the complete research/evidence payload.

Step Functions receives only:

{
    "run_id": "...",
    "status": "COMPLETE",
    "artifacts": {
        "research_results_key": "...",
        "evidence_packets_key": "...",
        "citation_registry_key": "...",
        "research_statistics_key": "..."
    },
    "research_statistics": {...},
    "source_error_count": 0
}

This keeps the Step Functions state payload safely below 100 KB.
"""

import hashlib
import json
import re
from html import unescape
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from backend.common.aws import put_json, update_run
from backend.common.config import RESEARCH_BUCKET, MAX_RESULTS
from backend.common.security import clean_text, validate_content
from backend.common.citations import add_citation

from backend.tools.arxiv import search as arxiv_search
from backend.tools.sec import search as sec_search
from backend.tools.cdc import places as cdc_places


# ============================================================================
# CONFIGURATION
# ============================================================================

USER_AGENT = (
    "CTS-NPN-Research-Agent/1.0 "
    "(research workflow; public-data research system)"
)

HTTP_TIMEOUT = 15

MAX_PAPERS_PER_QUERY = max(
    1,
    min(int(MAX_RESULTS or 10), 10),
)

MAX_PASSAGES_PER_PAPER = 12
MAX_PASSAGE_CHARS = 1800
MAX_FULLTEXT_CHARS = 120000

# Hard safety limit for anything accidentally returned to Step Functions.
STEP_FUNCTIONS_MAX_BYTES = 90_000


# ============================================================================
# KEYWORD SETS
# ============================================================================

METHOD_KEYWORDS = [
    "method",
    "methods",
    "methodology",
    "study design",
    "cohort",
    "population",
    "sample",
    "participants",
    "data source",
    "dataset",
    "statistical analysis",
    "regression",
    "machine learning",
    "randomized",
    "retrospective",
    "prospective",
    "cross-sectional",
]

RESULT_KEYWORDS = [
    "results",
    "result",
    "finding",
    "findings",
    "odds ratio",
    "risk ratio",
    "hazard ratio",
    "confidence interval",
    "p-value",
    "p value",
    "significant",
    "association",
    "accuracy",
    "auc",
    "area under the curve",
    "sensitivity",
    "specificity",
    "precision",
    "recall",
    "f1",
    "effect size",
    "relative risk",
    "absolute risk",
    "rate",
    "prevalence",
]

LIMITATION_KEYWORDS = [
    "limitation",
    "limitations",
    "bias",
    "confounding",
    "generalizability",
    "selection bias",
    "data limitation",
    "future work",
    "cannot conclude",
    "cannot establish causality",
]

ED_KEYWORDS = [
    "emergency department",
    "emergency room",
    "ed visit",
    "avoidable",
    "potentially avoidable",
    "ambulatory care sensitive",
    "urgent care",
    "primary care",
    "telehealth",
    "telemedicine",
    "care management",
    "care-management",
    "hospital utilization",
    "healthcare utilization",
    "health care utilization",
]


# ============================================================================
# QUANTITATIVE FINDING REGEX
# ============================================================================

QUANTITATIVE_PATTERN = re.compile(
    r"""
    (
        \b\d+(?:\.\d+)?\s*%
        |
        \b\d+(?:\.\d+)?\s*(?:percent|percentage)
        |
        \b(?:OR|RR|HR|IRR|AOR|CI|AUC)\s*[=:]?\s*
        \d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?
        |
        \bp\s*[<=>]\s*0?\.\d+
        |
        \bn\s*=\s*\d[\d,]*
        |
        \b\d[\d,]*\s*(?:patients|participants|members|visits|encounters)
        |
        \b\d+(?:\.\d+)?\s*(?:million|thousand|billion)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


# ============================================================================
# MAIN LAMBDA
# ============================================================================

def lambda_handler(event, context):
    """
    Execute research acquisition.

    IMPORTANT:
    The complete research payload is written to S3.
    Only lightweight metadata is returned to Step Functions.
    """

    event = event or {}

    run_id = str(
        event.get("run_id", "unknown")
    )

    plan = event.get(
        "plan",
        {},
    )

    if not isinstance(plan, dict):
        plan = {}

    question = clean_text(
        event.get("question", "")
    )

    print(
        f"CTS-NPN Research Agent started. run_id={run_id}"
    )

    try:

        # ====================================================================
        # UPDATE RUN STATUS
        # ====================================================================

        update_run(
            run_id,
            "RESEARCHING",
        )

        # ====================================================================
        # INITIAL RESEARCH RESULT OBJECT
        # ====================================================================

        research_results = {
            "run_id": run_id,
            "question": question,

            "research_methodology": {
                "agent": "CTS-NPN Research Agent",
                "version": "3.0",
                "purpose": (
                    "Acquire traceable public evidence for "
                    "research-to-report generation."
                ),
                "principles": [
                    "Source-first evidence acquisition",
                    "Primary-source preference",
                    "Context-preserving passage extraction",
                    "Quantitative finding extraction",
                    "Methodology extraction",
                    "Limitation extraction",
                    "Citation provenance",
                    "No unsupported inference",
                    "Explicit retrieval failure reporting",
                ],
            },

            "arxiv": [],
            "sec": [],
            "cdc": [],

            "evidence_packets": [],
            "citations": [],

            "research_statistics": {
                "queries_attempted": 0,
                "papers_discovered": 0,
                "papers_with_abstracts": 0,
                "papers_with_fulltext": 0,
                "passages_extracted": 0,
                "quantitative_findings": 0,
                "methodology_passages": 0,
                "results_passages": 0,
                "limitation_passages": 0,
                "sec_records": 0,
                "cdc_records": 0,
            },

            "source_errors": [],
        }

        # ====================================================================
        # 1. ARXIV
        # ====================================================================

        research_queries = plan.get(
            "research_queries",
            [],
        )

        if not isinstance(
            research_queries,
            list,
        ):
            research_queries = []

        for raw_query in research_queries:

            query = _safe_query(
                raw_query
            )

            if not query:
                continue

            research_results[
                "research_statistics"
            ][
                "queries_attempted"
            ] += 1

            try:

                papers = _search_arxiv(
                    query
                )

                # Fallback to configured project search tool.
                if not papers:

                    try:
                        if callable(arxiv_search):
                            papers = arxiv_search(
                                query
                            )
                        elif hasattr(
                            arxiv_search,
                            "search",
                        ):
                            papers = arxiv_search.search(
                                query
                            )
                    except Exception as fallback_exc:
                        print(
                            "arXiv project-tool fallback failed: "
                            f"{fallback_exc}"
                        )

                papers = (
                    papers or []
                )[
                    :MAX_PAPERS_PER_QUERY
                ]

                for paper in papers:

                    enriched = _enrich_arxiv_paper(
                        paper=paper,
                        query=query,
                        question=question,
                    )

                    research_results[
                        "arxiv"
                    ].append(
                        enriched
                    )

                    stats = research_results[
                        "research_statistics"
                    ]

                    stats[
                        "papers_discovered"
                    ] += 1

                    if enriched.get(
                        "abstract"
                    ):
                        stats[
                            "papers_with_abstracts"
                        ] += 1

                    if enriched.get(
                        "full_text",
                        {},
                    ).get(
                        "available",
                        False,
                    ):
                        stats[
                            "papers_with_fulltext"
                        ] += 1

                    evidence = enriched.get(
                        "evidence",
                        [],
                    )

                    stats[
                        "passages_extracted"
                    ] += len(
                        evidence
                    )

                    stats[
                        "quantitative_findings"
                    ] += sum(
                        len(
                            item.get(
                                "quantitative_findings",
                                [],
                            )
                        )
                        for item in evidence
                    )

                    stats[
                        "methodology_passages"
                    ] += sum(
                        1
                        for item in evidence
                        if "methodology"
                        in item.get(
                            "evidence_types",
                            [],
                        )
                    )

                    stats[
                        "results_passages"
                    ] += sum(
                        1
                        for item in evidence
                        if "results"
                        in item.get(
                            "evidence_types",
                            [],
                        )
                    )

                    stats[
                        "limitation_passages"
                    ] += sum(
                        1
                        for item in evidence
                        if "limitations"
                        in item.get(
                            "evidence_types",
                            [],
                        )
                    )

                    citation = {
                        "title": enriched.get(
                            "title",
                            "Unknown",
                        ),
                        "authors": enriched.get(
                            "authors",
                            [],
                        ),
                        "url": enriched.get(
                            "url",
                            "",
                        ),
                        "date": enriched.get(
                            "published_date",
                            "",
                        ),
                        "source": "arXiv",
                        "source_type": "research_paper",
                        "identifier": enriched.get(
                            "arxiv_id",
                            "",
                        ),
                        "retrieval_status": enriched.get(
                            "retrieval_status",
                            "UNKNOWN",
                        ),
                    }

                    research_results[
                        "citations"
                    ] = add_citation(
                        research_results[
                            "citations"
                        ],
                        citation,
                    )

                    for evidence_item in evidence:

                        research_results[
                            "evidence_packets"
                        ].append(
                            _build_evidence_packet(
                                paper=enriched,
                                evidence=evidence_item,
                                query=query,
                            )
                        )

            except Exception as exc:

                error = {
                    "source": "arXiv",
                    "query": query,
                    "error": _truncate(
                        str(exc),
                        1000,
                    ),
                }

                research_results[
                    "source_errors"
                ].append(
                    error
                )

                print(
                    f"arXiv query failed for "
                    f"'{query}': {exc}"
                )

        # ====================================================================
        # 2. SEC EDGAR
        # ====================================================================

        sec_queries = plan.get(
            "sec_queries",
            [],
        )

        if not isinstance(
            sec_queries,
            list,
        ):
            sec_queries = []

        for raw_query in sec_queries:

            query = _safe_query(
                raw_query
            )

            if not query:
                continue

            try:

                if callable(sec_search):
                    filings = sec_search(
                        query
                    )
                elif hasattr(
                    sec_search,
                    "search",
                ):
                    filings = sec_search.search(
                        query
                    )
                else:
                    filings = []

                for filing in (
                    filings or []
                )[
                    :MAX_PAPERS_PER_QUERY
                ]:

                    enriched_filing = _enrich_sec_filing(
                        filing,
                        query,
                    )

                    research_results[
                        "sec"
                    ].append(
                        enriched_filing
                    )

                    research_results[
                        "research_statistics"
                    ][
                        "sec_records"
                    ] += 1

                    citation = {
                        "title": (
                            f"{enriched_filing.get('company', 'Unknown')} "
                            f"{enriched_filing.get('filing_type', '')}"
                        ).strip(),

                        "url": enriched_filing.get(
                            "url",
                            "",
                        ),

                        "date": enriched_filing.get(
                            "date",
                            "",
                        ),

                        "source": "SEC EDGAR",
                        "source_type": "regulatory_filing",
                    }

                    research_results[
                        "citations"
                    ] = add_citation(
                        research_results[
                            "citations"
                        ],
                        citation,
                    )

                    for evidence_item in (
                        _extract_evidence_from_record(
                            enriched_filing,
                            query,
                            source_type="SEC EDGAR",
                        )
                    ):

                        research_results[
                            "evidence_packets"
                        ].append(
                            _build_generic_evidence_packet(
                                evidence_item,
                                source=enriched_filing,
                                query=query,
                            )
                        )

            except Exception as exc:

                research_results[
                    "source_errors"
                ].append(
                    {
                        "source": "SEC EDGAR",
                        "query": query,
                        "error": _truncate(
                            str(exc),
                            1000,
                        ),
                    }
                )

                print(
                    f"SEC query failed for "
                    f"'{query}': {exc}"
                )

        # ====================================================================
        # 3. CDC / PLACES
        # ====================================================================

        cdc_queries = plan.get(
            "cdc_queries",
            [],
        )

        if not isinstance(
            cdc_queries,
            list,
        ):
            cdc_queries = []

        for raw_query in cdc_queries:

            query = _safe_query(
                raw_query
            )

            if not query:
                continue

            try:

                if hasattr(
                    cdc_places,
                    "search_indicators",
                ):
                    indicators = (
                        cdc_places.search_indicators()
                    )
                elif callable(cdc_places):
                    indicators = cdc_places()
                else:
                    indicators = []

                for indicator in (
                    indicators or []
                )[
                    :MAX_PAPERS_PER_QUERY
                ]:

                    enriched_indicator = _enrich_cdc_indicator(
                        indicator,
                        query,
                    )

                    research_results[
                        "cdc"
                    ].append(
                        enriched_indicator
                    )

                    research_results[
                        "research_statistics"
                    ][
                        "cdc_records"
                    ] += 1

                    for evidence_item in (
                        _extract_evidence_from_record(
                            enriched_indicator,
                            query,
                            source_type="CDC PLACES",
                        )
                    ):

                        research_results[
                            "evidence_packets"
                        ].append(
                            _build_generic_evidence_packet(
                                evidence_item,
                                source=enriched_indicator,
                                query=query,
                            )
                        )

            except Exception as exc:

                research_results[
                    "source_errors"
                ].append(
                    {
                        "source": "CDC PLACES",
                        "query": query,
                        "error": _truncate(
                            str(exc),
                            1000,
                        ),
                    }
                )

                print(
                    f"CDC query failed for "
                    f"'{query}': {exc}"
                )

        # ====================================================================
        # 4. DEDUPLICATION
        # ====================================================================

        research_results[
            "arxiv"
        ] = _deduplicate_records(
            research_results[
                "arxiv"
            ]
        )

        research_results[
            "sec"
        ] = _deduplicate_records(
            research_results[
                "sec"
            ]
        )

        research_results[
            "cdc"
        ] = _deduplicate_records(
            research_results[
                "cdc"
            ]
        )

        research_results[
            "evidence_packets"
        ] = _deduplicate_evidence_packets(
            research_results[
                "evidence_packets"
            ]
        )

        research_results[
            "citations"
        ] = _deduplicate_citations(
            research_results[
                "citations"
            ]
        )

        # ====================================================================
        # 5. QUALITY METADATA
        # ====================================================================

        research_results[
            "research_statistics"
        ].update(
            _calculate_research_quality(
                research_results
            )
        )

        # ====================================================================
        # 6. VALIDATION
        # ====================================================================

        try:

            validate_content(
                json.dumps(
                    research_results,
                    ensure_ascii=False,
                    default=str,
                )
            )

            research_results[
                "validation"
            ] = {
                "valid": True,
                "message": (
                    "Research payload passed "
                    "content validation."
                ),
            }

        except ValueError as exc:

            research_results[
                "validation"
            ] = {
                "valid": False,
                "message": _truncate(
                    str(exc),
                    1000,
                ),
            }

        # ====================================================================
        # 7. PERSIST COMPLETE PAYLOAD TO S3
        # ====================================================================

        if not RESEARCH_BUCKET:
            raise RuntimeError(
                "RESEARCH_BUCKET environment variable "
                "is not configured."
            )

        research_results_key = (
            f"{run_id}/research_results.json"
        )

        evidence_packets_key = (
            f"{run_id}/evidence_packets.json"
        )

        citation_registry_key = (
            f"{run_id}/citation_registry.json"
        )

        research_statistics_key = (
            f"{run_id}/research_statistics.json"
        )

        # Complete research payload
        put_json(
            RESEARCH_BUCKET,
            research_results_key,
            research_results,
        )

        # Evidence packets
        put_json(
            RESEARCH_BUCKET,
            evidence_packets_key,
            research_results[
                "evidence_packets"
            ],
        )

        # Citation registry
        put_json(
            RESEARCH_BUCKET,
            citation_registry_key,
            research_results[
                "citations"
            ],
        )

        # Statistics
        put_json(
            RESEARCH_BUCKET,
            research_statistics_key,
            research_results[
                "research_statistics"
            ],
        )

        print(
            "Research artifacts successfully persisted to S3."
        )

        # ====================================================================
        # 8. UPDATE RUN
        # ====================================================================

        update_run(
            run_id,
            "RESEARCH_COMPLETE",
            research_results=research_results[
                "research_statistics"
            ],
        )

        # ====================================================================
        # 9. SMALL STEP FUNCTIONS OUTPUT
        # ====================================================================

        step_functions_output = {
            "run_id": run_id,

            "status": "COMPLETE",

            "artifacts": {
                "research_results_key": research_results_key,
                "evidence_packets_key": evidence_packets_key,
                "citation_registry_key": citation_registry_key,
                "research_statistics_key": research_statistics_key,
            },

            "research_statistics": (
                research_results.get(
                    "research_statistics",
                    {},
                )
            ),

            "source_error_count": len(
                research_results.get(
                    "source_errors",
                    [],
                )
            ),

            "message": (
                "Research completed. "
                "Complete research evidence is stored in S3. "
                "Only artifact references are returned to Step Functions."
            ),
        }

        # ====================================================================
        # FINAL SAFETY CHECK
        # ====================================================================

        step_functions_output = (
            _enforce_stepfunctions_payload_limit(
                step_functions_output
            )
        )

        output_size = len(
            json.dumps(
                step_functions_output,
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
        )

        print(
            f"Step Functions output size: "
            f"{output_size} bytes"
        )

        return step_functions_output

    # ========================================================================
    # GLOBAL FAILURE HANDLER
    # ========================================================================

    except Exception as exc:

        error_msg = (
            "Research agent error: "
            f"{_truncate(str(exc), 1500)}"
        )

        print(error_msg)

        try:

            update_run(
                run_id,
                "RESEARCH_FAILED",
                error=error_msg,
            )

        except Exception as update_exc:

            print(
                "Failed to update run status: "
                f"{update_exc}"
            )

        failed_output = {
            "run_id": run_id,
            "status": "FAILED",
            "error": error_msg,
        }

        return _enforce_stepfunctions_payload_limit(
            failed_output
        )


# ============================================================================
# STEP FUNCTIONS PAYLOAD SAFETY
# ============================================================================

def _enforce_stepfunctions_payload_limit(
    payload,
):
    """
    Guarantee that the Lambda return object remains comfortably below
    the requested 100 KB Step Functions threshold.

    Target:
        90 KB

    This leaves a safety margin for serialization/envelope overhead.

    The complete research data remains in S3.
    """

    try:

        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        )

        size = len(
            serialized.encode("utf-8")
        )

        if size <= STEP_FUNCTIONS_MAX_BYTES:
            return payload

        print(
            "WARNING: Step Functions output exceeded "
            f"{STEP_FUNCTIONS_MAX_BYTES} bytes. "
            "Returning emergency compact payload."
        )

        compact = {
            "run_id": payload.get(
                "run_id",
                "unknown",
            ),

            "status": payload.get(
                "status",
                "UNKNOWN",
            ),

            "message": (
                "Payload compacted for Step Functions. "
                "Complete research artifacts remain in S3."
            ),
        }

        if payload.get(
            "artifacts"
        ):
            compact[
                "artifacts"
            ] = payload[
                "artifacts"
            ]

        if payload.get(
            "source_error_count"
        ) is not None:
            compact[
                "source_error_count"
            ] = payload[
                "source_error_count"
            ]

        statistics = payload.get(
            "research_statistics",
            {},
        )

        if isinstance(
            statistics,
            dict,
        ):

            compact[
                "research_statistics"
            ] = {
                key: statistics.get(key)
                for key in (
                    "queries_attempted",
                    "papers_discovered",
                    "papers_with_abstracts",
                    "papers_with_fulltext",
                    "passages_extracted",
                    "quantitative_findings",
                    "methodology_passages",
                    "results_passages",
                    "limitation_passages",
                    "sec_records",
                    "cdc_records",
                    "retrieval_quality_score",
                )
                if key in statistics
            }

        return compact

    except Exception as exc:

        print(
            "Payload safety serialization error: "
            f"{exc}"
        )

        return {
            "run_id": str(
                payload.get(
                    "run_id",
                    "unknown",
                )
            ),

            "status": str(
                payload.get(
                    "status",
                    "UNKNOWN",
                )
            ),

            "message": (
                "Compact Step Functions response. "
                "Research artifacts are stored in S3."
            ),
        }


# ============================================================================
# ARXIV
# ============================================================================

def _search_arxiv(
    query,
):
    """
    Direct arXiv API search.
    """

    url = (
        "https://export.arxiv.org/api/query?"
        f"search_query=all:{quote(query)}"
        f"&start=0"
        f"&max_results={MAX_PAPERS_PER_QUERY}"
        "&sortBy=relevance"
        "&sortOrder=descending"
    )

    xml_text = _http_get(
        url,
        accept="application/atom+xml",
    )

    root = ET.fromstring(
        xml_text
    )

    namespace = {
        "atom": "http://www.w3.org/2005/Atom"
    }

    papers = []

    for entry in root.findall(
        "atom:entry",
        namespace,
    ):

        title = _xml_text(
            entry.find(
                "atom:title",
                namespace,
            )
        )

        summary = _xml_text(
            entry.find(
                "atom:summary",
                namespace,
            )
        )

        published = _xml_text(
            entry.find(
                "atom:published",
                namespace,
            )
        )

        updated = _xml_text(
            entry.find(
                "atom:updated",
                namespace,
            )
        )

        paper_id = _xml_text(
            entry.find(
                "atom:id",
                namespace,
            )
        )

        authors = []

        for author in entry.findall(
            "atom:author",
            namespace,
        ):

            name = _xml_text(
                author.find(
                    "atom:name",
                    namespace,
                )
            )

            if name:
                authors.append(
                    name
                )

        links = {}

        for link in entry.findall(
            "atom:link",
            namespace,
        ):

            href = link.attrib.get(
                "href",
                "",
            )

            rel = link.attrib.get(
                "rel",
                "",
            )

            link_type = link.attrib.get(
                "type",
                "",
            )

            if not href:
                continue

            if link_type == "application/pdf":
                links[
                    "pdf"
                ] = href

            elif rel == "alternate":
                links[
                    "abs"
                ] = href

        arxiv_id = _extract_arxiv_id(
            paper_id
        )

        papers.append(
            {
                "title": _normalise_whitespace(
                    title
                ),

                "authors": authors,

                "abstract": _normalise_whitespace(
                    summary
                ),

                "published_date": published,

                "updated_date": updated,

                "url": links.get(
                    "abs",
                    paper_id,
                ),

                "pdf_url": links.get(
                    "pdf",
                    "",
                ),

                "arxiv_id": arxiv_id,

                "source": "arXiv",
            }
        )

    return papers


def _enrich_arxiv_paper(
    paper,
    query,
    question,
):
    """
    Enrich an arXiv paper with full-text metadata and evidence.
    """

    enriched = dict(
        paper or {}
    )

    enriched[
        "research_query"
    ] = query

    enriched[
        "research_question"
    ] = question

    enriched.setdefault(
        "title",
        "Unknown",
    )

    enriched.setdefault(
        "authors",
        [],
    )

    enriched.setdefault(
        "abstract",
        "",
    )

    enriched.setdefault(
        "url",
        "",
    )

    enriched.setdefault(
        "pdf_url",
        "",
    )

    enriched.setdefault(
        "arxiv_id",
        _extract_arxiv_id(
            enriched.get(
                "url",
                "",
            )
        ),
    )

    abstract = enriched.get(
        "abstract",
        "",
    )

    full_text = {
        "available": False,
        "source_url": "",
        "retrieval_method": None,
        "character_count": 0,
        "text": "",
    }

    arxiv_id = enriched.get(
        "arxiv_id",
        "",
    )

    # ========================================================================
    # TRY AR5IV FULL TEXT
    # ========================================================================

    if arxiv_id:

        html_url = (
            "https://ar5iv.labs.arxiv.org/html/"
            f"{arxiv_id}"
        )

        try:

            html = _http_get(
                html_url,
                accept="text/html",
            )

            text = _html_to_text(
                html
            )

            if len(text) > 1000:

                full_text = {
                    "available": True,
                    "source_url": html_url,
                    "retrieval_method": "ar5iv_html",
                    "character_count": len(text),
                    "text": text[
                        :MAX_FULLTEXT_CHARS
                    ],
                }

        except Exception as exc:

            print(
                f"Full-text HTML unavailable "
                f"for {arxiv_id}: {exc}"
            )

    # ========================================================================
    # DO NOT STORE COMPLETE FULL TEXT IN RESEARCH METADATA
    # ========================================================================

    enriched[
        "full_text"
    ] = {
        key: value
        for key, value in full_text.items()
        if key != "text"
    }

    source_text = (
        full_text.get(
            "text"
        )
        or abstract
        or ""
    )

    # ========================================================================
    # EVIDENCE EXTRACTION
    # ========================================================================

    evidence = _extract_research_passages(
        source_text=source_text,
        title=enriched.get(
            "title",
            "",
        ),
        url=enriched.get(
            "url",
            "",
        ),
        query=query,
        abstract=abstract,
    )

    enriched[
        "evidence"
    ] = evidence

    enriched[
        "quantitative_findings"
    ] = _extract_quantitative_findings(
        source_text
    )

    enriched[
        "methodology_findings"
    ] = _extract_keyword_passages(
        source_text,
        METHOD_KEYWORDS,
    )

    enriched[
        "results_findings"
    ] = _extract_keyword_passages(
        source_text,
        RESULT_KEYWORDS,
    )

    enriched[
        "limitations_findings"
    ] = _extract_keyword_passages(
        source_text,
        LIMITATION_KEYWORDS,
    )

    # ========================================================================
    # RETRIEVAL STATUS
    # ========================================================================

    enriched[
        "retrieval_status"
    ] = (
        "FULL_TEXT"
        if full_text["available"]
        else (
            "ABSTRACT_ONLY"
            if abstract
            else "METADATA_ONLY"
        )
    )

    enriched[
        "evidence_quality"
    ] = _score_paper_evidence(
        enriched
    )

    return enriched


# ============================================================================
# PASSAGE EXTRACTION
# ============================================================================

def _extract_research_passages(
    source_text,
    title,
    url,
    query,
    abstract="",
):
    """
    Extract relevant evidence passages from research text.
    """

    text = _normalise_whitespace(
        source_text
    )

    if not text:
        return []

    sentences = _split_sentences(
        text
    )

    candidates = []

    for index, sentence in enumerate(
        sentences
    ):

        lower = sentence.lower()

        evidence_types = []

        # Topic relevance
        if any(
            keyword in lower
            for keyword in ED_KEYWORDS
        ):
            evidence_types.append(
                "topic_relevance"
            )

        # Methodology
        if any(
            keyword in lower
            for keyword in METHOD_KEYWORDS
        ):
            evidence_types.append(
                "methodology"
            )

        # Results
        if any(
            keyword in lower
            for keyword in RESULT_KEYWORDS
        ):
            evidence_types.append(
                "results"
            )

        # Limitations
        if any(
            keyword in lower
            for keyword in LIMITATION_KEYWORDS
        ):
            evidence_types.append(
                "limitations"
            )

        # Quantitative
        quantities = (
            _extract_quantitative_findings(
                sentence
            )
        )

        if quantities:
            evidence_types.append(
                "quantitative"
            )

        if not evidence_types:
            continue

        start = max(
            0,
            index - 1,
        )

        end = min(
            len(sentences),
            index + 2,
        )

        context = " ".join(
            sentences[
                start:end
            ]
        )

        context = _truncate(
            context,
            MAX_PASSAGE_CHARS,
        )

        evidence_id = _stable_id(
            f"{url}|{sentence}"
        )

        candidates.append(
            {
                "evidence_id": evidence_id,

                "title": title,

                "source_url": url,

                "query": query,

                "passage": context,

                "target_sentence": sentence,

                "evidence_types": sorted(
                    set(evidence_types)
                ),

                "quantitative_findings": quantities,

                "context_window": {
                    "preceding_sentences": (
                        1
                        if index > 0
                        else 0
                    ),
                    "following_sentences": (
                        1
                        if index + 1 < len(sentences)
                        else 0
                    ),
                },

                "source_context": (
                    "abstract"
                    if abstract
                    and context in abstract
                    else "full_text"
                ),
            }
        )

    # ========================================================================
    # RANK MOST USEFUL EVIDENCE FIRST
    # ========================================================================

    candidates.sort(
        key=lambda item: (
            "quantitative"
            in item["evidence_types"],

            "results"
            in item["evidence_types"],

            "methodology"
            in item["evidence_types"],

            len(
                item[
                    "quantitative_findings"
                ]
            ),
        ),
        reverse=True,
    )

    return candidates[
        :MAX_PASSAGES_PER_PAPER
    ]


def _extract_quantitative_findings(
    text,
):
    """
    Extract quantitative values and their surrounding context.
    """

    if not text:
        return []

    findings = []

    for match in QUANTITATIVE_PATTERN.finditer(
        text
    ):

        value = match.group(
            0
        ).strip()

        start = max(
            0,
            match.start() - 180,
        )

        end = min(
            len(text),
            match.end() + 220,
        )

        context = _normalise_whitespace(
            text[start:end]
        )

        findings.append(
            {
                "value": value,
                "context": context,
                "position": match.start(),
            }
        )

    unique = []

    seen = set()

    for finding in findings:

        key = (
            finding[
                "value"
            ].lower(),

            finding[
                "context"
            ].lower(),
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        unique.append(
            finding
        )

    return unique[:30]


def _extract_keyword_passages(
    text,
    keywords,
):
    """
    Extract passages matching methodology/results/limitation keywords.
    """

    if not text:
        return []

    sentences = _split_sentences(
        _normalise_whitespace(
            text
        )
    )

    passages = []

    for index, sentence in enumerate(
        sentences
    ):

        lower = sentence.lower()

        matched = [
            keyword
            for keyword in keywords
            if keyword in lower
        ]

        if not matched:
            continue

        start = max(
            0,
            index - 1,
        )

        end = min(
            len(sentences),
            index + 2,
        )

        passages.append(
            {
                "matched_terms": matched[
                    :10
                ],

                "passage": _truncate(
                    " ".join(
                        sentences[
                            start:end
                        ]
                    ),
                    MAX_PASSAGE_CHARS,
                ),
            }
        )

        if len(
            passages
        ) >= 15:
            break

    return passages


# ============================================================================
# SEC
# ============================================================================

def _enrich_sec_filing(
    filing,
    query,
):
    """
    Enrich SEC filing with evidence extraction.
    """

    result = dict(
        filing or {}
    )

    result[
        "research_query"
    ] = query

    result[
        "source"
    ] = "SEC EDGAR"

    text = (
        result.get(
            "text"
        )
        or result.get(
            "content"
        )
        or result.get(
            "description"
        )
        or ""
    )

    if text:

        result[
            "quantitative_findings"
        ] = _extract_quantitative_findings(
            text
        )

        result[
            "evidence"
        ] = _extract_research_passages(
            source_text=text,
            title=result.get(
                "company",
                "SEC Filing",
            ),
            url=result.get(
                "url",
                "",
            ),
            query=query,
        )

    else:

        result[
            "quantitative_findings"
        ] = []

        result[
            "evidence"
        ] = []

    return result


# ============================================================================
# CDC
# ============================================================================

def _enrich_cdc_indicator(
    indicator,
    query,
):
    """
    Enrich CDC PLACES indicator.
    """

    result = dict(
        indicator or {}
    )

    result[
        "research_query"
    ] = query

    result[
        "source"
    ] = "CDC PLACES"

    text = json.dumps(
        result,
        ensure_ascii=False,
        default=str,
    )

    result[
        "quantitative_findings"
    ] = _extract_quantitative_findings(
        text
    )

    result[
        "evidence"
    ] = _extract_research_passages(
        source_text=text,
        title=result.get(
            "measure",
            result.get(
                "name",
                "CDC PLACES Indicator",
            ),
        ),
        url=result.get(
            "url",
            "",
        ),
        query=query,
    )

    return result


# ============================================================================
# GENERIC SOURCE PROCESSING
# ============================================================================

def _extract_evidence_from_record(
    record,
    query,
    source_type,
):
    """
    Extract evidence from SEC/CDC records.
    """

    if not isinstance(
        record,
        dict,
    ):
        return []

    text_fields = [
        "text",
        "content",
        "abstract",
        "description",
        "summary",
        "findings",
        "result",
        "methodology",
    ]

    text_parts = []

    for field in text_fields:

        value = record.get(
            field
        )

        if isinstance(
            value,
            str,
        ):
            text_parts.append(
                value
            )

    if not text_parts:

        text_parts.append(
            json.dumps(
                record,
                ensure_ascii=False,
                default=str,
            )
        )

    text = _normalise_whitespace(
        " ".join(
            text_parts
        )
    )

    return _extract_research_passages(
        source_text=text,

        title=(
            record.get(
                "title"
            )
            or record.get(
                "company"
            )
            or record.get(
                "name"
            )
            or source_type
        ),

        url=record.get(
            "url",
            "",
        ),

        query=query,
    )


# ============================================================================
# EVIDENCE PACKETS
# ============================================================================

def _build_evidence_packet(
    paper,
    evidence,
    query,
):
    """
    Build standardized evidence packet for research papers.
    """

    return {
        "evidence_id": evidence.get(
            "evidence_id"
        ),

        "source": {
            "type": "research_paper",

            "provider": "arXiv",

            "title": paper.get(
                "title",
                "Unknown",
            ),

            "authors": paper.get(
                "authors",
                [],
            ),

            "publication_date": paper.get(
                "published_date",
                "",
            ),

            "url": paper.get(
                "url",
                "",
            ),

            "identifier": paper.get(
                "arxiv_id",
                "",
            ),
        },

        "research_query": query,

        "evidence": {
            "passage": evidence.get(
                "passage",
                "",
            ),

            "target_sentence": evidence.get(
                "target_sentence",
                "",
            ),

            "context_window": evidence.get(
                "context_window",
                {},
            ),

            "evidence_types": evidence.get(
                "evidence_types",
                [],
            ),
        },

        "quantitative_findings": evidence.get(
            "quantitative_findings",
            [],
        ),

        "provenance": {
            "retrieval_status": paper.get(
                "retrieval_status",
                "UNKNOWN",
            ),

            "source_context": evidence.get(
                "source_context",
                "unknown",
            ),

            "retrieved_by": (
                "CTS-NPN Research Agent"
            ),
        },

        "interpretation_policy": (
            "The passage is an extracted source observation. "
            "Downstream agents must not convert association "
            "into causation or infer unsupported conclusions."
        ),
    }


def _build_generic_evidence_packet(
    evidence,
    source,
    query,
):
    """
    Build standardized evidence packet for generic public sources.
    """

    return {
        "evidence_id": _stable_id(
            json.dumps(
                evidence,
                sort_keys=True,
                default=str,
            )
        ),

        "source": {
            "type": source.get(
                "source",
                "public_source",
            ),

            "title": (
                source.get(
                    "title"
                )
                or source.get(
                    "company"
                )
                or source.get(
                    "name"
                )
                or "Unknown"
            ),

            "url": source.get(
                "url",
                "",
            ),

            "date": source.get(
                "date",
                source.get(
                    "published_date",
                    "",
                ),
            ),
        },

        "research_query": query,

        "evidence": evidence,

        "quantitative_findings": source.get(
            "quantitative_findings",
            [],
        ),

        "provenance": {
            "retrieved_by": (
                "CTS-NPN Research Agent"
            ),
        },
    }


# ============================================================================
# QUALITY
# ============================================================================

def _score_paper_evidence(
    paper,
):
    """
    Calculate retrieval/evidence completeness score.

    NOTE:
    This is NOT scientific truth or clinical validity.
    """

    score = 0.0

    if paper.get(
        "title"
    ):
        score += 0.10

    if paper.get(
        "authors"
    ):
        score += 0.10

    if paper.get(
        "abstract"
    ):
        score += 0.15

    if paper.get(
        "full_text",
        {},
    ).get(
        "available"
    ):
        score += 0.25

    if paper.get(
        "methodology_findings"
    ):
        score += 0.15

    if paper.get(
        "results_findings"
    ):
        score += 0.15

    if paper.get(
        "quantitative_findings"
    ):
        score += 0.10

    return round(
        min(
            score,
            1.0,
        ),
        3,
    )


def _calculate_research_quality(
    results,
):
    """
    Calculate overall retrieval quality metadata.
    """

    stats = results[
        "research_statistics"
    ]

    papers = stats[
        "papers_discovered"
    ]

    packets = len(
        results.get(
            "evidence_packets",
            [],
        )
    )

    citations = len(
        results.get(
            "citations",
            [],
        )
    )

    fulltext_rate = (
        stats[
            "papers_with_fulltext"
        ]
        / papers
        if papers
        else 0.0
    )

    evidence_density = (
        packets
        / papers
        if papers
        else 0.0
    )

    citation_coverage = (
        citations
        / papers
        if papers
        else 0.0
    )

    retrieval_score = (
        0.35
        * min(
            fulltext_rate,
            1.0,
        )
        +
        0.35
        * min(
            evidence_density / 5.0,
            1.0,
        )
        +
        0.30
        * min(
            citation_coverage,
            1.0,
        )
    )

    return {
        "fulltext_retrieval_rate": round(
            fulltext_rate,
            3,
        ),

        "evidence_packets_per_paper": round(
            evidence_density,
            3,
        ),

        "citation_coverage_rate": round(
            citation_coverage,
            3,
        ),

        "retrieval_quality_score": round(
            retrieval_score,
            3,
        ),

        "quality_score_interpretation": (
            "Retrieval-quality metric only; "
            "does not represent scientific truth, "
            "model accuracy, causal validity, "
            "or clinical validity."
        ),
    }


# ============================================================================
# DEDUPLICATION
# ============================================================================

def _deduplicate_records(
    records,
):
    """
    Remove duplicate source records.
    """

    seen = set()
    output = []

    for record in records:

        if not isinstance(
            record,
            dict,
        ):
            continue

        key = (
            record.get(
                "url"
            )
            or record.get(
                "id"
            )
            or record.get(
                "arxiv_id"
            )
            or record.get(
                "title"
            )
            or json.dumps(
                record,
                sort_keys=True,
                default=str,
            )
        )

        key = str(
            key
        ).lower()

        if key in seen:
            continue

        seen.add(
            key
        )

        output.append(
            record
        )

    return output


def _deduplicate_evidence_packets(
    packets,
):
    """
    Remove duplicate evidence packets.
    """

    seen = set()
    output = []

    for packet in packets:

        evidence_id = packet.get(
            "evidence_id"
        )

        if not evidence_id:

            evidence_id = _stable_id(
                json.dumps(
                    packet,
                    sort_keys=True,
                    default=str,
                )
            )

        if evidence_id in seen:
            continue

        seen.add(
            evidence_id
        )

        output.append(
            packet
        )

    return output


def _deduplicate_citations(
    citations,
):
    """
    Remove duplicate citations.
    """

    seen = set()
    output = []

    for citation in citations:

        url = citation.get(
            "url",
            "",
        )

        title = citation.get(
            "title",
            "",
        )

        key = (
            url.lower()
            if url
            else title.lower()
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        output.append(
            citation
        )

    return output


# ============================================================================
# HTTP
# ============================================================================

def _http_get(
    url,
    accept="*/*",
):
    """
    Perform HTTP GET with timeout and user-agent.
    """

    request = Request(
        url,

        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
        },

        method="GET",
    )

    with urlopen(
        request,
        timeout=HTTP_TIMEOUT,
    ) as response:

        data = response.read()

        return data.decode(
            "utf-8",
            errors="replace",
        )


# ============================================================================
# TEXT UTILITIES
# ============================================================================

def _html_to_text(
    html,
):
    """
    Convert HTML into normalized text.
    """

    if not html:
        return ""

    # Remove script/style blocks.
    html = re.sub(
        r"<(script|style).*?>.*?</\1>",
        " ",
        html,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    # Convert block-level endings to spaces.
    html = re.sub(
        r"</(p|div|section|article|h[1-6]|li|br)>",
        "\n",
        html,
        flags=re.IGNORECASE,
    )

    # Remove remaining HTML tags.
    html = re.sub(
        r"<[^>]+>",
        " ",
        html,
    )

    text = unescape(
        html
    )

    return _normalise_whitespace(
        text
    )


def _xml_text(
    element,
):
    """
    Safely extract text from an XML element.
    """

    if element is None:
        return ""

    return "".join(
        element.itertext()
    ).strip()


def _split_sentences(
    text,
):
    """
    Basic sentence splitter.
    """

    if not text:
        return []

    return [
        sentence.strip()
        for sentence in re.split(
            r"(?<=[.!?])\s+",
            text,
        )
        if sentence.strip()
    ]


def _normalise_whitespace(
    text,
):
    """
    Normalize repeated whitespace.
    """

    if not text:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(text),
    ).strip()


def _truncate(
    text,
    limit,
):
    """
    Truncate text safely.
    """

    text = text or ""

    if len(text) <= limit:
        return text

    return (
        text[:limit].rstrip()
        + "..."
    )


def _safe_query(
    query,
):
    """
    Sanitize research query.
    """

    if query is None:
        return ""

    try:

        query = clean_text(
            str(query)
        )

    except Exception:

        query = str(
            query
        )

    return _normalise_whitespace(
        query
    )


def _extract_arxiv_id(
    value,
):
    """
    Extract arXiv identifier from URL or identifier.
    """

    if not value:
        return ""

    value = str(
        value
    )

    match = re.search(
        r"(?:arxiv\.org/(?:abs|pdf)/)?"
        r"([a-zA-Z\-]+/\d{7}"
        r"|\d{4}\.\d{4,5})"
        r"(?:v\d+)?",
        value,
    )

    if match:
        return match.group(
            1
        )

    return ""


def _stable_id(
    value,
):
    """
    Generate deterministic short SHA-256 identifier.
    """

    return hashlib.sha256(
        str(
            value
        ).encode(
            "utf-8"
        )
    ).hexdigest()[:20]


# ============================================================================
# END
# ============================================================================