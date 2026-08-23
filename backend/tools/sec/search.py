"""
CTS-NPN SEC EDGAR Research Search Tool
======================================

Production-oriented SEC EDGAR retrieval utility for CTS-NPN.

Purpose
-------
Retrieves primary-source SEC filing metadata from official SEC
data APIs and converts it into normalized research evidence records.

Supported inputs
----------------
- Company ticker: "UNH"
- Company name: "UnitedHealth Group"
- CIK: "731766"
- CIK with leading zeros: "0000731766"

Supported filing forms
----------------------
- 10-K
- 10-Q
- 8-K
- 20-F
- 40-F
- 6-K
- DEF 14A
- S-1
- S-3
- 13F-HR

Important
---------
The SEC public data APIs do not require an API key.

Automated requests should identify the client using a meaningful
User-Agent containing a contact address.

This module intentionally separates:

1. Company resolution
2. Filing metadata retrieval
3. Filing URL construction
4. Filing document retrieval
5. Research evidence packaging

No LLM-generated claims are inserted into this module.

The downstream Evidence, Critic, and Synthesis agents are responsible
for interpretation.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Optional
from urllib.parse import quote

import requests

from backend.common.config import MAX_RESULTS


# ============================================================================
# Logging
# ============================================================================

logger = logging.getLogger(__name__)


# ============================================================================
# SEC endpoints
# ============================================================================

SEC_DATA_BASE = "https://data.sec.gov"
SEC_WEB_BASE = "https://www.sec.gov"

SUBMISSIONS_URL = SEC_DATA_BASE + "/submissions/CIK{cik}.json"

# SEC ticker/CIK/company-name association file.
# This file is hosted on sec.gov, not data.sec.gov.
COMPANY_TICKERS_URL = (
    SEC_WEB_BASE + "/files/company_tickers.json"
)


# ============================================================================
# Runtime configuration
# ============================================================================

DEFAULT_TIMEOUT = 30

MAX_REQUEST_RETRIES = 3

DEFAULT_MAX_RESULTS = min(
    int(MAX_RESULTS),
    50,
)

# SEC requests should identify the client.
#
# Recommended:
#
# SEC_USER_AGENT="CTS-NPN Research Agent research@example.com"
#
# You can configure this through the environment.
SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "CTS-NPN Research Agent research@example.com",
).strip()

if not SEC_USER_AGENT:
    SEC_USER_AGENT = (
        "CTS-NPN Research Agent research@example.com"
    )


# ============================================================================
# HTTP session
# ============================================================================

_SESSION = requests.Session()

# IMPORTANT:
# Do NOT set a global "Host" header here.
#
# The same session is used for:
#
#   data.sec.gov
#
# and:
#
#   www.sec.gov
#
# A fixed Host header can break requests to the second domain.

_SESSION.headers.update(
    {
        "User-Agent": SEC_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
    }
)


# ============================================================================
# Utility helpers
# ============================================================================

def _normalize_text(value: Any) -> str:
    """
    Convert a value into normalized searchable text.
    """
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def _normalize_cik(value: Any) -> Optional[str]:
    """
    Normalize a CIK into SEC's 10-digit representation.

    Examples
    --------
    731766
        -> 0000731766

    0000731766
        -> 0000731766
    """
    if value is None:
        return None

    value = str(value).strip()

    digits = re.sub(
        r"\D",
        "",
        value,
    )

    if not digits:
        return None

    return digits.zfill(10)


def _normalize_form(
    form: Optional[str],
) -> Optional[str]:
    """
    Normalize SEC filing form names.
    """
    if not form:
        return None

    return re.sub(
        r"\s+",
        " ",
        str(form).upper().strip(),
    )


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


def _utc_now() -> str:
    """
    Return an ISO-8601 UTC timestamp.
    """
    return time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(),
    )


# ============================================================================
# SEC HTTP request helper
# ============================================================================

def _request_json(
    url: str,
    params: Optional[dict[str, Any]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """
    Perform a resilient GET request against an SEC JSON endpoint.

    Retries transient HTTP/network failures.

    Raises
    ------
    RuntimeError
        If the SEC endpoint cannot be reached successfully.
    """

    last_error: Optional[Exception] = None

    for attempt in range(
        1,
        MAX_REQUEST_RETRIES + 1,
    ):
        try:
            response = _SESSION.get(
                url,
                params=params,
                timeout=timeout,
                headers={
                    "User-Agent": SEC_USER_AGENT,
                    "Accept": "application/json",
                },
            )

            # --------------------------------------------------------------
            # Rate limiting / temporary server failures
            # --------------------------------------------------------------

            if response.status_code in (
                429,
                500,
                502,
                503,
                504,
            ):
                wait_seconds = min(
                    2 ** (attempt - 1),
                    8,
                )

                logger.warning(
                    "SEC temporary response %s. "
                    "Retrying in %ss.",
                    response.status_code,
                    wait_seconds,
                )

                if attempt < MAX_REQUEST_RETRIES:
                    time.sleep(wait_seconds)

                continue

            response.raise_for_status()

            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError(
                    "SEC returned a non-JSON response."
                ) from exc

            if not isinstance(payload, dict):
                raise RuntimeError(
                    "Unexpected SEC JSON response type: "
                    f"{type(payload).__name__}"
                )

            return payload

        except requests.exceptions.Timeout as exc:
            last_error = exc

            if attempt < MAX_REQUEST_RETRIES:
                wait_seconds = min(
                    2 ** (attempt - 1),
                    8,
                )

                logger.warning(
                    "SEC request timeout on attempt "
                    "%s/%s. Retrying in %ss.",
                    attempt,
                    MAX_REQUEST_RETRIES,
                    wait_seconds,
                )

                time.sleep(wait_seconds)

        except requests.exceptions.ConnectionError as exc:
            last_error = exc

            if attempt < MAX_REQUEST_RETRIES:
                wait_seconds = min(
                    2 ** (attempt - 1),
                    8,
                )

                logger.warning(
                    "SEC connection error on attempt "
                    "%s/%s. Retrying in %ss.",
                    attempt,
                    MAX_REQUEST_RETRIES,
                    wait_seconds,
                )

                time.sleep(wait_seconds)

        except requests.exceptions.HTTPError as exc:
            last_error = exc

            status = (
                exc.response.status_code
                if exc.response is not None
                else "unknown"
            )

            logger.error(
                "SEC HTTP error %s: %s",
                status,
                exc,
            )

            # Do not retry normal client errors such as 400/403/404.
            if status not in (
                429,
                500,
                502,
                503,
                504,
            ):
                break

            if attempt < MAX_REQUEST_RETRIES:
                wait_seconds = min(
                    2 ** (attempt - 1),
                    8,
                )

                time.sleep(wait_seconds)

        except requests.exceptions.RequestException as exc:
            last_error = exc

            if attempt < MAX_REQUEST_RETRIES:
                wait_seconds = min(
                    2 ** (attempt - 1),
                    8,
                )

                logger.warning(
                    "SEC request failed on attempt "
                    "%s/%s: %s",
                    attempt,
                    MAX_REQUEST_RETRIES,
                    exc,
                )

                time.sleep(wait_seconds)

        except ValueError as exc:
            last_error = exc
            break

    raise RuntimeError(
        "SEC request failed after "
        f"{MAX_REQUEST_RETRIES} attempts: "
        f"{last_error}"
    )


# ============================================================================
# Company resolution
# ============================================================================

def _load_company_tickers() -> dict[str, Any]:
    """
    Retrieve SEC's official ticker/CIK/company mapping.
    """

    return _request_json(
        COMPANY_TICKERS_URL,
        timeout=DEFAULT_TIMEOUT,
    )


def _resolve_company(
    query: str,
) -> Optional[dict[str, Any]]:
    """
    Resolve a company query into SEC CIK metadata.

    Resolution order
    ----------------
    1. Direct CIK
    2. Exact ticker
    3. Exact company name
    4. Partial ticker/company-name match
    """

    query = _normalize_text(query)

    if not query:
        return None

    # ------------------------------------------------------------------
    # Direct CIK
    # ------------------------------------------------------------------

    if query.isdigit():
        cik = _normalize_cik(query)

        if not cik:
            return None

        return {
            "cik": cik,
            "ticker": None,
            "title": None,
            "match_type": "cik",
        }

    # ------------------------------------------------------------------
    # Load SEC company mapping
    # ------------------------------------------------------------------

    data = _load_company_tickers()

    if not isinstance(data, dict):
        return None

    query_lower = query.lower()

    exact_ticker: Optional[dict[str, Any]] = None
    exact_name: Optional[dict[str, Any]] = None

    partial_matches: list[dict[str, Any]] = []

    # SEC company_tickers.json is normally a dictionary whose values
    # contain ticker/title/cik_str.
    for item in data.values():

        if not isinstance(item, dict):
            continue

        ticker = _normalize_text(
            item.get("ticker")
        )

        title = _normalize_text(
            item.get("title")
        )

        cik = _normalize_cik(
            item.get("cik_str")
        )

        if not cik:
            continue

        # --------------------------------------------------------------
        # Exact ticker
        # --------------------------------------------------------------

        if ticker.lower() == query_lower:
            exact_ticker = {
                "cik": cik,
                "ticker": ticker,
                "title": title,
                "match_type": "exact_ticker",
            }

            break

        # --------------------------------------------------------------
        # Exact company name
        # --------------------------------------------------------------

        if title.lower() == query_lower:
            exact_name = {
                "cik": cik,
                "ticker": ticker,
                "title": title,
                "match_type": "exact_company_name",
            }

        # --------------------------------------------------------------
        # Partial match
        # --------------------------------------------------------------

        if (
            query_lower in ticker.lower()
            or query_lower in title.lower()
        ):
            partial_matches.append(
                {
                    "cik": cik,
                    "ticker": ticker,
                    "title": title,
                    "match_type": "partial_match",
                }
            )

    if exact_ticker:
        return exact_ticker

    if exact_name:
        return exact_name

    if partial_matches:
        return partial_matches[0]

    return None


# ============================================================================
# Filing URL construction
# ============================================================================

def _build_filing_url(
    cik: str,
    accession_number: str,
    primary_document: str,
) -> str:
    """
    Construct canonical SEC filing document URL.
    """

    normalized_cik = _normalize_cik(cik)

    if not normalized_cik:
        return ""

    cik_numeric = str(
        int(normalized_cik)
    )

    accession_no_dashes = (
        accession_number
        .replace("-", "")
        .strip()
    )

    if not accession_no_dashes:
        return ""

    if not primary_document:
        return ""

    document = quote(
        primary_document,
        safe="._-",
    )

    return (
        f"{SEC_WEB_BASE}/Archives/edgar/data/"
        f"{cik_numeric}/"
        f"{accession_no_dashes}/"
        f"{document}"
    )


def _build_index_url(
    cik: str,
    accession_number: str,
) -> str:
    """
    Construct SEC filing directory/index URL.
    """

    normalized_cik = _normalize_cik(cik)

    if not normalized_cik:
        return ""

    cik_numeric = str(
        int(normalized_cik)
    )

    accession_no_dashes = (
        accession_number
        .replace("-", "")
        .strip()
    )

    if not accession_no_dashes:
        return ""

    return (
        f"{SEC_WEB_BASE}/Archives/edgar/data/"
        f"{cik_numeric}/"
        f"{accession_no_dashes}/"
    )


# ============================================================================
# Filing normalization
# ============================================================================

def _normalize_filing(
    company: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert an SEC submissions row into a normalized evidence record.
    """

    cik = _normalize_cik(
        company.get("cik")
    )

    accession_number = _normalize_text(
        row.get("accessionNumber")
    )

    primary_document = _normalize_text(
        row.get("primaryDocument")
    )

    form = _normalize_form(
        row.get("form")
    )

    filing_date = _normalize_text(
        row.get("filingDate")
    )

    report_date = _normalize_text(
        row.get("reportDate")
    )

    acceptance_datetime = _normalize_text(
        row.get("acceptanceDateTime")
    )

    url = ""

    index_url = ""

    if (
        cik
        and accession_number
    ):
        if primary_document:
            url = _build_filing_url(
                cik,
                accession_number,
                primary_document,
            )

        index_url = _build_index_url(
            cik,
            accession_number,
        )

    return {
        # ------------------------------------------------------------------
        # Identity
        # ------------------------------------------------------------------

        "source": "SEC EDGAR",

        "source_type": "regulatory_filing",

        "company": _normalize_text(
            company.get("title")
        ),

        "ticker": _normalize_text(
            company.get("ticker")
        ),

        "cik": cik,

        # ------------------------------------------------------------------
        # Filing metadata
        # ------------------------------------------------------------------

        "filing_type": form,

        "form": form,

        "accession_number": accession_number,

        "filing_date": filing_date,

        "date": filing_date,

        "report_date": report_date,

        "acceptance_datetime": acceptance_datetime,

        "primary_document": primary_document,

        # ------------------------------------------------------------------
        # Canonical SEC references
        # ------------------------------------------------------------------

        "url": url,

        "index_url": index_url,

        # ------------------------------------------------------------------
        # Evidence metadata
        # ------------------------------------------------------------------

        "evidence_level": "primary_source",

        "authority": (
            "U.S. Securities and Exchange Commission"
        ),

        "retrieval_method": (
            "SEC submissions API"
        ),

        "retrieved_at": _utc_now(),

        # ------------------------------------------------------------------
        # Research metadata
        # ------------------------------------------------------------------

        "research_metadata": {
            "primary_source": True,
            "llm_generated": False,
            "metadata_verified": True,
            "citation_ready": bool(url),
        },
    }


# ============================================================================
# Filing query matching
# ============================================================================

def _matches_query(
    filing: dict[str, Any],
    query: str,
) -> bool:
    """
    Determine whether a normalized filing matches the query.

    This is intentionally conservative.

    IMPORTANT:
    A filing is not claimed to contain a research concept simply
    because the company name matches it.
    """

    query = _normalize_text(
        query
    ).lower()

    if not query:
        return True

    searchable = " ".join(
        [
            filing.get("company", ""),
            filing.get("ticker", ""),
            filing.get("form", ""),
            filing.get("filing_type", ""),
            filing.get("primary_document", ""),
        ]
    ).lower()

    tokens = [
        token
        for token in re.findall(
            r"[a-zA-Z0-9]+",
            query,
        )
        if len(token) >= 3
    ]

    if not tokens:
        return True

    return any(
        token in searchable
        for token in tokens
    )


# ============================================================================
# Recent filing row construction
# ============================================================================

def _build_recent_filing_row(
    recent: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    """
    Safely convert SEC's column-oriented recent filing data
    into a single filing row.
    """

    forms = recent.get(
        "form",
        [],
    )

    accessions = recent.get(
        "accessionNumber",
        [],
    )

    filing_dates = recent.get(
        "filingDate",
        [],
    )

    report_dates = recent.get(
        "reportDate",
        [],
    )

    acceptance_datetimes = recent.get(
        "acceptanceDateTime",
        [],
    )

    primary_documents = recent.get(
        "primaryDocument",
        [],
    )

    return {
        "form": (
            forms[index]
            if index < len(forms)
            else ""
        ),

        "accessionNumber": (
            accessions[index]
            if index < len(accessions)
            else ""
        ),

        "filingDate": (
            filing_dates[index]
            if index < len(filing_dates)
            else ""
        ),

        "reportDate": (
            report_dates[index]
            if index < len(report_dates)
            else ""
        ),

        "acceptanceDateTime": (
            acceptance_datetimes[index]
            if index < len(acceptance_datetimes)
            else ""
        ),

        "primaryDocument": (
            primary_documents[index]
            if index < len(primary_documents)
            else ""
        ),
    }


# ============================================================================
# Public search API
# ============================================================================

def search(
    query: str,
    filing_type: str = "10-K",
    max_results: Optional[int] = None,
    include_all_forms: bool = False,
) -> list[dict[str, Any]]:
    """
    Search SEC EDGAR filings for a company.

    Parameters
    ----------
    query:
        Company ticker, company name, or CIK.

    filing_type:
        SEC form to retrieve.

        Examples:
            10-K
            10-Q
            8-K
            20-F
            40-F
            6-K
            DEF 14A
            S-1
            S-3

    max_results:
        Maximum number of normalized filings returned.

    include_all_forms:
        If True, return recent filings across all form types.

    Returns
    -------
    list[dict]
        Structured primary-source SEC evidence records.
    """

    if max_results is None:
        max_results = DEFAULT_MAX_RESULTS

    try:
        max_results = max(
            1,
            min(
                int(max_results),
                100,
            ),
        )
    except (TypeError, ValueError):
        max_results = DEFAULT_MAX_RESULTS

    query = _normalize_text(query)

    if not query:
        logger.warning(
            "SEC search called with empty query."
        )
        return []

    try:
        # ------------------------------------------------------------------
        # Resolve company
        # ------------------------------------------------------------------

        company = _resolve_company(
            query
        )

        if not company:
            logger.warning(
                "SEC company could not be resolved: %s",
                query,
            )
            return []

        cik = _normalize_cik(
            company.get("cik")
        )

        if not cik:
            return []

        # ------------------------------------------------------------------
        # Retrieve official SEC submissions
        # ------------------------------------------------------------------

        url = SUBMISSIONS_URL.format(
            cik=cik
        )

        data = _request_json(
            url,
            timeout=DEFAULT_TIMEOUT,
        )

        recent = (
            data
            .get("filings", {})
            .get("recent", {})
        )

        if not isinstance(
            recent,
            dict,
        ):
            return []

        # ------------------------------------------------------------------
        # Requested form
        # ------------------------------------------------------------------

        requested_form = _normalize_form(
            filing_type
        )

        results: list[dict[str, Any]] = []

        forms = recent.get(
            "form",
            []
        )

        accessions = recent.get(
            "accessionNumber",
            []
        )

        row_count = max(
            len(forms),
            len(accessions),
        )

        # ------------------------------------------------------------------
        # Process recent filings
        # ------------------------------------------------------------------

        for index in range(row_count):

            row = _build_recent_filing_row(
                recent,
                index,
            )

            form = row.get(
                "form",
                ""
            )

            if not include_all_forms:
                if (
                    _normalize_form(form)
                    != requested_form
                ):
                    continue

            normalized = _normalize_filing(
                company,
                row,
            )

            # Only use query matching when necessary.
            #
            # For direct ticker/name/CIK searches the company itself
            # has already been resolved. Therefore we should not
            # accidentally remove valid filings because the filing
            # metadata does not contain the original company query.

            results.append(
                normalized
            )

            if len(results) >= max_results:
                break

        return results

    except Exception as exc:
        logger.exception(
            "SEC search failed for '%s': %s",
            query,
            exc,
        )
        return []


# ============================================================================
# Multiple form search
# ============================================================================

def search_multiple_forms(
    query: str,
    filing_types: Optional[list[str]] = None,
    max_results_per_form: int = 10,
) -> list[dict[str, Any]]:
    """
    Retrieve filings across multiple SEC form types.

    Example
    -------
    search_multiple_forms(
        "UnitedHealth",
        ["10-K", "10-Q", "8-K"],
    )
    """

    if not filing_types:
        filing_types = [
            "10-K",
            "10-Q",
            "8-K",
        ]

    try:
        max_results_per_form = max(
            1,
            min(
                int(max_results_per_form),
                100,
            ),
        )
    except (TypeError, ValueError):
        max_results_per_form = 10

    results: list[dict[str, Any]] = []

    seen: set[str] = set()

    for form in filing_types:

        filings = search(
            query=query,
            filing_type=form,
            max_results=max_results_per_form,
        )

        for filing in filings:

            accession = filing.get(
                "accession_number"
            )

            unique_key = (
                accession
                or filing.get("url")
                or (
                    filing.get("company", "")
                    + "|"
                    + filing.get("form", "")
                    + "|"
                    + filing.get("filing_date", "")
                )
            )

            if not unique_key:
                continue

            if unique_key in seen:
                continue

            seen.add(unique_key)

            results.append(
                filing
            )

    return results


# ============================================================================
# Direct CIK filing retrieval
# ============================================================================

def get_company_filings(
    cik: str,
    filing_type: Optional[str] = None,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[dict[str, Any]]:
    """
    Retrieve filings directly by CIK.

    This bypasses ticker/company-name resolution.
    """

    normalized_cik = _normalize_cik(
        cik
    )

    if not normalized_cik:
        return []

    try:
        max_results = max(
            1,
            min(
                int(max_results),
                100,
            ),
        )
    except (TypeError, ValueError):
        max_results = DEFAULT_MAX_RESULTS

    try:
        data = _request_json(
            SUBMISSIONS_URL.format(
                cik=normalized_cik
            ),
            timeout=DEFAULT_TIMEOUT,
        )

        company = {
            "cik": normalized_cik,
            "ticker": "",
            "title": data.get(
                "name",
                "",
            ),
        }

        recent = (
            data
            .get("filings", {})
            .get("recent", {})
        )

        if not isinstance(
            recent,
            dict,
        ):
            return []

        requested_form = (
            _normalize_form(
                filing_type
            )
            if filing_type
            else None
        )

        forms = recent.get(
            "form",
            []
        )

        accessions = recent.get(
            "accessionNumber",
            []
        )

        row_count = max(
            len(forms),
            len(accessions),
        )

        results: list[dict[str, Any]] = []

        for index in range(row_count):

            row = _build_recent_filing_row(
                recent,
                index,
            )

            form = row.get(
                "form",
                ""
            )

            if (
                requested_form
                and _normalize_form(form)
                != requested_form
            ):
                continue

            results.append(
                _normalize_filing(
                    company,
                    row,
                )
            )

            if len(results) >= max_results:
                break

        return results

    except Exception as exc:
        logger.exception(
            "Unable to retrieve SEC filings for CIK %s: %s",
            normalized_cik,
            exc,
        )
        return []


# ============================================================================
# Filing document retrieval
# ============================================================================

def get_filing_text(
    filing: dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """
    Retrieve the primary SEC filing document.

    Search returns authoritative filing metadata.

    This function retrieves the actual primary document so that a
    downstream Evidence Agent can perform passage-level analysis.

    Returns
    -------
    dict
        Filing metadata plus document text/status.
    """

    if not isinstance(
        filing,
        dict,
    ):
        return {
            "document_status": "UNAVAILABLE",
            "document_text": "",
            "document_error": (
                "Invalid filing object."
            ),
        }

    url = _normalize_text(
        filing.get("url")
    )

    if not url:
        return {
            **filing,
            "document_status": "UNAVAILABLE",
            "document_text": "",
            "document_error": (
                "No filing URL available."
            ),
        }

    try:
        response = _SESSION.get(
            url,
            timeout=timeout,
            headers={
                # IMPORTANT:
                # Do not specify Host here.
                # requests will correctly set Host based on
                # the SEC URL being accessed.
                "User-Agent": SEC_USER_AGENT,
                "Accept": (
                    "text/html,"
                    "application/xhtml+xml,"
                    "application/xml,"
                    "text/plain,"
                    "*/*"
                ),
            },
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type",
            "",
        )

        text = response.text

        return {
            **filing,

            "document_status": "RETRIEVED",

            "document_content_type": content_type,

            "document_length": len(text),

            "document_text": text,

            "document_retrieved_at": _utc_now(),

            "document_source": url,
        }

    except requests.exceptions.Timeout as exc:

        logger.error(
            "SEC filing document request timed out: %s",
            exc,
        )

        return {
            **filing,
            "document_status": "FAILED",
            "document_text": "",
            "document_error": (
                "SEC filing document request timed out."
            ),
        }

    except requests.exceptions.HTTPError as exc:

        status = (
            exc.response.status_code
            if exc.response is not None
            else "unknown"
        )

        logger.error(
            "SEC filing document HTTP error %s: %s",
            status,
            exc,
        )

        return {
            **filing,
            "document_status": "FAILED",
            "document_text": "",
            "document_error": (
                f"SEC filing document HTTP error: {status}"
            ),
        }

    except requests.exceptions.RequestException as exc:

        logger.error(
            "SEC filing document request failed: %s",
            exc,
        )

        return {
            **filing,
            "document_status": "FAILED",
            "document_text": "",
            "document_error": str(exc),
        }

    except Exception as exc:

        logger.exception(
            "Unexpected SEC filing document error: %s",
            exc,
        )

        return {
            **filing,
            "document_status": "FAILED",
            "document_text": "",
            "document_error": str(exc),
        }


# ============================================================================
# Research-oriented SEC evidence extraction
# ============================================================================

def build_research_evidence(
    query: str,
    filing_types: Optional[list[str]] = None,
    max_results_per_form: int = 5,
    retrieve_documents: bool = False,
) -> dict[str, Any]:
    """
    Build a research-oriented SEC evidence package.

    Returns
    -------
    dict
        Structured SEC evidence package.

    Parameters
    ----------
    query:
        Company ticker, name, or CIK.

    filing_types:
        Filing types to retrieve.

    max_results_per_form:
        Maximum filings per form.

    retrieve_documents:
        If True, retrieve the actual primary SEC documents.

        WARNING:
        This can produce significantly larger payloads.

        Keep False when the Research Agent only needs metadata.
    """

    query = _normalize_text(
        query
    )

    if not query:
        return {
            "source": "SEC EDGAR",
            "source_type": "regulatory_research",
            "query": query,
            "retrieval_method": (
                "SEC data.sec.gov submissions API"
            ),
            "authority": (
                "U.S. Securities and Exchange Commission"
            ),
            "filing_count": 0,
            "filings": [],
            "evidence_policy": {
                "primary_source": True,
                "llm_generated": False,
                "metadata_verified": False,
                "citation_ready": False,
            },
            "retrieved_at": _utc_now(),
            "status": "INVALID_QUERY",
        }

    filings = search_multiple_forms(
        query=query,
        filing_types=filing_types,
        max_results_per_form=max_results_per_form,
    )

    if retrieve_documents:

        enriched_filings: list[dict[str, Any]] = []

        for filing in filings:

            enriched = get_filing_text(
                filing
            )

            enriched_filings.append(
                enriched
            )

        filings = enriched_filings

    return {
        "source": "SEC EDGAR",

        "source_type": "regulatory_research",

        "query": query,

        "retrieval_method": (
            "SEC data.sec.gov submissions API"
        ),

        "authority": (
            "U.S. Securities and Exchange Commission"
        ),

        "filing_count": len(filings),

        "filings": filings,

        "evidence_policy": {
            "primary_source": True,
            "llm_generated": False,
            "metadata_verified": True,
            "citation_ready": True,
        },

        "document_policy": {
            "documents_retrieved": retrieve_documents,
            "full_text_available": any(
                filing.get("document_status")
                == "RETRIEVED"
                for filing in filings
            ),
        },

        "retrieved_at": _utc_now(),

        "status": "SUCCESS",
    }


# ============================================================================
# SEC API health check
# ============================================================================

def health_check() -> dict[str, Any]:
    """
    Verify SEC EDGAR API availability.

    Returns a structured status instead of raising an exception.
    """

    started = time.time()

    try:

        data = _request_json(
            COMPANY_TICKERS_URL,
            timeout=10,
        )

        elapsed = time.time() - started

        company_count = (
            len(data)
            if isinstance(data, dict)
            else 0
        )

        return {
            "status": "HEALTHY",

            "source": "SEC EDGAR",

            "endpoint": COMPANY_TICKERS_URL,

            "company_records_available": company_count,

            "latency_seconds": round(
                elapsed,
                4,
            ),

            "checked_at": _utc_now(),

            "user_agent_configured": bool(
                SEC_USER_AGENT
            ),
        }

    except Exception as exc:

        return {
            "status": "UNAVAILABLE",

            "source": "SEC EDGAR",

            "endpoint": COMPANY_TICKERS_URL,

            "checked_at": _utc_now(),

            "error": str(exc),
        }


# ============================================================================
# Compatibility aliases
# ============================================================================

def search_filings(
    query: str,
    filing_type: str = "10-K",
    max_results: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Compatibility wrapper for callers using search_filings().
    """

    return search(
        query=query,
        filing_type=filing_type,
        max_results=max_results,
    )


def query(
    query_text: str,
    filing_type: str = "10-K",
    max_results: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Compatibility alias for generic research-tool callers.
    """

    return search(
        query=query_text,
        filing_type=filing_type,
        max_results=max_results,
    )


# ============================================================================
# Module test
# ============================================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
    )

    print("=" * 70)
    print("CTS-NPN SEC EDGAR Research Tool")
    print("=" * 70)

    health = health_check()

    print("\nSEC Health Check:")
    print(health)

    print("\nTesting UnitedHealth Group / UNH...")

    results = search(
        query="UNH",
        filing_type="10-K",
        max_results=3,
    )

    print(
        f"\nRetrieved {len(results)} filings."
    )

    for index, filing in enumerate(
        results,
        start=1,
    ):
        print(
            f"\n--- Filing {index} ---"
        )

        print(
            "Company:",
            filing.get("company"),
        )

        print(
            "Ticker:",
            filing.get("ticker"),
        )

        print(
            "CIK:",
            filing.get("cik"),
        )

        print(
            "Form:",
            filing.get("form"),
        )

        print(
            "Filing Date:",
            filing.get("filing_date"),
        )

        print(
            "Accession:",
            filing.get("accession_number"),
        )

        print(
            "URL:",
            filing.get("url"),
        )