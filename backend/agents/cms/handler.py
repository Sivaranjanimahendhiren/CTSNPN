"""
CTS-NPN CMS Research Agent
==========================

Storage-first CMS evidence acquisition agent.

IMPORTANT ARCHITECTURE RULE
---------------------------

This Lambda MUST NOT return the full CMS evidence package to Step Functions.

Large evidence is written to S3.

Step Functions receives ONLY a small manifest containing:
    - run_id
    - status
    - S3 artifact key
    - small metadata
    - error information when applicable

This prevents:
    States.DataLimitExceeded

and keeps Step Functions state payloads comfortably below the
200 KB project requirement.
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.common.aws import put_json, update_run
from backend.common.config import CMS_BUCKET, MAX_RESULTS


# ============================================================================
# CONFIGURATION
# ============================================================================

CMS_PDC_API = (
    "https://data.cms.gov/provider-data/api/1"
)

CMS_DATA_API = (
    "https://data.cms.gov/data-api/v1"
)

DEFAULT_DATASET_ID = os.getenv(
    "CMS_DEFAULT_DATASET_ID",
    "dgmq-aat3",
)

REQUEST_TIMEOUT = int(
    os.getenv(
        "CMS_API_TIMEOUT_SECONDS",
        "15",
    )
)

MAX_RECORDS = int(
    os.getenv(
        "CMS_MAX_RECORDS_PER_QUERY",
        str(min(MAX_RESULTS, 100)),
    )
)

MAX_RECORDS = max(
    1,
    min(
        MAX_RECORDS,
        100,
    ),
)

MAX_PAGES = int(
    os.getenv(
        "CMS_MAX_PAGES_PER_QUERY",
        "2",
    )
)

MAX_PAGES = max(
    1,
    min(
        MAX_PAGES,
        3,
    ),
)

USER_AGENT = os.getenv(
    "CMS_USER_AGENT",
    "CTS-NPN-Research-Agent/1.0",
)

PAGE_SIZE = min(
    MAX_RECORDS,
    50,
)

# ---------------------------------------------------------------------------
# Step Functions safety limits
# ---------------------------------------------------------------------------

# The user requirement is that Step Functions input remains below 200 KB.
# We also keep Lambda OUTPUT much smaller.
#
# These values are intentionally conservative.
MAX_STEP_FUNCTIONS_OUTPUT_BYTES = 64 * 1024
MAX_QUERY_TEXT_LENGTH = 500
MAX_RUN_ID_LENGTH = 128

# Only these metadata fields are returned to Step Functions.
SAFE_METADATA_FIELDS = {
    "total_queries",
    "successful_queries",
    "failed_queries",
    "total_records_retrieved",
    "total_pages_retrieved",
    "datasets_used",
    "real_source_records",
    "synthetic_records",
    "generated_records",
    "source",
}


# ============================================================================
# LAMBDA ENTRY POINT
# ============================================================================

def lambda_handler(event, context):
    """
    Execute CMS evidence acquisition.

    FULL CMS RECORDS:
        Stored in S3.

    STEP FUNCTIONS:
        Receives only a small manifest.

    This function never returns the complete research package.
    """

    # ------------------------------------------------------------------------
    # Defensive event normalization
    # ------------------------------------------------------------------------

    if not isinstance(event, dict):
        event = {}

    run_id = str(
        event.get(
            "run_id",
            "unknown",
        )
    )[:MAX_RUN_ID_LENGTH]

    question = str(
        event.get(
            "question",
            "",
        )
    )[:MAX_QUERY_TEXT_LENGTH]

    plan = event.get(
        "plan",
        {},
    )

    if not isinstance(plan, dict):
        plan = {}

    artifact_key = (
        f"{run_id}/cms_query_results.json"
    )

    try:

        update_run(
            run_id,
            "QUERYING_CMS",
        )

        # --------------------------------------------------------------------
        # Normalize planner CMS queries
        # --------------------------------------------------------------------

        cms_queries = plan.get(
            "cms_queries",
            [],
        )

        normalized_queries = _normalize_queries(
            cms_queries,
            question,
        )

        # Always have at least one safe query.
        if not normalized_queries:

            normalized_queries = [
                {
                    "query": (
                        question
                        or "CMS evidence relevant to research question"
                    ),
                    "dataset_id": DEFAULT_DATASET_ID,
                    "limit": min(
                        MAX_RECORDS,
                        25,
                    ),
                    "filters": {},
                    "api": "pdc",
                }
            ]

        # --------------------------------------------------------------------
        # Full research package lives ONLY in S3
        # --------------------------------------------------------------------

        research_package = {
            "run_id": run_id,
            "source": {
                "name": (
                    "Centers for Medicare & Medicaid Services"
                ),
                "short_name": "CMS",
                "catalog": (
                    "CMS Provider Data Catalog"
                ),
                "access": "public",
                "authentication": "none",
            },
            "question": question,
            "queries": normalized_queries,
            "results": [],
            "metadata": {},
        }

        # --------------------------------------------------------------------
        # Execute CMS queries
        # --------------------------------------------------------------------

        for query_spec in normalized_queries:

            query_text = query_spec.get(
                "query",
                "",
            )

            try:

                result = _execute_cms_query(
                    query_spec=query_spec,
                    run_id=run_id,
                )

                research_package[
                    "results"
                ].append(
                    result
                )

            except Exception as exc:

                print(
                    "CMS query failed: "
                    f"query={query_text!r} "
                    f"dataset={query_spec.get('dataset_id')} "
                    f"error={exc}"
                )

                research_package[
                    "results"
                ].append(
                    {
                        "status": "ERROR",
                        "query": query_text,
                        "dataset_id": query_spec.get(
                            "dataset_id"
                        ),
                        "error": str(exc)[:1000],
                        "retrieval_timestamp": _utc_now(),
                    }
                )

        # --------------------------------------------------------------------
        # Package metadata
        # --------------------------------------------------------------------

        research_package[
            "metadata"
        ] = _build_metadata(
            research_package[
                "results"
            ]
        )

        # --------------------------------------------------------------------
        # Store COMPLETE package in S3
        # --------------------------------------------------------------------

        if not CMS_BUCKET:

            raise RuntimeError(
                "CMS_BUCKET is not configured. "
                "CMS evidence cannot be safely persisted."
            )

        put_json(
            CMS_BUCKET,
            artifact_key,
            research_package,
        )

        # --------------------------------------------------------------------
        # Update run status with SMALL metadata only
        # --------------------------------------------------------------------

        safe_metadata = _build_safe_metadata(
            research_package[
                "metadata"
            ]
        )

        update_run(
            run_id,
            "CMS_QUERY_COMPLETE",
            cms_results=safe_metadata,
        )

        # --------------------------------------------------------------------
        # IMPORTANT:
        #
        # NEVER return research_package here.
        # NEVER return records here.
        #
        # Only return a tiny S3 manifest.
        # --------------------------------------------------------------------

        response = {
            "run_id": run_id,
            "status": "COMPLETE",
            "artifacts": {
                "cms_query_results_key": artifact_key,
            },
            "metadata": safe_metadata,
        }

        return _safe_step_functions_response(
            response
        )

    except Exception as exc:

        error_message = (
            f"CMS agent error: {str(exc)}"
        )

        print(
            error_message
        )

        try:

            update_run(
                run_id,
                "CMS_QUERY_FAILED",
                error=error_message[:1000],
            )

        except Exception as update_exc:

            print(
                "Unable to update run status: "
                f"{update_exc}"
            )

        response = {
            "run_id": run_id,
            "status": "FAILED",
            "error": error_message[:1000],
        }

        return _safe_step_functions_response(
            response
        )


# ============================================================================
# QUERY NORMALIZATION
# ============================================================================

def _normalize_queries(
    cms_queries,
    question,
):
    """
    Convert planner output into safe CMS query specifications.

    Supported forms:

        "hospital safety"

    or:

        {
            "query": "hospital safety",
            "dataset_id": "dgmq-aat3",
            "limit": 25
        }

    or:

        {
            "query": "...",
            "dataset_id": "...",
            "filters": {
                "State": "CA"
            }
        }
    """

    if not isinstance(
        cms_queries,
        list,
    ):
        return []

    normalized = []

    # Never allow an enormous planner list to expand the Lambda workload.
    cms_queries = cms_queries[:5]

    for item in cms_queries:

        # --------------------------------------------------------------------
        # String query
        # --------------------------------------------------------------------

        if isinstance(
            item,
            str,
        ):

            query_text = item.strip()

            if not query_text:
                continue

            query_text = query_text[
                :MAX_QUERY_TEXT_LENGTH
            ]

            normalized.append(
                {
                    "query": query_text,
                    "dataset_id": DEFAULT_DATASET_ID,
                    "limit": min(
                        MAX_RECORDS,
                        25,
                    ),
                    "filters": {},
                    "api": "pdc",
                }
            )

            continue

        # --------------------------------------------------------------------
        # Dictionary query
        # --------------------------------------------------------------------

        if isinstance(
            item,
            dict,
        ):

            query_text = str(
                item.get(
                    "query",
                    item.get(
                        "question",
                        question or "",
                    ),
                )
            ).strip()

            if not query_text:
                continue

            query_text = query_text[
                :MAX_QUERY_TEXT_LENGTH
            ]

            dataset_id = (
                item.get(
                    "dataset_id"
                )
                or item.get(
                    "dataset"
                )
                or DEFAULT_DATASET_ID
            )

            dataset_id = str(
                dataset_id
            ).strip()

            if not _valid_dataset_id(
                dataset_id
            ):
                dataset_id = DEFAULT_DATASET_ID

            limit = _safe_int(
                item.get(
                    "limit"
                ),
                25,
            )

            limit = max(
                1,
                min(
                    limit,
                    MAX_RECORDS,
                ),
            )

            filters = item.get(
                "filters",
                {},
            )

            if not isinstance(
                filters,
                dict,
            ):
                filters = {}

            # Remove internal semantic keys from actual CMS API filters.
            cms_filters = {}

            for key, value in filters.items():

                if str(key).startswith(
                    "_"
                ):
                    continue

                if value is None:
                    continue

                if (
                    isinstance(
                        value,
                        str,
                    )
                    and not value.strip()
                ):
                    continue

                cms_filters[
                    str(key)
                ] = str(value)[:200]

            # Only add real CMS-compatible inferred filters.
            inferred_filters = (
                _parse_query_filters(
                    query_text
                )
            )

            merged_filters = {
                **inferred_filters,
                **cms_filters,
            }

            api_type = str(
                item.get(
                    "api",
                    "pdc",
                )
            ).lower()

            if api_type not in (
                "pdc",
                "data_api",
                "data-api",
                "cms_data_api",
            ):
                api_type = "pdc"

            normalized.append(
                {
                    "query": query_text,
                    "dataset_id": dataset_id,
                    "limit": limit,
                    "filters": merged_filters,
                    "api": api_type,
                }
            )

    return normalized


# ============================================================================
# CMS QUERY EXECUTION
# ============================================================================

def _execute_cms_query(
    query_spec,
    run_id,
):
    """
    Execute one CMS query.

    Full records remain inside the S3 artifact.
    """

    dataset_id = query_spec.get(
        "dataset_id"
    )

    query_text = query_spec.get(
        "query",
        "",
    )

    limit = min(
        _safe_int(
            query_spec.get(
                "limit"
            ),
            25,
        ),
        MAX_RECORDS,
    )

    filters = query_spec.get(
        "filters",
        {},
    )

    if not isinstance(
        filters,
        dict,
    ):
        filters = {}

    api_type = (
        query_spec.get(
            "api"
        )
        or "pdc"
    ).lower()

    if not _valid_dataset_id(
        dataset_id
    ):
        raise ValueError(
            "Invalid CMS dataset identifier"
        )

    started = time.time()

    # ------------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------------

    if api_type in (
        "data_api",
        "data-api",
        "cms_data_api",
    ):

        records, pages, endpoint = (
            _query_data_api(
                dataset_id=dataset_id,
                filters=filters,
                limit=limit,
            )
        )

    else:

        records, pages, endpoint = (
            _query_pdc_api(
                dataset_id=dataset_id,
                filters=filters,
                limit=limit,
            )
        )

    elapsed = round(
        time.time() - started,
        3,
    )

    # ------------------------------------------------------------------------
    # Normalize records
    # ------------------------------------------------------------------------

    normalized_records = []

    for record in records:

        normalized_records.append(
            _normalize_record(
                record,
                dataset_id=dataset_id,
            )
        )

    normalized_records = (
        _deduplicate_records(
            normalized_records
        )
    )

    return {
        "status": "SUCCESS",
        "source": "CMS",
        "catalog": (
            "CMS Provider Data Catalog"
        ),
        "dataset_id": dataset_id,
        "query": query_text,
        "filters": filters,
        "endpoint": endpoint,
        "retrieval_timestamp": _utc_now(),
        "records": normalized_records,
        "record_count": len(
            normalized_records
        ),
        "pagination": {
            "pages_retrieved": pages,
            "requested_limit": limit,
            "max_pages": MAX_PAGES,
        },
        "performance": {
            "retrieval_seconds": elapsed,
        },
        "provenance": {
            "publisher": (
                "Centers for Medicare & Medicaid Services"
            ),
            "source_type": (
                "government_public_data"
            ),
            "access_method": (
                "CMS public API"
            ),
            "authentication_required": False,
            "dataset_identifier": dataset_id,
        },
        "quality": {
            "real_source": True,
            "synthetic": False,
            "generated": False,
            "records_normalized": True,
            "deduplicated": True,
        },
    }


# ============================================================================
# CMS PROVIDER DATA CATALOG API
# ============================================================================

def _query_pdc_api(
    dataset_id,
    filters,
    limit,
):
    """
    Query the CMS Provider Data Catalog.

    Pagination is deliberately conservative.
    """

    records = []
    offset = 0
    pages = 0

    endpoint_base = (
        f"{CMS_PDC_API}/datastore/query/"
        f"{dataset_id}/0"
    )

    while (
        len(records) < limit
        and pages < MAX_PAGES
    ):

        remaining = (
            limit - len(records)
        )

        page_limit = min(
            PAGE_SIZE,
            remaining,
        )

        params = {
            "offset": offset,
            "limit": page_limit,
        }

        # --------------------------------------------------------------------
        # Real CMS filters only.
        #
        # Internal semantic keys are excluded.
        # --------------------------------------------------------------------

        condition_index = 0

        for field, value in filters.items():

            if str(field).startswith(
                "_"
            ):
                continue

            if value is None:
                continue

            if (
                isinstance(
                    value,
                    str,
                )
                and not value.strip()
            ):
                continue

            params[
                f"conditions[{condition_index}][property]"
            ] = str(field)

            params[
                f"conditions[{condition_index}][value]"
            ] = str(value)

            params[
                f"conditions[{condition_index}][operator]"
            ] = "="

            condition_index += 1

        url = (
            f"{endpoint_base}?"
            f"{urlencode(params)}"
        )

        response = _http_get_json(
            url
        )

        page_records = (
            _extract_records(
                response
            )
        )

        if not page_records:
            break

        records.extend(
            page_records
        )

        pages += 1

        if len(
            page_records
        ) < page_limit:
            break

        offset += len(
            page_records
        )

    return (
        records[:limit],
        pages,
        endpoint_base,
    )


# ============================================================================
# CMS DATA API
# ============================================================================

def _query_data_api(
    dataset_id,
    filters,
    limit,
):
    """
    Query the CMS Data API.

    Kept intentionally small to avoid large Lambda payloads.
    """

    records = []
    offset = 0
    pages = 0

    endpoint_base = (
        f"{CMS_DATA_API}/dataset/"
        f"{dataset_id}/data"
    )

    while (
        len(records) < limit
        and pages < MAX_PAGES
    ):

        remaining = (
            limit - len(records)
        )

        page_size = min(
            50,
            remaining,
        )

        params = {
            "size": page_size,
            "offset": offset,
        }

        condition_index = 1

        for field, value in filters.items():

            if str(field).startswith(
                "_"
            ):
                continue

            if value is None:
                continue

            if (
                isinstance(
                    value,
                    str,
                )
                and not value.strip()
            ):
                continue

            params[
                f"filter[filter-{condition_index}]"
                "[condition][path]"
            ] = str(field)

            params[
                f"filter[filter-{condition_index}]"
                "[condition][operator]"
            ] = "="

            params[
                f"filter[filter-{condition_index}]"
                "[condition][value]"
            ] = str(value)

            condition_index += 1

        url = (
            f"{endpoint_base}?"
            f"{urlencode(params)}"
        )

        response = _http_get_json(
            url
        )

        page_records = (
            _extract_records(
                response
            )
        )

        if not page_records:
            break

        records.extend(
            page_records
        )

        pages += 1

        if len(
            page_records
        ) < page_size:
            break

        offset += len(
            page_records
        )

    return (
        records[:limit],
        pages,
        endpoint_base,
    )


# ============================================================================
# HTTP
# ============================================================================

def _http_get_json(
    url,
):
    """
    Perform public CMS HTTPS GET.
    """

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )

    try:

        with urlopen(
            request,
            timeout=REQUEST_TIMEOUT,
        ) as response:

            raw = response.read()

            if not raw:
                return {}

            return json.loads(
                raw.decode(
                    "utf-8",
                    errors="replace",
                )
            )

    except HTTPError as exc:

        body = ""

        try:

            body = exc.read().decode(
                "utf-8",
                errors="replace",
            )

        except Exception:
            pass

        raise RuntimeError(
            f"CMS HTTP {exc.code}: "
            f"{body[:500]}"
        ) from exc

    except URLError as exc:

        raise RuntimeError(
            f"CMS network error: "
            f"{exc.reason}"
        ) from exc

    except TimeoutError as exc:

        raise RuntimeError(
            "CMS API request timed out"
        ) from exc


# ============================================================================
# RESPONSE EXTRACTION
# ============================================================================

def _extract_records(
    response,
):
    """
    Normalize common CMS response structures.
    """

    if isinstance(
        response,
        list,
    ):

        return [
            item
            for item in response
            if isinstance(
                item,
                dict,
            )
        ]

    if not isinstance(
        response,
        dict,
    ):
        return []

    candidate_keys = (
        "data",
        "results",
        "records",
        "items",
    )

    for key in candidate_keys:

        value = response.get(
            key
        )

        if isinstance(
            value,
            list,
        ):

            return [
                item
                for item in value
                if isinstance(
                    item,
                    dict,
                )
            ]

    # Nested response.
    for value in response.values():

        if isinstance(
            value,
            dict,
        ):

            nested = _extract_records(
                value
            )

            if nested:
                return nested

    return []


# ============================================================================
# RECORD NORMALIZATION
# ============================================================================

def _normalize_record(
    record,
    dataset_id,
):
    """
    Preserve the CMS record and add CTS-NPN provenance.
    """

    normalized = dict(
        record
    )

    normalized[
        "_cts_npn"
    ] = {
        "source": "CMS",
        "dataset_id": dataset_id,
        "retrieved_at": _utc_now(),
        "record_hash": _record_hash(
            record
        ),
    }

    return normalized


def _deduplicate_records(
    records,
):
    """
    Remove exact duplicate records.
    """

    seen = set()
    output = []

    for record in records:

        metadata = record.get(
            "_cts_npn",
            {},
        )

        record_hash = metadata.get(
            "record_hash"
        )

        if not record_hash:

            output.append(
                record
            )

            continue

        if record_hash in seen:
            continue

        seen.add(
            record_hash
        )

        output.append(
            record
        )

    return output


def _record_hash(
    record,
):
    """
    Deterministic SHA-256 hash.
    """

    canonical = json.dumps(
        record,
        sort_keys=True,
        default=str,
        separators=(
            ",",
            ":",
        ),
    )

    return hashlib.sha256(
        canonical.encode(
            "utf-8"
        )
    ).hexdigest()


# ============================================================================
# NATURAL LANGUAGE FILTERS
# ============================================================================

def _parse_query_filters(
    query,
):
    """
    Conservative filter extraction.

    Only real CMS field filters are returned.

    Semantic topics are NOT sent to the CMS API.
    """

    filters = {}

    if not isinstance(
        query,
        str,
    ):
        return filters

    state_match = re.search(
        r"\b(?:state|in)\s+([A-Za-z]{2})\b",
        query,
        flags=re.IGNORECASE,
    )

    if state_match:

        filters["State"] = (
            state_match.group(
                1
            ).upper()
        )

    return filters


# ============================================================================
# METADATA
# ============================================================================

def _build_metadata(
    results,
):
    """
    Build compact acquisition metadata.
    """

    successful = [
        item
        for item in results
        if item.get(
            "status"
        ) == "SUCCESS"
    ]

    failed = [
        item
        for item in results
        if item.get(
            "status"
        ) == "ERROR"
    ]

    total_records = sum(
        item.get(
            "record_count",
            0,
        )
        for item in successful
    )

    datasets = sorted(
        {
            item.get(
                "dataset_id"
            )
            for item in successful
            if item.get(
                "dataset_id"
            )
        }
    )

    pages = sum(
        item.get(
            "pagination",
            {},
        ).get(
            "pages_retrieved",
            0,
        )
        for item in successful
    )

    return {
        "total_queries": len(
            results
        ),
        "successful_queries": len(
            successful
        ),
        "failed_queries": len(
            failed
        ),
        "total_records_retrieved": (
            total_records
        ),
        "total_pages_retrieved": (
            pages
        ),
        "datasets_used": datasets,
        "real_source_records": (
            total_records
        ),
        "synthetic_records": 0,
        "generated_records": 0,
        "retrieval_timestamp": _utc_now(),
        "source": (
            "Centers for Medicare & Medicaid Services"
        ),
        "source_catalog": (
            "CMS Provider Data Catalog"
        ),
        "authentication": "none",
    }


def _build_safe_metadata(
    metadata,
):
    """
    Return only small metadata to Step Functions.
    """

    if not isinstance(
        metadata,
        dict,
    ):
        return {}

    safe = {}

    for field in SAFE_METADATA_FIELDS:

        if field in metadata:

            value = metadata[
                field
            ]

            # Keep datasets small.
            if field == "datasets_used":

                value = [
                    str(x)[:128]
                    for x in value[:10]
                ]

            safe[field] = value

    return safe


# ============================================================================
# STEP FUNCTIONS PAYLOAD SAFETY
# ============================================================================

def _safe_step_functions_response(
    response,
):
    """
    Final defense against oversized Step Functions output.

    The normal response is already tiny.

    If anything unexpectedly makes it larger, reduce it to a minimal
    manifest rather than returning a huge state payload.
    """

    serialized = json.dumps(
        response,
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
        default=str,
    )

    size = len(
        serialized.encode(
            "utf-8"
        )
    )

    if size <= MAX_STEP_FUNCTIONS_OUTPUT_BYTES:
        return response

    print(
        "WARNING: CMS response exceeded internal safety limit. "
        "Returning minimal manifest."
    )

    return {
        "run_id": str(
            response.get(
                "run_id",
                "unknown",
            )
        )[:MAX_RUN_ID_LENGTH],
        "status": response.get(
            "status",
            "UNKNOWN",
        ),
        "artifacts": {
            "cms_query_results_key": (
                response.get(
                    "artifacts",
                    {},
                ).get(
                    "cms_query_results_key",
                    "",
                )
            )
        },
    }


# ============================================================================
# VALIDATION / UTILITIES
# ============================================================================

def _valid_dataset_id(
    dataset_id,
):
    """
    Validate CMS dataset identifiers.
    """

    if not dataset_id:
        return False

    return bool(
        re.fullmatch(
            r"[A-Za-z0-9_-]{3,128}",
            str(dataset_id),
        )
    )


def _safe_int(
    value,
    default,
):
    """
    Safely convert planner values to integers.
    """

    try:

        return int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return default


def _utc_now():
    """
    Return ISO-8601 UTC timestamp.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()