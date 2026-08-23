"""
CTS-NPN PDF Generator Agent

Purpose
-------
Generate the final publication-quality research PDF from artifacts stored in S3.

The generator:
1. Reads synthesis, evidence and critic artifacts from S3.
2. Handles UTF-8 / UTF-8 BOM / UTF-16 / UTF-32 / CP1252 / Latin-1.
3. Repairs common UTF-8 mojibake.
4. Extracts human-readable report content from nested artifacts.
5. Converts Markdown / structured text into a professional PDF.
6. Uses resume_template.pdf as the page background on EVERY page.
7. Falls back to resume_template.png when the PDF template is unavailable.
8. Supports multi-page reports.
9. Uploads the completed PDF directly to S3.
10. Generates a presigned download URL.
11. Stores compact metadata in S3.
12. Returns only compact metadata to Step Functions.

Required environment variables
------------------------------
ARTIFACT_BUCKET
REPORTS_BUCKET

Optional environment variables
------------------------------
REPORT_TEMPLATE_PATH
REPORT_TEMPLATE_S3_BUCKET
REPORT_TEMPLATE_S3_KEY
REPORT_DOWNLOAD_EXPIRES
PDF_MAX_TEXT_CHARS
PDF_MARGIN_LEFT
PDF_MARGIN_RIGHT
PDF_MARGIN_TOP
PDF_MARGIN_BOTTOM
"""

from __future__ import annotations

import html
import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import boto3

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from pypdf import PdfReader, PdfWriter


# ============================================================================
# LOGGING
# ============================================================================

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ============================================================================
# AWS
# ============================================================================

s3 = boto3.client("s3")


ARTIFACT_BUCKET = os.environ.get("ARTIFACT_BUCKET", "").strip()
REPORTS_BUCKET = os.environ.get("REPORTS_BUCKET", "").strip()


# ============================================================================
# VALIDATION
# ============================================================================

if not ARTIFACT_BUCKET:
    logger.warning("ARTIFACT_BUCKET environment variable is not configured.")

if not REPORTS_BUCKET:
    logger.warning("REPORTS_BUCKET environment variable is not configured.")


# ============================================================================
# CONFIGURATION
# ============================================================================

MAX_TEXT_CHARS = int(
    os.environ.get(
        "PDF_MAX_TEXT_CHARS",
        "500000",
    )
)

REPORT_DOWNLOAD_EXPIRES = int(
    os.environ.get(
        "REPORT_DOWNLOAD_EXPIRES",
        "3600",
    )
)


DEFAULT_SYNTHESIS_KEY = (
    "runs/{run_id}/synthesis/output.json"
)

DEFAULT_CRITIC_KEY = (
    "runs/{run_id}/critic/output.json"
)

DEFAULT_EVIDENCE_KEY = (
    "runs/{run_id}/evidence/output.json"
)

REPORT_KEY_TEMPLATE = (
    "runs/{run_id}/report/final.pdf"
)

REPORT_METADATA_KEY_TEMPLATE = (
    "runs/{run_id}/report/final_metadata.json"
)


# ============================================================================
# TEMPLATE CONFIGURATION
# ============================================================================

REPORT_TEMPLATE_PATH = os.environ.get(
    "REPORT_TEMPLATE_PATH",
    "",
).strip()

TEMPLATE_S3_BUCKET = os.environ.get(
    "REPORT_TEMPLATE_S3_BUCKET",
    "",
).strip()

TEMPLATE_S3_KEY = os.environ.get(
    "REPORT_TEMPLATE_S3_KEY",
    "resume_template.pdf",
).strip()


DEFAULT_TEMPLATE_PATHS = [
    REPORT_TEMPLATE_PATH,
    os.path.join(
        os.getcwd(),
        "resume_template.pdf",
    ),
    os.path.join(
        os.getcwd(),
        "resume_template.png",
    ),
    "/var/task/resume_template.pdf",
    "/var/task/resume_template.png",
    "/opt/resume_template.pdf",
    "/opt/resume_template.png",
]


# ============================================================================
# PAGE MARGINS
# ============================================================================

def env_float(
    name: str,
    default: float,
) -> float:
    try:
        return float(
            os.environ.get(
                name,
                str(default),
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        return default


MARGIN_LEFT = env_float(
    "PDF_MARGIN_LEFT",
    22,
)

MARGIN_RIGHT = env_float(
    "PDF_MARGIN_RIGHT",
    22,
)

MARGIN_TOP = env_float(
    "PDF_MARGIN_TOP",
    24,
)

MARGIN_BOTTOM = env_float(
    "PDF_MARGIN_BOTTOM",
    24,
)


# ============================================================================
# TIME
# ============================================================================

def utc_now() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================================
# S3 HELPERS
# ============================================================================

def parse_s3_reference(
    reference: Any,
    default_bucket: str,
) -> Tuple[str, str]:
    """
    Convert supported S3 reference formats into:
        (bucket, key)

    Supported:
        "key/path.json"
        "s3://bucket/key/path.json"
        {
            "bucket": "...",
            "key": "..."
        }
        {
            "s3_uri": "s3://bucket/key"
        }
    """

    bucket = default_bucket
    key: Optional[str] = None

    if isinstance(
        reference,
        str,
    ):
        reference = reference.strip()

        if reference.startswith("s3://"):
            value = reference[5:]
            parts = value.split(
                "/",
                1,
            )

            if len(parts) != 2:
                raise ValueError(
                    f"Invalid S3 URI: {reference}"
                )

            bucket = parts[0]
            key = parts[1]
        else:
            key = reference

    elif isinstance(
        reference,
        dict,
    ):
        bucket = (
            reference.get("bucket")
            or reference.get("Bucket")
            or reference.get("artifact_bucket")
            or default_bucket
        )

        key = (
            reference.get("key")
            or reference.get("Key")
            or reference.get("s3_key")
            or reference.get("artifact_key")
        )

        uri = (
            reference.get("s3_uri")
            or reference.get("s3Uri")
            or reference.get("uri")
        )

        if uri:
            uri = str(uri).strip()

            if not uri.startswith("s3://"):
                raise ValueError(
                    f"Invalid S3 URI: {uri}"
                )

            value = uri[5:]

            parts = value.split(
                "/",
                1,
            )

            if len(parts) != 2:
                raise ValueError(
                    f"Invalid S3 URI: {uri}"
                )

            bucket = parts[0]
            key = parts[1]

    if not bucket:
        raise ValueError(
            "S3 bucket is missing."
        )

    if not key:
        raise ValueError(
            "S3 object key is missing."
        )

    return (
        str(bucket),
        str(key),
    )


def read_s3_bytes(
    reference: Any,
    default_bucket: str,
) -> bytes:
    bucket, key = parse_s3_reference(
        reference,
        default_bucket,
    )

    logger.info(
        "Reading s3://%s/%s",
        bucket,
        key,
    )

    response = s3.get_object(
        Bucket=bucket,
        Key=key,
    )

    return response["Body"].read()


def read_json(
    reference: Any,
    default_bucket: str,
) -> Any:
    """
    Read and decode JSON from S3.
    """

    body = read_s3_bytes(
        reference,
        default_bucket,
    )

    text = decode_bytes(body)

    return decode_possible_json(text)


# ============================================================================
# ROBUST ENCODING / DECODING
# ============================================================================

def decode_bytes(
    data: bytes,
) -> str:
    """
    Decode common encodings safely.

    Supports:
        UTF-8
        UTF-8 BOM
        UTF-16 LE
        UTF-16 BE
        UTF-32
        CP1252
        Latin-1
    """

    if not data:
        return ""

    # UTF-8 BOM
    if data.startswith(
        b"\xef\xbb\xbf"
    ):
        return data.decode(
            "utf-8-sig",
            errors="replace",
        )

    # UTF-32 BOM
    if data.startswith(
        b"\xff\xfe\x00\x00"
    ):
        return data.decode(
            "utf-32-le",
            errors="replace",
        )

    if data.startswith(
        b"\x00\x00\xfe\xff"
    ):
        return data.decode(
            "utf-32-be",
            errors="replace",
        )

    # UTF-16 BOM
    if data.startswith(
        b"\xff\xfe"
    ):
        return data.decode(
            "utf-16-le",
            errors="replace",
        )

    if data.startswith(
        b"\xfe\xff"
    ):
        return data.decode(
            "utf-16-be",
            errors="replace",
        )

    encodings = [
        "utf-8",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "cp1252",
        "latin-1",
    ]

    for encoding in encodings:
        try:
            text = data.decode(
                encoding
            )

            # Reject obvious binary garbage.
            if "\x00" in text:
                null_ratio = (
                    text.count("\x00")
                    / max(
                        len(text),
                        1,
                    )
                )

                if null_ratio > 0.05:
                    continue

            return text

        except UnicodeDecodeError:
            continue

    return data.decode(
        "utf-8",
        errors="replace",
    )


# ============================================================================
# MOJIBAKE REPAIR
# ============================================================================

def repair_mojibake(
    text: str,
) -> str:
    """
    Repair common UTF-8 -> CP1252/Latin-1 mojibake.

    Examples:
        Ã©     -> é
        â€™    -> ’
        â€œ    -> “
        â€”    -> —
        Ã—     -> ×
    """

    if not text:
        return ""

    current = str(text)

    bad_markers = (
        "Ã",
        "Â",
        "â€",
        "â€™",
        "â€œ",
        "â€",
        "â€“",
        "â€”",
        "â€¦",
        "ðŸ",
        "�",
    )

    for _ in range(3):
        if not any(
            marker in current
            for marker in bad_markers
        ):
            break

        try:
            candidate = (
                current
                .encode("latin-1")
                .decode("utf-8")
            )

        except (
            UnicodeEncodeError,
            UnicodeDecodeError,
        ):
            break

        current_bad = sum(
            current.count(marker)
            for marker in bad_markers
        )

        candidate_bad = sum(
            candidate.count(marker)
            for marker in bad_markers
        )

        if candidate_bad < current_bad:
            current = candidate
        else:
            break

    return current


# ============================================================================
# POSSIBLE JSON DECODER
# ============================================================================

def decode_possible_json(
    value: Any,
) -> Any:
    """
    Decode JSON when a value itself contains JSON text.

    Handles:
        {"report":"hello"}
        "hello"
        escaped/nested JSON
        Markdown JSON fences
    """

    if not isinstance(
        value,
        str,
    ):
        return value

    text = repair_mojibake(
        value.strip()
    )

    if not text:
        return ""

    # Remove Markdown JSON fences.
    if text.startswith(
        "```json"
    ):
        text = text[
            len("```json"):
        ].strip()

        if text.endswith(
            "```"
        ):
            text = text[:-3].strip()

    elif text.startswith(
        "```"
    ):
        text = text[3:].strip()

        if text.endswith(
            "```"
        ):
            text = text[:-3].strip()

    # Try direct JSON parsing.
    looks_like_json = (
        (
            text.startswith("{")
            and text.endswith("}")
        )
        or (
            text.startswith("[")
            and text.endswith("]")
        )
        or (
            text.startswith('"')
            and text.endswith('"')
        )
    )

    if looks_like_json:
        try:
            parsed = json.loads(text)

            if parsed != text:
                return parsed

        except (
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ):
            pass

    return text


# ============================================================================
# GENERAL TEXT NORMALIZATION
# ============================================================================

def normalize_text(
    value: Any,
) -> str:
    """
    Convert arbitrary artifact values into readable text.
    """

    if value is None:
        return ""

    if isinstance(
        value,
        bytes,
    ):
        value = decode_bytes(value)

    if isinstance(
        value,
        str,
    ):
        value = repair_mojibake(value)

        decoded = decode_possible_json(
            value
        )

        if decoded != value:
            if isinstance(
                decoded,
                (
                    dict,
                    list,
                ),
            ):
                return normalize_text(
                    decoded
                )

            return repair_mojibake(
                str(decoded)
            )

        return value

    if isinstance(
        value,
        (
            int,
            float,
            bool,
        ),
    ):
        return str(value)

    try:
        return repair_mojibake(
            json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

    except Exception:
        return repair_mojibake(
            str(value)
        )


# ============================================================================
# EVENT ARTIFACT RESOLUTION
# ============================================================================

def resolve_artifact_reference(
    event: Dict[str, Any],
    artifact_name: str,
    default_key: str,
    run_id: str,
) -> Any:
    """
    Resolve an artifact reference from the Step Functions event.

    Supported locations:
        event.artifacts.<name>
        event.<name>
        event.artifact_references.<name>

    Falls back to:
        runs/{run_id}/...
    """

    artifacts = event.get(
        "artifacts",
        {},
    )

    if isinstance(
        artifacts,
        dict,
    ):
        value = artifacts.get(
            artifact_name
        )

        if value:
            return value

    value = event.get(
        artifact_name
    )

    if value:
        return value

    artifact_references = event.get(
        "artifact_references",
        {},
    )

    if isinstance(
        artifact_references,
        dict,
    ):
        value = artifact_references.get(
            artifact_name
        )

        if value:
            return value

    return default_key.format(
        run_id=run_id
    )


# ============================================================================
# CONTENT EXTRACTION
# ============================================================================

PREFERRED_CONTENT_KEYS = [
    "research_report",
    "research_document",
    "final_report",
    "report",
    "output",
    "content",
    "summary",
    "answer",
    "text",
    "final_answer",
    "analysis",
]


NESTED_CONTENT_KEYS = [
    "data",
    "result",
    "payload",
    "response",
    "body",
    "document",
    "message",
]


def extract_content(
    payload: Any,
    depth: int = 0,
) -> str:
    """
    Extract human-readable content from arbitrary nested artifacts.
    """

    if depth > 10:
        return normalize_text(
            payload
        )

    if payload is None:
        return ""

    if isinstance(
        payload,
        bytes,
    ):
        payload = decode_bytes(
            payload
        )

    if isinstance(
        payload,
        str,
    ):
        decoded = decode_possible_json(
            payload
        )

        if decoded != payload:
            return extract_content(
                decoded,
                depth + 1,
            )

        return repair_mojibake(
            payload.strip()
        )

    if isinstance(
        payload,
        dict,
    ):
        # Prefer report-like fields.
        for key in PREFERRED_CONTENT_KEYS:
            value = payload.get(
                key
            )

            if value in (
                None,
                "",
                [],
                {},
            ):
                continue

            extracted = extract_content(
                value,
                depth + 1,
            )

            if extracted.strip():
                return extracted

        # Then nested wrappers.
        for key in NESTED_CONTENT_KEYS:
            nested = payload.get(
                key
            )

            if nested in (
                None,
                "",
                [],
                {},
            ):
                continue

            extracted = extract_content(
                nested,
                depth + 1,
            )

            if extracted.strip():
                return extracted

        # Last resort: readable JSON.
        return normalize_text(
            payload
        )

    if isinstance(
        payload,
        list,
    ):
        parts: List[str] = []

        for item in payload:
            extracted = extract_content(
                item,
                depth + 1,
            )

            if extracted.strip():
                parts.append(
                    extracted
                )

        return "\n\n".join(parts)

    return normalize_text(
        payload
    )


# ============================================================================
# TEMPLATE RESOLUTION
# ============================================================================

def find_template() -> Tuple[str, bytes]:
    """
    Find resume_template.pdf first.

    If unavailable:
        resume_template.png

    Finally:
        S3 template
    """

    checked: List[str] = []

    # ----------------------------------------------------------------------
    # PDF TEMPLATE
    # ----------------------------------------------------------------------

    for path in DEFAULT_TEMPLATE_PATHS:
        if not path:
            continue

        absolute = os.path.abspath(
            path
        )

        checked.append(
            absolute
        )

        if (
            os.path.isfile(absolute)
            and absolute.lower().endswith(".pdf")
        ):
            logger.info(
                "Using PDF template: %s",
                absolute,
            )

            with open(
                absolute,
                "rb",
            ) as file:
                return (
                    "pdf",
                    file.read(),
                )

    # ----------------------------------------------------------------------
    # PNG TEMPLATE
    # ----------------------------------------------------------------------

    for path in DEFAULT_TEMPLATE_PATHS:
        if not path:
            continue

        absolute = os.path.abspath(
            path
        )

        if (
            os.path.isfile(absolute)
            and absolute.lower().endswith(".png")
        ):
            logger.info(
                "Using PNG template: %s",
                absolute,
            )

            with open(
                absolute,
                "rb",
            ) as file:
                return (
                    "png",
                    file.read(),
                )

    # ----------------------------------------------------------------------
    # S3 TEMPLATE
    # ----------------------------------------------------------------------

    if TEMPLATE_S3_BUCKET:
        try:
            logger.info(
                "Trying S3 template: s3://%s/%s",
                TEMPLATE_S3_BUCKET,
                TEMPLATE_S3_KEY,
            )

            response = s3.get_object(
                Bucket=TEMPLATE_S3_BUCKET,
                Key=TEMPLATE_S3_KEY,
            )

            body = response[
                "Body"
            ].read()

            if TEMPLATE_S3_KEY.lower().endswith(
                ".png"
            ):
                return (
                    "png",
                    body,
                )

            return (
                "pdf",
                body,
            )

        except Exception as exc:
            logger.warning(
                "S3 template lookup failed: %s",
                exc,
            )

    raise FileNotFoundError(
        "No resume_template.pdf or resume_template.png was found.\n\n"
        "Package the template with the Lambda or configure:\n"
        "REPORT_TEMPLATE_PATH\n"
        "REPORT_TEMPLATE_S3_BUCKET\n"
        "REPORT_TEMPLATE_S3_KEY\n\n"
        "Checked paths:\n"
        + "\n".join(checked)
    )


# ============================================================================
# TEMPLATE PAGE SIZE
# ============================================================================

def get_template_page_size(
    template_type: str,
    template_bytes: bytes,
) -> Tuple[float, float]:

    if template_type == "pdf":
        reader = PdfReader(
            io.BytesIO(
                template_bytes
            )
        )

        if not reader.pages:
            raise RuntimeError(
                "resume_template.pdf contains no pages."
            )

        page = reader.pages[0]

        return (
            float(
                page.mediabox.width
            ),
            float(
                page.mediabox.height
            ),
        )

    # PNG
    image = ImageReader(
        io.BytesIO(
            template_bytes
        )
    )

    width, height = image.getSize()

    if width <= 0 or height <= 0:
        return A4

    aspect = width / height
    a4_aspect = A4[0] / A4[1]

    if abs(
        aspect - a4_aspect
    ) < 0.10:
        return A4

    scale = 72.0 / 96.0

    return (
        width * scale,
        height * scale,
    )


# ============================================================================
# PDF STYLES
# ============================================================================

def build_styles():
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CTSNPNTITLE",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        spaceBefore=4,
        spaceAfter=10,
        keepWithNext=True,
    )

    h1_style = ParagraphStyle(
        "CTSNPNH1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        alignment=TA_LEFT,
        spaceBefore=11,
        spaceAfter=6,
        keepWithNext=True,
    )

    h2_style = ParagraphStyle(
        "CTSNPNH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=14,
        alignment=TA_LEFT,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True,
    )

    h3_style = ParagraphStyle(
        "CTSNPNH3",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        alignment=TA_LEFT,
        spaceBefore=6,
        spaceAfter=3,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "CTSNPBODY",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.8,
        leading=12.2,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
        splitLongWords=False,
    )

    bullet_style = ParagraphStyle(
        "CTSNPNBULLET",
        parent=body_style,
        leftIndent=12,
        firstLineIndent=-7,
        alignment=TA_LEFT,
        spaceAfter=3,
    )

    reference_style = ParagraphStyle(
        "CTSREFERENCE",
        parent=body_style,
        fontSize=7.6,
        leading=9.8,
        alignment=TA_LEFT,
        spaceAfter=4,
    )

    metadata_style = ParagraphStyle(
        "CTSMETADATA",
        parent=body_style,
        fontSize=7.5,
        leading=9.5,
        alignment=TA_LEFT,
        spaceAfter=3,
    )

    table_style = ParagraphStyle(
        "CTSTABLE",
        parent=body_style,
        fontSize=7.2,
        leading=8.7,
        alignment=TA_LEFT,
        spaceAfter=0,
    )

    return {
        "title": title_style,
        "h1": h1_style,
        "h2": h2_style,
        "h3": h3_style,
        "body": body_style,
        "bullet": bullet_style,
        "reference": reference_style,
        "metadata": metadata_style,
        "table": table_style,
    }


# ============================================================================
# INLINE MARKDOWN
# ============================================================================

def inline_markdown(
    text: str,
) -> str:
    """
    Convert basic Markdown into ReportLab-compatible inline markup.
    """

    text = str(
        text or ""
    )

    text = html.escape(
        text,
        quote=False,
    )

    # Bold
    text = re.sub(
        r"\*\*(.+?)\*\*",
        r"<b>\1</b>",
        text,
    )

    # Italic
    text = re.sub(
        r"(?<!\*)\*([^*]+?)\*(?!\*)",
        r"<i>\1</i>",
        text,
    )

    # Inline code
    text = re.sub(
        r"`([^`]+)`",
        r"<font name='Courier'>\1</font>",
        text,
    )

    # Markdown links
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r"<link href='\2' color='blue'>\1</link>",
        text,
    )

    # Plain URLs
    text = re.sub(
        r"(?<![\"'=])(https?://[^\s<]+)",
        r"<link href='\1' color='blue'>\1</link>",
        text,
    )

    return text


# ============================================================================
# TABLE PARSER
# ============================================================================

def build_table(
    lines: List[str],
    styles: Dict[str, ParagraphStyle],
    frame_width: float,
) -> Optional[Table]:

    rows: List[List[Paragraph]] = []

    for line in lines:

        stripped = (
            line.strip()
            .strip("|")
        )

        cells = [
            cell.strip()
            for cell in stripped.split("|")
        ]

        # Skip Markdown separator row.
        if cells and all(
            re.fullmatch(
                r":?-{3,}:?",
                cell,
            )
            for cell in cells
        ):
            continue

        rows.append(
            [
                Paragraph(
                    inline_markdown(cell),
                    styles["table"],
                )
                for cell in cells
            ]
        )

    if not rows:
        return None

    column_count = max(
        len(row)
        for row in rows
    )

    for row in rows:
        while len(row) < column_count:
            row.append(
                Paragraph(
                    "",
                    styles["table"],
                )
            )

    column_width = (
        frame_width
        / column_count
    )

    table = Table(
        rows,
        colWidths=[
            column_width
        ] * column_count,
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=True,
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.35,
                    None,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    4,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    3,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    3,
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold",
                ),
            ]
        )
    )

    return table


# ============================================================================
# MARKDOWN -> REPORTLAB
# ============================================================================

def markdown_to_story(
    markdown: str,
    styles: Dict[str, ParagraphStyle],
    frame_width: float,
) -> List[Any]:

    story: List[Any] = []

    markdown = (
        markdown
        .replace(
            "\r\n",
            "\n",
        )
        .replace(
            "\r",
            "\n",
        )
    )

    lines = markdown.split(
        "\n"
    )

    paragraph_buffer: List[str] = []

    def flush():
        nonlocal paragraph_buffer

        if not paragraph_buffer:
            return

        text = " ".join(
            line.strip()
            for line in paragraph_buffer
            if line.strip()
        ).strip()

        paragraph_buffer = []

        if not text:
            return

        story.append(
            Paragraph(
                inline_markdown(text),
                styles["body"],
            )
        )

    index = 0

    while index < len(lines):

        line = lines[index].strip()

        # --------------------------------------------------------------
        # EMPTY LINE
        # --------------------------------------------------------------

        if not line:
            flush()

            if story:
                story.append(
                    Spacer(
                        1,
                        3,
                    )
                )

            index += 1
            continue

        # --------------------------------------------------------------
        # H4
        # --------------------------------------------------------------

        if line.startswith(
            "#### "
        ):
            flush()

            story.append(
                Paragraph(
                    inline_markdown(
                        line[5:].strip()
                    ),
                    styles["h3"],
                )
            )

            index += 1
            continue

        # --------------------------------------------------------------
        # H3
        # --------------------------------------------------------------

        if line.startswith(
            "### "
        ):
            flush()

            story.append(
                Paragraph(
                    inline_markdown(
                        line[4:].strip()
                    ),
                    styles["h3"],
                )
            )

            index += 1
            continue

        # --------------------------------------------------------------
        # H2
        # --------------------------------------------------------------

        if line.startswith(
            "## "
        ):
            flush()

            story.append(
                Paragraph(
                    inline_markdown(
                        line[3:].strip()
                    ),
                    styles["h1"],
                )
            )

            index += 1
            continue

        # --------------------------------------------------------------
        # H1
        # --------------------------------------------------------------

        if line.startswith(
            "# "
        ):
            flush()

            story.append(
                Paragraph(
                    inline_markdown(
                        line[2:].strip()
                    ),
                    styles["title"],
                )
            )

            index += 1
            continue

        # --------------------------------------------------------------
        # HORIZONTAL RULE
        # --------------------------------------------------------------

        if line in (
            "---",
            "***",
            "___",
        ):
            flush()

            story.append(
                HRFlowable(
                    width="100%",
                    thickness=0.5,
                    spaceBefore=4,
                    spaceAfter=6,
                )
            )

            index += 1
            continue

        # --------------------------------------------------------------
        # MARKDOWN TABLE
        # --------------------------------------------------------------

        if (
            "|" in line
            and index + 1 < len(lines)
        ):
            next_line = lines[
                index + 1
            ].strip()

            if (
                "|" in next_line
                and re.search(
                    r"-{3,}",
                    next_line,
                )
            ):
                flush()

                table_lines: List[str] = []

                while (
                    index < len(lines)
                    and "|" in lines[index]
                ):
                    table_lines.append(
                        lines[index].strip()
                    )

                    index += 1

                table = build_table(
                    table_lines,
                    styles,
                    frame_width,
                )

                if table:
                    story.append(table)

                    story.append(
                        Spacer(
                            1,
                            6,
                        )
                    )

                continue

        # --------------------------------------------------------------
        # BULLET
        # --------------------------------------------------------------

        bullet_match = re.match(
            r"^[-*+]\s+(.+)$",
            line,
        )

        if bullet_match:
            flush()

            story.append(
                Paragraph(
                    "• "
                    + inline_markdown(
                        bullet_match.group(1)
                    ),
                    styles["bullet"],
                )
            )

            index += 1
            continue

        # --------------------------------------------------------------
        # NUMBERED LIST
        # --------------------------------------------------------------

        numbered_match = re.match(
            r"^(\d+)\.\s+(.+)$",
            line,
        )

        if numbered_match:
            flush()

            story.append(
                Paragraph(
                    numbered_match.group(1)
                    + ". "
                    + inline_markdown(
                        numbered_match.group(2)
                    ),
                    styles["bullet"],
                )
            )

            index += 1
            continue

        # --------------------------------------------------------------
        # REFERENCES
        # --------------------------------------------------------------

        if re.match(
            r"^\[S\d+\]",
            line,
        ):
            flush()

            story.append(
                Paragraph(
                    inline_markdown(line),
                    styles["reference"],
                )
            )

            index += 1
            continue

        # --------------------------------------------------------------
        # NORMAL PROSE
        # --------------------------------------------------------------

        paragraph_buffer.append(
            line
        )

        index += 1

    flush()

    return story


# ============================================================================
# PNG BACKGROUND
# ============================================================================

def draw_png_background(
    canvas,
    doc,
    template_bytes: bytes,
    page_width: float,
    page_height: float,
):
    """
    Draw PNG template behind every generated page.
    """

    canvas.saveState()

    canvas.drawImage(
        ImageReader(
            io.BytesIO(
                template_bytes
            )
        ),
        0,
        0,
        width=page_width,
        height=page_height,
        preserveAspectRatio=False,
        mask="auto",
    )

    canvas.restoreState()


# ============================================================================
# PDF OVERLAY GENERATION
# ============================================================================

def build_content_overlay(
    report_text: str,
    template_type: str,
    template_bytes: bytes,
    page_width: float,
    page_height: float,
) -> bytes:

    buffer = io.BytesIO()

    frame_width = (
        page_width
        - MARGIN_LEFT
        - MARGIN_RIGHT
    )

    frame_height = (
        page_height
        - MARGIN_TOP
        - MARGIN_BOTTOM
    )

    if frame_width <= 100:
        raise RuntimeError(
            "PDF margins leave insufficient content width."
        )

    if frame_height <= 100:
        raise RuntimeError(
            "PDF margins leave insufficient content height."
        )

    styles = build_styles()

    story = markdown_to_story(
        report_text,
        styles,
        frame_width,
    )

    if not story:
        story = [
            Paragraph(
                "No report content was available.",
                styles["body"],
            )
        ]

    # ======================================================================
    # PNG TEMPLATE
    # ======================================================================

    if template_type == "png":

        document = BaseDocTemplate(
            buffer,
            pagesize=(
                page_width,
                page_height,
            ),
            leftMargin=MARGIN_LEFT,
            rightMargin=MARGIN_RIGHT,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM,
            title="CTS-NPN Research Report",
            author="CTS-NPN PDF Generator",
        )

        frame = Frame(
            MARGIN_LEFT,
            MARGIN_BOTTOM,
            frame_width,
            frame_height,
            id="content",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )

        page_template = PageTemplate(
            id="resume-background",
            frames=[frame],
            onPage=lambda canvas, doc: draw_png_background(
                canvas,
                doc,
                template_bytes,
                page_width,
                page_height,
            ),
        )

        document.addPageTemplates(
            [page_template]
        )

        document.build(story)

        return buffer.getvalue()

    # ======================================================================
    # PDF TEMPLATE
    # ======================================================================

    document = BaseDocTemplate(
        buffer,
        pagesize=(
            page_width,
            page_height,
        ),
        leftMargin=MARGIN_LEFT,
        rightMargin=MARGIN_RIGHT,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title="CTS-NPN Research Report",
        author="CTS-NPN PDF Generator",
    )

    frame = Frame(
        MARGIN_LEFT,
        MARGIN_BOTTOM,
        frame_width,
        frame_height,
        id="content",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )

    page_template = PageTemplate(
        id="content",
        frames=[frame],
    )

    document.addPageTemplates(
        [page_template]
    )

    document.build(story)

    return buffer.getvalue()


# ============================================================================
# MERGE PDF TEMPLATE BEHIND EVERY PAGE
# ============================================================================

def merge_pdf_background_every_page(
    overlay_bytes: bytes,
    template_bytes: bytes,
) -> bytes:

    overlay_reader = PdfReader(
        io.BytesIO(
            overlay_bytes
        )
    )

    template_reader = PdfReader(
        io.BytesIO(
            template_bytes
        )
    )

    if not overlay_reader.pages:
        raise RuntimeError(
            "Generated content PDF contains no pages."
        )

    if not template_reader.pages:
        raise RuntimeError(
            "resume_template.pdf contains no pages."
        )

    writer = PdfWriter()

    # Use the first page of the template as the background
    # for every report page.
    template_page = template_reader.pages[0]

    for overlay_page in overlay_reader.pages:

        # Clone/re-read the template so each page receives
        # an independent background object.
        background_reader = PdfReader(
            io.BytesIO(
                template_bytes
            )
        )

        background = (
            background_reader.pages[0]
        )

        background.merge_page(
            overlay_page
        )

        writer.add_page(
            background
        )

    output = io.BytesIO()

    writer.write(
        output
    )

    return output.getvalue()


# ============================================================================
# FINAL REPORT TEXT
# ============================================================================

def build_final_report_text(
    run_id: str,
    synthesis: Any,
    evidence: Any,
    critic: Any,
) -> str:
    """
    Construct the final publication-ready report.

    Synthesis is the primary report.

    Evidence and critic are appended only if synthesis does not already
    contain corresponding sections.
    """

    synthesis_text = extract_content(
        synthesis
    )

    evidence_text = extract_content(
        evidence
    )

    critic_text = extract_content(
        critic
    )

    synthesis_text = repair_mojibake(
        synthesis_text
    )

    evidence_text = repair_mojibake(
        evidence_text
    )

    critic_text = repair_mojibake(
        critic_text
    )

    # ======================================================================
    # PRIMARY REPORT
    # ======================================================================

    if synthesis_text.strip():

        report = synthesis_text.strip()

    else:

        report = (
            "# CTS-NPN Research Report\n\n"
            "No synthesis report was available.\n"
        )

    report_lower = report.lower()

    # ======================================================================
    # EVIDENCE
    # ======================================================================

    if (
        evidence_text.strip()
        and "## evidence" not in report_lower
        and "## evidence base" not in report_lower
    ):
        report += (
            "\n\n"
            "## Evidence\n\n"
            + evidence_text.strip()
        )

    # ======================================================================
    # CRITICAL REVIEW
    # ======================================================================

    if (
        critic_text.strip()
        and "## critical review" not in report_lower
        and "## critic review" not in report_lower
    ):
        report += (
            "\n\n"
            "## Critical Review\n\n"
            + critic_text.strip()
        )

    # ======================================================================
    # GENERATOR METADATA
    # ======================================================================

    report += (
        "\n\n"
        "---\n\n"
        "## PDF Generation Metadata\n\n"
        f"- **Run ID:** {run_id}\n"
        f"- **Generated:** {utc_now()}\n"
        "- **Generator:** CTS-NPN PDF Generator Agent\n"
        "- **Background Template:** "
        "resume_template.pdf / resume_template.png\n"
        "- **Rendering:** "
        "Evidence-grounded multi-page document\n"
    )

    return report.strip()


# ============================================================================
# FINAL PDF BUILD
# ============================================================================

def build_pdf(
    run_id: str,
    synthesis: Any,
    evidence: Any,
    critic: Any,
) -> Tuple[bytes, Dict[str, Any]]:

    # ----------------------------------------------------------------------
    # FIND TEMPLATE
    # ----------------------------------------------------------------------

    template_type, template_bytes = find_template()

    page_width, page_height = get_template_page_size(
        template_type,
        template_bytes,
    )

    logger.info(
        "Template type=%s size=%.2fx%.2f",
        template_type,
        page_width,
        page_height,
    )

    # ----------------------------------------------------------------------
    # BUILD REPORT TEXT
    # ----------------------------------------------------------------------

    report_text = build_final_report_text(
        run_id=run_id,
        synthesis=synthesis,
        evidence=evidence,
        critic=critic,
    )

    # ----------------------------------------------------------------------
    # SAFETY LIMIT
    # ----------------------------------------------------------------------

    if len(report_text) > MAX_TEXT_CHARS:

        logger.warning(
            "Report exceeds PDF_MAX_TEXT_CHARS=%s",
            MAX_TEXT_CHARS,
        )

        report_text = (
            report_text[
                :MAX_TEXT_CHARS
            ]
            + "\n\n"
            "[PDF generator safety boundary reached. "
            "Complete source artifacts remain available in S3.]"
        )

    # ----------------------------------------------------------------------
    # CREATE CONTENT
    # ----------------------------------------------------------------------

    overlay = build_content_overlay(
        report_text=report_text,
        template_type=template_type,
        template_bytes=template_bytes,
        page_width=page_width,
        page_height=page_height,
    )

    # ----------------------------------------------------------------------
    # APPLY PDF BACKGROUND
    # ----------------------------------------------------------------------

    if template_type == "pdf":

        final_pdf = merge_pdf_background_every_page(
            overlay,
            template_bytes,
        )

    else:

        final_pdf = overlay

    # ----------------------------------------------------------------------
    # VALIDATE PDF
    # ----------------------------------------------------------------------

    final_reader = PdfReader(
        io.BytesIO(
            final_pdf
        )
    )

    page_count = len(
        final_reader.pages
    )

    if page_count <= 0:
        raise RuntimeError(
            "Final generated PDF contains zero pages."
        )

    metadata = {
        "template_type": template_type,
        "template_file": (
            "resume_template.pdf"
            if template_type == "pdf"
            else "resume_template.png"
        ),
        "page_width_points": round(
            page_width,
            2,
        ),
        "page_height_points": round(
            page_height,
            2,
        ),
        "page_count": page_count,
        "size_bytes": len(
            final_pdf
        ),
        "content_characters": len(
            report_text
        ),
        "background_applied_to_every_page": True,
        "generated_at": utc_now(),
    }

    return (
        final_pdf,
        metadata,
    )


# ============================================================================
# PRESIGNED DOWNLOAD URL
# ============================================================================

def create_download_url(
    bucket: str,
    key: str,
) -> str:

    return s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ResponseContentType": "application/pdf",
            "ResponseContentDisposition": (
                'attachment; filename="CTS-NPN-Research-Report.pdf"'
            ),
        },
        ExpiresIn=REPORT_DOWNLOAD_EXPIRES,
    )


# ============================================================================
# STORE METADATA
# ============================================================================

def store_metadata(
    metadata_key: str,
    metadata: Dict[str, Any],
) -> None:

    s3.put_object(
        Bucket=REPORTS_BUCKET,
        Key=metadata_key,
        Body=json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8"),
        ContentType="application/json",
    )


# ============================================================================
# MAIN LAMBDA
# ============================================================================

def lambda_handler(
    event,
    context,
):
    """
    AWS Lambda entry point.
    """

    event = (
        event
        if isinstance(
            event,
            dict,
        )
        else {}
    )

    run_id = str(
        event.get(
            "run_id",
            "",
        )
    ).strip()

    # ======================================================================
    # VALIDATE RUN ID
    # ======================================================================

    if not run_id:

        return {
            "status": "FAILED",
            "error": "run_id is required.",
        }

    # ======================================================================
    # VALIDATE REQUIRED BUCKETS
    # ======================================================================

    if not ARTIFACT_BUCKET:

        return {
            "run_id": run_id,
            "status": "FAILED",
            "error": (
                "ARTIFACT_BUCKET environment variable is not configured."
            ),
        }

    if not REPORTS_BUCKET:

        return {
            "run_id": run_id,
            "status": "FAILED",
            "error": (
                "REPORTS_BUCKET environment variable is not configured."
            ),
        }

    try:

        logger.info(
            "============================================================"
        )

        logger.info(
            "CTS-NPN PDF GENERATOR START"
        )

        logger.info(
            "run_id=%s",
            run_id,
        )

        logger.info(
            "============================================================"
        )

        # ==================================================================
        # 1. RESOLVE ARTIFACT REFERENCES
        # ==================================================================

        synthesis_reference = (
            resolve_artifact_reference(
                event,
                "synthesis",
                DEFAULT_SYNTHESIS_KEY,
                run_id,
            )
        )

        critic_reference = (
            resolve_artifact_reference(
                event,
                "critic",
                DEFAULT_CRITIC_KEY,
                run_id,
            )
        )

        evidence_reference = (
            resolve_artifact_reference(
                event,
                "evidence",
                DEFAULT_EVIDENCE_KEY,
                run_id,
            )
        )

        logger.info(
            "Synthesis reference: %s",
            synthesis_reference,
        )

        logger.info(
            "Evidence reference: %s",
            evidence_reference,
        )

        logger.info(
            "Critic reference: %s",
            critic_reference,
        )

        # ==================================================================
        # 2. READ ARTIFACTS FROM S3
        # ==================================================================

        synthesis = read_json(
            synthesis_reference,
            ARTIFACT_BUCKET,
        )

        evidence = read_json(
            evidence_reference,
            ARTIFACT_BUCKET,
        )

        critic = read_json(
            critic_reference,
            ARTIFACT_BUCKET,
        )

        logger.info(
            "All source artifacts loaded successfully."
        )

        # ==================================================================
        # 3. GENERATE FINAL PDF
        # ==================================================================

        pdf_bytes, pdf_metadata = build_pdf(
            run_id=run_id,
            synthesis=synthesis,
            evidence=evidence,
            critic=critic,
        )

        logger.info(
            "PDF generated: pages=%s bytes=%s",
            pdf_metadata["page_count"],
            len(pdf_bytes),
        )

        # ==================================================================
        # 4. BUILD REPORT S3 KEY
        # ==================================================================

        report_key = REPORT_KEY_TEMPLATE.format(
            run_id=run_id
        )

        # ==================================================================
        # 5. UPLOAD FINAL PDF
        # ==================================================================

        s3.put_object(
            Bucket=REPORTS_BUCKET,
            Key=report_key,
            Body=pdf_bytes,
            ContentType="application/pdf",
            ContentDisposition=(
                'attachment; filename="CTS-NPN-Research-Report.pdf"'
            ),
            Metadata={
                "run-id": run_id,
                "generator": "CTS-NPN-PDF-Generator",
                "template": pdf_metadata[
                    "template_file"
                ],
                "pages": str(
                    pdf_metadata[
                        "page_count"
                    ]
                ),
            },
        )

        logger.info(
            "Final PDF uploaded to s3://%s/%s",
            REPORTS_BUCKET,
            report_key,
        )

        # ==================================================================
        # 6. GENERATE PRESIGNED DOWNLOAD URL
        # ==================================================================

        download_url = create_download_url(
            REPORTS_BUCKET,
            report_key,
        )

        # ==================================================================
        # 7. STORE SMALL METADATA ARTIFACT
        # ==================================================================

        metadata_key = (
            REPORT_METADATA_KEY_TEMPLATE.format(
                run_id=run_id
            )
        )

        stored_metadata = {
            "run_id": run_id,
            "status": "COMPLETE",
            "report_key": report_key,
            "s3_uri": (
                f"s3://{REPORTS_BUCKET}/{report_key}"
            ),
            "download_url_expires_seconds": (
                REPORT_DOWNLOAD_EXPIRES
            ),
            "pdf": pdf_metadata,
            "source_artifacts": {
                "synthesis": True,
                "evidence": True,
                "critic": True,
            },
            "generated_at": utc_now(),
        }

        store_metadata(
            metadata_key,
            stored_metadata,
        )

        logger.info(
            "Metadata uploaded to s3://%s/%s",
            REPORTS_BUCKET,
            metadata_key,
        )

        # ==================================================================
        # 8. COMPACT STEP FUNCTIONS RESPONSE
        # ==================================================================

        result = {
            "run_id": run_id,
            "status": "COMPLETE",

            "report": {
                "bucket": REPORTS_BUCKET,
                "key": report_key,
                "s3_uri": (
                    f"s3://{REPORTS_BUCKET}/{report_key}"
                ),
                "content_type": "application/pdf",
                "size_bytes": len(pdf_bytes),
                "page_count": pdf_metadata[
                    "page_count"
                ],
            },

            "download_url": download_url,

            "metadata": {
                "bucket": REPORTS_BUCKET,
                "key": metadata_key,
                "s3_uri": (
                    f"s3://{REPORTS_BUCKET}/{metadata_key}"
                ),
            },

            "pdf_metadata": pdf_metadata,

            "source_artifacts": {
                "synthesis": True,
                "evidence": True,
                "critic": True,
            },

            "message": (
                "Final research PDF generated successfully, "
                "with the configured resume template applied "
                "to every page, stored in S3, and exposed through "
                "a presigned download URL."
            ),
        }

        logger.info(
            "============================================================"
        )

        logger.info(
            "CTS-NPN PDF GENERATOR COMPLETE"
        )

        logger.info(
            "run_id=%s pages=%s bytes=%s",
            run_id,
            pdf_metadata["page_count"],
            len(pdf_bytes),
        )

        logger.info(
            "============================================================"
        )

        return result

    # ======================================================================
    # FAILURE
    # ======================================================================

    except Exception as exc:

        error_type = type(
            exc
        ).__name__

        error_message = str(
            exc
        )

        logger.exception(
            "CTS-NPN PDF Generator failed for run_id=%s",
            run_id,
        )

        # IMPORTANT:
        # Never return large artifacts to Step Functions.
        return {
            "run_id": run_id,
            "status": "FAILED",
            "error": (
                f"{error_type}: "
                f"{error_message}"
            ),
        }