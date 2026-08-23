"""
CTS-NPN Common AWS Infrastructure
=================================

Shared infrastructure layer for the CTS-NPN multi-agent research system.

Purpose
-------

This module provides the common runtime primitives used by the Planner,
Research, CMS, Evidence, Synthesis, Critic and API agents.

Design principles

1. Deterministic execution
2. Strong provenance preservation
3. Structured S3 artifacts
4. Durable DynamoDB run state
5. Bedrock Converse API abstraction
6. Explicit error handling
7. Retry-aware external model invocation
8. UTF-8-safe document storage
9. JSON-safe serialization
10. Research reproducibility

Artifact hierarchy
------------------

s3://<research-bucket>/<run_id>/

    research_results.json
    organized_evidence.json
    evidence_summary.md
    source_manifest.json
    claims.json
    provenance.json

s3://<reports-bucket>/<run_id>/

    research_report.md
    validation_results.json
    report_metadata.json
    final_report.pdf

This structure allows every research run to be independently audited.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import (
    REGION,
    RESEARCH_BUCKET,
    REPORTS_BUCKET,
    RESULTS_TABLE,
    MODEL,
)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# AWS client configuration
# ---------------------------------------------------------------------------

AWS_RETRY_CONFIG = Config(
    retries={
        "max_attempts": 5,
        "mode": "standard",
    },
    connect_timeout=10,
    read_timeout=120,
)


# ---------------------------------------------------------------------------
# AWS clients/resources
# ---------------------------------------------------------------------------

AWS_REGION = REGION or os.environ.get(
    "AWS_REGION",
    "us-east-1",
)

s3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
    config=AWS_RETRY_CONFIG,
)

ddb_resource = boto3.resource(
    "dynamodb",
    region_name=AWS_REGION,
    config=AWS_RETRY_CONFIG,
)

ddb = (
    ddb_resource.Table(RESULTS_TABLE)
    if RESULTS_TABLE
    else None
)

br = boto3.client(
    "bedrock-runtime",
    region_name=AWS_REGION,
    config=AWS_RETRY_CONFIG,
)


# ---------------------------------------------------------------------------
# Time / identifiers
# ---------------------------------------------------------------------------

def now() -> str:
    """
    Return an ISO-8601 UTC timestamp.

    All agents should use this function rather than local timestamps so
    research runs remain comparable across Lambda executions and regions.
    """
    return datetime.now(timezone.utc).isoformat()


def generate_artifact_id(
    prefix: str = "artifact",
) -> str:
    """
    Generate a globally unique artifact identifier.
    """
    safe_prefix = str(prefix).strip() or "artifact"

    return (
        f"{safe_prefix}_{uuid.uuid4().hex}"
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _json_default(value: Any) -> Any:
    """
    Convert common AWS/Python values into JSON-safe representations.
    """

    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)

        return float(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, set):
        return list(value)

    return str(value)


def dumps_json(
    obj: Any,
    pretty: bool = True,
) -> str:
    """
    Serialize an object consistently.

    ensure_ascii=False is important because research metadata can contain
    author names, titles and international text.
    """

    return json.dumps(
        obj,
        ensure_ascii=False,
        indent=2 if pretty else None,
        default=_json_default,
    )


def loads_json(value: Any) -> Any:
    """
    Parse JSON from either bytes or string.
    """

    if isinstance(value, bytes):
        value = value.decode("utf-8")

    if isinstance(value, str):
        return json.loads(value)

    return json.loads(
        json.dumps(
            value,
            default=_json_default,
        )
    )


# ---------------------------------------------------------------------------
# DynamoDB value normalization
# ---------------------------------------------------------------------------

def _ddb_safe(value: Any) -> Any:
    """
    Convert Python values into DynamoDB-compatible values.

    boto3 DynamoDB does not accept Python float values directly.
    They are converted to Decimal recursively.
    """

    if isinstance(value, float):
        return Decimal(str(value))

    if isinstance(value, Decimal):
        return value

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): _ddb_safe(val)
            for key, val in value.items()
        }

    if isinstance(value, list):
        return [
            _ddb_safe(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return [
            _ddb_safe(item)
            for item in value
        ]

    if isinstance(value, set):
        return {
            _ddb_safe(item)
            for item in value
        }

    return value


# ---------------------------------------------------------------------------
# S3
# ---------------------------------------------------------------------------

def put_json(
    bucket: str,
    key: str,
    obj: Any,
    metadata: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Persist structured JSON research artifacts in S3.
    """

    if not bucket:
        raise ValueError(
            "S3 bucket is required"
        )

    if not key:
        raise ValueError(
            "S3 object key is required"
        )

    body = dumps_json(
        obj,
        pretty=True,
    ).encode("utf-8")

    params = {
        "Bucket": bucket,
        "Key": key,
        "Body": body,
        "ContentType": (
            "application/json; charset=utf-8"
        ),
    }

    if metadata:
        params["Metadata"] = {
            str(k): str(v)
            for k, v in metadata.items()
        }

    response = s3.put_object(
        **params
    )

    logger.info(
        "S3 JSON artifact stored: s3://%s/%s",
        bucket,
        key,
    )

    return {
        "bucket": bucket,
        "key": key,
        "etag": response.get("ETag"),
        "size_bytes": len(body),
    }


def put_text(
    bucket: str,
    key: str,
    text: str,
    content_type: str = (
        "text/markdown; charset=utf-8"
    ),
    metadata: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Store text artifacts safely as UTF-8.
    """

    if not bucket:
        raise ValueError(
            "S3 bucket is required"
        )

    if not key:
        raise ValueError(
            "S3 object key is required"
        )

    if text is None:
        text = ""

    if not isinstance(text, str):
        text = str(text)

    body = text.encode("utf-8")

    params = {
        "Bucket": bucket,
        "Key": key,
        "Body": body,
        "ContentType": content_type,
    }

    if metadata:
        params["Metadata"] = {
            str(k): str(v)
            for k, v in metadata.items()
        }

    response = s3.put_object(
        **params
    )

    logger.info(
        "S3 text artifact stored: s3://%s/%s",
        bucket,
        key,
    )

    return {
        "bucket": bucket,
        "key": key,
        "etag": response.get("ETag"),
        "size_bytes": len(body),
    }


def get_json(
    bucket: str,
    key: str,
) -> Any:
    """
    Retrieve and decode a JSON artifact.
    """

    if not bucket:
        raise ValueError(
            "S3 bucket is required"
        )

    if not key:
        raise ValueError(
            "S3 object key is required"
        )

    response = s3.get_object(
        Bucket=bucket,
        Key=key,
    )

    return loads_json(
        response["Body"].read()
    )


def get_text(
    bucket: str,
    key: str,
) -> str:
    """
    Retrieve a UTF-8 text artifact.
    """

    if not bucket:
        raise ValueError(
            "S3 bucket is required"
        )

    if not key:
        raise ValueError(
            "S3 object key is required"
        )

    response = s3.get_object(
        Bucket=bucket,
        Key=key,
    )

    return response["Body"].read().decode(
        "utf-8"
    )


def object_exists(
    bucket: str,
    key: str,
) -> bool:
    """
    Check whether an S3 artifact exists without downloading it.
    """

    if not bucket or not key:
        return False

    try:
        s3.head_object(
            Bucket=bucket,
            Key=key,
        )

        return True

    except ClientError as exc:
        error_code = (
            exc.response
            .get("Error", {})
            .get("Code")
        )

        if error_code in (
            "404",
            "NoSuchKey",
            "NotFound",
        ):
            return False

        raise


# ---------------------------------------------------------------------------
# Run state
# ---------------------------------------------------------------------------

def update_run(
    run_id: str,
    status: str,
    **fields: Any,
) -> None:
    """
    Update durable run state in DynamoDB.

    Uses UpdateExpression so fields accumulate during the orchestration
    lifecycle instead of replacing the entire item.
    """

    if not ddb:
        logger.warning(
            "DynamoDB RESULTS_TABLE is not configured; "
            "run state will not be persisted."
        )
        return

    if not run_id:
        raise ValueError(
            "run_id is required"
        )

    if not status:
        raise ValueError(
            "status is required"
        )

    timestamp = now()

    values = {
        ":status": status,
        ":updated_at": timestamp,
    }

    names = {
        "#status": "status",
        "#updated_at": "updated_at",
    }

    expressions = [
        "#status = :status",
        "#updated_at = :updated_at",
    ]

    counter = 0

    for key, value in fields.items():
        if value is None:
            continue

        counter += 1

        attribute_name = (
            f"#f{counter}"
        )

        attribute_value = (
            f":v{counter}"
        )

        names[attribute_name] = str(key)

        values[attribute_value] = _ddb_safe(
            value
        )

        expressions.append(
            f"{attribute_name} = "
            f"{attribute_value}"
        )

    try:
        ddb.update_item(
            Key={
                "run_id": run_id,
            },
            UpdateExpression=(
                "SET "
                + ", ".join(expressions)
            ),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )

        logger.info(
            "Run %s transitioned to %s",
            run_id,
            status,
        )

    except Exception:
        logger.exception(
            "Failed to update run state for %s",
            run_id,
        )


def get_run(
    run_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Retrieve the current run state.
    """

    if not ddb:
        return None

    if not run_id:
        return None

    try:
        response = ddb.get_item(
            Key={
                "run_id": run_id,
            }
        )

        return response.get("Item")

    except Exception:
        logger.exception(
            "Failed to retrieve run state for %s",
            run_id,
        )

        return None


# ---------------------------------------------------------------------------
# Bedrock
# ---------------------------------------------------------------------------

def bedrock(
    prompt: str,
    system: Optional[str] = None,
    max_tokens: int = 5000,
    temperature: float = 0.15,
    top_p: float = 0.9,
    retries: int = 3,
) -> str:
    """
    Invoke the configured Bedrock model through the Converse API.

    The model is used for reasoning and synthesis, not for inventing
    evidence. Evidence must be supplied by the research/CMS/evidence layers.
    """

    if not prompt or not prompt.strip():
        raise ValueError(
            "Bedrock prompt cannot be empty"
        )

    if not MODEL:
        raise ValueError(
            "MODEL is not configured in "
            "backend.common.config"
        )

    max_tokens = max(
        256,
        int(max_tokens),
    )

    temperature = max(
        0.0,
        min(float(temperature), 1.0),
    )

    top_p = max(
        0.0,
        min(float(top_p), 1.0),
    )

    retries = max(
        1,
        int(retries),
    )

    kwargs = {
        "modelId": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "text": prompt,
                    }
                ],
            }
        ],
        "inferenceConfig": {
            "maxTokens": max_tokens,
            "temperature": temperature,
            "topP": top_p,
        },
    }

    if system:
        kwargs["system"] = [
            {
                "text": system,
            }
        ]

    last_error = None

    for attempt in range(
        1,
        retries + 1,
    ):
        try:
            logger.info(
                "Bedrock invocation attempt "
                "%d/%d using model %s",
                attempt,
                retries,
                MODEL,
            )

            response = br.converse(
                **kwargs
            )

            output = (
                response
                .get("output", {})
                .get("message", {})
                .get("content", [])
            )

            if not output:
                raise RuntimeError(
                    "Bedrock returned an empty response."
                )

            text_parts = []

            for block in output:
                if (
                    isinstance(block, dict)
                    and "text" in block
                ):
                    text_parts.append(
                        str(block["text"])
                    )

            result = "\n".join(
                text_parts
            ).strip()

            if not result:
                raise RuntimeError(
                    "Bedrock returned no "
                    "textual content."
                )

            return result

        except Exception as exc:
            last_error = exc

            logger.warning(
                "Bedrock invocation failed "
                "on attempt %d: %s",
                attempt,
                exc,
            )

            if attempt < retries:
                sleep_seconds = min(
                    2 ** (attempt - 1),
                    8,
                )

                time.sleep(
                    sleep_seconds
                )

    raise RuntimeError(
        "Bedrock invocation failed after "
        f"{retries} attempts: {last_error}"
    )


# ---------------------------------------------------------------------------
# Research provenance helpers
# ---------------------------------------------------------------------------

def build_provenance(
    run_id: str,
    source: str,
    source_url: str = "",
    retrieved_at: Optional[str] = None,
    query: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a normalized provenance record.

    Every external evidence item should carry provenance whenever possible.
    """

    return {
        "run_id": run_id,
        "source": source,
        "source_url": source_url,
        "retrieved_at": (
            retrieved_at or now()
        ),
        "query": query,
        "metadata": metadata or {},
    }


# ---------------------------------------------------------------------------
# Artifact manifest
# ---------------------------------------------------------------------------

def build_artifact_record(
    run_id: str,
    artifact_type: str,
    bucket: str,
    key: str,
    **metadata: Any,
) -> Dict[str, Any]:
    """
    Create a standardized artifact record.
    """

    return {
        "artifact_id": generate_artifact_id(
            artifact_type
        ),
        "run_id": run_id,
        "artifact_type": artifact_type,
        "bucket": bucket,
        "key": key,
        "created_at": now(),
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# Research artifact helpers
# ---------------------------------------------------------------------------

def research_key(
    run_id: str,
    filename: str,
) -> str:
    """
    Build a standard research artifact S3 key.
    """

    if not run_id:
        raise ValueError(
            "run_id is required"
        )

    if not filename:
        raise ValueError(
            "filename is required"
        )

    return (
        f"{run_id.strip('/')}/"
        f"{filename.lstrip('/')}"
    )


def report_key(
    run_id: str,
    filename: str,
) -> str:
    """
    Build a standard report artifact S3 key.
    """

    if not run_id:
        raise ValueError(
            "run_id is required"
        )

    if not filename:
        raise ValueError(
            "filename is required"
        )

    return (
        f"{run_id.strip('/')}/"
        f"{filename.lstrip('/')}"
    )


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "REGION",
    "RESEARCH_BUCKET",
    "REPORTS_BUCKET",
    "RESULTS_TABLE",
    "MODEL",
    "AWS_REGION",
    "s3",
    "ddb_resource",
    "ddb",
    "br",
    "now",
    "generate_artifact_id",
    "dumps_json",
    "loads_json",
    "put_json",
    "put_text",
    "get_json",
    "get_text",
    "object_exists",
    "update_run",
    "get_run",
    "bedrock",
    "build_provenance",
    "build_artifact_record",
    "research_key",
    "report_key",
]