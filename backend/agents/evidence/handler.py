"""
CTS-NPN Evidence Agent
======================

Purpose
-------
Evidence engineering and quantitative-verification layer of the
CTS-NPN research-to-report pipeline.

Architecture
------------
Large evidence packages are persisted to S3.

Step Functions receives only:
    - run_id
    - status
    - compact metadata
    - S3 artifact references

The Evidence Agent NEVER:
    - invents evidence
    - manufactures statistics
    - converts absence of evidence into evidence of absence
    - treats correlation as causation
    - treats utilization patterns as proof of avoidability
    - treats prediction as clinical diagnosis

Observed values are labelled OBSERVED.
Derived values are labelled DERIVED and include formulas.

IMPORTANT
---------
The Lambda response is intentionally kept well below 100 KB.

All large objects are written to S3 and are NOT returned to
Step Functions.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import boto3

from backend.common.aws import put_json, put_text, update_run
from backend.common.config import RESEARCH_BUCKET
from backend.common.security import clean_text, validate_content
from backend.common.citations import format_report_citations


# ============================================================================
# CONFIGURATION
# ============================================================================

AGENT_VERSION = "evidence-agent-v3.0"

# Target is intentionally much smaller than the Step Functions 256 KB limit.
# This gives a safety margin.
MAX_STEP_FUNCTIONS_RESPONSE_BYTES = 90_000

MIN_SOURCE_QUALITY = 0.50
MIN_EVIDENCE_QUALITY_FOR_STRONG_CLAIM = 0.70

MAX_TEXT_LENGTH = 12_000
MAX_SUMMARY_ITEMS = 50
MAX_RETURNED_ERRORS = 10

SOURCE_WEIGHTS = {
    "cms": 1.00,
    "cdc": 1.00,
    "sec": 0.90,
    "arxiv": 0.80,
    "academic": 0.80,
    "peer_reviewed": 0.95,
    "government": 1.00,
    "research": 0.80,
    "unknown": 0.40,
}

SOURCE_TYPE_MAP = {
    "cms": "government_dataset",
    "cdc": "government_dataset",
    "sec": "regulatory_filing",
    "arxiv": "research_paper",
    "academic": "research_paper",
    "peer_reviewed": "research_paper",
    "research": "research_material",
}


# ============================================================================
# AWS CLIENT
# ============================================================================

_s3_client = None


def _get_s3_client():
    global _s3_client

    if _s3_client is None:
        _s3_client = boto3.client("s3")

    return _s3_client


# ============================================================================
# MAIN LAMBDA HANDLER
# ============================================================================

def lambda_handler(event, context):
    """
    Execute the Evidence Agent.

    EXPECTED STEP FUNCTIONS INPUT
    -----------------------------

    {
        "run_id": "RUN123",
        "question": "Research question...",
        "artifacts": {
            "research_results": {
                "bucket": "bucket-name",
                "key": "RUN123/research/research_results.json"
            }
        }
    }

    OR:

    {
        "run_id": "RUN123",
        "question": "Research question...",
        "artifacts": {
            "research_results":
                "s3://bucket-name/RUN123/research/research_results.json"
        }
    }

    OR:

    {
        "run_id": "RUN123",
        "question": "Research question...",
        "artifacts": {
            "research_results":
                "RUN123/research/research_results.json"
        }
    }

    IMPORTANT
    ---------
    Only compact metadata and S3 references are returned.

    Full evidence is NEVER returned to Step Functions.
    """

    event = event if isinstance(event, dict) else {}

    run_id = str(event.get("run_id", "unknown"))

    try:
        # ------------------------------------------------------------------
        # 0. BASIC VALIDATION
        # ------------------------------------------------------------------

        if not RESEARCH_BUCKET:
            raise RuntimeError(
                "RESEARCH_BUCKET is not configured. "
                "Evidence Agent requires S3 persistence."
            )

        # ------------------------------------------------------------------
        # 1. CHECK THAT INPUT IS COMPACT
        # ------------------------------------------------------------------
        #
        # If an upstream agent accidentally sends a giant inline payload,
        # fail safely rather than allowing the pipeline to continue with
        # oversized Step Functions state.
        #
        # S3 references are the intended contract.
        # ------------------------------------------------------------------

        _validate_input_contract(event)

        update_run(
            run_id,
            "ORGANIZING_EVIDENCE",
        )

        question = clean_text(
            str(event.get("question", ""))
        )

        # ------------------------------------------------------------------
        # 2. LOAD LARGE RESEARCH ARTIFACTS FROM S3
        # ------------------------------------------------------------------

        hydrated_event = _hydrate_event_from_s3(
            event=event,
            run_id=run_id,
        )

        # ------------------------------------------------------------------
        # 3. COLLECT ALL SOURCE MATERIAL
        # ------------------------------------------------------------------

        raw_sources = _collect_sources(
            hydrated_event
        )

        # ------------------------------------------------------------------
        # 4. NORMALIZE SOURCE RECORDS
        # ------------------------------------------------------------------

        normalized_records = []

        for source_type, records in raw_sources.items():

            for index, record in enumerate(records):

                normalized = _normalize_record(
                    record=record,
                    source_type=source_type,
                    index=index,
                    run_id=run_id,
                )

                normalized_records.append(
                    normalized
                )

        # ------------------------------------------------------------------
        # 5. REMOVE EXACT DUPLICATES
        # ------------------------------------------------------------------

        (
            deduplicated_records,
            duplicate_records,
        ) = _deduplicate_records(
            normalized_records
        )

        # ------------------------------------------------------------------
        # 6. VALIDATE SOURCE RECORDS
        # ------------------------------------------------------------------

        validation = _validate_records(
            deduplicated_records
        )

        # ------------------------------------------------------------------
        # 7. EXTRACT QUANTITATIVE EVIDENCE
        # ------------------------------------------------------------------

        quantitative_evidence = (
            _extract_quantitative_evidence(
                deduplicated_records
            )
        )

        # ------------------------------------------------------------------
        # 8. CALCULATE DERIVED STATISTICS
        # ------------------------------------------------------------------

        derived_statistics = (
            _calculate_derived_statistics(
                quantitative_evidence
            )
        )

        # ------------------------------------------------------------------
        # 9. DETECT CONTRADICTIONS
        # ------------------------------------------------------------------

        contradictions = _detect_contradictions(
            quantitative_evidence
        )

        # ------------------------------------------------------------------
        # 10. SCORE SOURCE QUALITY
        # ------------------------------------------------------------------

        source_quality = _score_source_quality(
            deduplicated_records
        )

        # ------------------------------------------------------------------
        # 11. BUILD CLAIM / EVIDENCE LEDGER
        # ------------------------------------------------------------------

        evidence_ledger = _build_evidence_ledger(
            question=question,
            records=deduplicated_records,
            quantitative_evidence=quantitative_evidence,
            derived_statistics=derived_statistics,
        )

        # ------------------------------------------------------------------
        # 12. BUILD EVIDENCE PROFILE
        # ------------------------------------------------------------------

        evidence_profile = _build_evidence_profile(
            records=deduplicated_records,
            quantitative_evidence=quantitative_evidence,
            derived_statistics=derived_statistics,
            contradictions=contradictions,
            source_quality=source_quality,
            duplicate_count=len(
                duplicate_records
            ),
        )

        # ------------------------------------------------------------------
        # 13. BUILD COMPLETE EVIDENCE PACKAGE
        # ------------------------------------------------------------------

        evidence = {
            "agent": {
                "name": "CTS-NPN Evidence Agent",
                "version": AGENT_VERSION,
                "generated_at": _utc_now(),
            },
            "run_id": run_id,
            "research_question": question,

            "source_inventory": {
                source_type: len(records)
                for source_type, records
                in raw_sources.items()
            },

            "records": deduplicated_records,
            "duplicate_records": duplicate_records,

            "quantitative_evidence":
                quantitative_evidence,

            "derived_statistics":
                derived_statistics,

            "contradictions":
                contradictions,

            "source_quality":
                source_quality,

            "evidence_ledger":
                evidence_ledger,

            "validation":
                validation,

            "evidence_profile":
                evidence_profile,

            "citations":
                hydrated_event.get(
                    "citations",
                    [],
                ),
        }

        # ------------------------------------------------------------------
        # 14. SECURITY VALIDATION
        # ------------------------------------------------------------------

        validate_content(
            json.dumps(
                evidence,
                ensure_ascii=False,
                default=str,
            )
        )

        # ------------------------------------------------------------------
        # 15. HUMAN-READABLE SUMMARY
        # ------------------------------------------------------------------

        summary = _generate_evidence_summary(
            evidence
        )

        # ------------------------------------------------------------------
        # 16. WRITE EVERYTHING LARGE TO S3
        # ------------------------------------------------------------------

        artifact_keys = {
            "organized_evidence":
                f"{run_id}/evidence/organized_evidence.json",

            "evidence_ledger":
                f"{run_id}/evidence/evidence_ledger.json",

            "quantitative_evidence":
                f"{run_id}/evidence/quantitative_evidence.json",

            "contradictions":
                f"{run_id}/evidence/contradictions.json",

            "evidence_summary":
                f"{run_id}/evidence/evidence_summary.md",

            "evidence_profile":
                f"{run_id}/evidence/evidence_profile.json",

            "source_quality":
                f"{run_id}/evidence/source_quality.json",

            "validation":
                f"{run_id}/evidence/validation.json",
        }

        # Complete evidence package
        put_json(
            RESEARCH_BUCKET,
            artifact_keys[
                "organized_evidence"
            ],
            evidence,
        )

        # Evidence ledger
        put_json(
            RESEARCH_BUCKET,
            artifact_keys[
                "evidence_ledger"
            ],
            evidence_ledger,
        )

        # Quantitative evidence
        put_json(
            RESEARCH_BUCKET,
            artifact_keys[
                "quantitative_evidence"
            ],
            {
                "observed":
                    quantitative_evidence,
                "derived":
                    derived_statistics,
            },
        )

        # Contradictions
        put_json(
            RESEARCH_BUCKET,
            artifact_keys[
                "contradictions"
            ],
            contradictions,
        )

        # Evidence profile
        put_json(
            RESEARCH_BUCKET,
            artifact_keys[
                "evidence_profile"
            ],
            evidence_profile,
        )

        # Full source quality
        put_json(
            RESEARCH_BUCKET,
            artifact_keys[
                "source_quality"
            ],
            source_quality,
        )

        # Validation
        put_json(
            RESEARCH_BUCKET,
            artifact_keys[
                "validation"
            ],
            validation,
        )

        # Human-readable summary
        put_text(
            RESEARCH_BUCKET,
            artifact_keys[
                "evidence_summary"
            ],
            summary,
        )

        # ------------------------------------------------------------------
        # 17. UPDATE PIPELINE STATUS
        # ------------------------------------------------------------------

        update_run(
            run_id,
            "EVIDENCE_ORGANIZED",
            evidence_summary=evidence_profile,
        )

        # ------------------------------------------------------------------
        # 18. BUILD COMPACT STEP FUNCTIONS RESPONSE
        # ------------------------------------------------------------------
        #
        # IMPORTANT:
        #
        # Do NOT return:
        #     evidence
        #     records
        #     quantitative_evidence
        #     source_quality
        #     evidence_ledger
        #
        # Those objects may be very large.
        #
        # Only compact metadata + S3 references are returned.
        # ------------------------------------------------------------------

        response = {
            "run_id": run_id,

            "status": "COMPLETE",

            "agent": {
                "name":
                    "CTS-NPN Evidence Agent",
                "version":
                    AGENT_VERSION,
            },

            "storage": {
                "type": "S3",
                "bucket":
                    RESEARCH_BUCKET,
            },

            "artifacts": artifact_keys,

            # This is the COMPACT profile only.
            "evidence_profile":
                _compact_evidence_profile(
                    evidence_profile
                ),

            "source_inventory": {
                source_type: len(records)
                for source_type, records
                in raw_sources.items()
            },

            "validation": {
                "valid":
                    bool(
                        validation.get(
                            "valid",
                            False,
                        )
                    ),
                "total_records":
                    int(
                        validation.get(
                            "total_records",
                            0,
                        )
                    ),
                "valid_records":
                    int(
                        validation.get(
                            "valid_records",
                            0,
                        )
                    ),
                "invalid_records":
                    int(
                        validation.get(
                            "invalid_records",
                            0,
                        )
                    ),
                "warning_count":
                    len(
                        validation.get(
                            "warnings",
                            [],
                        )
                    ),
            },

            "statistics": {
                "quantitative_observations":
                    len(
                        quantitative_evidence
                    ),
                "derived_statistics":
                    len(
                        derived_statistics
                    ),
                "contradictions":
                    len(
                        contradictions
                    ),
                "duplicates_removed":
                    len(
                        duplicate_records
                    ),
            },

            "message":
                (
                    "Evidence processing completed. "
                    "All large evidence artifacts were "
                    "persisted to S3. Step Functions "
                    "receives only compact metadata and "
                    "S3 artifact references."
                ),
        }

        # ------------------------------------------------------------------
        # 19. HARD RESPONSE SIZE CHECK
        # ------------------------------------------------------------------
        #
        # This is the final safety barrier.
        #
        # The response is intentionally limited to 90 KB,
        # giving substantial room below the requested 100 KB.
        # ------------------------------------------------------------------

        response = _enforce_stepfunctions_limit(
            response
        )

        return response

    except Exception as exc:

        error_message = (
            "Evidence agent error: "
            f"{type(exc).__name__}: {str(exc)}"
        )

        # Prevent an unexpectedly large exception from entering
        # Step Functions.
        error_message = clean_text(
            error_message
        )[:2000]

        print(error_message)

        try:
            update_run(
                run_id,
                "EVIDENCE_FAILED",
                error=error_message,
            )
        except Exception as update_exc:

            print(
                "Failed to update run status: "
                f"{type(update_exc).__name__}: "
                f"{str(update_exc)}"
            )

        failure_response = {
            "run_id": run_id,
            "status": "FAILED",
            "agent": {
                "name":
                    "CTS-NPN Evidence Agent",
                "version":
                    AGENT_VERSION,
            },
            "error": error_message,
        }

        return _enforce_stepfunctions_limit(
            failure_response
        )


# ============================================================================
# INPUT CONTRACT VALIDATION
# ============================================================================

def _validate_input_contract(
    event: Dict[str, Any]
) -> None:
    """
    Prevent accidental large inline payloads from being processed.

    The Evidence Agent should receive S3 references from Step Functions.

    Small control metadata is allowed.
    Large source arrays are rejected.
    """

    event_bytes = _json_size_bytes(
        event
    )

    # This is already above our desired response target.
    # It also protects against accidental giant inputs.
    if event_bytes > 90_000:
        raise ValueError(
            "Evidence Agent input exceeds 90 KB. "
            "Pass large research data through S3 and "
            "provide only S3 artifact references to Step Functions."
        )

    large_inline_fields = (
        "cms_findings",
        "cms",
        "cdc",
        "arxiv",
        "sec",
        "research",
        "records",
        "evidence_packets",
    )

    for field in large_inline_fields:

        value = event.get(field)

        if value is None:
            continue

        serialized_size = _json_size_bytes(
            value
        )

        # Small legacy payloads are tolerated.
        # Anything above 40 KB should be in S3.
        if serialized_size > 40_000:
            raise ValueError(
                f"Large inline field '{field}' detected "
                f"({serialized_size} bytes). "
                "Store the research artifact in S3 and "
                "pass its S3 key/reference instead."
            )


# ============================================================================
# S3 ARTIFACT HYDRATION
# ============================================================================

def _hydrate_event_from_s3(
    event: Dict[str, Any],
    run_id: str,
) -> Dict[str, Any]:
    """
    Load upstream research artifacts from S3.

    Supported forms:

        "research_results":
            "RUN123/research/research_results.json"

    OR:

        "research_results":
            {
                "bucket": "my-bucket",
                "key": "RUN123/research/research_results.json"
            }

    OR:

        "research_results":
            "s3://my-bucket/RUN123/research/research_results.json"
    """

    hydrated = dict(event)

    artifacts = event.get(
        "artifacts",
        {}
    )

    if not isinstance(
        artifacts,
        dict,
    ):
        artifacts = {}

    artifacts = dict(
        artifacts
    )

    # ------------------------------------------------------------------
    # Direct research artifact references
    # ------------------------------------------------------------------

    possible_direct_keys = [
        "research_results_s3_key",
        "research_artifact_key",
        "research_s3_key",
    ]

    for field in possible_direct_keys:

        value = event.get(field)

        if (
            value
            and "research_results"
            not in artifacts
        ):
            artifacts[
                "research_results"
            ] = value

    # ------------------------------------------------------------------
    # No S3 references
    #
    # Small legacy inputs are still allowed.
    # ------------------------------------------------------------------

    if not artifacts:
        return hydrated

    # ------------------------------------------------------------------
    # Read S3 artifacts
    # ------------------------------------------------------------------

    for artifact_name, artifact_reference in artifacts.items():

        try:

            if not _looks_like_json_artifact_reference(
                artifact_reference
            ):
                continue

            artifact = _read_json_artifact(
                artifact_reference,
                run_id=run_id,
            )

            if artifact is None:
                continue

            _merge_research_artifact(
                hydrated,
                artifact_name,
                artifact,
            )

        except Exception as exc:

            print(
                f"Unable to load artifact "
                f"{artifact_name}: "
                f"{type(exc).__name__}: "
                f"{str(exc)}"
            )

            raise

    return hydrated


def _looks_like_json_artifact_reference(
    reference: Any,
) -> bool:

    if isinstance(
        reference,
        dict,
    ):

        return bool(
            reference.get("key")
            or reference.get("s3_key")
            or reference.get("uri")
            or reference.get("s3_uri")
        )

    if isinstance(
        reference,
        str,
    ):

        return (
            reference.startswith(
                "s3://"
            )
            or reference.endswith(
                ".json"
            )
        )

    return False


def _read_json_artifact(
    reference: Any,
    run_id: str,
) -> Optional[Any]:
    """
    Read JSON from S3.

    Supports:

        s3://bucket/key

        key

        {
            "bucket": "...",
            "key": "..."
        }

        {
            "s3_key": "..."
        }

        {
            "uri": "..."
        }

        {
            "s3_uri": "..."
        }
    """

    bucket = RESEARCH_BUCKET
    key = None

    if isinstance(
        reference,
        dict,
    ):

        bucket = (
            reference.get("bucket")
            or reference.get("Bucket")
            or RESEARCH_BUCKET
        )

        key = (
            reference.get("key")
            or reference.get("s3_key")
            or reference.get("Key")
        )

        uri = (
            reference.get("uri")
            or reference.get("s3_uri")
        )

        if uri:
            bucket, key = _parse_s3_uri(
                uri
            )

    elif isinstance(
        reference,
        str,
    ):

        if reference.startswith(
            "s3://"
        ):

            bucket, key = _parse_s3_uri(
                reference
            )

        else:
            key = reference

    if not bucket:
        raise ValueError(
            "S3 artifact bucket is not configured."
        )

    if not key:
        raise ValueError(
            "S3 artifact key is missing."
        )

    response = _get_s3_client().get_object(
        Bucket=bucket,
        Key=key,
    )

    body = response["Body"].read()

    if isinstance(
        body,
        bytes,
    ):
        body = body.decode(
            "utf-8"
        )

    return json.loads(
        body
    )


def _parse_s3_uri(
    uri: str,
) -> Tuple[str, str]:

    value = uri[
        len("s3://"):
    ]

    parts = value.split(
        "/",
        1,
    )

    if len(parts) != 2:
        raise ValueError(
            f"Invalid S3 URI: {uri}"
        )

    return parts[0], parts[1]


def _merge_research_artifact(
    event: Dict[str, Any],
    artifact_name: str,
    artifact: Any,
) -> None:
    """
    Merge an S3 research artifact into the historical
    event structure.

    Supported research artifact formats:

        {
            "arxiv": [...],
            "sec": [...],
            "cdc": [...],
            "cms": [...],
            "citations": [...]
        }

    OR:

        {
            "research": {...}
        }

    OR:

        [...]
    """

    if isinstance(
        artifact,
        list,
    ):

        existing = event.get(
            "research",
            []
        )

        if not isinstance(
            existing,
            list,
        ):
            existing = []

        event["research"] = (
            existing + artifact
        )

        return

    if not isinstance(
        artifact,
        dict,
    ):
        return

    # ------------------------------------------------------------------
    # Merge known source arrays
    # ------------------------------------------------------------------

    source_keys = [
        "cms",
        "cms_findings",
        "cdc",
        "arxiv",
        "sec",
        "research",
        "citations",
    ]

    for key in source_keys:

        value = artifact.get(
            key
        )

        if value is None:
            continue

        if key == "citations":

            if not event.get(
                "citations"
            ):
                event[
                    "citations"
                ] = value

            continue

        if (
            key not in event
            or not event.get(key)
        ):
            event[key] = value

    # ------------------------------------------------------------------
    # Nested wrappers
    # ------------------------------------------------------------------

    for wrapper_key in (
        "data",
        "results",
        "research_results",
        "payload",
    ):

        nested = artifact.get(
            wrapper_key
        )

        if isinstance(
            nested,
            dict,
        ):

            _merge_research_artifact(
                event,
                artifact_name,
                nested,
            )

    # ------------------------------------------------------------------
    # Evidence packet collections
    # ------------------------------------------------------------------

    if "evidence_packets" in artifact:

        packets = artifact.get(
            "evidence_packets"
        )

        if packets is not None:

            existing = event.get(
                "research",
                []
            )

            if not isinstance(
                existing,
                list,
            ):
                existing = []

            flattened = _flatten_records(
                packets
            )

            event["research"] = (
                existing + flattened
            )


# ============================================================================
# SOURCE COLLECTION
# ============================================================================

def _collect_sources(
    event: Dict[str, Any],
) -> Dict[str, List[Any]]:
    """
    Collect source records from supported upstream agents.
    """

    sources = {
        "cms": [],
        "cdc": [],
        "arxiv": [],
        "sec": [],
        "research": [],
    }

    # CMS
    cms = event.get(
        "cms_findings",
        event.get(
            "cms",
            []
        ),
    )

    sources["cms"] = _flatten_records(
        cms
    )

    # CDC
    sources["cdc"] = _flatten_records(
        event.get(
            "cdc",
            []
        )
    )

    # arXiv
    arxiv = event.get(
        "arxiv",
        []
    )

    if not arxiv:

        arxiv = event.get(
            "research",
            []
        )

    sources["arxiv"] = _flatten_records(
        arxiv
    )

    # SEC
    sources["sec"] = _flatten_records(
        event.get(
            "sec",
            []
        )
    )

    # Generic research
    generic_research = event.get(
        "research",
        []
    )

    if (
        generic_research
        and arxiv
        and generic_research != arxiv
    ):

        sources["research"] = (
            _flatten_records(
                generic_research
            )
        )

    return sources


def _flatten_records(
    data: Any,
) -> List[Any]:
    """
    Flatten common API response structures.
    """

    if data is None:
        return []

    if isinstance(
        data,
        list,
    ):
        return data

    if isinstance(
        data,
        dict,
    ):

        for key in (
            "records",
            "results",
            "data",
            "items",
            "findings",
            "documents",
            "papers",
            "evidence_packets",
        ):

            value = data.get(
                key
            )

            if isinstance(
                value,
                list,
            ):
                return value

            if isinstance(
                value,
                dict,
            ):

                nested = _flatten_records(
                    value
                )

                if nested:
                    return nested

        return [data]

    return [data]


# ============================================================================
# NORMALIZATION
# ============================================================================

def _normalize_record(
    record: Any,
    source_type: str,
    index: int,
    run_id: str,
) -> Dict[str, Any]:

    if isinstance(
        record,
        dict,
    ):

        raw = dict(
            record
        )

    else:

        raw = {
            "text": str(record)
        }

    title = _first_value(
        raw,
        [
            "title",
            "name",
            "document_title",
            "dataset_name",
            "paper_title",
        ],
    )

    url = _first_value(
        raw,
        [
            "url",
            "link",
            "source_url",
            "landing_page",
            "pdf_url",
        ],
    )

    source_id = _first_value(
        raw,
        [
            "id",
            "source_id",
            "dataset_id",
            "paper_id",
            "accession_number",
        ],
    )

    date = _first_value(
        raw,
        [
            "date",
            "published_date",
            "publication_date",
            "release_date",
            "filing_date",
        ],
    )

    text = _first_value(
        raw,
        [
            "text",
            "abstract",
            "description",
            "summary",
            "content",
            "snippet",
        ],
    )

    if text:

        text = clean_text(
            str(text)
        )[:MAX_TEXT_LENGTH]

    canonical_string = json.dumps(
        raw,
        sort_keys=True,
        default=str,
    )

    fingerprint = hashlib.sha256(
        canonical_string.encode(
            "utf-8"
        )
    ).hexdigest()

    return {
        "evidence_id":
            f"{run_id}-{source_type}-{index + 1}",

        "fingerprint":
            fingerprint,

        "source_type":
            source_type,

        "source_class":
            SOURCE_TYPE_MAP.get(
                source_type,
                "unknown",
            ),

        "title":
            str(
                title
                or "Untitled source"
            ),

        "source_id":
            str(
                source_id
                or fingerprint[:16]
            ),

        "url":
            str(
                url
                or ""
            ),

        "date":
            str(
                date
                or ""
            ),

        "text":
            text
            or "",

        # Complete original source remains in S3,
        # never in Step Functions output.
        "raw_record":
            raw,

        "provenance": {
            "collection_method":
                "upstream_source_agent",
            "source_type":
                source_type,
            "agent_version":
                AGENT_VERSION,
        },

        "source_weight":
            SOURCE_WEIGHTS.get(
                source_type,
                SOURCE_WEIGHTS["unknown"],
            ),
    }


def _first_value(
    record: Dict[str, Any],
    keys: Iterable[str],
) -> Any:

    for key in keys:

        value = record.get(
            key
        )

        if value not in (
            None,
            "",
            [],
            {},
        ):
            return value

    return None


# ============================================================================
# DEDUPLICATION
# ============================================================================

def _deduplicate_records(
    records: List[Dict[str, Any]]
) -> Tuple[
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:

    seen = set()
    unique = []
    duplicates = []

    for record in records:

        fingerprint = record.get(
            "fingerprint"
        )

        if not fingerprint:

            fingerprint = hashlib.sha256(
                json.dumps(
                    record,
                    sort_keys=True,
                    default=str,
                ).encode(
                    "utf-8"
                )
            ).hexdigest()

        if fingerprint in seen:

            duplicates.append(
                {
                    "evidence_id":
                        record.get(
                            "evidence_id"
                        ),
                    "fingerprint":
                        fingerprint,
                    "reason":
                        "Exact duplicate",
                }
            )

            continue

        seen.add(
            fingerprint
        )

        unique.append(
            record
        )

    return unique, duplicates


# ============================================================================
# VALIDATION
# ============================================================================

def _validate_records(
    records: List[Dict[str, Any]]
) -> Dict[str, Any]:

    valid_count = 0
    invalid_count = 0
    warnings = []

    for record in records:

        if not record.get(
            "title"
        ):

            warnings.append(
                f"{record['evidence_id']}: "
                "missing title"
            )

        if not record.get(
            "url"
        ):

            warnings.append(
                f"{record['evidence_id']}: "
                "missing source URL"
            )

        if (
            not record.get("text")
            and not record.get(
                "raw_record"
            )
        ):

            invalid_count += 1
            continue

        valid_count += 1

    return {
        "valid":
            invalid_count == 0,

        "total_records":
            len(records),

        "valid_records":
            valid_count,

        "invalid_records":
            invalid_count,

        "warnings":
            warnings[:100],
    }


# ============================================================================
# QUANTITATIVE EVIDENCE EXTRACTION
# ============================================================================

def _extract_quantitative_evidence(
    records: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:

    evidence = []

    number_pattern = re.compile(
        r"""
        (?P<value>
            [-+]?
            (?:\d+(?:,\d{3})*|\d+)
            (?:\.\d+)?
        )
        \s*
        (?P<unit>
            %
            |percent
            |percentage
            |million
            |billion
            |thousand
            |days?
            |years?
            |months?
            |visits?
            |patients?
            |members?
            |claims?
            |dollars?
            |\$
        )?
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    for record in records:

        text = record.get(
            "text",
            ""
        )

        if not text:
            continue

        for match in number_pattern.finditer(
            text
        ):

            raw_value = match.group(
                "value"
            )

            unit = (
                match.group(
                    "unit"
                )
                or ""
            )

            try:

                value = float(
                    raw_value.replace(
                        ",",
                        "",
                    )
                )

            except ValueError:
                continue

            # Ignore meaningless isolated tiny decimals.
            if (
                value < 1
                and not unit
            ):
                continue

            start = max(
                0,
                match.start() - 180,
            )

            end = min(
                len(text),
                match.end() + 180,
            )

            context = text[
                start:end
            ].strip()

            measurement_id = (
                f"{record['evidence_id']}-"
                f"m{len(evidence) + 1}"
            )

            evidence.append(
                {
                    "measurement_id":
                        measurement_id,

                    "evidence_id":
                        record[
                            "evidence_id"
                        ],

                    "source_type":
                        record[
                            "source_type"
                        ],

                    "title":
                        record[
                            "title"
                        ],

                    "value":
                        value,

                    "unit":
                        unit,

                    "context":
                        context,

                    "status":
                        "OBSERVED",

                    "provenance": {
                        "source_url":
                            record.get(
                                "url",
                                "",
                            ),
                        "source_id":
                            record.get(
                                "source_id",
                                "",
                            ),
                    },
                }
            )

    return evidence


# ============================================================================
# QUANTITATIVE ANALYSIS
# ============================================================================

def _calculate_derived_statistics(
    quantitative: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:

    derived = []

    grouped = defaultdict(list)

    for item in quantitative:

        key = (
            item.get(
                "unit",
                "",
            ),
            _measurement_context_key(
                item.get(
                    "context",
                    "",
                )
            ),
        )

        grouped[key].append(
            item
        )

    for key, items in grouped.items():

        values = [
            float(
                item["value"]
            )
            for item in items
            if _is_finite_number(
                item.get(
                    "value"
                )
            )
        ]

        if len(values) < 2:
            continue

        mean_value = statistics.mean(
            values
        )

        median_value = statistics.median(
            values
        )

        minimum = min(
            values
        )

        maximum = max(
            values
        )

        standard_deviation = (
            statistics.stdev(
                values
            )
            if len(values) >= 2
            else 0.0
        )

        derived.append(
            {
                "statistic_id":
                    f"derived-{len(derived) + 1}",

                "measurement_type":
                    "DESCRIPTIVE_STATISTICS",

                "unit":
                    key[0],

                "n":
                    len(values),

                "mean":
                    _round(
                        mean_value
                    ),

                "median":
                    _round(
                        median_value
                    ),

                "minimum":
                    _round(
                        minimum
                    ),

                "maximum":
                    _round(
                        maximum
                    ),

                "standard_deviation":
                    _round(
                        standard_deviation
                    ),

                "formula": {
                    "mean":
                        "sum(x_i) / n",

                    "median":
                        (
                            "middle ordered observation "
                            "(or mean of two middle observations)"
                        ),

                    "standard_deviation":
                        (
                            "sqrt(sum((x_i - mean)^2) / (n - 1))"
                        ),
                },

                "source_measurements": [
                    item[
                        "measurement_id"
                    ]
                    for item in items
                ],

                "status":
                    "DERIVED",

                "interpretation_rule":
                    (
                        "Descriptive statistics summarize "
                        "the supplied observations. They do "
                        "not establish causality or "
                        "generalizability."
                    ),
            }
        )

    return derived


def _measurement_context_key(
    context: str
) -> str:

    text = context.lower()

    text = re.sub(
        r"[-+]?\d+(?:\.\d+)?",
        "#",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text[:300]


def _is_finite_number(
    value: Any
) -> bool:

    try:

        number = float(
            value
        )

        return math.isfinite(
            number
        )

    except (
        TypeError,
        ValueError,
    ):

        return False


def _round(
    value: float,
    digits: int = 6,
) -> float:

    return round(
        float(value),
        digits,
    )


# ============================================================================
# CONTRADICTION DETECTION
# ============================================================================

def _detect_contradictions(
    quantitative: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:

    contradictions = []

    grouped = defaultdict(list)

    for item in quantitative:

        key = (
            item.get(
                "unit",
                "",
            ),
            _semantic_key(
                item.get(
                    "context",
                    "",
                )
            ),
        )

        grouped[key].append(
            item
        )

    for key, items in grouped.items():

        values = [
            item
            for item in items
            if _is_finite_number(
                item.get(
                    "value"
                )
            )
        ]

        if len(values) < 2:
            continue

        numeric_values = [
            float(
                item["value"]
            )
            for item in values
        ]

        low = min(
            numeric_values
        )

        high = max(
            numeric_values
        )

        if low == 0:

            ratio = float(
                "inf"
            )

        else:

            ratio = (
                high
                / abs(low)
            )

        if ratio >= 10:

            contradictions.append(
                {
                    "type":
                        "NUMERICAL_DISCREPANCY",

                    "unit":
                        key[0],

                    "range": {
                        "minimum":
                            low,

                        "maximum":
                            high,

                        "ratio":
                            (
                                ratio
                                if math.isfinite(
                                    ratio
                                )
                                else "infinite"
                            ),
                    },

                    "evidence_ids": [
                        item[
                            "evidence_id"
                        ]
                        for item in values
                    ],

                    "severity":
                        "REVIEW_REQUIRED",

                    "interpretation":
                        (
                            "Large numerical variation was "
                            "detected. This may represent "
                            "different populations, periods, "
                            "definitions, denominators, or "
                            "methodologies. It must not be "
                            "treated as a contradiction until "
                            "those dimensions are reconciled."
                        ),
                }
            )

    return contradictions


def _semantic_key(
    text: str
) -> str:

    text = text.lower()

    text = re.sub(
        r"[-+]?\d+(?:\.\d+)?",
        "#",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text[:250]


# ============================================================================
# SOURCE QUALITY
# ============================================================================

def _score_source_quality(
    records: List[Dict[str, Any]]
) -> Dict[str, Any]:

    source_scores = []

    for record in records:

        source_type = record.get(
            "source_type",
            "unknown",
        )

        base = SOURCE_WEIGHTS.get(
            source_type,
            SOURCE_WEIGHTS["unknown"],
        )

        completeness = 0.0

        if record.get(
            "title"
        ):
            completeness += 0.20

        if record.get(
            "url"
        ):
            completeness += 0.25

        if record.get(
            "date"
        ):
            completeness += 0.15

        if record.get(
            "text"
        ):
            completeness += 0.25

        if record.get(
            "source_id"
        ):
            completeness += 0.15

        score = (
            0.70 * base
            + 0.30 * completeness
        )

        score = max(
            0.0,
            min(
                1.0,
                score,
            ),
        )

        source_scores.append(
            {
                "evidence_id":
                    record[
                        "evidence_id"
                    ],

                "source_type":
                    source_type,

                "source_quality_score":
                    round(
                        score,
                        4,
                    ),

                "dimensions": {
                    "source_authority":
                        base,

                    "metadata_completeness":
                        completeness,
                },
            }
        )

    if source_scores:

        overall = statistics.mean(
            item[
                "source_quality_score"
            ]
            for item in source_scores
        )

    else:

        overall = 0.0

    return {
        "overall_score":
            round(
                overall,
                4,
            ),

        "records":
            source_scores,

        "methodology": {
            "source_authority_weight":
                0.70,

            "metadata_completeness_weight":
                0.30,

            "note":
                (
                    "This is an internal provenance-quality "
                    "heuristic. It is not a statistical "
                    "measure of scientific truth."
                ),
        },
    }


# ============================================================================
# EVIDENCE LEDGER
# ============================================================================

def _build_evidence_ledger(
    question: str,
    records: List[Dict[str, Any]],
    quantitative_evidence: List[Dict[str, Any]],
    derived_statistics: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:

    ledger = []

    for record in records:

        text = record.get(
            "text",
            ""
        )

        claim_type = _classify_claim_type(
            text
        )

        related_measurements = [
            item[
                "measurement_id"
            ]
            for item in quantitative_evidence
            if item[
                "evidence_id"
            ]
            == record[
                "evidence_id"
            ]
        ]

        ledger.append(
            {
                "ledger_id":
                    f"ledger-{len(ledger) + 1}",

                "research_question":
                    question,

                "evidence_id":
                    record[
                        "evidence_id"
                    ],

                "source_type":
                    record[
                        "source_type"
                    ],

                "claim_type":
                    claim_type,

                "title":
                    record[
                        "title"
                    ],

                "source_url":
                    record[
                        "url"
                    ],

                "observations": {
                    "quantitative_measurements":
                        related_measurements,

                    "qualitative_evidence_present":
                        bool(
                            text
                        ),
                },

                "status":
                    (
                        "EVIDENCE_AVAILABLE"
                        if text
                        else "INSUFFICIENT_SOURCE_TEXT"
                    ),

                "research_rule":
                    (
                        "The source supports only claims "
                        "that are directly justified by "
                        "its content and methodology."
                    ),
            }
        )

    return ledger


def _classify_claim_type(
    text: str
) -> str:

    lower = text.lower()

    if any(
        term in lower
        for term in (
            "randomized",
            "randomised",
            "trial",
        )
    ):
        return "INTERVENTIONAL"

    if any(
        term in lower
        for term in (
            "association",
            "associated",
            "correlation",
            "relationship",
        )
    ):
        return "ASSOCIATIONAL"

    if any(
        term in lower
        for term in (
            "survey",
            "prevalence",
            "distribution",
            "descriptive",
        )
    ):
        return "DESCRIPTIVE"

    if any(
        term in lower
        for term in (
            "forecast",
            "prediction",
            "model",
            "classifier",
        )
    ):
        return "PREDICTIVE"

    if any(
        term in lower
        for term in (
            "methodology",
            "method",
            "dataset",
        )
    ):
        return "METHODOLOGICAL"

    return "GENERAL"


# ============================================================================
# EVIDENCE PROFILE
# ============================================================================

def _build_evidence_profile(
    records: List[Dict[str, Any]],
    quantitative_evidence: List[Dict[str, Any]],
    derived_statistics: List[Dict[str, Any]],
    contradictions: List[Dict[str, Any]],
    source_quality: Dict[str, Any],
    duplicate_count: int,
) -> Dict[str, Any]:

    source_types = Counter(
        record.get(
            "source_type",
            "unknown",
        )
        for record in records
    )

    quantitative_count = len(
        quantitative_evidence
    )

    strong_source_count = sum(
        1
        for item in source_quality.get(
            "records",
            [],
        )
        if item.get(
            "source_quality_score",
            0,
        )
        >= MIN_EVIDENCE_QUALITY_FOR_STRONG_CLAIM
    )

    coverage = (
        strong_source_count
        / len(records)
        if records
        else 0
    )

    contradiction_penalty = min(
        len(contradictions) * 0.05,
        0.30,
    )

    quantitative_bonus = min(
        quantitative_count / 100,
        0.20,
    )

    diversity = min(
        len(source_types) / 4,
        1.0,
    )

    overall_score = (
        0.35
        * source_quality.get(
            "overall_score",
            0,
        )
        + 0.25 * coverage
        + 0.20 * diversity
        + 0.20 * quantitative_bonus
        - contradiction_penalty
    )

    overall_score = max(
        0.0,
        min(
            1.0,
            overall_score,
        ),
    )

    return {
        "total_records":
            len(records),

        "source_diversity":
            len(source_types),

        "source_types":
            dict(source_types),

        "quantitative_observations":
            quantitative_count,

        "derived_statistics":
            len(
                derived_statistics
            ),

        "contradictions_requiring_review":
            len(
                contradictions
            ),

        "duplicates_removed":
            duplicate_count,

        "high_quality_sources":
            strong_source_count,

        "high_quality_source_coverage":
            round(
                coverage,
                4,
            ),

        "source_quality_score":
            source_quality.get(
                "overall_score",
                0,
            ),

        "overall_evidence_score":
            round(
                overall_score,
                4,
            ),

        "evidence_strength":
            _evidence_strength(
                overall_score
            ),

        "interpretation":
            (
                "Evidence strength is an internal "
                "pipeline-quality indicator. It must "
                "not be represented in the final report "
                "as a probability of truth."
            ),
    }


def _compact_evidence_profile(
    profile: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Return ONLY the small profile needed by downstream
    Step Functions states.

    The complete source-quality records are stored in S3.
    """

    return {
        "total_records":
            int(
                profile.get(
                    "total_records",
                    0,
                )
            ),

        "source_diversity":
            int(
                profile.get(
                    "source_diversity",
                    0,
                )
            ),

        "source_types":
            dict(
                profile.get(
                    "source_types",
                    {},
                )
            ),

        "quantitative_observations":
            int(
                profile.get(
                    "quantitative_observations",
                    0,
                )
            ),

        "derived_statistics":
            int(
                profile.get(
                    "derived_statistics",
                    0,
                )
            ),

        "contradictions_requiring_review":
            int(
                profile.get(
                    "contradictions_requiring_review",
                    0,
                )
            ),

        "duplicates_removed":
            int(
                profile.get(
                    "duplicates_removed",
                    0,
                )
            ),

        "high_quality_sources":
            int(
                profile.get(
                    "high_quality_sources",
                    0,
                )
            ),

        "high_quality_source_coverage":
            float(
                profile.get(
                    "high_quality_source_coverage",
                    0,
                )
            ),

        "source_quality_score":
            float(
                profile.get(
                    "source_quality_score",
                    0,
                )
            ),

        "overall_evidence_score":
            float(
                profile.get(
                    "overall_evidence_score",
                    0,
                )
            ),

        "evidence_strength":
            str(
                profile.get(
                    "evidence_strength",
                    "INSUFFICIENT",
                )
            ),
    }


def _evidence_strength(
    score: float
) -> str:

    if score >= 0.85:
        return "HIGH"

    if score >= 0.70:
        return "MODERATE-HIGH"

    if score >= 0.55:
        return "MODERATE"

    if score >= 0.40:
        return "LIMITED"

    return "INSUFFICIENT"


# ============================================================================
# HUMAN-READABLE SUMMARY
# ============================================================================

def _generate_evidence_summary(
    evidence: Dict[str, Any]
) -> str:

    profile = evidence[
        "evidence_profile"
    ]

    lines = []

    lines.append(
        f"# Evidence Engineering Report - "
        f"{evidence['run_id']}"
    )

    lines.append("")

    lines.append(
        "## Research Question"
    )

    lines.append(
        evidence.get(
            "research_question",
            "",
        )
    )

    lines.append("")

    lines.append(
        "## Evidence Profile"
    )

    lines.append(
        f"- Total evidence records: "
        f"{profile['total_records']}"
    )

    lines.append(
        f"- Source diversity: "
        f"{profile['source_diversity']}"
    )

    lines.append(
        f"- Quantitative observations: "
        f"{profile['quantitative_observations']}"
    )

    lines.append(
        f"- Derived statistics: "
        f"{profile['derived_statistics']}"
    )

    lines.append(
        f"- Contradictions requiring review: "
        f"{profile['contradictions_requiring_review']}"
    )

    lines.append(
        f"- Duplicate records removed: "
        f"{profile['duplicates_removed']}"
    )

    lines.append(
        f"- Overall evidence score: "
        f"{profile['overall_evidence_score']:.2%}"
    )

    lines.append(
        f"- Evidence strength: "
        f"{profile['evidence_strength']}"
    )

    lines.append("")

    lines.append(
        "## Methodological Interpretation"
    )

    lines.append(
        "The evidence score is an internal quality-control "
        "indicator based on source authority, provenance "
        "completeness, source diversity, quantitative "
        "coverage, and detected discrepancies. It is not "
        "a probability that an individual claim is true."
    )

    lines.append("")

    lines.append(
        "## Source Distribution"
    )

    for source_type, count in sorted(
        profile[
            "source_types"
        ].items()
    ):

        lines.append(
            f"- {source_type}: {count}"
        )

    lines.append("")

    lines.append(
        "## Quantitative Evidence"
    )

    quantitative = evidence.get(
        "quantitative_evidence",
        [],
    )

    for item in quantitative[
        :MAX_SUMMARY_ITEMS
    ]:

        lines.append(
            f"- {item['measurement_id']}: "
            f"{item['value']} {item['unit']} "
            f"[OBSERVED] — "
            f"{item['title']}"
        )

    lines.append("")

    lines.append(
        "## Derived Statistics"
    )

    derived = evidence.get(
        "derived_statistics",
        [],
    )

    for item in derived[
        :MAX_SUMMARY_ITEMS
    ]:

        lines.append(
            f"- {item['statistic_id']}: "
            f"n={item['n']}, "
            f"mean={item['mean']}, "
            f"median={item['median']}, "
            f"SD={item['standard_deviation']} "
            f"[DERIVED]"
        )

        lines.append(
            "  Formula: "
            f"{item['formula']['mean']}"
        )

    lines.append("")

    lines.append(
        "## Contradictions / Reconciliation Required"
    )

    contradictions = evidence.get(
        "contradictions",
        [],
    )

    if not contradictions:

        lines.append(
            "No major numerical discrepancies "
            "were detected."
        )

    else:

        for item in contradictions:

            lines.append(
                f"- {item['type']}: "
                f"{item['interpretation']}"
            )

    lines.append("")

    lines.append(
        "## Evidence Ledger"
    )

    for ledger_item in evidence.get(
        "evidence_ledger",
        [],
    )[
        :MAX_SUMMARY_ITEMS
    ]:

        lines.append(
            f"- {ledger_item['ledger_id']} | "
            f"{ledger_item['source_type']} | "
            f"{ledger_item['claim_type']} | "
            f"{ledger_item['title']}"
        )

    lines.append("")

    lines.append(
        "## References"
    )

    citations = evidence.get(
        "citations",
        [],
    )

    if citations:

        try:

            lines.append(
                format_report_citations(
                    citations[:50]
                )
            )

        except Exception:

            for citation in citations[:50]:

                if isinstance(
                    citation,
                    dict,
                ):

                    lines.append(
                        "- "
                        f"{citation.get('title', 'Source')} "
                        f"{citation.get('url', '')}"
                    )

    else:

        lines.append(
            "No citation records were supplied by "
            "the upstream source agents."
        )

    lines.append("")

    lines.append(
        "## Research Integrity Statement"
    )

    lines.append(
        "Observed values are preserved separately from "
        "derived statistics. Derived statistics are calculated "
        "only from numeric observations available to this "
        "agent and are accompanied by their mathematical "
        "definition. The evidence layer does not infer "
        "causality from association, does not interpret "
        "utilization as proof of avoidability, and does not "
        "substitute model predictions for clinical or policy "
        "judgment."
    )

    return "\n".join(
        lines
    )


# ============================================================================
# STEP FUNCTIONS SIZE PROTECTION
# ============================================================================

def _json_size_bytes(
    value: Any
) -> int:
    """
    Calculate UTF-8 JSON size.
    """

    payload = json.dumps(
        value,
        ensure_ascii=False,
        default=str,
        separators=(
            ",",
            ":",
        ),
    )

    return len(
        payload.encode(
            "utf-8"
        )
    )


def _enforce_stepfunctions_limit(
    response: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Final hard safety barrier.

    The response must remain below 90 KB.

    This is intentionally lower than the requested 100 KB
    to provide a safety margin.
    """

    size = _json_size_bytes(
        response
    )

    if size <= MAX_STEP_FUNCTIONS_RESPONSE_BYTES:
        return response

    # ------------------------------------------------------------------
    # If an unexpected future code change makes the response large,
    # remove optional metadata before failing.
    # ------------------------------------------------------------------

    compact_response = {
        "run_id":
            response.get(
                "run_id",
                "unknown",
            ),

        "status":
            response.get(
                "status",
                "UNKNOWN",
            ),

        "agent":
            response.get(
                "agent",
                {},
            ),

        "storage":
            response.get(
                "storage",
                {},
            ),

        "artifacts":
            response.get(
                "artifacts",
                {},
            ),

        "message":
            (
                "Evidence Agent completed. "
                "Large evidence data is stored in S3. "
                "Use the returned artifact keys to retrieve it."
            ),
    }

    compact_size = _json_size_bytes(
        compact_response
    )

    if compact_size <= MAX_STEP_FUNCTIONS_RESPONSE_BYTES:
        return compact_response

    # ------------------------------------------------------------------
    # If even the compact response is unexpectedly large,
    # return only the essential S3 contract.
    # ------------------------------------------------------------------

    emergency_response = {
        "run_id":
            str(
                response.get(
                    "run_id",
                    "unknown",
                )
            ),

        "status":
            str(
                response.get(
                    "status",
                    "UNKNOWN",
                )
            ),

        "storage": {
            "type":
                "S3",
            "bucket":
                response.get(
                    "storage",
                    {}
                ).get(
                    "bucket",
                    "",
                ),
        },

        "artifacts":
            response.get(
                "artifacts",
                {},
            ),

        "message":
            (
                "Evidence artifacts are stored in S3. "
                "Step Functions response was reduced "
                "to the minimum safe metadata contract."
            ),
    }

    emergency_size = _json_size_bytes(
        emergency_response
    )

    if emergency_size > MAX_STEP_FUNCTIONS_RESPONSE_BYTES:

        raise RuntimeError(
            "Unable to construct a Step Functions "
            "response below 90 KB. "
            f"Final size: {emergency_size} bytes."
        )

    return emergency_response


# ============================================================================
# TIME / UTILITY
# ============================================================================

def _utc_now() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================================
# END OF EVIDENCE AGENT
# ============================================================================