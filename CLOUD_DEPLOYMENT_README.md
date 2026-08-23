# CTS-NPN: Cloud-Deployed Agentic Research-to-Report System

## 📋 Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [AWS Services Used](#aws-services-used)
4. [Agent Flow](#agent-flow)
5. [System Components](#system-components)
6. [Installation](#installation)
7. [Usage](#usage)
8. [Output Format](#output-format)
9. [Monitoring](#monitoring)
10. [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

**CTS-NPN** is a cloud-native multi-agent system that automates research paper discovery, analysis, and report generation. It uses **AWS serverless services** and **LLM-powered agents** to conduct comprehensive research on healthcare topics and generate professional PDF reports.

### Key Features
- ✅ **Multi-agent orchestration** via AWS Step Functions
- ✅ **Serverless architecture** (no servers to manage)
- ✅ **Multi-source data integration** (arXiv, SEC EDGAR, CDC PLACES, CMS)
- ✅ **AI-powered synthesis** using Amazon Bedrock
- ✅ **Automated PDF generation** with professional formatting
- ✅ **Citation management** with verified sources
- ✅ **REST API** for easy integration

### Use Cases
- Healthcare research analysis
- Provider consolidation trends
- Policy impact assessment
- Clinical evidence synthesis
- Regulatory compliance reporting

---

## 🏗️ Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        REST API                              │
│                  (API Gateway + Lambda)                      │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Step Functions Orchestrator                │
│              (Manages agent execution flow)                  │
└──────┬──────────────┬──────────────┬──────────────┬──────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
│  Planner   │  │ Research   │  │    CMS     │  │ Evidence   │
│  Agent     │  │   Agent    │  │   Agent    │  │   Agent    │
└────────────┘  └────────────┘  └────────────┘  └────────────┘
       │              │              │              │
       └──────────────┼──────────────┼──────────────┘
                      ▼
            ┌──────────────────────┐
            │  Synthesis Agent     │
            │  (Generate Markdown) │
            └──────────┬───────────┘
                       ▼
            ┌──────────────────────┐
            │   Critic Agent       │
            │  (Validate Quality)  │
            └──────────┬───────────┘
                       ▼
            ┌──────────────────────┐
            │  PDF Generator       │
            │  (Create Final PDF)  │
            └──────────┬───────────┘
                       ▼
                  ┌─────────┐
                  │   S3    │
                  │ Reports │
                  └─────────┘
```

### Data Flow

```
User Request
    │
    ▼
API Gateway (HTTPS)
    │
    ▼
Step Functions State Machine
    │
    ├─→ Planner: Analyze question
    │   └─→ Research Plan (JSON)
    │
    ├─→ [Parallel Execution]
    │   ├─→ Research Agent: arXiv, SEC, CDC search
    │   │   └─→ Evidence packets (S3)
    │   │
    │   └─→ CMS Agent: Provider data query
    │       └─→ CMS records (S3)
    │
    ├─→ Evidence Agent: Normalize findings
    │   └─→ Evidence index (S3)
    │
    ├─→ Synthesis Agent: Generate report
    │   └─→ Markdown content (S3)
    │
    ├─→ Critic Agent: Validate quality
    │   └─→ Validation report (S3)
    │
    └─→ PDF Generator: Create PDF
        └─→ Final PDF + Metadata (S3)
            │
            ▼
        Download URL
        Presigned (24h expiry)
```

---

## ☁️ AWS Services Used

### 1. **API Gateway (HTTP)**
- **Purpose**: REST API endpoint for research requests
- **Method**: POST `/research` - submit research question
- **Method**: GET `/research/{run_id}` - check execution status
- **Method**: GET `/research/{run_id}/report` - retrieve PDF report
- **Authentication**: Optional (can be configured)
- **Rate Limiting**: Configurable

### 2. **Step Functions (State Machine)**
- **Purpose**: Orchestrates agent execution workflow
- **Type**: Express State Machine (for high-throughput)
- **Features**:
  - Sequential execution (Planner → Research+CMS → Evidence → Synthesis → Critic → PDF)
  - Parallel branches (Research & CMS run simultaneously)
  - Error handling with retries
  - Timeout management
  - Execution history tracking
- **Cost**: Pay per transition

### 3. **Lambda Functions (9 total)**

| Agent | Function | Timeout | Memory | Purpose |
|-------|----------|---------|--------|---------|
| **API Handler** | ApiFunction | 120s | 512 MB | REST API endpoint |
| **Planner** | PlannerFunction | 120s | 512 MB | Question analysis & planning |
| **Research** | ResearchFunction | 120s | 512 MB | arXiv, SEC, CDC search |
| **CMS** | CmsFunction | 120s | 512 MB | CMS provider data query |
| **Evidence** | EvidenceFunction | 120s | 512 MB | Evidence normalization |
| **Synthesis** | SynthesisFunction | 300s | 1024 MB | LLM-powered report writing |
| **Critic** | CriticFunction | 300s | 1024 MB | Quality validation |
| **PDF Generator** | PDFGeneratorFunction | 300s | 1024 MB | PDF creation |
| **CMS Sync** | CmsSyncFunction | 180s | 512 MB | Scheduled sync (15 min) |

**Features**:
- Python 3.12 runtime
- VPC/No VPC (configurable)
- CloudWatch Logs integration
- Bedrock API access
- S3 read/write permissions
- DynamoDB access

### 4. **DynamoDB**
- **Table**: `ResultsTable`
- **Purpose**: Store execution metadata and run state
- **Partition Key**: `run_id` (string)
- **Attributes**:
  - `status` - STARTED, RUNNING, COMPLETE, FAILED
  - `question` - Original research question
  - `created_at` - ISO-8601 timestamp
  - `execution_arn` - Step Functions execution ARN
  - `artifacts` - S3 references to generated files
- **Billing**: On-demand (no provisioning)
- **TTL**: 90 days (configurable)

### 5. **S3 Buckets (3 total)**

| Bucket | Purpose | Retention | Versioning |
|--------|---------|-----------|-----------|
| **research-bucket** | Research artifacts | 90 days | Enabled |
| **cms-bucket** | CMS data cache | 30 days | Enabled |
| **reports-bucket** | Generated PDFs | 365 days | Enabled |

**Structure**:
```
research-bucket/
├── runs/
│   └── {run_id}/
│       ├── research_results.json
│       ├── evidence_packets.json
│       ├── citation_registry.json
│       └── research_statistics.json

reports-bucket/
├── runs/
│   └── {run_id}/
│       ├── pdf/
│       │   └── output.pdf
│       └── metadata/
│           └── output.json

cms-bucket/
├── runs/
│   └── {run_id}/
│       └── cms_query_results.json
```

### 6. **Bedrock (LLM Service)**
- **Model**: `amazon.nova-micro-v1:0`
- **Purpose**: 
  - Question analysis (Planner)
  - Report synthesis (Synthesis Agent)
  - Content validation (Critic Agent)
- **API**: `bedrock:InvokeModel`
- **Usage**: Pay per input/output tokens
- **Region**: us-east-1

### 7. **CloudWatch**
- **Logs**: All Lambda logs streamed
- **Metrics**: Lambda duration, errors, throttles
- **Alarms**: Configurable for failures
- **Insights**: Log query capability

### 8. **IAM Roles & Policies**
- **9 execution roles** (one per Lambda)
- **Permissions**:
  - S3: Read/Write to buckets
  - DynamoDB: CRUD operations
  - Bedrock: InvokeModel, Converse
  - Logs: CreateLogGroup, CreateLogStream, PutLogEvents
  - Step Functions: StartExecution

---

## 🤖 Agent Flow

### 1. **API Handler** (Entry Point)
```
Input:  { "question": "What are healthcare consolidation trends?" }
Output: { "run_id": "ABC123", "status": "STARTED", "execution_arn": "..." }
```
- Validates request
- Generates unique run_id
- Stores in DynamoDB
- Starts Step Functions execution
- Returns immediately

### 2. **Planner Agent** (5-10 minutes)
```
Input:  question, previous context
Output: research_plan, key_concepts, search_strategies
```
**Process**:
1. Analyzes research question
2. Identifies key concepts
3. Determines search strategy
4. Uses Bedrock to generate plan
5. Outputs structured research plan

**Outputs to**: Step Functions context

### 3. **Research Agent** (2-4 minutes) [Parallel with CMS]
```
Input:  research_plan, key_concepts
Output: 40+ research papers, evidence packets
```
**Data Sources**:
1. **arXiv API**: Academic papers (physics, CS, etc.)
2. **SEC EDGAR**: Company filings, regulatory documents
3. **CDC PLACES**: Health data, disease metrics

**Process**:
1. Searches multiple sources in parallel
2. Extracts metadata (title, authors, URL, abstract)
3. Retrieves full-text when available
4. Chunks content into evidence passages
5. Generates citations
6. Stores in S3 (research_results.json)

**Metrics**:
- Papers discovered: ~40
- Full-text success: ~90%
- Passages extracted: ~350
- Quality score: 0.57+

### 4. **CMS Agent** (30-60 seconds) [Parallel with Research]
```
Input:  question context
Output: 75+ provider records, CMS metrics
```
**Data Source**: CMS Provider Data Catalog (Dataset: mj5m-pzi6)

**Process**:
1. Queries CMS PDC API
2. Filters by relevance (healthcare consolidation)
3. Retrieves provider utilization data
4. Normalizes metrics
5. Stores in S3 (cms_query_results.json)

**Metrics**:
- Queries executed: 3
- Records retrieved: ~75
- Datasets used: 1

### 5. **Evidence Agent** (1-2 minutes)
```
Input:  research_results + cms_results
Output: normalized_evidence_packets, evidence_index
```
**Process**:
1. Reads research and CMS data from S3
2. Normalizes evidence format
3. Organizes by topic/category
4. Assigns confidence scores
5. Generates evidence index
6. Stores in S3 (evidence_packets.json)

**Evidence Types**:
- Research findings (from papers)
- Regulatory data (from SEC)
- Clinical data (from CDC)
- Provider metrics (from CMS)

### 6. **Synthesis Agent** (2-3 minutes)
```
Input:  evidence_packets, evidence_index
Output: markdown_report, metadata
```
**Process**:
1. Reads evidence from S3
2. Organizes into narrative structure
3. Uses Bedrock (nova-micro) to generate markdown
4. Creates sections:
   - Executive Summary
   - Introduction
   - Key Findings
   - Analysis
   - Recommendations
   - Conclusion
5. Adds citations and references
6. Stores in S3 (synthesis_output.md)

**Report Quality**:
- Pages: 5-15
- Word count: 2,000-5,000
- Citations: 20-30
- Quality score: 8.5+/10

### 7. **Critic Agent** (1-2 minutes)
```
Input:  synthesis_output, evidence_index
Output: validation_report, approval_status
```
**Process**:
1. Reads synthesized report
2. Validates claims against evidence
3. Checks citation accuracy
4. Assesses writing quality
5. Uses Bedrock to generate validation report
6. Assigns approval status (APPROVED/REVISE)
7. Stores in S3 (critic_output.json)

**Validation Checks**:
- Citation verification
- Fact-checking
- Logical flow
- Completeness
- Professional tone

### 8. **PDF Generator** (30-60 seconds)
```
Input:  synthesis_output, evidence_index, critic_output
Output: final_pdf, presigned_download_url
```
**Process**:
1. Reads markdown from S3
2. Converts to reportlab story
3. Applies template styling
4. Overlays background image (resume_template.png)
5. Generates PDF (5-15 pages)
6. Uploads to S3 (reports/{run_id}/pdf/output.pdf)
7. Creates presigned URL (24-hour expiry)
8. Stores metadata in S3

**PDF Features**:
- Professional formatting
- Table of contents
- Page numbers
- Metadata
- Optimized file size
- Searchable text

---

## 🔧 System Components

### Backend Structure
```
backend/
├── agents/
│   ├── planner/handler.py
│   ├── research/handler.py
│   ├── cms/handler.py
│   ├── evidence/handler.py
│   ├── synthesis/handler.py
│   ├── critic/handler.py
│   ├── pdf_generator/handler.py
│   └── report/handler.py
├── api/
│   ├── handler.py (REST API)
│   └── cms_sync.py (Scheduled sync)
├── tools/
│   ├── arxiv/search.py
│   ├── sec/search.py
│   ├── cdc/places.py
│   └── cms/query.py
└── common/
    ├── aws.py (AWS utilities)
    ├── citations.py (Citation management)
    ├── security.py (Data validation)
    ├── config.py (Configuration)
    └── s3_artifacts.py (S3 operations)
```

### Configuration Files
- `template.yaml` - SAM infrastructure as code
- `samconfig.toml` - Deployment configuration
- `workflow/research_state_machine.json` - Step Functions definition
- `requirements.txt` - Python dependencies
- `.env` - Local environment variables (not committed)

---

## 📦 Installation

### Prerequisites
- Python 3.12+
- AWS Account with Bedrock access (us-east-1)
- AWS CLI configured
- SAM CLI installed

### Step 1: Clone Repository
```bash
git clone https://github.com/Sivaranjanimahendhiren/CTSNPN.git
cd CTSNPN
git checkout sivaranjani-branch
```

### Step 2: Create Python Environment
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # macOS/Linux
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure AWS
```bash
aws configure
# Enter your AWS credentials and region (us-east-1 recommended)
```

### Step 5: Deploy to AWS
```bash
sam build
sam deploy --guided
```

**Deployment Prompts**:
- Stack name: `cts-npn-agent`
- Region: `us-east-1`
- Parameters: Use defaults or customize
- Capabilities: Accept CAPABILITY_IAM

### Step 6: Configure Environment
```bash
# Copy example to .env and update
cp .env.example .env

# Set these variables:
export RESEARCH_BUCKET=cts-npn-research
export CMS_BUCKET=cts-npn-cms
export REPORTS_BUCKET=cts-npn-reports
export BEDROCK_MODEL_ID=amazon.nova-micro-v1:0
```

---

## 🚀 Usage

### Method 1: REST API
```bash
# Submit Research Request
curl -X POST https://{api-endpoint}/research \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are healthcare provider consolidation trends?"
  }'

# Response:
# {
#   "run_id": "ABC123XYZ",
#   "status": "STARTED",
#   "execution_arn": "arn:aws:states:..."
# }
```

### Method 2: AWS CLI
```bash
# Check Execution Status
aws stepfunctions describe-execution \
  --execution-arn "arn:aws:states:us-east-1:...:execution:...:ABC123XYZ" \
  --region us-east-1

# Get Report
aws s3 cp s3://cts-npn-reports/runs/ABC123XYZ/pdf/output.pdf ./report.pdf
```

### Method 3: Python
```python
import boto3
import json

# Initialize API Gateway
client = boto3.client('apigateway')

# Submit request
response = client.invoke(
    restApiId='your-api-id',
    resourceId='research',
    httpMethod='POST',
    body=json.dumps({
        "question": "Healthcare consolidation trends?"
    })
)

run_id = json.loads(response['body'].read())['run_id']
print(f"Research submitted with run_id: {run_id}")
```

---

## 📊 Output Format

### 1. Execution Response
```json
{
  "service": "CTS-NPN",
  "run_id": "D704F615",
  "execution_arn": "arn:aws:states:us-east-1:711387116742:execution:ResearchStateMachine-CN5aV3yzSmVB:D704F615",
  "status": "STARTED",
  "message": "Research workflow accepted and submitted to the multi-agent orchestrator."
}
```

### 2. Status Response
```json
{
  "run_id": "D704F615",
  "status": "RUNNING",
  "current_agent": "ResearchFunction",
  "progress": {
    "planner": "COMPLETE",
    "research": "RUNNING",
    "cms": "RUNNING",
    "evidence": "PENDING",
    "synthesis": "PENDING",
    "critic": "PENDING",
    "pdf_generator": "PENDING"
  },
  "execution_arn": "arn:aws:states:us-east-1:711387116742:execution:...",
  "start_time": "2026-08-23T12:00:00Z"
}
```

### 3. Report Response
```json
{
  "run_id": "D704F615",
  "status": "COMPLETE",
  "report": {
    "bucket": "cts-npn-reports",
    "key": "runs/D704F615/pdf/output.pdf",
    "s3_uri": "s3://cts-npn-reports/runs/D704F615/pdf/output.pdf",
    "size_bytes": 1245680,
    "page_count": 12,
    "content_type": "application/pdf"
  },
  "download_url": "https://cts-npn-reports.s3.amazonaws.com/runs/D704F615/pdf/output.pdf?X-Amz-Algorithm=...",
  "metadata": {
    "generation_time": "2026-08-23T12:15:30Z",
    "total_execution_time_seconds": 845,
    "research_papers_analyzed": 42,
    "cms_records_reviewed": 75,
    "citations_included": 28,
    "quality_score": 8.7
  }
}
```

### 4. S3 Artifacts

**Research Results** (`research_results.json`):
```json
{
  "papers_discovered": 42,
  "papers_with_fulltext": 38,
  "passages_extracted": 356,
  "papers": [
    {
      "title": "Healthcare Provider Consolidation...",
      "authors": "Smith et al.",
      "source": "arXiv:2301.xxxxx",
      "url": "https://arxiv.org/abs/2301.xxxxx",
      "abstract": "...",
      "publication_date": "2023-01-15",
      "passages": [...]
    }
  ]
}
```

**Evidence Packets** (`evidence_packets.json`):
```json
{
  "total_items": 45,
  "by_source": {
    "research_papers": 12,
    "cms_data": 8,
    "sec_filings": 5,
    "cdc_data": 2
  },
  "evidence": [
    {
      "id": "EV001",
      "type": "research_finding",
      "source": "arXiv",
      "content": "Healthcare consolidation increased...",
      "confidence": 0.92,
      "citations": ["Smith et al. 2023"]
    }
  ]
}
```

**Generated PDF** (12-15 pages):
- Title page with metadata
- Executive summary
- Table of contents
- Introduction
- Key findings section
- Analysis
- Recommendations
- References/Citations
- Metadata footer

---

## 📈 Monitoring

### CloudWatch Logs
```bash
# View all logs
aws logs tail /aws/lambda/cts-npn-agent --follow --region us-east-1

# View specific function
aws logs tail /aws/lambda/cts-npn-agent-ResearchFunction --follow --region us-east-1

# Search for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/cts-npn-agent \
  --filter-pattern "ERROR"
```

### DynamoDB Monitoring
```bash
# Query execution record
aws dynamodb get-item \
  --table-name cts-npn-agent-ResultsTable \
  --key '{"run_id": {"S": "D704F615"}}' \
  --region us-east-1
```

### Step Functions Monitoring
```bash
# Get execution history
aws stepfunctions get-execution-history \
  --execution-arn "arn:aws:states:us-east-1:711387116742:execution:ResearchStateMachine-CN5aV3yzSmVB:D704F615" \
  --region us-east-1
```

### Performance Metrics
- **Average execution time**: 10-15 minutes
- **Papers discovered**: 35-50
- **Full-text success rate**: >85%
- **PDF generation time**: 30-60 seconds
- **Report quality score**: 8.0-9.0/10

---

## 🔍 Troubleshooting

### Issue: "Bedrock:InvokeModel Access Denied"
**Solution**: Add IAM policy
```bash
aws iam put-role-policy \
  --role-name cts-npn-agent-SynthesisFunctionRole-XXXXX \
  --policy-name BedrockInvokePolicy \
  --policy-document file://bedrock-policy.json
```

### Issue: "S3 Bucket Already Exists"
**Solution**: Bucket names must be globally unique
- Edit `samconfig.toml`
- Change bucket names
- Redeploy

### Issue: "Step Functions Timeout"
**Solution**: Increase Lambda timeout
- Edit `template.yaml`
- Set `Timeout: 300` (was 120)
- Set `MemorySize: 2048` (was 512)
- Redeploy

### Issue: "PDF Generation Fails"
**Solution**: Check template file
```bash
# Verify template exists
ls -la report_template.pdf

# Verify S3 permissions
aws s3 ls s3://cts-npn-reports/
```

### Issue: "API Returns 404"
**Solution**: Verify API endpoint
- Check deployment succeeded
- Use correct endpoint URL
- Verify HTTPS (not HTTP)
- Check request format (POST with JSON body)

---

## 📚 API Reference

### POST /research
Submit a new research request
```
Request:
{
  "question": "What are healthcare provider consolidation trends?"
}

Response:
{
  "run_id": "ABC123",
  "status": "STARTED",
  "execution_arn": "arn:aws:states:...",
  "message": "Research workflow accepted..."
}
```

### GET /research/{run_id}
Check execution status
```
Response:
{
  "run_id": "ABC123",
  "status": "RUNNING|COMPLETE|FAILED",
  "current_agent": "ResearchFunction",
  "progress": {...},
  "start_time": "2026-08-23T12:00:00Z"
}
```

### GET /research/{run_id}/report
Retrieve generated report
```
Response:
{
  "run_id": "ABC123",
  "status": "COMPLETE",
  "report": {
    "s3_uri": "s3://...",
    "size_bytes": 1245680,
    "page_count": 12
  },
  "download_url": "https://...",
  "metadata": {...}
}
```

---

## 🚀 Best Practices

1. **Request Formatting**
   - Use clear, specific questions
   - Include relevant context
   - Avoid ambiguous terminology

2. **Error Handling**
   - Implement retry logic (exponential backoff)
   - Check CloudWatch logs
   - Verify IAM permissions

3. **Cost Optimization**
   - Monitor Lambda durations
   - Use on-demand DynamoDB
   - Implement S3 lifecycle policies
   - Clean up old reports

4. **Security**
   - Restrict API access with API keys
   - Use VPC endpoints for private access
   - Encrypt S3 buckets
   - Rotate Bedrock credentials

---

## 📞 Support

For issues:
1. Check CloudWatch logs
2. Review TEST_EXECUTION_CHECKLIST.md
3. Consult TESTING.md for detailed procedures
4. File an issue with logs and reproduction steps

---

## 📄 License

This project is part of the CTS-NPN research initiative.

---

**Version**: 1.0  
**Last Updated**: August 23, 2026  
**Status**: Production Ready
