"""
CTS-NPN Central Configuration
=============================

Central configuration for the CTS-NPN multi-agent research system.

Architecture:

    API
      |
      v
    Step Functions
      |
      +--> Planner
      +--> Research
      |      +--> arXiv
      |      +--> SEC EDGAR
      |      +--> CMS
      |      +--> CDC PLACES
      |
      +--> Evidence
      +--> Synthesis
      +--> Critic
      +--> Report Rendering
      |
      +--> Provenance / Citation Manifest
      +--> S3 Artifact Storage

Design principles
-----------------

1. No API credentials are embedded in source code.
2. Public research APIs are configurable.
3. CMS datasets are configurable individually.
4. Dataset IDs are separated from API endpoints.
5. Production behavior is controlled through environment variables.
6. Compatible with Lambda + Step Functions.
7. Configuration is deterministic and auditable.
8. Research source provenance is preserved.
9. Claims must be traceable to evidence.
10. Evidence must be traceable to an identifiable source.
11. The system must never invent missing source metadata.
12. Generated reports should carry machine-readable provenance.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv


# ============================================================================
# PROJECT / ENVIRONMENT
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ENV_FILE = PROJECT_ROOT / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _env_bool(
    name: str,
    default: bool,
) -> bool:
    """
    Read a boolean environment variable safely.
    """
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def _env_int(
    name: str,
    default: int,
) -> int:
    """
    Read an integer environment variable safely.
    """
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be an integer. Received: {value!r}"
        ) from exc


def _env_float(
    name: str,
    default: float,
) -> float:
    """
    Read a float environment variable safely.
    """
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be a number. Received: {value!r}"
        ) from exc


def _env_list(
    name: str,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    """
    Read a comma-separated environment variable.

    Example:

        CTS_ALLOWED_SOURCE_TYPES=arxiv,cms,cdc,sec_edgar
    """
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    return tuple(
        item.strip()
        for item in value.split(",")
        if item.strip()
    )


# ============================================================================
# AWS
# ============================================================================

REGION = os.getenv(
    "AWS_REGION",
    "us-east-1",
).strip()


# ============================================================================
# S3 STORAGE
# ============================================================================

RESEARCH_BUCKET = os.getenv(
    "RESEARCH_BUCKET",
    "",
).strip()

CMS_BUCKET = os.getenv(
    "CMS_BUCKET",
    "",
).strip()

REPORTS_BUCKET = os.getenv(
    "REPORTS_BUCKET",
    "",
).strip()

# Compatibility alias.
ARTIFACT_BUCKET = os.getenv(
    "ARTIFACT_BUCKET",
    RESEARCH_BUCKET,
).strip()

# Optional explicit prefixes.
RESEARCH_PREFIX = os.getenv(
    "RESEARCH_PREFIX",
    "research",
).strip().strip("/")

EVIDENCE_PREFIX = os.getenv(
    "EVIDENCE_PREFIX",
    "evidence",
).strip().strip("/")

REPORT_PREFIX = os.getenv(
    "REPORT_PREFIX",
    "reports",
).strip().strip("/")

MANIFEST_PREFIX = os.getenv(
    "MANIFEST_PREFIX",
    "manifests",
).strip().strip("/")


# ============================================================================
# DYNAMODB
# ============================================================================

RESULTS_TABLE = os.getenv(
    "RESULTS_TABLE",
    "",
).strip()


# ============================================================================
# STEP FUNCTIONS
# ============================================================================

STATE_MACHINE_ARN = os.getenv(
    "STATE_MACHINE_ARN",
    "",
).strip()


# ============================================================================
# AMAZON BEDROCK
# ============================================================================

MODEL = os.getenv(
    "BEDROCK_MODEL_ID",
    "amazon.nova-micro-v1:0",
).strip()

BEDROCK_MAX_TOKENS = _env_int(
    "BEDROCK_MAX_TOKENS",
    8000,
)

BEDROCK_TEMPERATURE = _env_float(
    "BEDROCK_TEMPERATURE",
    0.15,
)

BEDROCK_TOP_P = _env_float(
    "BEDROCK_TOP_P",
    0.9,
)


# ============================================================================
# CMS PROVIDER DATA CATALOG
# ============================================================================

CMS_PDC_BASE_URL = os.getenv(
    "CMS_PDC_BASE_URL",
    "https://data.cms.gov/provider-data/api/1",
).strip().rstrip("/")

CMS_PDC_DATASTORE_URL = os.getenv(
    "CMS_PDC_DATASTORE_URL",
    f"{CMS_PDC_BASE_URL}/datastore/query",
).strip().rstrip("/")

CMS_PDC_SEARCH_URL = os.getenv(
    "CMS_PDC_SEARCH_URL",
    f"{CMS_PDC_BASE_URL}/search",
).strip().rstrip("/")

CMS_PDC_METASTORE_URL = os.getenv(
    "CMS_PDC_METASTORE_URL",
    f"{CMS_PDC_BASE_URL}/metastore/schemas/dataset/items",
).strip().rstrip("/")


# ============================================================================
# CMS DEFAULT DATASET
# ============================================================================

CMS_PDC_DATASET_ID = os.getenv(
    "CMS_PDC_DATASET_ID",
    "mj5m-pzi6",
).strip()

CMS_PDC_INDEX = _env_int(
    "CMS_PDC_INDEX",
    0,
)


# ============================================================================
# ADDITIONAL CMS DATASETS
# ============================================================================

CMS_DATASETS = {
    "doctors_clinicians": os.getenv(
        "CMS_DATASET_DOCTORS_CLINICIANS",
        "mj5m-pzi6",
    ).strip(),

    "hospital_general_information": os.getenv(
        "CMS_DATASET_HOSPITAL_GENERAL",
        "xubh-q36u",
    ).strip(),

    "timely_effective_care_hospital": os.getenv(
        "CMS_DATASET_TIMELY_EFFECTIVE_CARE",
        "yv7e-xc69",
    ).strip(),
}


# ============================================================================
# CMS RESEARCH SETTINGS
# ============================================================================

CMS_PAGE_SIZE = _env_int(
    "CMS_PAGE_SIZE",
    100,
)

CMS_MAX_PAGES = _env_int(
    "CMS_MAX_PAGES",
    20,
)

CMS_REQUEST_TIMEOUT = _env_int(
    "CMS_REQUEST_TIMEOUT",
    30,
)

CMS_MAX_RESULTS = _env_int(
    "CMS_MAX_RESULTS",
    1500,
)

# Backwards compatibility.
MAX_RESULTS = _env_int(
    "MAX_RESULTS",
    CMS_MAX_RESULTS,
)


# ============================================================================
# CDC PLACES
# ============================================================================

CDC_PLACES_API = os.getenv(
    "CDC_PLACES_API",
    "https://chronicdata.cdc.gov/resource/vgc8-iyc4.json",
).strip()

CDC_PLACES_DATASET_ID = os.getenv(
    "CDC_PLACES_DATASET_ID",
    "vgc8-iyc4",
).strip()

CDC_REQUEST_TIMEOUT = _env_int(
    "CDC_REQUEST_TIMEOUT",
    30,
)

CDC_MAX_RESULTS = _env_int(
    "CDC_MAX_RESULTS",
    1000,
)


# ============================================================================
# arXiv
# ============================================================================

ARXIV_API_URL = os.getenv(
    "ARXIV_API_URL",
    "https://export.arxiv.org/api/query",
).strip()

ARXIV_MAX_RESULTS = _env_int(
    "ARXIV_MAX_RESULTS",
    10,
)

ARXIV_MAX_PAPERS_PER_QUERY = _env_int(
    "ARXIV_MAX_PAPERS_PER_QUERY",
    10,
)

ARXIV_REQUEST_TIMEOUT = _env_int(
    "ARXIV_REQUEST_TIMEOUT",
    30,
)


# ============================================================================
# SEC EDGAR
# ============================================================================

SEC_SUBMISSIONS_URL = os.getenv(
    "SEC_SUBMISSIONS_URL",
    "https://data.sec.gov/submissions",
).strip().rstrip("/")

SEC_COMPANY_TICKERS_URL = os.getenv(
    "SEC_COMPANY_TICKERS_URL",
    "https://www.sec.gov/files/company_tickers.json",
).strip()

SEC_EFTS_SEARCH_URL = os.getenv(
    "SEC_EFTS_SEARCH_URL",
    "https://efts.sec.gov/LATEST/search-index",
).strip()

SEC_REQUEST_TIMEOUT = _env_int(
    "SEC_REQUEST_TIMEOUT",
    30,
)

SEC_MAX_RESULTS = _env_int(
    "SEC_MAX_RESULTS",
    20,
)

# SEC requires a descriptive User-Agent.
SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "CTS-NPN Research Agent research@example.com",
).strip()


# ============================================================================
# RESEARCH ENGINE
# ============================================================================

RESEARCH_MAX_SOURCES = _env_int(
    "RESEARCH_MAX_SOURCES",
    50,
)

RESEARCH_MAX_PASSAGES_PER_SOURCE = _env_int(
    "RESEARCH_MAX_PASSAGES_PER_SOURCE",
    10,
)

RESEARCH_MIN_RELEVANCE_SCORE = _env_float(
    "RESEARCH_MIN_RELEVANCE_SCORE",
    0.45,
)

RESEARCH_MIN_CITATIONS = _env_int(
    "RESEARCH_MIN_CITATIONS",
    5,
)

# Research source classes allowed by the research planner.
RESEARCH_ALLOWED_SOURCE_TYPES = _env_list(
    "RESEARCH_ALLOWED_SOURCE_TYPES",
    (
        "arxiv",
        "academic_paper",
        "sec_edgar",
        "cms",
        "cdc",
        "government",
        "dataset",
        "webpage",
        "report",
    ),
)


# ============================================================================
# EVIDENCE ENGINE
# ============================================================================

EVIDENCE_SOURCE_TYPES = (
    "peer_reviewed_research",
    "preprint",
    "regulatory_filing",
    "government_dataset",
    "public_health_dataset",
    "government_methodology",
    "official_documentation",
    "open_source_resource",
)

MIN_EVIDENCE_SOURCE_TYPES = _env_int(
    "MIN_EVIDENCE_SOURCE_TYPES",
    3,
)

# Minimum evidence relevance required before an evidence item
# can normally be attached to a report claim.
EVIDENCE_MIN_RELEVANCE_SCORE = _env_float(
    "EVIDENCE_MIN_RELEVANCE_SCORE",
    0.45,
)

# Minimum passage length for contextual evidence.
EVIDENCE_MIN_PASSAGE_LENGTH = _env_int(
    "EVIDENCE_MIN_PASSAGE_LENGTH",
    40,
)

# Whether evidence must contain a passage/context before
# being considered report-ready.
EVIDENCE_REQUIRE_PASSAGE = _env_bool(
    "EVIDENCE_REQUIRE_PASSAGE",
    True,
)

# Whether a source should have a stable identifier or URL.
EVIDENCE_REQUIRE_SOURCE_IDENTITY = _env_bool(
    "EVIDENCE_REQUIRE_SOURCE_IDENTITY",
    True,
)

# Evidence quality threshold.
EVIDENCE_MIN_QUALITY_SCORE = _env_float(
    "EVIDENCE_MIN_QUALITY_SCORE",
    0.60,
)


# ============================================================================
# CLAIM / PROVENANCE ENGINE
# ============================================================================

# Supported claim attribution modes.
CLAIM_ATTRIBUTION_TYPES = (
    "source_reported",
    "system_calculated",
    "system_inferred",
    "analyst_interpretation",
)

# Whether every report claim must have evidence.
CLAIMS_REQUIRE_EVIDENCE = _env_bool(
    "CLAIMS_REQUIRE_EVIDENCE",
    True,
)

# Whether broken claim -> evidence links should fail validation.
CLAIMS_REJECT_BROKEN_EVIDENCE_LINKS = _env_bool(
    "CLAIMS_REJECT_BROKEN_EVIDENCE_LINKS",
    True,
)

# Minimum structural citation coverage.
# Example: 0.80 means at least 80% of report claims
# must have evidence references.
MIN_CITATION_COVERAGE = _env_float(
    "MIN_CITATION_COVERAGE",
    0.80,
)

# Publication threshold for citation-quality audit.
MIN_CITATION_QUALITY_SCORE = _env_float(
    "MIN_CITATION_QUALITY_SCORE",
    0.60,
)


# ============================================================================
# PROVENANCE / MANIFEST
# ============================================================================

ENABLE_SOURCE_PROVENANCE = _env_bool(
    "ENABLE_SOURCE_PROVENANCE",
    True,
)

ENABLE_EVIDENCE_SCORING = _env_bool(
    "ENABLE_EVIDENCE_SCORING",
    True,
)

ENABLE_CLAIM_TRACEABILITY = _env_bool(
    "ENABLE_CLAIM_TRACEABILITY",
    True,
)

ENABLE_CITATION_DEDUPLICATION = _env_bool(
    "ENABLE_CITATION_DEDUPLICATION",
    True,
)

ENABLE_PROVENANCE_MANIFEST = _env_bool(
    "ENABLE_PROVENANCE_MANIFEST",
    True,
)

PROVENANCE_MANIFEST_VERSION = os.getenv(
    "PROVENANCE_MANIFEST_VERSION",
    "1.0",
).strip()

# Store evidence passages and claim/evidence relationships.
STORE_EVIDENCE_PASSAGES = _env_bool(
    "STORE_EVIDENCE_PASSAGES",
    True,
)

STORE_CLAIM_EVIDENCE_LINKS = _env_bool(
    "STORE_CLAIM_EVIDENCE_LINKS",
    True,
)


# ============================================================================
# REPORT GENERATION
# ============================================================================

REPORT_STYLE = os.getenv(
    "REPORT_STYLE",
    "research_documentation",
).strip()

REPORT_CITATION_STYLE = os.getenv(
    "REPORT_CITATION_STYLE",
    "APA",
).strip().upper()

REPORT_MIN_WORDS = _env_int(
    "REPORT_MIN_WORDS",
    1200,
)

REPORT_MAX_WORDS = _env_int(
    "REPORT_MAX_WORDS",
    5000,
)

# Allowed citation styles supported by the citation engine.
SUPPORTED_CITATION_STYLES = (
    "APA",
    "MLA",
    "CHICAGO",
    "SIMPLE",
)


# ============================================================================
# REPORT TEMPLATE
# ============================================================================

REPORT_TEMPLATE_PATH = os.getenv(
    "REPORT_TEMPLATE_PATH",
    str(PROJECT_ROOT / "report_template.pdf"),
).strip()

REPORT_TEMPLATE_S3_KEY = os.getenv(
    "REPORT_TEMPLATE_S3_KEY",
    "templates/report_template.pdf",
).strip()


# ============================================================================
# REPORT OUTPUT
# ============================================================================

REPORT_OUTPUT_FORMAT = os.getenv(
    "REPORT_OUTPUT_FORMAT",
    "pdf",
).strip().lower()

REPORT_STORE_MARKDOWN = _env_bool(
    "REPORT_STORE_MARKDOWN",
    True,
)

REPORT_STORE_JSON = _env_bool(
    "REPORT_STORE_JSON",
    True,
)

REPORT_STORE_PROVENANCE_MANIFEST = _env_bool(
    "REPORT_STORE_PROVENANCE_MANIFEST",
    True,
)

REPORT_STORE_EVIDENCE = _env_bool(
    "REPORT_STORE_EVIDENCE",
    True,
)


# ============================================================================
# REPORT QUALITY GATES
# ============================================================================

# Whether the report generator should reject reports that contain
# unsupported claims.
REPORT_REJECT_UNSUPPORTED_CLAIMS = _env_bool(
    "REPORT_REJECT_UNSUPPORTED_CLAIMS",
    True,
)

# Whether the report generator should reject broken claim/evidence links.
REPORT_REJECT_BROKEN_EVIDENCE_LINKS = _env_bool(
    "REPORT_REJECT_BROKEN_EVIDENCE_LINKS",
    True,
)

# Whether the report must satisfy minimum citation coverage.
REPORT_REQUIRE_MIN_CITATION_COVERAGE = _env_bool(
    "REPORT_REQUIRE_MIN_CITATION_COVERAGE",
    True,
)

# Whether the report must satisfy minimum citation quality.
REPORT_REQUIRE_MIN_CITATION_QUALITY = _env_bool(
    "REPORT_REQUIRE_MIN_CITATION_QUALITY",
    True,
)


# ============================================================================
# SAFETY
# ============================================================================

SAFETY_REQUIRE_EMERGENCY_DISCLAIMER = _env_bool(
    "SAFETY_REQUIRE_EMERGENCY_DISCLAIMER",
    True,
)

SAFETY_MODE = os.getenv(
    "SAFETY_MODE",
    "strict",
).strip().lower()


# ============================================================================
# AGENT EXECUTION
# ============================================================================

AGENT_MAX_RETRIES = _env_int(
    "AGENT_MAX_RETRIES",
    2,
)

AGENT_TIMEOUT_SECONDS = _env_int(
    "AGENT_TIMEOUT_SECONDS",
    120,
)


# ============================================================================
# OBSERVABILITY
# ============================================================================

LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "INFO",
).strip().upper()

ENABLE_AUDIT_LOGGING = _env_bool(
    "ENABLE_AUDIT_LOGGING",
    True,
)

# Optional execution tracing.
ENABLE_EXECUTION_TRACE = _env_bool(
    "ENABLE_EXECUTION_TRACE",
    True,
)

# Optional research-source trace.
ENABLE_RESEARCH_TRACE = _env_bool(
    "ENABLE_RESEARCH_TRACE",
    True,
)


# ============================================================================
# DEMO / SIMULATION
# ============================================================================

DEMO_MODE = _env_bool(
    "DEMO_MODE",
    False,
)

ALLOW_SYNTHETIC_FALLBACK = _env_bool(
    "ALLOW_SYNTHETIC_FALLBACK",
    False,
)


# ============================================================================
# VALIDATION
# ============================================================================

def validate_configuration() -> bool:
    """
    Validate the most important runtime configuration.

    Importing config.py does not automatically fail for missing
    optional infrastructure settings.

    Runtime components can call this function before execution.
    """

    errors = []

    # ------------------------------------------------------------------------
    # AWS / MODEL
    # ------------------------------------------------------------------------

    if not REGION:
        errors.append(
            "AWS_REGION is not configured."
        )

    if not MODEL:
        errors.append(
            "BEDROCK_MODEL_ID is not configured."
        )

    # ------------------------------------------------------------------------
    # HTTPS ENDPOINTS
    # ------------------------------------------------------------------------

    https_urls = {
        "CMS_PDC_BASE_URL": CMS_PDC_BASE_URL,
        "ARXIV_API_URL": ARXIV_API_URL,
        "SEC_EFTS_SEARCH_URL": SEC_EFTS_SEARCH_URL,
        "SEC_SUBMISSIONS_URL": SEC_SUBMISSIONS_URL,
        "CDC_PLACES_API": CDC_PLACES_API,
    }

    for name, value in https_urls.items():
        if not value.startswith("https://"):
            errors.append(
                f"{name} must use HTTPS."
            )

    # ------------------------------------------------------------------------
    # NUMERIC LIMITS
    # ------------------------------------------------------------------------

    if MAX_RESULTS <= 0:
        errors.append(
            "MAX_RESULTS must be greater than zero."
        )

    if CMS_PAGE_SIZE <= 0:
        errors.append(
            "CMS_PAGE_SIZE must be greater than zero."
        )

    if CMS_MAX_PAGES <= 0:
        errors.append(
            "CMS_MAX_PAGES must be greater than zero."
        )

    if CMS_MAX_RESULTS <= 0:
        errors.append(
            "CMS_MAX_RESULTS must be greater than zero."
        )

    if CDC_MAX_RESULTS <= 0:
        errors.append(
            "CDC_MAX_RESULTS must be greater than zero."
        )

    if ARXIV_MAX_RESULTS <= 0:
        errors.append(
            "ARXIV_MAX_RESULTS must be greater than zero."
        )

    if SEC_MAX_RESULTS <= 0:
        errors.append(
            "SEC_MAX_RESULTS must be greater than zero."
        )

    # ------------------------------------------------------------------------
    # RESEARCH
    # ------------------------------------------------------------------------

    if RESEARCH_MAX_SOURCES <= 0:
        errors.append(
            "RESEARCH_MAX_SOURCES must be greater than zero."
        )

    if RESEARCH_MAX_PASSAGES_PER_SOURCE <= 0:
        errors.append(
            "RESEARCH_MAX_PASSAGES_PER_SOURCE must be greater than zero."
        )

    if RESEARCH_MIN_CITATIONS < 0:
        errors.append(
            "RESEARCH_MIN_CITATIONS cannot be negative."
        )

    if not 0.0 <= RESEARCH_MIN_RELEVANCE_SCORE <= 1.0:
        errors.append(
            "RESEARCH_MIN_RELEVANCE_SCORE must be between 0 and 1."
        )

    # ------------------------------------------------------------------------
    # BEDROCK
    # ------------------------------------------------------------------------

    if BEDROCK_MAX_TOKENS <= 0:
        errors.append(
            "BEDROCK_MAX_TOKENS must be greater than zero."
        )

    if not 0.0 <= BEDROCK_TEMPERATURE <= 1.0:
        errors.append(
            "BEDROCK_TEMPERATURE must be between 0 and 1."
        )

    if not 0.0 <= BEDROCK_TOP_P <= 1.0:
        errors.append(
            "BEDROCK_TOP_P must be between 0 and 1."
        )

    # ------------------------------------------------------------------------
    # EVIDENCE
    # ------------------------------------------------------------------------

    if MIN_EVIDENCE_SOURCE_TYPES <= 0:
        errors.append(
            "MIN_EVIDENCE_SOURCE_TYPES must be greater than zero."
        )

    if not 0.0 <= EVIDENCE_MIN_RELEVANCE_SCORE <= 1.0:
        errors.append(
            "EVIDENCE_MIN_RELEVANCE_SCORE must be between 0 and 1."
        )

    if EVIDENCE_MIN_PASSAGE_LENGTH < 0:
        errors.append(
            "EVIDENCE_MIN_PASSAGE_LENGTH cannot be negative."
        )

    if not 0.0 <= EVIDENCE_MIN_QUALITY_SCORE <= 1.0:
        errors.append(
            "EVIDENCE_MIN_QUALITY_SCORE must be between 0 and 1."
        )

    # ------------------------------------------------------------------------
    # CLAIM / CITATION QUALITY
    # ------------------------------------------------------------------------

    if not 0.0 <= MIN_CITATION_COVERAGE <= 1.0:
        errors.append(
            "MIN_CITATION_COVERAGE must be between 0 and 1."
        )

    if not 0.0 <= MIN_CITATION_QUALITY_SCORE <= 1.0:
        errors.append(
            "MIN_CITATION_QUALITY_SCORE must be between 0 and 1."
        )

    # ------------------------------------------------------------------------
    # REPORT
    # ------------------------------------------------------------------------

    if REPORT_MIN_WORDS <= 0:
        errors.append(
            "REPORT_MIN_WORDS must be greater than zero."
        )

    if REPORT_MAX_WORDS < REPORT_MIN_WORDS:
        errors.append(
            "REPORT_MAX_WORDS must be greater than or equal to REPORT_MIN_WORDS."
        )

    if REPORT_CITATION_STYLE not in SUPPORTED_CITATION_STYLES:
        errors.append(
            "REPORT_CITATION_STYLE must be one of: "
            + ", ".join(SUPPORTED_CITATION_STYLES)
        )

    allowed_output_formats = {
        "pdf",
        "markdown",
        "md",
        "json",
    }

    if REPORT_OUTPUT_FORMAT not in allowed_output_formats:
        errors.append(
            "REPORT_OUTPUT_FORMAT must be one of: "
            + ", ".join(sorted(allowed_output_formats))
        )

    # ------------------------------------------------------------------------
    # SAFETY
    # ------------------------------------------------------------------------

    allowed_safety_modes = {
        "strict",
        "standard",
        "demo",
    }

    if SAFETY_MODE not in allowed_safety_modes:
        errors.append(
            "SAFETY_MODE must be one of: "
            + ", ".join(sorted(allowed_safety_modes))
        )

    # ------------------------------------------------------------------------
    # AGENTS
    # ------------------------------------------------------------------------

    if AGENT_MAX_RETRIES < 0:
        errors.append(
            "AGENT_MAX_RETRIES cannot be negative."
        )

    if AGENT_TIMEOUT_SECONDS <= 0:
        errors.append(
            "AGENT_TIMEOUT_SECONDS must be greater than zero."
        )

    # ------------------------------------------------------------------------
    # LOGGING
    # ------------------------------------------------------------------------

    allowed_log_levels = {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }

    if LOG_LEVEL not in allowed_log_levels:
        errors.append(
            "LOG_LEVEL must be one of: "
            + ", ".join(sorted(allowed_log_levels))
        )

    # ------------------------------------------------------------------------
    # FINAL RESULT
    # ------------------------------------------------------------------------

    if errors:
        raise RuntimeError(
            "CTS-NPN configuration validation failed:\n- "
            + "\n- ".join(errors)
        )

    return True


# ============================================================================
# CONFIGURATION SUMMARY
# ============================================================================

def get_configuration_summary() -> dict:
    """
    Return a safe, machine-readable configuration summary.

    Secrets are intentionally excluded.
    Useful for debugging, audit logs and Step Functions execution metadata.
    """

    return {
        "project_root": str(PROJECT_ROOT),
        "aws_region": REGION,

        "research_bucket_configured": bool(RESEARCH_BUCKET),
        "cms_bucket_configured": bool(CMS_BUCKET),
        "reports_bucket_configured": bool(REPORTS_BUCKET),
        "results_table_configured": bool(RESULTS_TABLE),
        "state_machine_configured": bool(STATE_MACHINE_ARN),

        "bedrock_model": MODEL,

        "cms_dataset_id": CMS_PDC_DATASET_ID,
        "cms_dataset_count": len(CMS_DATASETS),

        "research_max_sources": RESEARCH_MAX_SOURCES,
        "research_min_citations": RESEARCH_MIN_CITATIONS,

        "evidence_require_passage": EVIDENCE_REQUIRE_PASSAGE,
        "evidence_min_relevance": EVIDENCE_MIN_RELEVANCE_SCORE,
        "evidence_min_quality": EVIDENCE_MIN_QUALITY_SCORE,

        "claims_require_evidence": CLAIMS_REQUIRE_EVIDENCE,
        "min_citation_coverage": MIN_CITATION_COVERAGE,
        "min_citation_quality": MIN_CITATION_QUALITY_SCORE,

        "provenance_enabled": ENABLE_SOURCE_PROVENANCE,
        "evidence_scoring_enabled": ENABLE_EVIDENCE_SCORING,
        "claim_traceability_enabled": ENABLE_CLAIM_TRACEABILITY,
        "manifest_enabled": ENABLE_PROVENANCE_MANIFEST,

        "report_style": REPORT_STYLE,
        "report_citation_style": REPORT_CITATION_STYLE,
        "report_output_format": REPORT_OUTPUT_FORMAT,

        "safety_mode": SAFETY_MODE,
        "demo_mode": DEMO_MODE,

        "configuration_version": "2.0",
    }