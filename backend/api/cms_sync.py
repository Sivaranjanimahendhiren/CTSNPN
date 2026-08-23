"""
CTS-NPN CMS Data Synchronization Agent
======================================

Purpose
-------

Synchronizes authoritative public CMS datasets into the CTS-NPN research
evidence layer.

This component is intentionally designed as a DATA INGESTION service rather
than a reasoning agent.

Responsibilities
----------------

1. Discover/access authoritative CMS datasets.
2. Retrieve records through public CMS APIs.
3. Handle API pagination.
4. Capture dataset provenance.
5. Capture schema information.
6. Create deterministic research snapshots.
7. Compute basic data-quality statistics.
8. Detect duplicate records.
9. Detect missing values.
10. Produce machine-readable metadata for downstream agents.
11. Persist raw and derived artifacts to S3.
12. Return a compact synchronization manifest.

IMPORTANT
---------

This Lambda does NOT infer that an emergency department visit was
"avoidable."

Interpretation, statistical analysis, evidence grading, and clinical/policy
reasoning belong to downstream research agents.

Design principles
-----------------

- Reproducibility
- Source traceability
- Explicit provenance
- Fail-soft dataset processing
- No fabricated records
- No fabricated statistics
- API pagination
- Dataset-specific configuration
- Research-oriented metadata
- Safe downstream consumption
"""

import hashlib
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.common.aws import put_json
from backend.common.config import CMS_BUCKET


# ============================================================================
# Configuration
# ============================================================================

DEFAULT_PAGE_SIZE = 1000
MAX_PAGES_PER_DATASET = 20
HTTP_TIMEOUT_SECONDS = 25
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.5

# CMS Provider Data Catalog datastore API.
#
# This is a public CMS API and does not require an API key.
CMS_PDC_API = (
    "https://data.cms.gov/provider-data/api/1/datastore/query"
)


# ============================================================================
# Dataset Registry
# ============================================================================

DATASET_REGISTRY = [
    {
        "dataset_key": "cms_provider_dataset_dgmq_aat3",
        "name": "CMS Provider Data Catalog Dataset dgmq-aat3",
        "source": "CMS Provider Data Catalog",
        "dataset_id": "dgmq-aat3",
        "datastore_id": "dgmq-aat3",
        "api_type": "pdc_datastore",
        "research_role": [
            "provider_context",
            "provider_availability",
            "provider_characteristics",
        ],
        "enabled": True,
    },

    # ------------------------------------------------------------------------
    # Medicare Shared Savings Program
    #
    # The exact datastore UUID can change by published version.
    #
    # Therefore this entry remains disabled until the corresponding current
    # CMS datastore UUID is configured.
    # ------------------------------------------------------------------------

    {
        "dataset_key": "cms_shared_savings_performance",
        "name": (
            "Medicare Shared Savings Program Performance Year "
            "Financial and Quality Results"
        ),
        "source": "CMS Medicare Shared Savings Program",
        "dataset_id": "performance-year-financial-and-quality-results",
        "datastore_id": "",
        "api_type": "pdc_datastore",
        "research_role": [
            "aco_performance",
            "quality",
            "benchmark",
            "expenditure",
            "shared_savings",
            "shared_losses",
        ],
        "enabled": False,
    },
]


# ============================================================================
# Generic Helpers
# ============================================================================

def utc_now():
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def json_safe(value):
    """
    Convert values into JSON-safe representations.

    CMS responses occasionally contain Decimal-like or unusual values.
    """
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [json_safe(item) for item in value]

    if isinstance(value, tuple):
        return [json_safe(item) for item in value]

    return value


def stable_hash(value):
    """
    Produce a deterministic SHA-256 hash.

    Used for:
    - Snapshot identification
    - Record fingerprints
    - Reproducibility
    """
    serialized = json.dumps(
        json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


# ============================================================================
# HTTP Client
# ============================================================================

def http_get_json(url, params=None):
    """
    Execute a GET request with retries.

    No authentication is assumed because the targeted CMS public APIs are
    intended for public machine-readable access.
    """

    if params:
        query_string = urlencode(params)
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{query_string}"

    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            request = Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": (
                        "CTS-NPN-Research-Agent/1.0"
                    ),
                },
                method="GET",
            )

            with urlopen(
                request,
                timeout=HTTP_TIMEOUT_SECONDS,
            ) as response:

                body = response.read().decode("utf-8")

                if not body:
                    return {}

                return json.loads(body)

        except HTTPError as exc:
            last_error = (
                f"HTTP {exc.code}: {exc.reason}"
            )

            # Do not retry most permanent client errors.
            if (
                400 <= exc.code < 500
                and exc.code not in (408, 429)
            ):
                break

        except URLError as exc:
            last_error = (
                f"Network error: {exc}"
            )

        except TimeoutError as exc:
            last_error = (
                f"Timeout: {exc}"
            )

        except json.JSONDecodeError as exc:
            last_error = (
                f"Invalid JSON response: {exc}"
            )

        except Exception as exc:
            last_error = str(exc)

        if attempt < MAX_RETRIES - 1:
            sleep_seconds = (
                INITIAL_BACKOFF_SECONDS
                * (2 ** attempt)
            )

            time.sleep(sleep_seconds)

    raise RuntimeError(
        "CMS API request failed after "
        f"{MAX_RETRIES} attempts: {last_error}"
    )


# ============================================================================
# CMS API Extraction
# ============================================================================

def fetch_pdc_dataset(
    datastore_id,
    page_size=DEFAULT_PAGE_SIZE,
    max_pages=MAX_PAGES_PER_DATASET,
):
    """
    Retrieve a CMS Provider Data Catalog datastore.

    Pagination is performed using offset/limit.

    Returns
    -------
    dict
        {
            "records": [...],
            "pages": int,
            "api_requests": int,
            "retrieval_complete": bool
        }
    """

    if not datastore_id:
        raise ValueError(
            "Missing CMS datastore_id."
        )

    if page_size <= 0:
        raise ValueError(
            "page_size must be greater than zero."
        )

    if max_pages <= 0:
        raise ValueError(
            "max_pages must be greater than zero."
        )

    records = []
    offset = 0
    page_number = 0
    api_requests = 0
    retrieval_complete = False

    while page_number < max_pages:

        params = {
            "offset": offset,
            "limit": page_size,
        }

        url = (
            f"{CMS_PDC_API}/"
            f"{datastore_id}/0"
        )

        response = http_get_json(
            url,
            params=params,
        )

        api_requests += 1
        page_number += 1

        page_records = extract_records(response)

        records.extend(page_records)

        # No records means there is nothing more to retrieve.
        if not page_records:
            retrieval_complete = True
            break

        # Fewer records than requested normally means final page.
        if len(page_records) < page_size:
            retrieval_complete = True
            break

        offset += page_size

    return {
        "records": records,
        "pages": page_number,
        "api_requests": api_requests,
        "retrieval_complete": retrieval_complete,
    }


def extract_records(response):
    """
    Normalize common CMS datastore response shapes.

    CMS APIs may return data under different response envelopes depending
    on dataset/API version.
    """

    if not response:
        return []

    if isinstance(response, list):
        return response

    if not isinstance(response, dict):
        return []

    candidate_keys = [
        "data",
        "results",
        "records",
        "rows",
    ]

    for key in candidate_keys:
        value = response.get(key)

        if isinstance(value, list):
            return value

    # Some responses may use a nested object.
    for value in response.values():

        if isinstance(value, dict):
            nested = extract_records(value)

            if nested:
                return nested

    return []


# ============================================================================
# Data Quality Analysis
# ============================================================================

def infer_schema(records):
    """
    Infer a lightweight schema from retrieved records.

    This is intentionally descriptive rather than prescriptive.
    """

    if not records:
        return {}

    fields = {}

    for record in records:

        if not isinstance(record, dict):
            continue

        for field, value in record.items():

            field_info = fields.setdefault(
                field,
                {
                    "observed_types": set(),
                    "non_null_count": 0,
                    "null_count": 0,
                },
            )

            if value is None or value == "":
                field_info["null_count"] += 1
                continue

            field_info["non_null_count"] += 1

            field_info["observed_types"].add(
                type(value).__name__
            )

    normalized = {}

    for field, info in fields.items():

        normalized[field] = {
            "observed_types": sorted(
                info["observed_types"]
            ),
            "non_null_count": info["non_null_count"],
            "null_count": info["null_count"],
        }

    return normalized


def profile_data(records):
    """
    Produce research-oriented data-quality statistics.

    Metrics include:
    - Row count
    - Field count
    - Duplicate count
    - Duplicate rate
    - Missing cells
    - Missing-cell rate
    - Completeness
    - Numeric summaries
    """

    row_count = len(records)

    if row_count == 0:
        return {
            "row_count": 0,
            "field_count": 0,
            "duplicate_count": 0,
            "duplicate_rate": 0.0,
            "missing_cells": 0,
            "missing_cell_rate": 0.0,
            "completeness_rate": 1.0,
            "numeric_fields": {},
        }

    all_fields = set()

    for record in records:

        if isinstance(record, dict):
            all_fields.update(record.keys())

    field_count = len(all_fields)

    fingerprints = set()

    duplicate_count = 0
    missing_cells = 0

    total_cells = (
        row_count * field_count
    )

    numeric_values = {}

    for record in records:

        if not isinstance(record, dict):
            continue

        fingerprint = stable_hash(record)

        if fingerprint in fingerprints:
            duplicate_count += 1

        fingerprints.add(fingerprint)

        for field in all_fields:

            value = record.get(field)

            if value is None or value == "":
                missing_cells += 1
                continue

            if isinstance(value, bool):
                continue

            if isinstance(value, (int, float)):

                numeric_values.setdefault(
                    field,
                    [],
                ).append(float(value))

    numeric_summary = {}

    for field, values in numeric_values.items():

        if not values:
            continue

        numeric_summary[field] = {
            "count": len(values),
            "minimum": min(values),
            "maximum": max(values),
            "mean": (
                sum(values) / len(values)
            ),
        }

    duplicate_rate = (
        duplicate_count / row_count
        if row_count
        else 0.0
    )

    missing_rate = (
        missing_cells / total_cells
        if total_cells
        else 0.0
    )

    return {
        "row_count": row_count,
        "field_count": field_count,
        "duplicate_count": duplicate_count,
        "duplicate_rate": duplicate_rate,
        "missing_cells": missing_cells,
        "missing_cell_rate": missing_rate,
        "completeness_rate": 1 - missing_rate,
        "numeric_fields": numeric_summary,
    }


# ============================================================================
# Research Manifest
# ============================================================================

def build_dataset_manifest(
    config,
    retrieval,
    retrieval_timestamp,
):
    """
    Construct a reproducible research dataset manifest.
    """

    records = retrieval["records"]

    schema = infer_schema(records)
    profile = profile_data(records)

    snapshot_hash = stable_hash(records)

    datastore_id = config.get(
        "datastore_id"
    )

    return {
        "dataset_key": config["dataset_key"],
        "dataset_name": config["name"],
        "dataset_id": config["dataset_id"],
        "datastore_id": datastore_id,
        "source": config["source"],
        "api_type": config["api_type"],
        "research_role": config.get(
            "research_role",
            [],
        ),

        "provenance": {
            "source_organization": (
                "Centers for Medicare & Medicaid Services"
            ),
            "source_url": (
                "https://data.cms.gov/"
            ),
            "api_endpoint": (
                f"{CMS_PDC_API}/"
                f"{datastore_id}/0"
                if datastore_id
                else None
            ),
            "retrieved_at": retrieval_timestamp,
            "retrieval_method": (
                "CMS public datastore API"
            ),
        },

        "retrieval": {
            "pages": retrieval["pages"],
            "api_requests": retrieval[
                "api_requests"
            ],
            "retrieval_complete": retrieval[
                "retrieval_complete"
            ],
        },

        "quality": profile,

        "schema": schema,

        "snapshot": {
            "record_count": len(records),
            "sha256": snapshot_hash,
        },
    }


# ============================================================================
# S3 Persistence
# ============================================================================

def store_dataset(
    run_date,
    config,
    retrieval,
    manifest,
):
    """
    Persist raw records and research metadata to S3.
    """

    if not CMS_BUCKET:
        print(
            "[CMS] CMS_BUCKET is not configured. "
            "Skipping S3 persistence."
        )
        return

    dataset_key = config["dataset_key"]

    base_path = (
        f"cms/"
        f"{run_date}/"
        f"{dataset_key}"
    )

    # Raw dataset snapshot.
    put_json(
        CMS_BUCKET,
        f"{base_path}/raw.json",
        {
            "dataset": manifest,
            "records": json_safe(
                retrieval["records"]
            ),
        },
    )

    # Dataset manifest.
    put_json(
        CMS_BUCKET,
        f"{base_path}/manifest.json",
        manifest,
    )

    # Data-quality profile.
    put_json(
        CMS_BUCKET,
        f"{base_path}/quality.json",
        manifest["quality"],
    )

    # Schema snapshot.
    put_json(
        CMS_BUCKET,
        f"{base_path}/schema.json",
        manifest["schema"],
    )


# ============================================================================
# Dataset Synchronization
# ============================================================================

def sync_dataset(config, run_date):
    """
    Synchronize one dataset.

    Failure of one dataset does not terminate the entire synchronization
    process.
    """

    if not config.get("enabled", True):

        return {
            "dataset_key": config["dataset_key"],
            "name": config["name"],
            "status": "SKIPPED",
            "reason": (
                "Dataset disabled in registry"
            ),
        }

    started_at = utc_now()
    started_epoch = time.time()

    try:

        print(
            "[CMS] Starting dataset: "
            f"{config['name']}"
        )

        retrieval = fetch_pdc_dataset(
            datastore_id=config.get(
                "datastore_id"
            ),
            page_size=DEFAULT_PAGE_SIZE,
            max_pages=MAX_PAGES_PER_DATASET,
        )

        completed_at = utc_now()

        duration_seconds = (
            time.time() - started_epoch
        )

        manifest = build_dataset_manifest(
            config=config,
            retrieval=retrieval,
            retrieval_timestamp=completed_at,
        )

        manifest["sync"] = {
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_seconds": round(
                duration_seconds,
                3,
            ),
        }

        store_dataset(
            run_date=run_date,
            config=config,
            retrieval=retrieval,
            manifest=manifest,
        )

        record_count = len(
            retrieval["records"]
        )

        print(
            "[CMS] Completed dataset: "
            f"{config['name']} | "
            f"records={record_count}"
        )

        return {
            "dataset_key": config["dataset_key"],
            "name": config["name"],
            "status": "SUCCESS",
            "record_count": record_count,
            "pages": retrieval["pages"],
            "api_requests": retrieval[
                "api_requests"
            ],
            "retrieval_complete": retrieval[
                "retrieval_complete"
            ],
            "snapshot_sha256": manifest[
                "snapshot"
            ]["sha256"],
            "quality": manifest["quality"],
            "duration_seconds": round(
                duration_seconds,
                3,
            ),
        }

    except Exception as exc:

        error_message = str(exc)

        print(
            "[CMS] Dataset failed: "
            f"{config['name']} | "
            f"{error_message}"
        )

        return {
            "dataset_key": config["dataset_key"],
            "name": config["name"],
            "status": "FAILED",
            "error": error_message,
            "duration_seconds": round(
                time.time() - started_epoch,
                3,
            ),
        }


# ============================================================================
# Event Validation
# ============================================================================

def validate_requested_datasets(value):
    """
    Validate an optional list of requested dataset keys.
    """

    if value is None:
        return None

    if not isinstance(value, list):
        raise ValueError(
            "'datasets' must be a JSON array."
        )

    cleaned = []

    for item in value:

        if not isinstance(item, str):
            raise ValueError(
                "Every dataset name in 'datasets' "
                "must be a string."
            )

        item = item.strip()

        if not item:
            raise ValueError(
                "Dataset names cannot be empty."
            )

        if item not in cleaned:
            cleaned.append(item)

    return cleaned


# ============================================================================
# Lambda Entry Point
# ============================================================================

def lambda_handler(event, context):
    """
    Synchronize authoritative CMS datasets.

    EventBridge-compatible entry point.

    Optional event parameters:

        {
            "datasets": [
                "cms_provider_dataset_dgmq_aat3"
            ]
        }

    If datasets is omitted, every enabled dataset in the registry is
    synchronized.
    """

    sync_started = utc_now()
    sync_started_epoch = time.time()

    print(
        "============================================================"
    )
    print(
        "CTS-NPN CMS SYNCHRONIZATION START"
    )
    print(
        f"Started: {sync_started}"
    )
    print(
        "============================================================"
    )

    # ------------------------------------------------------------------------
    # Validate event
    # ------------------------------------------------------------------------

    if event is None:
        event = {}

    if not isinstance(event, dict):
        return {
            "statusCode": 400,
            "body": json.dumps({
                "status": "FAILED",
                "error": (
                    "Lambda event must be a JSON object."
                ),
            }),
        }

    try:
        requested_datasets = validate_requested_datasets(
            event.get("datasets")
        )
    except ValueError as exc:

        print(
            f"[CMS] Invalid event: {exc}"
        )

        return {
            "statusCode": 400,
            "body": json.dumps({
                "status": "FAILED",
                "error": "INVALID_REQUEST",
                "message": str(exc),
            }),
        }

    # ------------------------------------------------------------------------
    # Run metadata
    # ------------------------------------------------------------------------

    run_date = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d")

    sync_id = getattr(
        context,
        "aws_request_id",
        None,
    ) or getattr(
        context,
        "request_id",
        None,
    ) or "manual-sync"

    # ------------------------------------------------------------------------
    # Dataset selection
    # ------------------------------------------------------------------------

    if requested_datasets is None:

        selected_registry = [
            dataset
            for dataset in DATASET_REGISTRY
            if dataset.get("enabled", True)
        ]

    else:

        selected_registry = [
            dataset
            for dataset in DATASET_REGISTRY
            if dataset["dataset_key"]
            in requested_datasets
        ]

        known_keys = {
            dataset["dataset_key"]
            for dataset in DATASET_REGISTRY
        }

        unknown_keys = [
            key
            for key in requested_datasets
            if key not in known_keys
        ]

        if unknown_keys:

            print(
                "[CMS] Unknown dataset keys requested: "
                f"{unknown_keys}"
            )

            return {
                "statusCode": 400,
                "body": json.dumps({
                    "status": "FAILED",
                    "error": "UNKNOWN_DATASET",
                    "unknown_datasets": unknown_keys,
                }),
            }

    # ------------------------------------------------------------------------
    # Process datasets
    # ------------------------------------------------------------------------

    results = []

    total_records = 0
    successful = 0
    failed = 0
    skipped = 0

    for dataset_config in selected_registry:

        result = sync_dataset(
            config=dataset_config,
            run_date=run_date,
        )

        results.append(result)

        status = result.get("status")

        if status == "SUCCESS":

            successful += 1

            total_records += result.get(
                "record_count",
                0,
            )

        elif status == "FAILED":

            failed += 1

        elif status == "SKIPPED":

            skipped += 1

    # ------------------------------------------------------------------------
    # Global synchronization manifest
    # ------------------------------------------------------------------------

    sync_completed = utc_now()

    sync_manifest = {
        "system": "CTS-NPN",

        "component": (
            "CMS Data Synchronization Agent"
        ),

        "sync_id": sync_id,

        "started_at": sync_started,

        "completed_at": sync_completed,

        "duration_seconds": round(
            time.time() - sync_started_epoch,
            3,
        ),

        "source": {
            "organization": (
                "Centers for Medicare & Medicaid Services"
            ),
            "access_method": (
                "Public CMS Data API"
            ),
            "authentication": "None",
            "source_url": (
                "https://data.cms.gov/"
            ),
        },

        "execution": {
            "datasets_requested": (
                requested_datasets
                if requested_datasets is not None
                else "ALL_ENABLED"
            ),
            "datasets_processed": len(
                selected_registry
            ),
            "successful": successful,
            "failed": failed,
            "skipped": skipped,
            "total_records": total_records,
        },

        "dataset_results": results,

        "research_integrity": {
            "raw_data_preserved": bool(
                CMS_BUCKET
            ),
            "provenance_recorded": True,
            "schema_recorded": True,
            "quality_profile_recorded": True,
            "snapshot_hash_recorded": True,
            "derived_clinical_interpretation": False,
        },
    }

    # ------------------------------------------------------------------------
    # Persist global synchronization manifest
    # ------------------------------------------------------------------------

    if CMS_BUCKET:

        timestamp_key = datetime.now(
            timezone.utc
        ).strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        put_json(
            CMS_BUCKET,
            (
                "cms/"
                "sync_reports/"
                f"{timestamp_key}.json"
            ),
            sync_manifest,
        )

        # Latest pointer makes downstream retrieval easier.
        put_json(
            CMS_BUCKET,
            "cms/latest_sync.json",
            sync_manifest,
        )

    # ------------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------------

    print(
        "============================================================"
    )

    print(
        "CTS-NPN CMS SYNCHRONIZATION COMPLETE"
    )

    print(
        f"Datasets processed : "
        f"{len(selected_registry)}"
    )

    print(
        f"Successful         : "
        f"{successful}"
    )

    print(
        f"Failed             : "
        f"{failed}"
    )

    print(
        f"Skipped            : "
        f"{skipped}"
    )

    print(
        f"Records retrieved  : "
        f"{total_records}"
    )

    print(
        "============================================================"
    )

    return {
        "statusCode": 200 if failed == 0 else 207,
        "body": json.dumps(
            json_safe(sync_manifest),
            ensure_ascii=False,
        ),
    }