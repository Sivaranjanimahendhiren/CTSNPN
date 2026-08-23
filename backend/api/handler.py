"""
CTS-NPN API Gateway Lambda

Purpose
-------
Controlled API boundary for CTS-NPN.

Responsibilities:
1. Accept and validate research requests.
2. Normalize and sanitize user-controlled input.
3. Create a persistent run record.
4. Start exactly one AWS Step Functions execution.
5. Expose execution/run status through a GET endpoint.

Supported API routes:
    OPTIONS *
    POST /research
    POST /
    GET /runs/{run_id}
    GET /{run_id}
"""

import json
import os
import re
import traceback
import base64
import boto3

from datetime import datetime, timezone

from backend.common.config import REGION, STATE_MACHINE_ARN
from backend.common.aws import ddb, get_run
from backend.common.security import (
    new_run_id,
    require_fields,
    clean_text,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AWS_REGION = REGION or os.environ.get(
    "AWS_REGION",
    "us-east-1",
)

MAX_QUESTION_LENGTH = int(
    os.environ.get(
        "MAX_QUESTION_LENGTH",
        "12000",
    )
)

MAX_REQUESTED_BY_LENGTH = int(
    os.environ.get(
        "MAX_REQUESTED_BY_LENGTH",
        "200",
    )
)

MAX_CONTEXT_BYTES = int(
    os.environ.get(
        "MAX_CONTEXT_BYTES",
        "50000",
    )
)

SERVICE_NAME = "CTS-NPN"

SERVICE_VERSION = os.environ.get(
    "SERVICE_VERSION",
    "1.0.0",
)


# ---------------------------------------------------------------------------
# HTTP response helper
# ---------------------------------------------------------------------------

def resp(code, body, extra_headers=None):
    """
    Construct a consistent API Gateway-compatible response.
    """

    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": (
            "Content-Type,Authorization,X-Requested-With"
        ),
        "Access-Control-Allow-Methods": (
            "GET,POST,OPTIONS"
        ),
        "Cache-Control": "no-store",
        "X-CTS-NPN-Service": SERVICE_NAME,
        "X-CTS-NPN-Version": SERVICE_VERSION,
    }

    if extra_headers:
        headers.update(extra_headers)

    return {
        "statusCode": code,
        "headers": headers,
        "body": json.dumps(
            body,
            default=str,
            ensure_ascii=False,
        ),
    }


# ---------------------------------------------------------------------------
# Request extraction
# ---------------------------------------------------------------------------

def _http_method(event):
    """
    Support both API Gateway HTTP API v2 and REST API event structures.
    """

    if not isinstance(event, dict):
        return "POST"

    return (
        event.get("requestContext", {})
        .get("http", {})
        .get("method")
        or event.get("httpMethod")
        or "POST"
    ).upper()


def _path_run_id(event):
    """
    Extract run_id from routes such as:

        GET /runs/{run_id}

    or:

        GET /api/runs/{run_id}

    or:

        GET /{run_id}
    """

    path_parameters = event.get("pathParameters") or {}

    return (
        path_parameters.get("run_id")
        or path_parameters.get("id")
    )


# ---------------------------------------------------------------------------
# Body parsing
# ---------------------------------------------------------------------------

def _parse_body(event):
    """
    Parse the incoming API request body.

    Supports:
    - API Gateway JSON strings
    - Direct Lambda invocation dictionaries
    - Base64 encoded API Gateway payloads
    """

    if not isinstance(event, dict):
        raise ValueError(
            "Lambda event must be a JSON object."
        )

    body = event.get("body")

    # Direct Lambda invocation:
    # {
    #     "question": "...",
    #     "requested_by": "...",
    #     "context": {}
    # }
    if body is None:
        return event

    # Some direct invocations may already contain a dictionary body.
    if isinstance(body, dict):
        return body

    if not isinstance(body, str):
        raise ValueError(
            "Request body must be a JSON object."
        )

    # Decode API Gateway base64 body when required.
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(
                body
            ).decode("utf-8")
        except Exception as exc:
            raise ValueError(
                "Invalid base64 request body."
            ) from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Request body contains invalid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            "Request body must contain a JSON object."
        )

    return payload


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def _validate_question(question):
    """
    Validate and normalize the research question.
    """

    if question is None:
        raise ValueError(
            "Field 'question' is required."
        )

    if not isinstance(question, str):
        raise ValueError(
            "Field 'question' must be a string."
        )

    question = clean_text(
        question
    ).strip()

    if not question:
        raise ValueError(
            "Research question cannot be empty."
        )

    if len(question) > MAX_QUESTION_LENGTH:
        raise ValueError(
            "Research question exceeds the maximum "
            f"allowed length of {MAX_QUESTION_LENGTH} characters."
        )

    return question


def _validate_requested_by(value):
    """
    Normalize the request provenance field.
    """

    if value is None:
        return "demo-user"

    if not isinstance(value, str):
        raise ValueError(
            "Field 'requested_by' must be a string."
        )

    value = clean_text(
        value
    ).strip()

    if not value:
        return "demo-user"

    if len(value) > MAX_REQUESTED_BY_LENGTH:
        raise ValueError(
            "Field 'requested_by' exceeds the maximum "
            "allowed length."
        )

    return value


def _validate_context(context):
    """
    Validate optional contextual information.

    Context is treated as metadata/research context.
    """

    if context is None:
        return {}

    if not isinstance(context, dict):
        raise ValueError(
            "Field 'context' must be a JSON object."
        )

    try:
        serialized = json.dumps(
            context,
            ensure_ascii=False,
        )
    except Exception as exc:
        raise ValueError(
            "Field 'context' contains non-serializable data."
        ) from exc

    context_size = len(
        serialized.encode("utf-8")
    )

    if context_size > MAX_CONTEXT_BYTES:
        raise ValueError(
            "Context exceeds the maximum allowed size "
            f"of {MAX_CONTEXT_BYTES} bytes."
        )

    return context


# ---------------------------------------------------------------------------
# Request normalization
# ---------------------------------------------------------------------------

def _build_execution_input(payload, run_id):
    """
    Construct the canonical Step Functions input.

    The state machine expects:

        run_id
        question
        requested_by
        context

    This contract is intentionally preserved.
    """

    question = _validate_question(
        payload.get("question")
    )

    requested_by = _validate_requested_by(
        payload.get("requested_by")
    )

    context = _validate_context(
        payload.get("context", {})
    )

    return {
        "run_id": run_id,
        "question": question,
        "requested_by": requested_by,
        "context": context,
    }


# ---------------------------------------------------------------------------
# DynamoDB run registration
# ---------------------------------------------------------------------------

def _create_run_record(run_id, execution_input):
    """
    Create the initial research-run registry entry.
    """

    if not ddb:
        print(
            "WARNING: DynamoDB client is not configured. "
            "Run registry record was not created."
        )
        return

    now = datetime.now(
        timezone.utc
    ).isoformat()

    item = {
        "run_id": run_id,
        "status": "STARTING",
        "service": SERVICE_NAME,
        "service_version": SERVICE_VERSION,
        "question": execution_input["question"],
        "requested_by": execution_input["requested_by"],
        "created_at": now,
        "updated_at": now,
        "workflow": "research-to-report",
        "architecture": "multi-agent-step-functions",
        "input_validated": True,
        "execution_started": False,
    }

    ddb.put_item(
        Item=item
    )


def _mark_execution_started(
    run_id,
    execution_arn,
):
    """
    Update the run registry after Step Functions
    accepts the execution.
    """

    if not ddb:
        return

    now = datetime.now(
        timezone.utc
    ).isoformat()

    ddb.update_item(
        Key={
            "run_id": run_id
        },
        UpdateExpression=(
            "SET #status = :status, "
            "execution_arn = :execution_arn, "
            "execution_started = :started, "
            "updated_at = :updated_at"
        ),
        ExpressionAttributeNames={
            "#status": "status"
        },
        ExpressionAttributeValues={
            ":status": "STARTED",
            ":execution_arn": execution_arn,
            ":started": True,
            ":updated_at": now,
        },
    )


def _mark_start_failed(
    run_id,
    error_message,
):
    """
    Record a workflow-start failure without exposing
    internal infrastructure details to the API client.
    """

    if not ddb:
        return

    now = datetime.now(
        timezone.utc
    ).isoformat()

    try:
        ddb.update_item(
            Key={
                "run_id": run_id
            },
            UpdateExpression=(
                "SET #status = :status, "
                "error = :error, "
                "updated_at = :updated_at"
            ),
            ExpressionAttributeNames={
                "#status": "status"
            },
            ExpressionAttributeValues={
                ":status": "START_FAILED",
                ":error": str(error_message)[:2000],
                ":updated_at": now,
            },
        )

    except Exception as exc:
        print(
            "Unable to update failed run record: "
            f"{exc}"
        )


# ---------------------------------------------------------------------------
# Run lookup
# ---------------------------------------------------------------------------

def _get_run_status(run_id):
    """
    Return the application-level run state.
    """

    try:
        item = get_run(
            run_id
        )
        return item
    except Exception as exc:
        print(
            "Run lookup failed: "
            f"{exc}"
        )
        raise


# ---------------------------------------------------------------------------
# Security / route validation
# ---------------------------------------------------------------------------

def _validate_run_id(run_id):
    """
    Validate a run identifier before using it as a lookup key.
    """

    if not run_id:
        return False

    if not isinstance(run_id, str):
        return False

    if len(run_id) > 128:
        return False

    return bool(
        re.fullmatch(
            r"[A-Za-z0-9._:-]+",
            run_id,
        )
    )


# ---------------------------------------------------------------------------
# POST /research
# ---------------------------------------------------------------------------

def _start_research(event, context):
    """
    Start a new CTS-NPN research workflow.
    """

    run_id = None

    try:
        # ---------------------------------------------------------------
        # Parse request
        # ---------------------------------------------------------------

        payload = _parse_body(
            event
        )

        if not isinstance(payload, dict):
            raise ValueError(
                "Request payload must be a JSON object."
            )

        # ---------------------------------------------------------------
        # Require primary research question
        # ---------------------------------------------------------------

        require_fields(
            payload,
            ["question"],
        )

        # ---------------------------------------------------------------
        # Never accept a client-generated run ID
        # ---------------------------------------------------------------

        run_id = new_run_id()

        # ---------------------------------------------------------------
        # Build canonical Step Functions input
        # ---------------------------------------------------------------

        execution_input = _build_execution_input(
            payload,
            run_id,
        )

        # ---------------------------------------------------------------
        # Persist request before starting workflow
        # ---------------------------------------------------------------

        _create_run_record(
            run_id,
            execution_input,
        )

        print(
            json.dumps(
                {
                    "event": "RESEARCH_REQUEST_ACCEPTED",
                    "run_id": run_id,
                    "requested_by": execution_input[
                        "requested_by"
                    ],
                },
                ensure_ascii=False,
            )
        )

        # ---------------------------------------------------------------
        # Validate state machine configuration
        # ---------------------------------------------------------------

        if not STATE_MACHINE_ARN:
            raise RuntimeError(
                "STATE_MACHINE_ARN is not configured."
            )

        # ---------------------------------------------------------------
        # Create Step Functions client
        # ---------------------------------------------------------------

        sfn = boto3.client(
            "stepfunctions",
            region_name=AWS_REGION,
        )

        # ---------------------------------------------------------------
        # Serialize execution input exactly once
        # ---------------------------------------------------------------

        state_machine_input = json.dumps(
            execution_input,
            ensure_ascii=False,
        )

        # ---------------------------------------------------------------
        # Start multi-agent workflow
        # ---------------------------------------------------------------

        execution = sfn.start_execution(
            stateMachineArn=STATE_MACHINE_ARN,
            name=run_id,
            input=state_machine_input,
        )

        execution_arn = execution[
            "executionArn"
        ]

        # ---------------------------------------------------------------
        # Update DynamoDB registry
        # ---------------------------------------------------------------

        _mark_execution_started(
            run_id,
            execution_arn,
        )

        # ---------------------------------------------------------------
        # Return successful response
        # ---------------------------------------------------------------

        return resp(
            202,
            {
                "service": SERVICE_NAME,
                "run_id": run_id,
                "execution_arn": execution_arn,
                "status": "STARTED",
                "message": (
                    "Research workflow accepted and "
                    "submitted to the multi-agent orchestrator."
                ),
            },
        )

    except ValueError as exc:
        print(
            "Request validation failed: "
            f"{exc}"
        )

        return resp(
            400,
            {
                "error": "INVALID_REQUEST",
                "message": str(exc),
            },
        )

    except Exception as exc:
        error_message = str(exc)

        print(
            "Research execution failed:\n"
            + traceback.format_exc()
        )

        # Preserve failure state when a run ID was created.
        if run_id:
            try:
                _mark_start_failed(
                    run_id,
                    error_message,
                )
            except Exception:
                pass

        return resp(
            500,
            {
                "error": "WORKFLOW_START_FAILED",
                "message": (
                    "The research workflow could not be started."
                ),
            },
        )


# ---------------------------------------------------------------------------
# GET /runs/{run_id}
# ---------------------------------------------------------------------------

def _get_research_run(run_id):
    """
    Retrieve the current application-level status
    of a research run.
    """

    if not _validate_run_id(
        run_id
    ):
        return resp(
            400,
            {
                "error": "INVALID_RUN_ID",
                "message": (
                    "The supplied run_id is invalid."
                ),
            },
        )

    try:
        item = _get_run_status(
            run_id
        )
    except Exception:
        return resp(
            500,
            {
                "error": "RUN_LOOKUP_FAILED",
                "message": (
                    "The research run status could not be retrieved."
                ),
            },
        )

    if not item:
        return resp(
            404,
            {
                "error": "RUN_NOT_FOUND",
                "message": (
                    "Research run was not found."
                ),
                "run_id": run_id,
            },
        )

    return resp(
        200,
        {
            "service": SERVICE_NAME,
            "run": item,
        },
    )


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    Main API Lambda entry point.

    Supported routes:

        OPTIONS *
            CORS preflight.

        POST /research
            Start research-to-report execution.

        POST /
            Backward-compatible research execution.

        GET /runs/{run_id}
            Retrieve run status.

        GET /{run_id}
            Supported when API Gateway route parameters
            are configured.
    """

    # ---------------------------------------------------------------
    # Defensive event normalization
    # ---------------------------------------------------------------

    if not isinstance(event, dict):
        return resp(
            400,
            {
                "error": "INVALID_EVENT",
                "message": (
                    "Lambda event must be a JSON object."
                ),
            },
        )

    method = _http_method(
        event
    )

    request_id = getattr(
        context,
        "aws_request_id",
        "unknown",
    )

    print(
        json.dumps(
            {
                "event": "API_REQUEST",
                "method": method,
                "request_id": request_id,
            },
            ensure_ascii=False,
        )
    )

    # ---------------------------------------------------------------
    # CORS preflight
    # ---------------------------------------------------------------

    if method == "OPTIONS":
        return resp(
            204,
            {},
        )

    # ---------------------------------------------------------------
    # GET run status
    # ---------------------------------------------------------------

    if method == "GET":

        run_id = _path_run_id(
            event
        )

        # Fallback for query-string based access:
        #
        # GET /runs?run_id=abc
        #
        if not run_id:
            query_parameters = (
                event.get("queryStringParameters")
                or {}
            )

            run_id = (
                query_parameters.get("run_id")
                or query_parameters.get("id")
            )

        if not run_id:
            return resp(
                400,
                {
                    "error": "RUN_ID_REQUIRED",
                    "message": (
                        "Provide a run_id using the route "
                        "parameter or query parameter."
                    ),
                },
            )

        return _get_research_run(
            run_id
        )

    # ---------------------------------------------------------------
    # POST research request
    # ---------------------------------------------------------------

    if method == "POST":
        return _start_research(
            event,
            context,
        )

    # ---------------------------------------------------------------
    # Unsupported method
    # ---------------------------------------------------------------

    return resp(
        405,
        {
            "error": "METHOD_NOT_ALLOWED",
            "message": (
                f"HTTP method '{method}' is not supported."
            ),
        },
        {
            "Allow": "GET,POST,OPTIONS",
        },
    )