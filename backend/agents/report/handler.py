import json
import os
import re
from datetime import datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape as xml_escape

import boto3

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable,
)


# ============================================================================
# AWS clients
# ============================================================================

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")


# ============================================================================
# Configuration
# ============================================================================

REPORTS_BUCKET = os.environ["REPORTS_BUCKET"]
RESULTS_TABLE = os.environ["RESULTS_TABLE"]

PDF_PREFIX = os.environ.get(
    "REPORTS_PDF_PREFIX",
    "reports/pdf/",
)

REPORT_TITLE = os.environ.get(
    "REPORT_TITLE",
    "CTS-NPN Research Intelligence Report",
)

REPORT_AUTHOR = os.environ.get(
    "REPORT_AUTHOR",
    "CTS-NPN Research-to-Report Analyst",
)


# ============================================================================
# Lambda entry point
# ============================================================================


def lambda_handler(event, context):
    """
    Generate the final CTS-NPN research report PDF.

    Expected event:

    {
        "run_id": "TEST002"
    }

    Flow:

    1. Validate run_id.
    2. Read orchestration result from DynamoDB.
    3. Locate final research report in S3.
    4. Parse JSON / Markdown / text.
    5. Extract final report content.
    6. Generate a professional multi-page PDF.
    7. Upload PDF to S3.
    8. Update DynamoDB with PDF metadata.
    9. Return PDF location.
    """

    print("=" * 72)
    print("CTS-NPN PDF GENERATOR")
    print("=" * 72)

    print("PDF GENERATOR EVENT:")
    print(json.dumps(event, default=str))

    # ------------------------------------------------------------------------
    # Validate event
    # ------------------------------------------------------------------------

    if not isinstance(event, dict):
        raise ValueError(
            "Lambda event must be a JSON object"
        )

    run_id = event.get("run_id")

    if not run_id:
        raise ValueError(
            "run_id is required"
        )

    run_id = str(run_id).strip()

    if not run_id:
        raise ValueError(
            "run_id cannot be empty"
        )

    # ------------------------------------------------------------------------
    # Read orchestration result from DynamoDB
    # ------------------------------------------------------------------------

    table = dynamodb.Table(RESULTS_TABLE)

    item_response = table.get_item(
        Key={
            "run_id": run_id
        }
    )

    item = item_response.get(
        "Item",
        {}
    )

    print(
        "DynamoDB result item:"
    )

    print(
        json.dumps(
            item,
            default=str
        )
    )

    # ------------------------------------------------------------------------
    # Determine final report S3 key
    # ------------------------------------------------------------------------

    report_key = (
        item.get("final_report_key")
        or item.get("report_key")
        or item.get("synthesis_key")
        or f"reports/final/{run_id}/research_report.json"
    )

    print(
        f"Reading final report from "
        f"s3://{REPORTS_BUCKET}/{report_key}"
    )

    # ------------------------------------------------------------------------
    # Read final report from S3
    # ------------------------------------------------------------------------

    raw = _read_report_from_s3(
        run_id=run_id,
        preferred_key=report_key,
    )

    # ------------------------------------------------------------------------
    # Parse report
    # ------------------------------------------------------------------------

    report = _parse_report(raw)

    # ------------------------------------------------------------------------
    # Extract readable report content
    # ------------------------------------------------------------------------

    report_text = _extract_report_text(
        report
    )

    if not report_text.strip():
        raise ValueError(
            f"Final report is empty for run_id={run_id}"
        )

    print(
        f"Final report characters: "
        f"{len(report_text)}"
    )

    # ------------------------------------------------------------------------
    # Extract optional metadata
    # ------------------------------------------------------------------------

    metadata = _extract_report_metadata(
        report
    )

    # ------------------------------------------------------------------------
    # Generate PDF
    # ------------------------------------------------------------------------

    pdf_bytes = create_pdf(
        title=REPORT_TITLE,
        body=report_text,
        run_id=run_id,
        metadata=metadata,
    )

    if not pdf_bytes:
        raise RuntimeError(
            "PDF generation returned empty output"
        )

    print(
        f"Generated PDF size: "
        f"{len(pdf_bytes)} bytes"
    )

    # ------------------------------------------------------------------------
    # Determine PDF S3 key
    # ------------------------------------------------------------------------

    pdf_prefix = PDF_PREFIX.strip("/")

    if pdf_prefix:
        pdf_key = (
            f"{pdf_prefix}/"
            f"{run_id}/"
            f"research_report.pdf"
        )
    else:
        pdf_key = (
            f"{run_id}/"
            f"research_report.pdf"
        )

    pdf_uri = (
        f"s3://{REPORTS_BUCKET}/{pdf_key}"
    )

    print(
        f"Uploading PDF to "
        f"{pdf_uri}"
    )

    # ------------------------------------------------------------------------
    # Upload PDF
    # ------------------------------------------------------------------------

    s3.put_object(
        Bucket=REPORTS_BUCKET,
        Key=pdf_key,
        Body=pdf_bytes,
        ContentType="application/pdf",
        ContentDisposition=(
            f'inline; '
            f'filename="CTS-NPN-{run_id}-research-report.pdf"'
        ),
        Metadata={
            "run-id": run_id,
            "report-type": "research-report",
            "generator": "cts-npn-report-agent",
        },
    )

    print(
        "PDF uploaded successfully."
    )

    # ------------------------------------------------------------------------
    # Update DynamoDB
    # ------------------------------------------------------------------------

    table.update_item(
        Key={
            "run_id": run_id
        },
        UpdateExpression=(
            "SET "
            "pdf_key = :pdf_key, "
            "pdf_bucket = :pdf_bucket, "
            "pdf_s3_uri = :pdf_uri, "
            "pdf_status = :status, "
            "pdf_generated_at = :generated_at"
        ),
        ExpressionAttributeValues={
            ":pdf_key": pdf_key,
            ":pdf_bucket": REPORTS_BUCKET,
            ":pdf_uri": pdf_uri,
            ":status": "PDF_GENERATED",
            ":generated_at": _utc_now(),
        },
    )

    print(
        "DynamoDB updated successfully."
    )

    print("=" * 72)
    print("PDF GENERATION COMPLETE")
    print("=" * 72)

    # ------------------------------------------------------------------------
    # Return result
    # ------------------------------------------------------------------------

    return {
        "run_id": run_id,
        "pdf_bucket": REPORTS_BUCKET,
        "pdf_key": pdf_key,
        "pdf_s3_uri": pdf_uri,
        "source_report_key": report_key,
        "status": "PDF_GENERATED",
        "pdf_generated_at": _utc_now(),
    }


# ============================================================================
# S3 report reader
# ============================================================================


def _read_report_from_s3(
    run_id: str,
    preferred_key: str,
) -> str:
    """
    Read the final report from S3.

    The DynamoDB-provided key is attempted first.

    Fallback locations are included for compatibility with
    different CTS-NPN orchestration versions.
    """

    candidates = []

    if preferred_key:
        candidates.append(
            preferred_key
        )

    candidates.extend(
        [
            f"reports/final/{run_id}/research_report.json",
            f"reports/final/{run_id}/report.json",
            f"reports/final/{run_id}/research_report.md",
            f"reports/final/{run_id}/report.md",
            f"reports/drafts/{run_id}/research_report.json",
            f"reports/drafts/{run_id}/research_report.md",
            f"runs/{run_id}/report/final.json",
            f"runs/{run_id}/report/final.md",
            f"runs/{run_id}/synthesis/output.json",
            f"runs/{run_id}/synthesis/output.md",
        ]
    )

    # ------------------------------------------------------------------------
    # Remove duplicates while preserving order.
    # ------------------------------------------------------------------------

    unique_candidates = []

    for candidate in candidates:

        candidate = str(
            candidate
        ).strip()

        if (
            candidate
            and candidate not in unique_candidates
        ):
            unique_candidates.append(
                candidate
            )

    last_error = None

    # ------------------------------------------------------------------------
    # Try each candidate
    # ------------------------------------------------------------------------

    for candidate in unique_candidates:

        print(
            f"Trying report key: "
            f"s3://{REPORTS_BUCKET}/{candidate}"
        )

        try:

            response = s3.get_object(
                Bucket=REPORTS_BUCKET,
                Key=candidate,
            )

            raw = response["Body"].read()

            if isinstance(raw, bytes):

                raw = raw.decode(
                    "utf-8",
                    errors="replace",
                )

            else:

                raw = str(
                    raw
                )

            if not raw.strip():

                raise ValueError(
                    f"S3 report object is empty: "
                    f"{candidate}"
                )

            print(
                f"Successfully read report: "
                f"{candidate}"
            )

            return raw

        except Exception as exc:

            last_error = exc

            print(
                f"Could not read "
                f"s3://{REPORTS_BUCKET}/{candidate}: "
                f"{exc}"
            )

    raise RuntimeError(
        f"Final report not found for "
        f"run_id={run_id}. "
        f"Last error: {last_error}"
    )


# ============================================================================
# Report parser
# ============================================================================


def _parse_report(raw: str):
    """
    Parse the S3 report.

    Supports:

    - JSON object
    - JSON array
    - plain text
    - Markdown
    """

    if not raw:

        raise ValueError(
            "Report content is empty"
        )

    raw = raw.strip()

    # ------------------------------------------------------------------------
    # Try JSON
    # ------------------------------------------------------------------------

    try:

        parsed = json.loads(
            raw
        )

        if isinstance(
            parsed,
            dict
        ):
            return parsed

        if isinstance(
            parsed,
            list
        ):
            return {
                "content": json.dumps(
                    parsed,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            }

        return {
            "content": str(
                parsed
            )
        }

    except json.JSONDecodeError:

        # The S3 object is plain text/Markdown.
        return {
            "content": raw
        }


# ============================================================================
# Report content extraction
# ============================================================================


def _extract_report_text(
    report
) -> str:
    """
    Extract final readable report content.

    Supports common CTS-NPN report structures.
    """

    if isinstance(
        report,
        str
    ):
        return report

    if not isinstance(
        report,
        dict
    ):

        return json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    # ------------------------------------------------------------------------
    # Preferred report fields
    # ------------------------------------------------------------------------

    candidates = [
        "report",
        "content",
        "final_report",
        "text",
        "markdown",
        "report_text",
        "final_report_text",
        "research_report",
        "research_report_text",
        "synthesis",
        "output",
        "answer",
        "result",
    ]

    for field in candidates:

        value = report.get(
            field
        )

        if value is None:
            continue

        if isinstance(
            value,
            str
        ):

            if value.strip():
                return value

        elif isinstance(
            value,
            dict
        ):

            nested_text = _extract_report_text(
                value
            )

            if nested_text.strip():
                return nested_text

        else:

            return json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

    # ------------------------------------------------------------------------
    # If no dedicated report field exists,
    # preserve the entire JSON object.
    # ------------------------------------------------------------------------

    return json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        default=str,
    )


# ============================================================================
# Metadata extraction
# ============================================================================


def _extract_report_metadata(
    report
) -> dict:
    """
    Extract optional metadata from the final report JSON.

    This does not affect compatibility with plain Markdown/text reports.
    """

    if not isinstance(
        report,
        dict
    ):
        return {}

    metadata = {}

    possible_fields = [
        "query",
        "question",
        "topic",
        "title",
        "research_question",
        "generated_at",
        "created_at",
        "sources_count",
        "source_count",
        "agent_count",
        "agents",
    ]

    for field in possible_fields:

        value = report.get(
            field
        )

        if value is not None:

            metadata[field] = value

    return metadata


# ============================================================================
# PDF generation
# ============================================================================


def create_pdf(
    title: str,
    body: str,
    run_id: str,
    metadata: dict = None,
) -> bytes:
    """
    Create a professional multi-page research report PDF.

    Features:

    - A4 document
    - professional title page
    - metadata
    - headings
    - subheadings
    - paragraphs
    - bullets
    - numbered lists
    - blockquotes
    - Markdown tables
    - horizontal rules
    - bold text
    - italic text
    - inline code
    - clickable URLs
    - page numbering
    - headers and footers
    - automatic page flow
    - long-report support
    """

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
        title=title,
        author=REPORT_AUTHOR,
        subject=(
            "CTS-NPN Research-to-Report "
            "Analyst Research Report"
        ),
        creator="CTS-NPN",
    )

    styles = getSampleStyleSheet()

    # =========================================================================
    # Styles
    # =========================================================================

    title_style = ParagraphStyle(
        "CTSNPTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=27,
        spaceAfter=10,
    )

    subtitle_style = ParagraphStyle(
        "CTSNPSubtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        spaceAfter=5,
    )

    metadata_style = ParagraphStyle(
        "CTSNPMetadata",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        spaceAfter=3,
    )

    heading_style = ParagraphStyle(
        "CTSNPHeading",
        parent=styles["Heading2"],
        alignment=TA_LEFT,
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True,
    )

    subheading_style = ParagraphStyle(
        "CTSNPSubHeading",
        parent=styles["Heading3"],
        alignment=TA_LEFT,
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=15,
        spaceBefore=10,
        spaceAfter=6,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "CTSNPBody",
        parent=styles["BodyText"],
        alignment=TA_LEFT,
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        spaceAfter=7,
        wordWrap="CJK",
    )

    bullet_style = ParagraphStyle(
        "CTSNPBullet",
        parent=body_style,
        leftIndent=12,
        firstLineIndent=-7,
        spaceAfter=5,
    )

    numbered_style = ParagraphStyle(
        "CTSNPNumbered",
        parent=body_style,
        leftIndent=14,
        firstLineIndent=-9,
        spaceAfter=5,
    )

    quote_style = ParagraphStyle(
        "CTSNPQuote",
        parent=body_style,
        leftIndent=12,
        rightIndent=8,
        fontName="Helvetica-Oblique",
        spaceBefore=5,
        spaceAfter=8,
    )

    code_style = ParagraphStyle(
        "CTSNPCode",
        parent=body_style,
        fontName="Courier",
        fontSize=8,
        leading=11,
        leftIndent=8,
        rightIndent=8,
        spaceBefore=4,
        spaceAfter=6,
    )

    small_style = ParagraphStyle(
        "CTSNPSmall",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
    )

    # =========================================================================
    # Story
    # =========================================================================

    story = []

    # ------------------------------------------------------------------------
    # Report cover/header
    # ------------------------------------------------------------------------

    story.append(
        Spacer(
            1,
            12 * mm
        )
    )

    story.append(
        Paragraph(
            _escape_pdf_text(
                title
            ),
            title_style,
        )
    )

    story.append(
        HRFlowable(
            width="70%",
            thickness=1,
            spaceBefore=4,
            spaceAfter=10,
            hAlign="CENTER",
        )
    )

    story.append(
        Paragraph(
            _escape_pdf_text(
                "CTS-NPN Research-to-Report Analyst"
            ),
            subtitle_style,
        )
    )

    story.append(
        Paragraph(
            _escape_pdf_text(
                f"Research Run: {run_id}"
            ),
            metadata_style,
        )
    )

    story.append(
        Paragraph(
            _escape_pdf_text(
                f"Generated: {_utc_now()}"
            ),
            metadata_style,
        )
    )

    # ------------------------------------------------------------------------
    # Optional metadata
    # ------------------------------------------------------------------------

    if metadata:

        metadata_story = (
            _metadata_flowables(
                metadata,
                metadata_style
            )
        )

        if metadata_story:

            story.append(
                Spacer(
                    1,
                    4
                )
            )

            story.extend(
                metadata_story
            )

    story.append(
        Spacer(
            1,
            8
        )
    )

    story.append(
        HRFlowable(
            width="100%",
            thickness=0.5,
            spaceBefore=3,
            spaceAfter=12,
        )
    )

    # ------------------------------------------------------------------------
    # Report body
    # ------------------------------------------------------------------------

    body = str(
        body
    ).replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )

    sections = _convert_text_to_story(
        body=body,
        heading_style=heading_style,
        subheading_style=subheading_style,
        body_style=body_style,
        bullet_style=bullet_style,
        numbered_style=numbered_style,
        quote_style=quote_style,
        code_style=code_style,
        small_style=small_style,
    )

    story.extend(
        sections
    )

    # ------------------------------------------------------------------------
    # Empty protection
    # ------------------------------------------------------------------------

    if not story:

        story.append(
            Paragraph(
                "No report content available.",
                body_style,
            )
        )

    # ------------------------------------------------------------------------
    # Build PDF
    # ------------------------------------------------------------------------

    document.build(
        story,
        onFirstPage=_draw_page_header_footer,
        onLaterPages=_draw_page_header_footer,
    )

    return buffer.getvalue()


# ============================================================================
# Metadata flowables
# ============================================================================


def _metadata_flowables(
    metadata: dict,
    metadata_style,
):
    """
    Convert useful metadata into small PDF lines.
    """

    story = []

    labels = {
        "query": "Research Query",
        "question": "Research Question",
        "topic": "Topic",
        "title": "Report Title",
        "research_question": "Research Question",
        "generated_at": "Generated At",
        "created_at": "Created At",
        "sources_count": "Sources",
        "source_count": "Sources",
        "agent_count": "Agents",
    }

    for key, value in metadata.items():

        if key == "agents":

            if isinstance(
                value,
                list
            ):

                value = ", ".join(
                    str(x)
                    for x in value
                )

        if isinstance(
            value,
            (dict, list)
        ):

            value = json.dumps(
                value,
                ensure_ascii=False,
                default=str,
            )

        label = labels.get(
            key,
            key.replace(
                "_",
                " "
            ).title(),
        )

        text = (
            f"<b>{_escape_pdf_text(label)}:</b> "
            f"{_escape_pdf_text(str(value))}"
        )

        story.append(
            Paragraph(
                text,
                metadata_style,
            )
        )

    return story


# ============================================================================
# Text → ReportLab flowables
# ============================================================================


def _convert_text_to_story(
    body: str,
    heading_style,
    subheading_style,
    body_style,
    bullet_style,
    numbered_style,
    quote_style,
    code_style,
    small_style,
):
    """
    Convert Markdown-like report text into ReportLab flowables.

    Supported:

    # Heading
    ## Heading
    ### Heading

    - bullet
    * bullet

    1. numbered item

    > blockquote

    ```text
    code
    ```

    | Table | Column |
    |-------|--------|
    | A     | B      |

    ---

    Normal paragraphs
    """

    story = []

    lines = body.split(
        "\n"
    )

    paragraph_buffer = []

    in_code_block = False
    code_buffer = []

    def flush_paragraph():

        if not paragraph_buffer:
            return

        paragraph = " ".join(
            line.strip()
            for line in paragraph_buffer
            if line.strip()
        ).strip()

        paragraph_buffer.clear()

        if paragraph:

            story.append(
                Paragraph(
                    _escape_pdf_text(
                        paragraph,
                        markdown=True,
                    ),
                    body_style,
                )
            )

    def flush_code():

        nonlocal code_buffer

        if not code_buffer:
            return

        code_text = "\n".join(
            code_buffer
        )

        code_buffer = []

        escaped = _escape_pdf_text(
            code_text,
            markdown=False,
        )

        escaped = escaped.replace(
            "\n",
            "<br/>",
        )

        story.append(
            Paragraph(
                escaped,
                code_style,
            )
        )

    index = 0

    while index < len(lines):

        raw_line = lines[index]

        line = raw_line.strip()

        # ====================================================================
        # Code block
        # ====================================================================

        if line.startswith("```"):

            if in_code_block:

                flush_code()

                in_code_block = False

            else:

                flush_paragraph()

                in_code_block = True

                code_buffer = []

            index += 1
            continue

        if in_code_block:

            code_buffer.append(
                raw_line
            )

            index += 1
            continue

        # ====================================================================
        # Empty line
        # ====================================================================

        if not line:

            flush_paragraph()

            story.append(
                Spacer(
                    1,
                    3
                )
            )

            index += 1
            continue

        # ====================================================================
        # Horizontal rule
        # ====================================================================

        if _is_horizontal_rule(line):

            flush_paragraph()

            story.append(
                HRFlowable(
                    width="100%",
                    thickness=0.5,
                    spaceBefore=5,
                    spaceAfter=8,
                )
            )

            index += 1
            continue

        # ====================================================================
        # Markdown table
        # ====================================================================

        if (
            "|" in line
            and index + 1 < len(lines)
            and _is_table_separator(
                lines[index + 1].strip()
            )
        ):

            flush_paragraph()

            table_lines = []

            table_lines.append(
                line
            )

            index += 1

            # Separator
            table_lines.append(
                lines[index].strip()
            )

            index += 1

            while index < len(lines):

                candidate = lines[index].strip()

                if (
                    not candidate
                    or "|" not in candidate
                ):
                    break

                table_lines.append(
                    candidate
                )

                index += 1

            table = _create_markdown_table(
                table_lines,
                body_style,
                small_style,
            )

            if table is not None:

                story.append(
                    KeepTogether(
                        table
                    )
                )

            continue

        # ====================================================================
        # Headings
        # ====================================================================

        if line.startswith("### "):

            flush_paragraph()

            heading = line[4:].strip()

            story.append(
                Paragraph(
                    _escape_pdf_text(
                        heading
                    ),
                    subheading_style,
                )
            )

            index += 1
            continue

        if line.startswith("## "):

            flush_paragraph()

            heading = line[3:].strip()

            story.append(
                Paragraph(
                    _escape_pdf_text(
                        heading
                    ),
                    heading_style,
                )
            )

            index += 1
            continue

        if line.startswith("# "):

            flush_paragraph()

            heading = line[2:].strip()

            story.append(
                Paragraph(
                    _escape_pdf_text(
                        heading
                    ),
                    heading_style,
                )
            )

            index += 1
            continue

        # ====================================================================
        # Blockquote
        # ====================================================================

        if line.startswith(">"):

            flush_paragraph()

            quote = line[1:].strip()

            story.append(
                Paragraph(
                    _escape_pdf_text(
                        quote,
                        markdown=True,
                    ),
                    quote_style,
                )
            )

            index += 1
            continue

        # ====================================================================
        # Bullet list
        # ====================================================================

        if line.startswith("- "):

            flush_paragraph()

            bullet = line[2:].strip()

            story.append(
                Paragraph(
                    f"&#8226;&nbsp; "
                    f"{_escape_pdf_text(bullet, markdown=True)}",
                    bullet_style,
                )
            )

            index += 1
            continue

        if line.startswith("* "):

            flush_paragraph()

            bullet = line[2:].strip()

            story.append(
                Paragraph(
                    f"&#8226;&nbsp; "
                    f"{_escape_pdf_text(bullet, markdown=True)}",
                    bullet_style,
                )
            )

            index += 1
            continue

        if line.startswith("+ "):

            flush_paragraph()

            bullet = line[2:].strip()

            story.append(
                Paragraph(
                    f"&#8226;&nbsp; "
                    f"{_escape_pdf_text(bullet, markdown=True)}",
                    bullet_style,
                )
            )

            index += 1
            continue

        # ====================================================================
        # Numbered list
        # ====================================================================

        if _is_numbered_list_item(line):

            flush_paragraph()

            story.append(
                Paragraph(
                    _escape_pdf_text(
                        line,
                        markdown=True,
                    ),
                    numbered_style,
                )
            )

            index += 1
            continue

        # ====================================================================
        # Normal text
        # ====================================================================

        paragraph_buffer.append(
            line
        )

        index += 1

    # ========================================================================
    # Flush remaining content
    # ========================================================================

    if in_code_block:
        flush_code()

    flush_paragraph()

    if not story:

        story.append(
            Paragraph(
                "No report content available.",
                body_style,
            )
        )

    return story


# ============================================================================
# Markdown table support
# ============================================================================


def _is_table_separator(
    line: str
) -> bool:
    """
    Detect Markdown table separator:

    |---|---|
    |:---|---:|
    """

    if "|" not in line:
        return False

    cells = _split_table_row(
        line
    )

    if not cells:
        return False

    for cell in cells:

        cleaned = cell.strip()

        if not cleaned:
            return False

        cleaned = cleaned.strip(
            ":"
        )

        if not cleaned:
            return False

        if not re.fullmatch(
            r"-+",
            cleaned
        ):
            return False

    return True


def _split_table_row(
    line: str
):
    """
    Split a Markdown table row while
    tolerating leading/trailing pipes.
    """

    line = line.strip()

    if line.startswith("|"):
        line = line[1:]

    if line.endswith("|"):
        line = line[:-1]

    if not line:
        return []

    return [
        cell.strip()
        for cell in line.split("|")
    ]


def _create_markdown_table(
    table_lines,
    body_style,
    small_style,
):
    """
    Create a ReportLab table from Markdown table lines.
    """

    if len(table_lines) < 2:
        return None

    header = _split_table_row(
        table_lines[0]
    )

    if not header:
        return None

    data = []

    # Header
    data.append(
        [
            Paragraph(
                _escape_pdf_text(
                    cell,
                    markdown=True,
                ),
                small_style,
            )
            for cell in header
        ]
    )

    # Rows
    for row_line in table_lines[2:]:

        row = _split_table_row(
            row_line
        )

        if not row:
            continue

        # Normalize row length.
        if len(row) < len(header):

            row.extend(
                [
                    ""
                    for _ in range(
                        len(header) - len(row)
                    )
                ]
            )

        elif len(row) > len(header):

            row = row[
                :len(header)
            ]

        data.append(
            [
                Paragraph(
                    _escape_pdf_text(
                        cell,
                        markdown=True,
                    ),
                    small_style,
                )
                for cell in row
            ]
        )

    if not data:
        return None

    # ------------------------------------------------------------------------
    # Calculate usable width.
    # ------------------------------------------------------------------------

    page_width = (
        A4[0]
        - (18 * mm)
        - (18 * mm)
    )

    column_count = len(
        header
    )

    if column_count <= 0:
        return None

    column_width = (
        page_width
        / column_count
    )

    table = Table(
        data,
        colWidths=[
            column_width
            for _ in range(
                column_count
            )
        ],
        repeatRows=1,
        hAlign="LEFT",
    )

    table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor(
                        "#E8EEF5"
                    ),
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor(
                        "#172033"
                    ),
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold",
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.4,
                    colors.HexColor(
                        "#CBD5E1"
                    ),
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [
                        colors.white,
                        colors.HexColor(
                            "#F8FAFC"
                        ),
                    ],
                ),
            ]
        )
    )

    return table


# ============================================================================
# List helpers
# ============================================================================


def _is_numbered_list_item(
    line: str
) -> bool:
    """
    Detect simple numbered list items:

    1. Example
    2. Example
    10. Example
    """

    if not line:
        return False

    match = re.match(
        r"^\d+\.\s+",
        line,
    )

    return match is not None


def _is_horizontal_rule(
    line: str
) -> bool:
    """
    Detect Markdown horizontal rules.
    """

    cleaned = line.replace(
        " ",
        ""
    )

    return (
        cleaned == "---"
        or cleaned == "***"
        or cleaned == "___"
    )


# ============================================================================
# PDF text escaping and Markdown inline formatting
# ============================================================================


def _escape_pdf_text(
    value: str,
    markdown: bool = True,
) -> str:
    """
    Escape text for ReportLab Paragraph markup.

    Handles:

    - XML / HTML-sensitive characters
    - Markdown bold
    - Markdown italic
    - inline code
    - clickable URLs
    """

    if value is None:
        return ""

    value = str(
        value
    )

    # ------------------------------------------------------------------------
    # Escape XML first.
    # ------------------------------------------------------------------------

    value = xml_escape(
        value
    )

    if not markdown:
        return value

    # ------------------------------------------------------------------------
    # Inline code.
    #
    # Example:
    #
    # `run_id`
    # ------------------------------------------------------------------------

    value = _replace_inline_code(
        value
    )

    # ------------------------------------------------------------------------
    # Bold.
    #
    # **text**
    # ------------------------------------------------------------------------

    value = _replace_markdown_bold(
        value
    )

    # ------------------------------------------------------------------------
    # Italic.
    #
    # *text*
    # ------------------------------------------------------------------------

    value = _replace_markdown_italic(
        value
    )

    # ------------------------------------------------------------------------
    # Markdown links.
    #
    # [OpenAI](https://openai.com)
    # ------------------------------------------------------------------------

    value = _replace_markdown_links(
        value
    )

    # ------------------------------------------------------------------------
    # Bare URLs.
    # ------------------------------------------------------------------------

    value = _replace_bare_urls(
        value
    )

    return value


def _replace_inline_code(
    value: str
) -> str:
    """
    Convert `code` to ReportLab monospace.
    """

    pattern = re.compile(
        r"`([^`]+)`"
    )

    return pattern.sub(
        lambda match:
        f"<font name='Courier'>"
        f"{match.group(1)}"
        f"</font>",
        value,
    )


def _replace_markdown_bold(
    value: str
) -> str:
    """
    Convert **text** into ReportLab bold.
    """

    pattern = re.compile(
        r"\*\*(.+?)\*\*"
    )

    return pattern.sub(
        lambda match:
        f"<b>{match.group(1)}</b>",
        value,
    )


def _replace_markdown_italic(
    value: str
) -> str:
    """
    Convert simple *text* into ReportLab italic.

    Does not process text that is already
    inside ReportLab tags.
    """

    pattern = re.compile(
        r"(?<!\*)\*([^*]+?)\*(?!\*)"
    )

    return pattern.sub(
        lambda match:
        f"<i>{match.group(1)}</i>",
        value,
    )


def _replace_markdown_links(
    value: str
) -> str:
    """
    Convert:

    [Example](https://example.com)

    into a clickable ReportLab link.
    """

    pattern = re.compile(
        r"\[([^\]]+)\]"
        r"\((https?://[^)\s]+)\)"
    )

    def replacement(match):

        label = match.group(
            1
        )

        url = match.group(
            2
        )

        return (
            f'<link href="{url}" '
            f'color="#2563EB">'
            f"{label}"
            f"</link>"
        )

    return pattern.sub(
        replacement,
        value,
    )


def _replace_bare_urls(
    value: str
) -> str:
    """
    Convert bare http/https URLs into
    clickable ReportLab links.

    Existing <link> tags are avoided.
    """

    pattern = re.compile(
        r"(?<![\"=>])"
        r"(https?://[^\s<]+)"
    )

    def replacement(match):

        url = match.group(
            1
        )

        trailing = ""

        while url and url[-1] in ".,;:)]":

            trailing = (
                url[-1]
                + trailing
            )

            url = url[:-1]

        if not url:
            return match.group(
                1
            )

        return (
            f'<link href="{url}" '
            f'color="#2563EB">'
            f"{url}"
            f"</link>"
            f"{trailing}"
        )

    return pattern.sub(
        replacement,
        value,
    )


# ============================================================================
# Date/time helper
# ============================================================================


def _utc_now() -> str:
    """
    Return current UTC timestamp in ISO-8601 format.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()
    

# ============================================================================
# Page header / footer
# ============================================================================


def _draw_page_header_footer(
    canvas,
    document,
):
    """
    Draw professional page header and footer.

    Header:
        CTS-NPN Research Intelligence

    Footer:
        CTS-NPN Research-to-Report Analyst
        Page X
    """

    canvas.saveState()

    width, height = A4

    # ------------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------------

    canvas.setFont(
        "Helvetica-Bold",
        7,
    )

    canvas.drawString(
        18 * mm,
        height - 12 * mm,
        "CTS-NPN Research Intelligence",
    )

    canvas.setFont(
        "Helvetica",
        7,
    )

    canvas.drawRightString(
        width - 18 * mm,
        height - 12 * mm,
        "Research-to-Report Analyst",
    )

    # ------------------------------------------------------------------------
    # Header line
    # ------------------------------------------------------------------------

    canvas.setStrokeColor(
        colors.HexColor(
            "#CBD5E1"
        )
    )

    canvas.setLineWidth(
        0.4
    )

    canvas.line(
        18 * mm,
        height - 14 * mm,
        width - 18 * mm,
        height - 14 * mm,
    )

    # ------------------------------------------------------------------------
    # Footer line
    # ------------------------------------------------------------------------

    canvas.line(
        18 * mm,
        14 * mm,
        width - 18 * mm,
        14 * mm,
    )

    # ------------------------------------------------------------------------
    # Footer left
    # ------------------------------------------------------------------------

    canvas.setFont(
        "Helvetica",
        7,
    )

    canvas.setFillColor(
        colors.HexColor(
            "#475569"
        )
    )

    canvas.drawString(
        18 * mm,
        9 * mm,
        "CTS-NPN Research-to-Report Analyst",
    )

    # ------------------------------------------------------------------------
    # Footer right
    # ------------------------------------------------------------------------

    canvas.drawRightString(
        width - 18 * mm,
        9 * mm,
        f"Page {document.page}",
    )

    canvas.restoreState()