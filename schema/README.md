# CareNexus AI — Database Schema Documentation

> **Project:** CareNexus AI — Clinical Decision Support System  
> **DBMS:** PostgreSQL 18  
> **Database:** `carepath`  
> **Host:** `localhost:5432`  
> **Schema Version:** 1.0.0 (Alembic migration `8fe552e0c397`)

---

## Overview

CarePath AI uses a fully relational PostgreSQL schema to support four distinct user portals — Patient, Hospital Staff, CMS Analyst, and Admin — all sharing one unified database. The schema is organized into **8 functional domains** across **41 application tables**.

| Metric | Value |
|---|---|
| Total Tables | 41 (+ 1 system table) |
| Total Columns | 415 |
| Foreign Key Constraints | 42 |
| Primary Key Strategy | UUID (transactional) / INTEGER auto-increment (analytics) |
| ORM | SQLAlchemy 2.0 |
| Migration Tool | Alembic |
| Clinical Standard | OMOP CDM aligned |

---

## Files in This Folder

| File | Description |
|---|---|
| `README.md` | This file — project overview, stats, connection info, design decisions |
| `DATABASE_SCHEMAS.md` | Complete human-readable schema — every table, every column, annotated |
| `database_schemas.json` | Machine-readable JSON schema for tooling and code generation |
| `schema.sql` | Live DDL dump — exact `CREATE TABLE` statements from PostgreSQL |
| `ER_DIAGRAM.md` | ASCII entity-relationship diagram with cardinality and data flow |

---

## Domain Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CarePath AI Schema                           │
│                    41 Tables across 8 Domains                       │
├──────────────────────┬──────────────────────────────────────────────┤
│ Domain               │ Tables                                       │
├──────────────────────┼──────────────────────────────────────────────┤
│ Identity & Auth      │ users, patients, hospital_staff,             │
│                      │ payer_organizations, cms_users               │
├──────────────────────┼──────────────────────────────────────────────┤
│ Patient Health       │ patient_data_records (34 cols, OMOP),        │
│ Records              │ patient_conditions, patient_medications,      │
│                      │ patient_allergies, patient_preferences,       │
│                      │ emergency_contacts, patient_activity_log      │
├──────────────────────┼──────────────────────────────────────────────┤
│ Clinical Assessment  │ assessments, assessment_symptoms,            │
│ Pipeline             │ assessment_safety_questions,                  │
│                      │ assessment_medical_context,                   │
│                      │ care_recommendations, emergency_requests      │
├──────────────────────┼──────────────────────────────────────────────┤
│ Care Plans           │ care_plans, care_plan_actions,               │
│                      │ care_plan_providers, daily_goals,             │
│                      │ safety_protocols                              │
├──────────────────────┼──────────────────────────────────────────────┤
│ Providers &          │ providers, hospitals                         │
│ Facilities           │                                               │
├──────────────────────┼──────────────────────────────────────────────┤
│ Encounters, Labs     │ healthcare_encounters, lab_results,          │
│ & Files              │ medical_files, file_ai_summaries,             │
│                      │ claims, patient_procedures                    │
├──────────────────────┼──────────────────────────────────────────────┤
│ Hospital Analytics   │ hos_ed_trends, hos_request_volume,           │
│ (read-only)          │ hos_avoidable_diagnoses,                      │
│                      │ hos_care_actions, hos_care_requests           │
├──────────────────────┼──────────────────────────────────────────────┤
│ CMS Analytics        │ cms_metric_trends, cms_engagement_trends,    │
│ (read-only)          │ cms_member_risks, cms_provider_analytics,     │
│                      │ cms_visit_distributions                       │
└──────────────────────┴──────────────────────────────────────────────┘
```

---

## Connection Details

```env
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/carepath
```

```python
# SQLAlchemy engine (backend/app/core/database.py)
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

---

## Demo Credentials

| Role | Email | Password | Portal |
|---|---|---|---|
| Patient | `patient204@example.com` | `password123` | http://localhost:5173 |
| Hospital Staff | `hospital@example.com` | `password123` | http://localhost:5173 |
| CMS Analyst | `cms@example.com` | `password123` | http://localhost:5173 |
| Admin | `admin@example.com` | `password123` | http://localhost:5173 |

---

## Schema Design Principles

### 1. UUID Primary Keys on All Transactional Tables
All 22 transactional tables use `UUID` PKs generated at the application layer. This prevents sequential ID guessing through the API and supports safe distributed inserts without coordination.

### 2. OMOP CDM Alignment
`patient_data_records` (34 columns) follows OMOP Common Data Model conventions — 8 comorbidity boolean flags, 7 medication class flags, 6 lab value fields. This makes the dataset directly compatible with health informatics pipelines and EHR integrations.

### 3. Soft Deletes via `status` Column
Core entities (`patients`, `providers`, `hospitals`, `care_plans`) are never hard-deleted. A `status = 'Inactive'` flag preserves the full audit trail and referential integrity.

### 4. AI Traceability
Both `care_recommendations.model_name` and `file_ai_summaries.model_name` record exactly which AI engine or model version produced each output. This ensures every AI decision is attributable and auditable.

### 5. Session-per-Request Pattern
FastAPI's `Depends(get_db)` dependency opens a fresh SQLAlchemy session per HTTP request. The session commits on success and rolls back on exception, then closes — preventing cross-request state leakage.

### 6. Analytics Tables are Read-Only
The 10 `hos_*` and `cms_*` analytics tables are populated exclusively by seed scripts (`seed_hos_cms.py`). The live API never writes to them. They use `INTEGER` auto-increment PKs since there is no distributed insert concern.

### 7. JSON Columns for Variable AI Output
`hos_care_requests` stores `conditions`, `recent_utilization`, and `ai_assessment` as `JSON` columns, accommodating structured but variable AI output without forcing a rigid schema on evolving fields.

---

## How to Apply / Re-generate

### Apply migrations to a fresh database
```powershell
cd backend
python -m alembic upgrade head
```

### Seed all demo data
```powershell
cd backend
$env:PYTHONPATH = "."
python scripts/seed_database.py
python scripts/seed_hos_cms.py
```

### Re-dump SQL schema from live database
```powershell
$env:PGPASSWORD = 'password'
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" `
  -U postgres -d carepath `
  --schema-only --no-owner --no-acl `
  -f schema\schema.sql
```

### Check migration status
```powershell
cd backend
python -m alembic current
python -m alembic history
```
