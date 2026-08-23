"""
CTS-NPN CDC PLACES Research Data Tool
=====================================

Purpose
-------
Provides a production-oriented interface to the CDC PLACES API for the
CTS-NPN research pipeline.

The tool is designed for evidence-oriented research rather than simple
data retrieval.

It provides:

1. Geographic filtering
2. Indicator filtering
3. Pagination
4. Deterministic limits
5. Response normalization
6. Provenance metadata
7. Basic descriptive statistics
8. Data-quality diagnostics
9. Explicit error reporting
10. Research-friendly evidence records

Important
---------
CDC PLACES provides population/community-level public-health data.

It MUST NOT be interpreted as individual-level clinical evidence.

The output deliberately separates:

    observed data
    derived statistics
    metadata
    interpretation constraints

This allows downstream Evidence, Synthesis, and Critic agents to reason
about the source without treating population-level observations as
patient-level clinical facts.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from backend.common.config import CDC_PLACES_API, MAX_RESULTS


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 30

MAX_API_LIMIT = 50000

MAX_PAGE_SIZE = 5000

SOURCE_NAME = "CDC PLACES"

SOURCE_TYPE = "public_health_dataset"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    """
    Return an ISO-8601 UTC timestamp.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    """
    Safely convert a value to integer.
    """

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(
    value: Any,
) -> Optional[float]:
    """
    Safely convert an API value to float.

    Returns None for missing, invalid, NaN, or infinite values.
    """

    try:
        if value is None or value == "":
            return None

        number = float(value)

        if math.isnan(number) or math.isinf(number):
            return None

        return number

    except (TypeError, ValueError):
        return None


def _clean_string(
    value: Any,
) -> str:
    """
    Convert API values to safe strings.
    """

    if value is None:
        return ""

    return str(value).strip()


# ---------------------------------------------------------------------------
# Record normalization
# ---------------------------------------------------------------------------

def _normalize_record(
    record: dict[str, Any],
) -> dict[str, Any]:
    """
    Normalize one CDC PLACES record.

    The original CDC fields are retained.

    Common geographic and measurement fields are exposed under the
    _cts_npn namespace so downstream agents have a stable structure.
    """

    normalized = dict(record)

    geography = {
        "state": _clean_string(
            record.get("StateAbbr")
            or record.get("stateabbr")
        ),
        "state_name": _clean_string(
            record.get("StateDesc")
            or record.get("state_name")
        ),
        "county": _clean_string(
            record.get("CountyName")
            or record.get("county_name")
        ),
        "county_fips": _clean_string(
            record.get("CountyFIPS")
            or record.get("countyfips")
        ),
        "census_tract": _clean_string(
            record.get("CensusTractNumber")
            or record.get("censustractnumber")
        ),
    }

    measure = {
        "name": _clean_string(
            record.get("Measure")
            or record.get("MeasureId")
            or record.get("measure")
            or record.get("measureid")
        ),
        "category": _clean_string(
            record.get("Category")
            or record.get("CategoryType")
            or record.get("category")
        ),
        "value": _safe_float(
            record.get("Data_Value")
            if record.get("Data_Value") is not None
            else (
                record.get("DataValue")
                if record.get("DataValue") is not None
                else record.get("data_value")
            )
        ),
        "low": _safe_float(
            record.get("Low_Confidence_Limit")
            if record.get("Low_Confidence_Limit") is not None
            else record.get("low_confidence_limit")
        ),
        "high": _safe_float(
            record.get("High_Confidence_Limit")
            if record.get("High_Confidence_Limit") is not None
            else record.get("high_confidence_limit")
        ),
    }

    normalized["_cts_npn"] = {
        "source": SOURCE_NAME,
        "source_type": SOURCE_TYPE,
        "retrieved_at": _utc_now(),
        "geography": geography,
        "measure": measure,
    }

    return normalized


# ---------------------------------------------------------------------------
# API parameters
# ---------------------------------------------------------------------------

def _build_params(
    state: Optional[str] = None,
    county: Optional[str] = None,
    census_tract: Optional[str] = None,
    indicator_type: Optional[str] = None,
    limit: int = MAX_RESULTS,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Build CDC/Socrata API parameters.
    """

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = MAX_RESULTS

    try:
        offset = int(offset)
    except (TypeError, ValueError):
        offset = 0

    page_size = max(
        1,
        min(limit, MAX_PAGE_SIZE),
    )

    params: dict[str, Any] = {
        "$limit": page_size,
        "$offset": max(0, offset),
    }

    if state:
        params["StateAbbr"] = state.strip().upper()

    if county:
        params["CountyName"] = county.strip()

    if census_tract:
        params["CensusTractNumber"] = census_tract.strip()

    if indicator_type:
        params["CategoryType"] = indicator_type.strip().upper()

    return params


# ---------------------------------------------------------------------------
# API request
# ---------------------------------------------------------------------------

def _request(
    params: dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Execute a CDC PLACES API request.

    Returns
    -------
    tuple
        records, request metadata

    Raises
    ------
    RuntimeError
        When the API/network/response format fails.
    """

    started = datetime.now(timezone.utc)

    try:
        response = requests.get(
            CDC_PLACES_API,
            params=params,
            timeout=timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "CTS-NPN-Research-Agent/1.0"
                ),
            },
        )

        response.raise_for_status()

        try:
            payload = response.json()

        except ValueError as exc:
            raise RuntimeError(
                "CDC PLACES returned a non-JSON response."
            ) from exc

        if not isinstance(payload, list):
            raise RuntimeError(
                "Unexpected CDC PLACES response type: "
                f"{type(payload).__name__}"
            )

        elapsed = (
            datetime.now(timezone.utc)
            - started
        ).total_seconds()

        metadata = {
            "http_status": response.status_code,
            "records_returned": len(payload),
            "request_duration_seconds": round(
                elapsed,
                4,
            ),
            "endpoint": CDC_PLACES_API,
            "parameters": dict(params),
        }

        return payload, metadata

    except requests.exceptions.Timeout as exc:

        logger.error(
            "CDC PLACES request timed out: %s",
            exc,
        )

        raise RuntimeError(
            "CDC PLACES API request timed out."
        ) from exc

    except requests.exceptions.ConnectionError as exc:

        logger.error(
            "CDC PLACES connection failed: %s",
            exc,
        )

        raise RuntimeError(
            "Unable to connect to CDC PLACES API."
        ) from exc

    except requests.exceptions.HTTPError as exc:

        status = (
            exc.response.status_code
            if exc.response is not None
            else "unknown"
        )

        logger.error(
            "CDC PLACES HTTP error %s: %s",
            status,
            exc,
        )

        raise RuntimeError(
            "CDC PLACES HTTP request failed "
            f"with status {status}."
        ) from exc

    except requests.exceptions.RequestException as exc:

        logger.error(
            "CDC PLACES request failed: %s",
            exc,
        )

        raise RuntimeError(
            f"CDC PLACES request failed: {str(exc)}"
        ) from exc


# ---------------------------------------------------------------------------
# Descriptive statistics
# ---------------------------------------------------------------------------

def _calculate_statistics(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Calculate descriptive statistics over retrieved records.

    These statistics describe only the returned dataset.

    They do NOT establish:

    - causality
    - individual clinical risk
    - individual emergency status
    - medical necessity
    """

    values: list[float] = []

    states: Counter[str] = Counter()

    counties: Counter[str] = Counter()

    measures: Counter[str] = Counter()

    for record in records:

        metadata = record.get(
            "_cts_npn",
            {},
        )

        geography = metadata.get(
            "geography",
            {},
        )

        measure = metadata.get(
            "measure",
            {},
        )

        state = geography.get("state")

        county = geography.get("county")

        measure_name = measure.get("name")

        if state:
            states[state] += 1

        if county:
            counties[county] += 1

        if measure_name:
            measures[measure_name] += 1

        value = measure.get("value")

        if value is not None:
            values.append(value)

    statistics: dict[str, Any] = {
        "record_count": len(records),
        "numeric_value_count": len(values),
        "state_count": len(states),
        "county_count": len(counties),
        "measure_count": len(measures),
    }

    if values:

        mean = sum(values) / len(values)

        sorted_values = sorted(values)

        mid = len(sorted_values) // 2

        if len(sorted_values) % 2 == 0:

            median = (
                sorted_values[mid - 1]
                + sorted_values[mid]
            ) / 2

        else:
            median = sorted_values[mid]

        statistics.update(
            {
                "mean": round(mean, 4),
                "median": round(median, 4),
                "minimum": round(
                    min(values),
                    4,
                ),
                "maximum": round(
                    max(values),
                    4,
                ),
            }
        )

    else:

        statistics.update(
            {
                "mean": None,
                "median": None,
                "minimum": None,
                "maximum": None,
            }
        )

    statistics["top_states"] = [
        {
            "state": state,
            "records": count,
        }
        for state, count in states.most_common(10)
    ]

    statistics["top_counties"] = [
        {
            "county": county,
            "records": count,
        }
        for county, count in counties.most_common(10)
    ]

    statistics["top_measures"] = [
        {
            "measure": measure,
            "records": count,
        }
        for measure, count in measures.most_common(20)
    ]

    return statistics


# ---------------------------------------------------------------------------
# Data-quality diagnostics
# ---------------------------------------------------------------------------

def _calculate_data_quality(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Calculate basic data-quality diagnostics.

    These checks are descriptive only and do not replace formal
    dataset validation.
    """

    total = len(records)

    if total == 0:
        return {
            "record_count": 0,
            "records_with_geography": 0,
            "records_with_measure": 0,
            "records_with_numeric_value": 0,
            "missing_geography_rate": 0.0,
            "missing_measure_rate": 0.0,
            "missing_numeric_value_rate": 0.0,
        }

    geography_count = 0
    measure_count = 0
    numeric_count = 0

    for record in records:

        metadata = record.get(
            "_cts_npn",
            {},
        )

        geography = metadata.get(
            "geography",
            {},
        )

        measure = metadata.get(
            "measure",
            {},
        )

        has_geography = bool(
            geography.get("state")
            or geography.get("county")
            or geography.get("census_tract")
        )

        has_measure = bool(
            measure.get("name")
            or measure.get("category")
        )

        has_numeric_value = (
            measure.get("value") is not None
        )

        if has_geography:
            geography_count += 1

        if has_measure:
            measure_count += 1

        if has_numeric_value:
            numeric_count += 1

    return {
        "record_count": total,
        "records_with_geography": geography_count,
        "records_with_measure": measure_count,
        "records_with_numeric_value": numeric_count,
        "missing_geography_rate": round(
            1 - (geography_count / total),
            4,
        ),
        "missing_measure_rate": round(
            1 - (measure_count / total),
            4,
        ),
        "missing_numeric_value_rate": round(
            1 - (numeric_count / total),
            4,
        ),
    }


# ---------------------------------------------------------------------------
# Main data retrieval function
# ---------------------------------------------------------------------------

def get_health_data(
    state: Optional[str] = None,
    county: Optional[str] = None,
    census_tract: Optional[str] = None,
    limit: Optional[int] = None,
    indicator_type: Optional[str] = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Retrieve CDC PLACES health data.

    Parameters
    ----------
    state:
        State abbreviation such as CA, NY, TX.

    county:
        County name.

    census_tract:
        Census tract identifier.

    limit:
        Maximum number of records.

    indicator_type:
        Optional CDC indicator category.

    offset:
        Pagination offset.

    Returns
    -------
    list[dict]
        Normalized CDC PLACES records.

    Raises
    ------
    RuntimeError
        If the CDC API cannot be queried successfully.
    """

    if limit is None:
        limit = MAX_RESULTS

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = MAX_RESULTS

    limit = max(
        1,
        min(limit, MAX_API_LIMIT),
    )

    params = _build_params(
        state=state,
        county=county,
        census_tract=census_tract,
        indicator_type=indicator_type,
        limit=limit,
        offset=offset,
    )

    raw_records, request_metadata = _request(
        params
    )

    records = [
        _normalize_record(record)
        for record in raw_records
        if isinstance(record, dict)
    ]

    for record in records:
        record["_cts_npn"]["request"] = request_metadata

    return records[:limit]


# ---------------------------------------------------------------------------
# Research-oriented indicator search
# ---------------------------------------------------------------------------

def search_indicators(
    indicator_type: str = "CHRONIC",
    state: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Search CDC PLACES indicators.

    Retained for compatibility with the Research Agent.
    """

    effective_limit = (
        limit
        if limit is not None
        else MAX_RESULTS
    )

    return get_health_data(
        state=state,
        indicator_type=indicator_type,
        limit=effective_limit,
    )


# ---------------------------------------------------------------------------
# Evidence-oriented query
# ---------------------------------------------------------------------------

def research_query(
    state: Optional[str] = None,
    county: Optional[str] = None,
    census_tract: Optional[str] = None,
    indicator_type: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """
    Execute a CDC PLACES query and return a complete evidence package.

    Intended for the CTS-NPN Research Agent.

    The returned package contains:

        records
        query
        provenance
        statistics
        data_quality
        interpretation_constraints
    """

    effective_limit = (
        limit
        if limit is not None
        else MAX_RESULTS
    )

    try:
        effective_limit = int(effective_limit)
    except (TypeError, ValueError):
        effective_limit = MAX_RESULTS

    effective_limit = max(
        1,
        min(effective_limit, MAX_API_LIMIT),
    )

    params = _build_params(
        state=state,
        county=county,
        census_tract=census_tract,
        indicator_type=indicator_type,
        limit=effective_limit,
        offset=0,
    )

    raw_records, request_metadata = _request(
        params
    )

    records = [
        _normalize_record(record)
        for record in raw_records
        if isinstance(record, dict)
    ]

    for record in records:
        record["_cts_npn"]["request"] = request_metadata

    statistics = _calculate_statistics(
        records
    )

    data_quality = _calculate_data_quality(
        records
    )

    query_parameters = {
        "state": state,
        "county": county,
        "census_tract": census_tract,
        "indicator_type": indicator_type,
        "limit": effective_limit,
    }

    provenance = {
        "source": SOURCE_NAME,
        "source_type": SOURCE_TYPE,
        "endpoint": CDC_PLACES_API,
        "retrieved_at": _utc_now(),
        "query": query_parameters,
        "request": request_metadata,
    }

    return {
        "source": SOURCE_NAME,
        "source_type": SOURCE_TYPE,
        "query": query_parameters,
        "records": records,
        "record_count": len(records),
        "statistics": statistics,
        "data_quality": data_quality,
        "provenance": provenance,
        "evidence_interpretation": {
            "level": "population",
            "supports": [
                "descriptive population-health context",
                "geographic comparison",
                "health-indicator prevalence context",
                "community-level risk-factor analysis",
            ],
            "does_not_support": [
                "individual diagnosis",
                "individual clinical risk determination",
                "individual emergency classification",
                "clinical treatment decisions",
                "proof that a specific ED visit was avoidable",
            ],
        },
    }


# ---------------------------------------------------------------------------
# Dataset health / connectivity check
# ---------------------------------------------------------------------------

def health_check() -> dict[str, Any]:
    """
    Verify CDC PLACES API availability.

    Returns a structured health status instead of raising an exception.
    """

    started = datetime.now(
        timezone.utc
    )

    try:

        records, metadata = _request(
            {
                "$limit": 1,
                "$offset": 0,
            },
            timeout=10,
        )

        elapsed = (
            datetime.now(timezone.utc)
            - started
        ).total_seconds()

        return {
            "status": "HEALTHY",
            "source": SOURCE_NAME,
            "endpoint": CDC_PLACES_API,
            "records_tested": len(records),
            "latency_seconds": round(
                elapsed,
                4,
            ),
            "checked_at": _utc_now(),
            "metadata": metadata,
        }

    except Exception as exc:

        return {
            "status": "UNAVAILABLE",
            "source": SOURCE_NAME,
            "endpoint": CDC_PLACES_API,
            "checked_at": _utc_now(),
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Backward-compatible alias
# ---------------------------------------------------------------------------

def query(
    state: Optional[str] = None,
    county: Optional[str] = None,
    census_tract: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Backward-compatible alias for get_health_data().
    """

    return get_health_data(
        state=state,
        county=county,
        census_tract=census_tract,
        limit=limit,
    )