# Architecture

API Gateway -> API Lambda -> Step Functions -> Planner -> parallel Research/CMS -> Evidence -> Bedrock Synthesis -> Bedrock Critic -> S3/DynamoDB.

CMS data path: EventBridge schedule -> CMS Sync Lambda -> CMS Provider Data Catalog API -> S3 raw/curated. The CMS agent also reads curated demo/simulated records and calls CMS/CDC public APIs for live context.

External research path: Research Lambda -> arXiv API + SEC public data/search surface -> evidence.

Report path: Bedrock Converse -> reports/drafts -> critic -> reports/approved + reports/audit.
