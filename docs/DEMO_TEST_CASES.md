# CTS-NPN demo test cases

## TC-01 — Low-acuity repeated ED pattern
Input: synthetic member SYN001. Expected: candidate navigation pattern because repeated ED use exists with no documented primary-care/urgent-care/telehealth utilization and low acuity signal. Output must be framed as a navigation opportunity, not a diagnosis.

## TC-02 — Genuine emergency safety case
Input: synthetic member SYN008, chest-pain/high-acuity signal. Expected: NOT flagged by the deterministic demo heuristic. The report must explicitly preserve emergency access.

## TC-03 — Real CMS provider hook
Run the CMS sync Lambda. Expected: current CMS Provider Data Catalog API response is stored under `raw/provider-pdc/<timestamp>.json` and `curated/provider-pdc/latest.json`.

## TC-04 — Research run
POST `/research` with a research question. Expected: run ID returned, Step Functions execution starts, research + CMS branches run, evidence lands in research S3, draft/audit/approved outputs land in reports S3.

## TC-05 — Critic rejection
Temporarily inject an unsafe phrase into a draft in a local unit test. Expected: critic rejects it. Production critic also contains a deterministic emergency-language gate.

## TC-06 — Traceability
Every report should contain a References section and evidence JSON should contain source URLs/types. The demo should never invent a citation.

## Demo command
`python demo/run_demo.py`

## Important data note
The local demo data is synthetic and contains no real patient information. CMS synthetic claims are suitable for software testing but are not valid for drawing conclusions about real Medicare beneficiaries. CMS explicitly describes its synthetic claims as realistic-but-not-real and warns against inferential use.
