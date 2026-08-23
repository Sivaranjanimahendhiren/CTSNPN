"""
CTS-NPN S3 Artifact Storage

===========================

Central helper for storing and retrieving agent artifacts.

Artifact structure:

    s3://<ARTIFACT_BUCKET>/runs/<run_id>/<agent>/<filename>

Example:

    s3://cts-npn-research/runs/
        12345/
        planner/
        output.json

The module is designed for Lambda, Step Functions and local
development using the standard AWS credential chain.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import boto3


# ============================================================================
# S3 client
# ============================================================================

s3 = boto3.client(
    "s3",
    region_name=os.getenv("AWS_REGION", "us-east-1"),
)


# ============================================================================
# Configuration
# ============================================================================

ARTIFACT_BUCKET = (
    os.environ.get("ARTIFACT_BUCKET")
    or os.environ.get("RESEARCH_BUCKET")
    or ""
).strip()


# ============================================================================
# Validation
# ============================================================================

def _require_bucket(
    bucket: Optional[str] = None,
) -> str:
    """
    Return a valid bucket name.

    If no bucket is supplied, use ARTIFACT_BUCKET.
    """

    resolved_bucket = (
        bucket
        or ARTIFACT_BUCKET
        or ""
    ).strip()

    if not resolved_bucket:
        raise RuntimeError(
            "S3 artifact bucket is not configured. "
            "Set ARTIFACT_BUCKET or RESEARCH_BUCKET."
        )

    return resolved_bucket


def _validate_run_component(
    value: str,
    name: str,
) -> str:
    """
    Validate path components used in S3 artifact keys.
    """

    value = str(value or "").strip()

    if not value:
        raise ValueError(
            f"{name} cannot be empty."
        )

    if "/" in value or "\\" in value:
        raise ValueError(
            f"{name} cannot contain '/' or '\\'."
        )

    return value


# ============================================================================
# Artifact key
# ============================================================================

def artifact_key(
    run_id: str,
    agent: str,
    filename: str = "output.json",
) -> str:
    """
    Generate the canonical S3 artifact key.

    Result:

        runs/<run_id>/<agent>/<filename>
    """

    run_id = _validate_run_component(
        run_id,
        "run_id",
    )

    agent = _validate_run_component(
        agent,
        "agent",
    )

    filename = str(
        filename or "output.json"
    ).strip()

    if not filename:
        filename = "output.json"

    if filename.startswith("/"):
        filename = filename[1:]

    return (
        f"runs/{run_id}/{agent}/{filename}"
    )


# ============================================================================
# Write artifact
# ============================================================================

def write_artifact(
    run_id: str,
    agent: str,
    data: Any,
    filename: str = "output.json",
    bucket: Optional[str] = None,
) -> Dict[str, str]:
    """
    Serialize data to JSON and store it in S3.

    Returns:

        {
            "bucket": "...",
            "key": "...",
            "s3_uri": "s3://..."
        }
    """

    resolved_bucket = _require_bucket(
        bucket
    )

    key = artifact_key(
        run_id,
        agent,
        filename,
    )

    body = json.dumps(
        data,
        ensure_ascii=False,
        default=str,
        indent=2,
    ).encode("utf-8")

    s3.put_object(
        Bucket=resolved_bucket,
        Key=key,
        Body=body,
        ContentType="application/json; charset=utf-8",
    )

    return {
        "bucket": resolved_bucket,
        "key": key,
        "s3_uri": (
            f"s3://{resolved_bucket}/{key}"
        ),
    }


# ============================================================================
# Read artifact
# ============================================================================

def read_artifact(
    bucket: str,
    key: str,
) -> Any:
    """
    Read a JSON artifact from S3.
    """

    bucket = _require_bucket(
        bucket
    )

    key = str(
        key or ""
    ).strip()

    if not key:
        raise ValueError(
            "S3 object key cannot be empty."
        )

    response = s3.get_object(
        Bucket=bucket,
        Key=key,
    )

    body = response["Body"].read()

    return json.loads(
        body.decode("utf-8")
    )


# ============================================================================
# Read artifact URI
# ============================================================================

def read_artifact_uri(
    uri: str,
) -> Any:
    """
    Read a JSON artifact from an S3 URI.

    Expected format:

        s3://bucket/key
    """

    uri = str(
        uri or ""
    ).strip()

    if not uri.startswith("s3://"):
        raise ValueError(
            f"Invalid S3 URI: {uri}"
        )

    value = uri[5:]

    if "/" not in value:
        raise ValueError(
            f"Invalid S3 URI; missing object key: {uri}"
        )

    bucket, key = value.split(
        "/",
        1,
    )

    if not bucket:
        raise ValueError(
            f"Invalid S3 URI; missing bucket: {uri}"
        )

    if not key:
        raise ValueError(
            f"Invalid S3 URI; missing key: {uri}"
        )

    return read_artifact(
        bucket,
        key,
    )


# ============================================================================
# Optional utility functions
# ============================================================================

def artifact_exists(
    bucket: str,
    key: str,
) -> bool:
    """
    Check whether an S3 artifact exists.

    Returns False for a missing object.
    """

    bucket = _require_bucket(
        bucket
    )

    try:
        s3.head_object(
            Bucket=bucket,
            Key=key,
        )
        return True

    except s3.exceptions.ClientError as exc:

        error_code = (
            exc.response
            .get("Error", {})
            .get("Code", "")
        )

        if error_code in {
            "404",
            "NoSuchKey",
            "NotFound",
        }:
            return False

        raise


def delete_artifact(
    bucket: str,
    key: str,
) -> Dict[str, str]:
    """
    Delete an artifact from S3.
    """

    bucket = _require_bucket(
        bucket
    )

    key = str(
        key or ""
    ).strip()

    if not key:
        raise ValueError(
            "S3 object key cannot be empty."
        )

    s3.delete_object(
        Bucket=bucket,
        Key=key,
    )

    return {
        "bucket": bucket,
        "key": key,
        "s3_uri": f"s3://{bucket}/{key}",
    }