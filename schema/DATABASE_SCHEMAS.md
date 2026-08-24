# CarePath AI — Complete Database Schema Reference

> **DBMS:** PostgreSQL 18 &nbsp;|&nbsp; **Database:** `carepath` &nbsp;|&nbsp; **Tables:** 41 &nbsp;|&nbsp; **Columns:** 415 &nbsp;|&nbsp; **FK Constraints:** 42  
> _Generated from live database. Last updated: 2026-08-24._

---

## Table of Contents

**Domain 1 — Identity & Auth**
- [users](#1-users)
- [patients](#2-patients)
- [hospital_staff](#3-hospital_staff)
- [payer_organizations](#4-payer_organizations)
- [cms_users](#5-cms_users)

**Domain 2 — Patient Health Records**
- [patient_data_records](#6-patient_data_records)
- [patient_conditions](#7-patient_conditions)
- [patient_medications](#8-patient_medications)
- [patient_allergies](#9-patient_allergies)
- [patient_preferences](#10-patient_preferences)
- [emergency_contacts](#11-emergency_contacts)
- [patient_activity_log](#12-patient_activity_log)

**Domain 3 — Clinical Assessment Pipeline**
- [assessments](#13-assessments)
- [assessment_symptoms](#14-assessment_symptoms)
- [assessment_safety_questions](#15-assessment_safety_questions)
- [assessment_medical_context](#16-assessment_medical_context)
- [care_recommendations](#17-care_recommendations)
- [emergency_requests](#18-emergency_requests)

**Domain 4 — Care Plans**
- [care_plans](#19-care_plans)
- [care_plan_actions](#20-care_plan_actions)
- [care_plan_providers](#21-care_plan_providers)
- [daily_goals](#22-daily_goals)
- [safety_protocols](#23-safety_protocols)

**Domain 5 — Providers & Facilities**
- [providers](#24-providers)
- [hospitals](#25-hospitals)

**Domain 6 — Encounters, Labs & Files**
- [healthcare_encounters](#26-healthcare_encounters)
- [lab_results](#27-lab_results)
- [medical_files](#28-medical_files)
- [file_ai_summaries](#29-file_ai_summaries)
- [claims](#30-claims)
- [patient_procedures](#31-patient_procedures)

**Domain 7 — Hospital Analytics** _(read-only)_
- [hos_ed_trends](#32-hos_ed_trends)
- [hos_request_volume](#33-hos_request_volume)
- [hos_avoidable_diagnoses](#34-hos_avoidable_diagnoses)
- [hos_care_actions](#35-hos_care_actions)
- [hos_care_requests](#36-hos_care_requests)

**Domain 8 — CMS Analytics** _(read-only)_
- [cms_metric_trends](#37-cms_metric_trends)
- [cms_engagement_trends](#38-cms_engagement_trends)
- [cms_member_risks](#39-cms_member_risks)
- [cms_provider_analytics](#40-cms_provider_analytics)
- [cms_visit_distributions](#41-cms_visit_distributions)

**References**
- [Foreign Key Constraints (42)](#foreign-key-constraints)
- [Schema Summary](#schema-summary)

---

## DOMAIN 1 — IDENTITY & AUTH

---

### 1. `users`

> Root identity table. Every login — patient, hospital staff, CMS analyst, or admin — is authenticated through this table. The `role` field determines which portal the user sees after login.

| # | Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | | Auto-generated UUID |
| 2 | `email` | VARCHAR | NOT NULL | UNIQUE | | Login credential |
| 3 | `password_hash` | VARCHAR | NOT NULL | | | bcrypt hash — never stored plain |
| 4 | `role` | VARCHAR | NOT NULL | | | `PATIENT` · `HOSPITAL_STAFF` · `CMS_ANALYST` · `ADMIN` |
| 5 | `is_active` | BOOLEAN | NULL | | | Soft enable/disable account |
| 6 | `created_at` | TIMESTAMP | NULL | | | |
| 7 | `updated_at` | TIMESTAMP | NULL | | | |

---

### 2. `patients`

> Patient health profile. Links to `users` via `user_id` to give a patient portal login. Can exist without a user account (imported-only records).

| # | Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | | |
| 2 | `patient_id` | VARCHAR | NOT NULL | UNIQUE | | Human-readable ID e.g. `"204"` |
| 3 | `user_id` | UUID | NULL | FK → users.id | | NULL if no portal login |
| 4 | `name` | VARCHAR | NOT NULL | | | Full name |
| 5 | `date_of_birth` | DATE | NULL | | | |
| 6 | `age` | INTEGER | NOT NULL | | | Denormalized for fast queries |
| 7 | `gender` | VARCHAR | NOT NULL | | | `Male` · `Female` |
| 8 | `blood_group` | VARCHAR | NULL | | | e.g. `A+`, `O-`, `AB+` |
| 9 | `status` | VARCHAR | NOT NULL | | | `Active` · `Inactive` |
| 10 | `phone` | VARCHAR | NULL | | | |
| 11 | `email` | VARCHAR | NULL | | | Patient contact email |
| 12 | `address` | TEXT | NULL | | | |
| 13 | `profile_picture_url` | VARCHAR | NULL | | | Path to uploaded avatar |
| 14 | `created_at` | TIMESTAMP | NULL | | | |
| 15 | `updated_at` | TIMESTAMP | NULL | | | |

---

### 3. `hospital_staff`

> Links a `users` account to a specific hospital with a named role and department.

| # | Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | | |
| 2 | `user_id` | UUID | NOT NULL | FK → users.id | | |
| 3 | `hospital_id` | UUID | NOT NULL | FK → hospitals.id | | |
| 4 | `staff_role` | VARCHAR | NOT NULL | | | e.g. `Doctor`, `Nurse`, `Admin` |
| 5 | `department` | VARCHAR | NOT NULL | | | e.g. `Emergency`, `Cardiology` |
| 6 | `created_at` | TIMESTAMP | NULL | | | |
| 7 | `updated_at` | TIMESTAMP | NULL | | | |

---

### 4. `payer_organizations`

> Insurance and CMS payer entities that CMS analysts belong to.

| # | Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | | |
| 2 | `name` | VARCHAR | NOT NULL | | | e.g. `"Blue Cross PPO"` |
| 3 | `organization_type` | VARCHAR | NOT NULL | | | e.g. `Insurance`, `Medicare`, `Medicaid` |
| 4 | `status` | VARCHAR | NOT NULL | | | `Active` · `Inactive` |
| 5 | `created_at` | TIMESTAMP | NULL | | | |
| 6 | `updated_at` | TIMESTAMP | NULL | | | |

---

### 5. `cms_users`

> Links a `users` account to a payer organization with a CMS-specific role.

| # | Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | | |
| 2 | `user_id` | UUID | NOT NULL | FK → users.id | | |
| 3 | `payer_id` | UUID | NOT NULL | FK → payer_organizations.id | | |
| 4 | `role` | VARCHAR | NOT NULL | | | e.g. `Analyst`, `Manager`, `Director` |
| 5 | `created_at` | TIMESTAMP | NULL | | | |
| 6 | `updated_at` | TIMESTAMP | NULL | | | |

---

## DOMAIN 2 — PATIENT HEALTH RECORDS

---

### 6. `patient_data_records`

> **OMOP CDM-aligned EHR import table.** 34 columns per visit row. This is the primary clinical data source fed into the Random Forest ML triage model. Each row represents one facility visit with comorbidities, medications, and lab values at that point in time.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `patient_id` | UUID | NOT NULL | FK → patients.id | |
| 3 | `source_record_key` | VARCHAR | NOT NULL | UNIQUE | Deduplication key from CSV import |
| 4 | `source_patient_id` | INTEGER | NOT NULL | | Original CSV patient ID |
| 5 | `age` | INTEGER | NOT NULL | | Age at time of this visit |
| 6 | `gender` | VARCHAR | NOT NULL | | |
| 7 | `history_diabetes` | BOOLEAN | NULL | | OMOP comorbidity flag |
| 8 | `history_hypertension` | BOOLEAN | NULL | | OMOP comorbidity flag |
| 9 | `history_heart_disease` | BOOLEAN | NULL | | OMOP comorbidity flag |
| 10 | `history_copd` | BOOLEAN | NULL | | OMOP comorbidity flag |
| 11 | `history_asthma` | BOOLEAN | NULL | | OMOP comorbidity flag |
| 12 | `history_kidney_disease` | BOOLEAN | NULL | | OMOP comorbidity flag |
| 13 | `history_stroke_or_tia` | BOOLEAN | NULL | | OMOP comorbidity flag |
| 14 | `history_cancer` | BOOLEAN | NULL | | OMOP comorbidity flag |
| 15 | `facility_name` | VARCHAR | NOT NULL | | Facility name for this visit |
| 16 | `hospital_visit_date` | DATE | NOT NULL | | Date of this specific visit |
| 17 | `num_ed_visits_last_12m` | INTEGER | NULL | | Rolling 12-month ED visit count |
| 18 | `days_since_last_discharge` | INTEGER | NULL | | Recency of last inpatient discharge |
| 19 | `active_medication_count` | INTEGER | NULL | | Total active medications |
| 20 | `on_immunosuppressants` | BOOLEAN | NULL | | Medication class flag |
| 21 | `on_blood_thinners` | BOOLEAN | NULL | | Medication class flag |
| 22 | `on_cardiac_meds` | BOOLEAN | NULL | | Medication class flag |
| 23 | `on_insulin` | BOOLEAN | NULL | | Medication class flag |
| 24 | `on_metformin` | BOOLEAN | NULL | | Medication class flag |
| 25 | `on_albuterol_inhaler` | BOOLEAN | NULL | | Medication class flag |
| 26 | `on_opioids` | BOOLEAN | NULL | | Medication class flag |
| 27 | `last_lab_date` | DATE | NULL | | Date of most recent labs |
| 28 | `fasting_glucose` | NUMERIC | NULL | | mg/dL |
| 29 | `hba1c` | NUMERIC | NULL | | % |
| 30 | `systolic_bp` | NUMERIC | NULL | | mmHg |
| 31 | `cholesterol_ldl` | NUMERIC | NULL | | mg/dL |
| 32 | `bun` | NUMERIC | NULL | | mg/dL |
| 33 | `creatinine` | NUMERIC | NULL | | mg/dL |
| 34 | `imported_at` | TIMESTAMP | NULL | | When this record was imported |

---

### 7. `patient_conditions`

> Active and historical diagnoses per patient, traceable back to the source import record.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `patient_id` | UUID | NOT NULL | FK → patients.id | |
| 3 | `condition` | VARCHAR | NOT NULL | | Diagnosis name |
| 4 | `status` | VARCHAR | NOT NULL | | `Active` · `Resolved` · `Inactive` |
| 5 | `first_seen_date` | DATE | NULL | | |
| 6 | `last_seen_date` | DATE | NULL | | |
| 7 | `source_record_id` | UUID | NULL | FK → patient_data_records.id | Links to originating import record |
| 8 | `created_at` | TIMESTAMP | NULL | | |
| 9 | `updated_at` | TIMESTAMP | NULL | | |

---

### 8. `patient_medications`

> Medication history with optional OMOP/RxNorm code per patient.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `patient_id` | UUID | NOT NULL | FK → patients.id | |
| 3 | `medication_name` | VARCHAR | NOT NULL | | e.g. `Metformin`, `Lisinopril` |
| 4 | `medication_code` | VARCHAR | NULL | | OMOP / RxNorm concept code |
| 5 | `active` | BOOLEAN | NULL | | Currently prescribed? |
| 6 | `first_seen_date` | DATE | NULL | | |
| 7 | `last_seen_date` | DATE | NULL | | |
| 8 | `source_record_id` | UUID | NULL | FK → patient_data_records.id | |
| 9 | `created_at` | TIMESTAMP | NULL | | |
| 10 | `updated_at` | TIMESTAMP | NULL | | |

---

### 9. `patient_allergies`

> Allergen, reaction description, and severity level per patient.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `patient_id` | UUID | NOT NULL | FK → patients.id | |
| 3 | `allergen` | VARCHAR | NOT NULL | | e.g. `Penicillin`, `Peanuts`, `Latex` |
| 4 | `reaction` | VARCHAR | NULL | | e.g. `Hives`, `Shortness of breath` |
| 5 | `severity` | VARCHAR | NULL | | `Mild` · `Moderate` · `Severe` |
| 6 | `active` | BOOLEAN | NULL | | Currently active allergy? |
| 7 | `created_at` | TIMESTAMP | NULL | | |
| 8 | `updated_at` | TIMESTAMP | NULL | | |

---

### 10. `patient_preferences`

> AI consent, data sharing, and communication preferences. One row per patient (UNIQUE constraint on `patient_id`).

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `patient_id` | UUID | NOT NULL | FK → patients.id · UNIQUE | One record per patient |
| 3 | `ai_data_analysis` | BOOLEAN | NULL | | Consent for AI clinical analysis |
| 4 | `share_with_specialists` | BOOLEAN | NULL | | Consent to share data with specialists |
| 5 | `communication_preference` | VARCHAR | NULL | | `Email` · `SMS` · `Phone` |
| 6 | `created_at` | TIMESTAMP | NULL | | |
| 7 | `updated_at` | TIMESTAMP | NULL | | |

---

### 11. `emergency_contacts`

> Patient-designated emergency contacts.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `patient_id` | UUID | NOT NULL | FK → patients.id | |
| 3 | `name` | VARCHAR | NOT NULL | | |
| 4 | `relationship` | VARCHAR | NOT NULL | | e.g. `Spouse`, `Parent`, `Sibling` |
| 5 | `phone` | VARCHAR | NOT NULL | | |
| 6 | `email` | VARCHAR | NULL | | |
| 7 | `is_primary` | BOOLEAN | NULL | | Primary emergency contact flag |
| 8 | `created_at` | TIMESTAMP | NULL | | |
| 9 | `updated_at` | TIMESTAMP | NULL | | |

---

### 12. `patient_activity_log`

> Immutable audit trail of all patient-facing events. Uses a polymorphic `reference_type` + `reference_id` pattern to point to any entity.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `patient_id` | UUID | NOT NULL | FK → patients.id | |
| 3 | `activity_type` | VARCHAR | NOT NULL | | e.g. `ASSESSMENT_SUBMITTED`, `CARE_PLAN_CREATED`, `FILE_UPLOADED` |
| 4 | `reference_type` | VARCHAR | NULL | | Entity type e.g. `assessment`, `care_plan` |
| 5 | `reference_id` | UUID | NULL | | ID of the related entity (polymorphic) |
| 6 | `title` | VARCHAR | NOT NULL | | Human-readable event title |
| 7 | `description` | TEXT | NULL | | |
| 8 | `activity_date` | TIMESTAMP | NULL | | When the event occurred |
| 9 | `created_at` | TIMESTAMP | NULL | | When the log entry was written |

---

## DOMAIN 3 — CLINICAL ASSESSMENT PIPELINE

---

### 13. `assessments`

> A triage session. Created when a patient submits symptoms. The parent record for the entire assessment pipeline.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `patient_id` | UUID | NOT NULL | FK → patients.id | |
| 3 | `status` | VARCHAR | NOT NULL | | `Submitted` · `Completed` · `Cancelled` |
| 4 | `primary_symptom` | VARCHAR | NOT NULL | | Main reported symptom |
| 5 | `duration` | VARCHAR | NOT NULL | | e.g. `"3 days"`, `"1 week"` |
| 6 | `severity` | INTEGER | NOT NULL | | Scale 1–10 |
| 7 | `worsening` | VARCHAR | NOT NULL | | `Yes` · `No` · `Same` |
| 8 | `additional_notes` | TEXT | NULL | | Free-text patient notes |
| 9 | `medical_context_confirmed` | BOOLEAN | NULL | | Patient confirmed EHR context |
| 10 | `started_at` | TIMESTAMP | NULL | | Assessment session opened |
| 11 | `submitted_at` | TIMESTAMP | NULL | | Patient clicked Submit |
| 12 | `completed_at` | TIMESTAMP | NULL | | AI pipeline finished processing |
| 13 | `created_at` | TIMESTAMP | NULL | | |
| 14 | `updated_at` | TIMESTAMP | NULL | | |

---

### 14. `assessment_symptoms`

> Each individual symptom selected by the patient during an assessment. One row per symptom per assessment.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `assessment_id` | UUID | NOT NULL | FK → assessments.id | |
| 3 | `symptom` | VARCHAR | NOT NULL | | e.g. `"Chest tightness"`, `"Dizziness"` |
| 4 | `symptom_code` | VARCHAR | NULL | | OMOP concept code if mapped |
| 5 | `selected` | BOOLEAN | NULL | | Was this symptom actively selected? |
| 6 | `created_at` | TIMESTAMP | NULL | | |

---

### 15. `assessment_safety_questions`

> Boolean safety screening answers. These are the inputs to the ESI (Emergency Severity Index) safety gate that can override the ML model and force an Emergency recommendation.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `assessment_id` | UUID | NOT NULL | FK → assessments.id | |
| 3 | `question_code` | VARCHAR | NOT NULL | | e.g. `"Q_CHEST_PAIN"`, `"Q_DYSPNEA"` |
| 4 | `question_text` | TEXT | NOT NULL | | Full question text shown to patient |
| 5 | `answer` | BOOLEAN | NOT NULL | | `true` = yes, `false` = no |
| 6 | `created_at` | TIMESTAMP | NULL | | |

---

### 16. `assessment_medical_context`

> Confirmed medical history key-value pairs captured for this specific assessment session. Pulled from `patient_data_records` and confirmed by the patient before submission.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `assessment_id` | UUID | NOT NULL | FK → assessments.id | |
| 3 | `context_type` | VARCHAR | NOT NULL | | e.g. `"condition"`, `"medication"`, `"lab"` |
| 4 | `context_key` | VARCHAR | NOT NULL | | e.g. `"history_diabetes"` |
| 5 | `context_value` | TEXT | NOT NULL | | e.g. `"true"` |
| 6 | `confirmed` | BOOLEAN | NULL | | Patient confirmed this item |
| 7 | `created_at` | TIMESTAMP | NULL | | |

---

### 17. `care_recommendations`

> The triage decision produced by the AI/rules engine. Every field is non-null to ensure the patient always receives a complete, actionable recommendation. The `model_name` field traces which engine version produced this output.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `assessment_id` | UUID | NOT NULL | FK → assessments.id | |
| 3 | `recommendation_type` | VARCHAR | NOT NULL | | `Emergency` · `Urgent Care` · `Primary Care` · `Telehealth` |
| 4 | `title` | VARCHAR | NOT NULL | | Short display title |
| 5 | `timeframe` | VARCHAR | NOT NULL | | e.g. `"Immediately"`, `"Within 24 hours"`, `"Within 1–3 days"` |
| 6 | `priority_level` | VARCHAR | NOT NULL | | `Critical` · `High` · `Medium` · `Low` |
| 7 | `emergency_flag` | BOOLEAN | NULL | | If `true` → auto-creates `emergency_requests` row |
| 8 | `reason` | TEXT | NOT NULL | | Clinical reasoning text |
| 9 | `explanation` | TEXT | NOT NULL | | Patient-readable explanation |
| 10 | `safety_advisory` | TEXT | NOT NULL | | Warning signs to watch for |
| 11 | `model_name` | VARCHAR | NOT NULL | | Engine that produced this e.g. `"care-nav-rules-v1"` |
| 12 | `status` | VARCHAR | NOT NULL | | `Generated` · `Reviewed` · `Superseded` |
| 13 | `generated_at` | TIMESTAMP | NULL | | When AI produced this |
| 14 | `created_at` | TIMESTAMP | NULL | | |

---

### 18. `emergency_requests`

> Created automatically when `care_recommendations.emergency_flag = true`. Triggers the urgent care pathway.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `patient_id` | UUID | NOT NULL | FK → patients.id | |
| 3 | `assessment_id` | UUID | NOT NULL | FK → assessments.id | |
| 4 | `recommendation_id` | UUID | NULL | FK → care_recommendations.id | |
| 5 | `priority` | VARCHAR | NOT NULL | | `Critical` · `High` · `Medium` |
| 6 | `status` | VARCHAR | NOT NULL | | `Pending` · `Dispatched` · `Resolved` |
| 7 | `request_type` | VARCHAR | NOT NULL | | e.g. `"911_DISPATCH"`, `"ED_REFERRAL"` |
| 8 | `notes` | TEXT | NULL | | |
| 9 | `created_at` | TIMESTAMP | NULL | | |
| 10 | `updated_at` | TIMESTAMP | NULL | | |

---

## DOMAIN 4 — CARE PLANS

---

### 19. `care_plans`

> The active care roadmap. Ties patient + assessment + recommendation together into a trackable plan with a defined start/end date and status lifecycle.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `patient_id` | UUID | NOT NULL | FK → patients.id | |
| 3 | `assessment_id` | UUID | NOT NULL | FK → assessments.id | |
| 4 | `recommendation_id` | UUID | NOT NULL | FK → care_recommendations.id | |
| 5 | `title` | VARCHAR | NOT NULL | | e.g. `"Symptom Management Plan"` |
| 6 | `category` | VARCHAR | NOT NULL | | `Follow-up` · `Chronic` · `Acute` · `Preventive` |
| 7 | `subtitle` | VARCHAR | NULL | | Optional subheading |
| 8 | `description` | TEXT | NOT NULL | | Full plan description |
| 9 | `status` | VARCHAR | NOT NULL | | `Active` · `Completed` · `Cancelled` |
| 10 | `active` | BOOLEAN | NULL | | Quick active/inactive flag |
| 11 | `start_date` | DATE | NULL | | |
| 12 | `end_date` | DATE | NULL | | |
| 13 | `created_at` | TIMESTAMP | NULL | | |
| 14 | `updated_at` | TIMESTAMP | NULL | | |

---

### 20. `care_plan_actions`

> Step-by-step actionable tasks assigned within a care plan. Ordered by `sort_order` for display.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `care_plan_id` | UUID | NOT NULL | FK → care_plans.id | |
| 3 | `title` | VARCHAR | NOT NULL | | e.g. `"Schedule PCP Appointment"` |
| 4 | `description` | TEXT | NULL | | |
| 5 | `action_type` | VARCHAR | NOT NULL | | `Appointment` · `Medication` · `Test` · `Referral` · `Lifestyle` |
| 6 | `frequency` | VARCHAR | NULL | | e.g. `"Once"`, `"Daily"`, `"Weekly"` |
| 7 | `status` | VARCHAR | NOT NULL | | `Pending` · `In Progress` · `Completed` · `Skipped` |
| 8 | `due_date` | DATE | NULL | | Target completion date |
| 9 | `sort_order` | INTEGER | NULL | | Display order within plan |
| 10 | `completed_at` | TIMESTAMP | NULL | | When patient marked complete |
| 11 | `created_at` | TIMESTAMP | NULL | | |
| 12 | `updated_at` | TIMESTAMP | NULL | | |

---

### 21. `care_plan_providers`

> Providers linked to a care plan — either AI-recommended or manually assigned by staff.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `care_plan_id` | UUID | NOT NULL | FK → care_plans.id | |
| 3 | `provider_id` | UUID | NOT NULL | FK → providers.id | |
| 4 | `role` | VARCHAR | NOT NULL | | e.g. `"Primary"`, `"Specialist"`, `"Referral"` |
| 5 | `recommended` | BOOLEAN | NULL | | `true` = AI recommended, `false` = manually added |
| 6 | `created_at` | TIMESTAMP | NULL | | |

---

### 22. `daily_goals`

> Daily patient checkbox goals generated from a care plan. One row per goal per day.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `care_plan_id` | UUID | NOT NULL | FK → care_plans.id | |
| 3 | `goal_text` | VARCHAR | NOT NULL | | e.g. `"Log daily symptoms"`, `"Take medication"` |
| 4 | `frequency` | VARCHAR | NOT NULL | | `Daily` · `Weekly` |
| 5 | `completed` | BOOLEAN | NULL | | Patient checked this off today? |
| 6 | `goal_date` | DATE | NOT NULL | | Target date for this goal |
| 7 | `created_at` | TIMESTAMP | NULL | | |
| 8 | `updated_at` | TIMESTAMP | NULL | | |

---

### 23. `safety_protocols`

> Emergency warning triggers attached to a care plan. Defines conditions under which the patient must seek emergency care.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `care_plan_id` | UUID | NOT NULL | FK → care_plans.id | |
| 3 | `title` | VARCHAR | NOT NULL | | e.g. `"Emergency Warning Signs"` |
| 4 | `description` | TEXT | NOT NULL | | Full description of warning condition |
| 5 | `severity` | VARCHAR | NOT NULL | | `High` · `Medium` · `Low` |
| 6 | `emergency_action` | TEXT | NOT NULL | | e.g. `"Call 911 or go to nearest ED immediately"` |
| 7 | `created_at` | TIMESTAMP | NULL | | |
| 8 | `updated_at` | TIMESTAMP | NULL | | |

---

## DOMAIN 5 — PROVIDERS & FACILITIES

---

### 24. `providers`

> Care providers with geolocation coordinates for Haversine distance-based facility matching. Used by the geospatial recommendation engine to find nearest care of the recommended tier.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `name` | VARCHAR | NOT NULL | | Provider / doctor name |
| 3 | `provider_type` | VARCHAR | NOT NULL | | `ED` · `Urgent Care` · `PCP` · `Telehealth` · `Specialist` |
| 4 | `specialty` | VARCHAR | NOT NULL | | e.g. `"Cardiology"`, `"General Practice"` |
| 5 | `facility_name` | VARCHAR | NOT NULL | | Facility they are affiliated with |
| 6 | `phone` | VARCHAR | NULL | | |
| 7 | `address` | VARCHAR | NULL | | |
| 8 | `latitude` | NUMERIC | NULL | | For Haversine distance calculation |
| 9 | `longitude` | NUMERIC | NULL | | For Haversine distance calculation |
| 10 | `available` | BOOLEAN | NULL | | Currently accepting patients? |
| 11 | `status` | VARCHAR | NOT NULL | | `Active` · `Inactive` |
| 12 | `created_at` | TIMESTAMP | NULL | | |
| 13 | `updated_at` | TIMESTAMP | NULL | | |

---

### 25. `hospitals`

> Hospital and facility registry. Used by the hospital portal for staff assignments and dashboards.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `name` | VARCHAR | NOT NULL | | |
| 3 | `facility_type` | VARCHAR | NOT NULL | | `Hospital` · `Clinic` · `Urgent Care` · `ED` |
| 4 | `address` | VARCHAR | NULL | | |
| 5 | `city` | VARCHAR | NULL | | |
| 6 | `state` | VARCHAR | NULL | | |
| 7 | `status` | VARCHAR | NOT NULL | | `Active` · `Inactive` |
| 8 | `created_at` | TIMESTAMP | NULL | | |
| 9 | `updated_at` | TIMESTAMP | NULL | | |

---

## DOMAIN 6 — ENCOUNTERS, LABS & FILES

---

### 26. `healthcare_encounters`

> Full visit history per patient. Links to `patient_data_records` as the originating OMOP import record when imported from CSV.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `patient_id` | UUID | NOT NULL | FK → patients.id | |
| 3 | `provider_id` | UUID | NULL | FK → providers.id | |
| 4 | `source_record_id` | UUID | NULL | FK → patient_data_records.id | Links to OMOP import row |
| 5 | `encounter_type` | VARCHAR | NOT NULL | | `ED` · `Inpatient` · `Outpatient` · `Clinic Visit` |
| 6 | `facility_name` | VARCHAR | NOT NULL | | |
| 7 | `encounter_date` | DATE | NOT NULL | | |
| 8 | `discharge_date` | DATE | NULL | | |
| 9 | `status` | VARCHAR | NOT NULL | | `Completed` · `Active` · `Cancelled` |
| 10 | `is_emergency` | BOOLEAN | NULL | | ED visit flag |
| 11 | `ed_visits_last_12m` | INTEGER | NULL | | Rolling ED count at time of visit |
| 12 | `days_since_last_discharge` | INTEGER | NULL | | |
| 13 | `notes` | TEXT | NULL | | |
| 14 | `primary_diagnosis` | VARCHAR | NULL | | |
| 15 | `icd10_code` | VARCHAR | NULL | | ICD-10 diagnosis code |
| 16 | `created_at` | TIMESTAMP | NULL | | |
| 17 | `updated_at` | TIMESTAMP | NULL | | |

---

### 27. `lab_results`

> Clinical laboratory values per patient per date. Six standard metabolic panel values stored individually for querying.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `patient_id` | UUID | NOT NULL | FK → patients.id | |
| 3 | `source_record_id` | UUID | NULL | FK → patient_data_records.id | |
| 4 | `lab_date` | DATE | NOT NULL | | |
| 5 | `fasting_glucose` | NUMERIC | NULL | | mg/dL |
| 6 | `hba1c` | NUMERIC | NULL | | % |
| 7 | `systolic_bp` | NUMERIC | NULL | | mmHg |
| 8 | `cholesterol_ldl` | NUMERIC | NULL | | mg/dL |
| 9 | `bun` | NUMERIC | NULL | | mg/dL |
| 10 | `creatinine` | NUMERIC | NULL | | mg/dL |
| 11 | `created_at` | TIMESTAMP | NULL | | |

---

### 28. `medical_files`

> Clinical document metadata. Actual file bytes are stored on disk at `backend/uploads/`. The database stores only the path, metadata, and category.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `patient_id` | UUID | NOT NULL | FK → patients.id | |
| 3 | `provider_id` | UUID | NULL | FK → providers.id | Uploading provider |
| 4 | `name` | VARCHAR | NOT NULL | | Display name |
| 5 | `description` | TEXT | NULL | | |
| 6 | `category` | VARCHAR | NOT NULL | | `Lab Report` · `Imaging` · `Prescription` · `Discharge Summary` |
| 7 | `file_url` | VARCHAR | NULL | | Relative path on disk |
| 8 | `file_type` | VARCHAR | NOT NULL | | `PDF` · `JPEG` · `PNG` |
| 9 | `file_size` | VARCHAR | NOT NULL | | e.g. `"2 MB"` |
| 10 | `icon_type` | VARCHAR | NULL | | UI display icon hint |
| 11 | `status` | VARCHAR | NOT NULL | | `Active` · `Archived` |
| 12 | `document_date` | DATE | NULL | | Date of the document itself |
| 13 | `uploaded_at` | TIMESTAMP | NULL | | When file was uploaded |
| 14 | `updated_at` | TIMESTAMP | NULL | | |

---

### 29. `file_ai_summaries`

> AI-generated summary for each medical file. One row per file (1:1 with `medical_files`). Stores the model name for traceability.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | |
| 2 | `medical_file_id` | UUID | NOT NULL | FK → medical_files.id · UNIQUE | One summary per file |
| 3 | `overview` | TEXT | NOT NULL | | 2–3 sentence document summary |
| 4 | `key_findings` | TEXT | NOT NULL | | Bullet-point key clinical findings |
| 5 | `model_name` | VARCHAR | NOT NULL | | Which AI model generated this |
| 6 | `status` | VARCHAR | NOT NULL | | `Generated` · `Failed` · `Reviewing` |
| 7 | `generated_at` | TIMESTAMP | NULL | | |
| 8 | `updated_at` | TIMESTAMP | NULL | | |

---

### 30. `claims`

> Insurance billing claims with ICD-10 diagnosis codes, CPT procedure codes, and itemized amounts.

| # | Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | `gen_random_uuid()` | |
| 2 | `claim_id` | VARCHAR | NOT NULL | UNIQUE | | e.g. `"CLM-20240915-001"` |
| 3 | `patient_id` | UUID | NOT NULL | FK → patients.id | | |
| 4 | `encounter_id` | UUID | NULL | FK → healthcare_encounters.id | | |
| 5 | `payer_name` | VARCHAR | NULL | | | Insurance plan name |
| 6 | `claim_type` | VARCHAR | NULL | | | e.g. `"Professional"`, `"Institutional"` |
| 7 | `service_date` | DATE | NULL | | | Date of service |
| 8 | `claim_date` | DATE | NULL | | | Date claim was filed |
| 9 | `diagnosis_icd10` | VARCHAR | NULL | | | ICD-10 diagnosis code |
| 10 | `procedure_cpt` | VARCHAR | NULL | | | CPT procedure code |
| 11 | `billed_amount` | NUMERIC | NULL | | | Amount billed |
| 12 | `allowed_amount` | NUMERIC | NULL | | | Payer allowed amount |
| 13 | `paid_amount` | NUMERIC | NULL | | | Amount paid |
| 14 | `patient_responsibility` | NUMERIC | NULL | | | Patient out-of-pocket |
| 15 | `status` | VARCHAR | NOT NULL | | `'Pending'` | `Pending` · `Approved` · `Denied` · `Paid` |
| 16 | `prior_auth_required` | BOOLEAN | NULL | | `false` | |
| 17 | `coverage_type` | VARCHAR | NULL | | | e.g. `"In-Network"`, `"Out-of-Network"` |
| 18 | `created_at` | TIMESTAMP | NULL | | `now()` | |
| 19 | `updated_at` | TIMESTAMP | NULL | | `now()` | |

---

### 31. `patient_procedures`

> Clinical procedures performed during an encounter, identified by CPT code.

| # | Column | Type | Null | Key | Default | Description |
|---|---|---|---|---|---|---|
| 1 | `id` | UUID | NOT NULL | **PK** | `gen_random_uuid()` | |
| 2 | `patient_id` | UUID | NOT NULL | FK → patients.id | | |
| 3 | `encounter_id` | UUID | NULL | FK → healthcare_encounters.id | | |
| 4 | `procedure_name` | VARCHAR | NOT NULL | | | |
| 5 | `cpt_code` | VARCHAR | NULL | | | CPT procedure code |
| 6 | `procedure_date` | DATE | NULL | | | |
| 7 | `created_at` | TIMESTAMP | NULL | | `now()` | |

---

## DOMAIN 7 — HOSPITAL ANALYTICS _(read-only)_

> These tables are populated by `seed_hos_cms.py` and read by the Hospital Staff portal dashboard. The live API never writes to them. INTEGER PKs are used because these are reference data rows, not distributed transactional records.

---

### 32. `hos_ed_trends`

> Daily ED total vs avoidable visits — powers the bar chart on the hospital dashboard.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | INTEGER | NOT NULL | **PK** (auto-increment) | |
| 2 | `day` | VARCHAR | NOT NULL | | `Mon` · `Tue` · `Wed` · `Thu` · `Fri` · `Sat` · `Sun` |
| 3 | `total` | INTEGER | NOT NULL | | Total ED visits that day |
| 4 | `avoidable` | INTEGER | NOT NULL | | Avoidable ED visits (could have gone to Urgent Care / PCP) |

---

### 33. `hos_request_volume`

> Daily care request volume — powers the line chart on the hospital dashboard.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | INTEGER | NOT NULL | **PK** (auto-increment) | |
| 2 | `day` | VARCHAR | NOT NULL | | Day of week |
| 3 | `volume` | INTEGER | NOT NULL | | Total care requests submitted |

---

### 34. `hos_avoidable_diagnoses`

> ICD code breakdown of avoidable diagnoses — shows which diagnoses are most commonly brought to the ED unnecessarily.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | INTEGER | NOT NULL | **PK** (auto-increment) | |
| 2 | `code` | VARCHAR | NOT NULL | | Short ICD reference code |
| 3 | `name` | VARCHAR | NOT NULL | | Diagnosis name |
| 4 | `count` | INTEGER | NOT NULL | | Total case count |
| 5 | `percentage` | INTEGER | NOT NULL | | % avoidable |

---

### 35. `hos_care_actions`

> Hospital staff action queue — tasks requiring follow-up by hospital team members.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | VARCHAR | NOT NULL | **PK** | e.g. `"ACT-001"` |
| 2 | `patient_name` | VARCHAR | NOT NULL | | |
| 3 | `initials` | VARCHAR | NOT NULL | | For avatar display |
| 4 | `mrn` | VARCHAR | NOT NULL | | Medical record number |
| 5 | `action_required` | VARCHAR | NOT NULL | | e.g. `"Medication Reconciliation"` |
| 6 | `action_subtitle` | VARCHAR | NULL | | Additional context |
| 7 | `status` | VARCHAR | NOT NULL | | `Pending` · `In Progress` · `Completed` |
| 8 | `priority` | VARCHAR | NOT NULL | | `High` · `Medium` · `Low` |
| 9 | `assigned_to` | JSON | NULL | | Staff assignment details object |
| 10 | `created_at` | TIMESTAMP | NULL | | |
| 11 | `updated_at` | TIMESTAMP | NULL | | |

---

### 36. `hos_care_requests`

> Prior authorization request queue with AI-generated assessment data stored as JSON columns.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | VARCHAR | NOT NULL | **PK** | e.g. `"REQ-3321"` |
| 2 | `patient_id` | VARCHAR | NOT NULL | | |
| 3 | `patient_name` | VARCHAR | NOT NULL | | |
| 4 | `dob` | VARCHAR | NULL | | Date of birth display string |
| 5 | `mrn` | VARCHAR | NOT NULL | | Medical record number |
| 6 | `type` | VARCHAR | NOT NULL | | e.g. `"Cardiology Consult"`, `"Imaging - MRI"` |
| 7 | `priority` | VARCHAR | NOT NULL | | `Urgent` · `Standard` · `Low` |
| 8 | `status` | VARCHAR | NOT NULL | | `Pending` · `Approved` · `Completed` · `Urgent` |
| 9 | `requested_ago` | VARCHAR | NULL | | Human-readable time e.g. `"2 hours ago"` |
| 10 | `primary_care` | VARCHAR | NULL | | Referring primary care doctor |
| 11 | `insurance` | VARCHAR | NULL | | Insurance plan name |
| 12 | `conditions` | JSON | NULL | | Patient condition list `["Diabetes","Hypertension"]` |
| 13 | `recent_utilization` | JSON | NULL | | Utilization summary object |
| 14 | `ai_assessment` | JSON | NULL | | AI recommendation result object |
| 15 | `determination_notes` | TEXT | NULL | | Staff determination notes |
| 16 | `auth_duration_days` | INTEGER | NULL | | Authorization period in days |
| 17 | `created_at` | TIMESTAMP | NULL | | |
| 18 | `updated_at` | TIMESTAMP | NULL | | |

---

## DOMAIN 8 — CMS ANALYTICS _(read-only)_

> These tables feed the CMS Payer Analytics portal dashboard. Populated by `seed_hos_cms.py`. Not written to by the live API.

---

### 37. `cms_metric_trends`

> Weekly ED and repeat visit counts — powers the trend line chart.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | INTEGER | NOT NULL | **PK** (auto-increment) | |
| 2 | `week` | VARCHAR | NOT NULL | | e.g. `"Week 1"` |
| 3 | `ed_visits` | INTEGER | NOT NULL | | Total ED visits that week |
| 4 | `repeat_visits` | INTEGER | NOT NULL | | Repeat/return visits |

---

### 38. `cms_engagement_trends`

> Quarterly ED vs PCP visit engagement — shows whether patients are using preventive vs emergency care.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | INTEGER | NOT NULL | **PK** (auto-increment) | |
| 2 | `time` | VARCHAR | NOT NULL | | `Q1` · `Q2` · `Q3` · `Q4` · `Current` |
| 3 | `ed_visits` | INTEGER | NOT NULL | | ED visit count |
| 4 | `pcp_visits` | INTEGER | NOT NULL | | Primary care visit count |

---

### 39. `cms_member_risks`

> Risk-stratified member list for population health management. Identifies members with high ED utilization patterns.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | VARCHAR | NOT NULL | **PK** | Member ID e.g. `"PT-1024"` |
| 2 | `ed_visits` | INTEGER | NOT NULL | | |
| 3 | `pcp_visits` | INTEGER | NOT NULL | | |
| 4 | `urgent_visits` | INTEGER | NOT NULL | | |
| 5 | `hosp_visits` | INTEGER | NOT NULL | | |
| 6 | `last_discharge` | VARCHAR | NULL | | Human-readable last discharge date |
| 7 | `pattern` | VARCHAR | NOT NULL | | `Repeated ED` · `Low PCP` · `Post-Discharge` |
| 8 | `priority` | VARCHAR | NOT NULL | | `High` · `Medium` · `Low` |
| 9 | `created_at` | TIMESTAMP | NULL | | |

---

### 40. `cms_provider_analytics`

> Per-hospital performance metrics for the CMS payer view.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | INTEGER | NOT NULL | **PK** (auto-increment) | |
| 2 | `name` | VARCHAR | NOT NULL | | Hospital name |
| 3 | `code` | VARCHAR | NOT NULL | | Short code e.g. `"CG"` |
| 4 | `ed_visits` | VARCHAR | NOT NULL | | Formatted count e.g. `"4,820"` |
| 5 | `repeat_rate` | VARCHAR | NOT NULL | | e.g. `"21%"` |
| 6 | `post_discharge` | VARCHAR | NOT NULL | | Post-discharge return rate |
| 7 | `nav_rate` | VARCHAR | NOT NULL | | Care navigation success rate |
| 8 | `trend` | VARCHAR | NOT NULL | | `Up` · `Steady` · `Down` |

---

### 41. `cms_visit_distributions`

> Visit frequency histogram — how many members visit the ED N times per period.

| # | Column | Type | Null | Key | Description |
|---|---|---|---|---|---|
| 1 | `id` | INTEGER | NOT NULL | **PK** (auto-increment) | |
| 2 | `visits` | VARCHAR | NOT NULL | | Bucket label e.g. `"2"`, `"3"`, `"4"`, `"5+"` |
| 3 | `members` | INTEGER | NOT NULL | | Number of members in this bucket |
| 4 | `color` | VARCHAR | NOT NULL | | Hex color for chart rendering |

---

## Foreign Key Constraints

> 42 constraints enforcing referential integrity across the schema.

| # | Table | Column | References | Constraint Name |
|---|---|---|---|---|
| 1 | `assessment_medical_context` | `assessment_id` | `assessments.id` | assessment_medical_context_assessment_id_fkey |
| 2 | `assessment_safety_questions` | `assessment_id` | `assessments.id` | assessment_safety_questions_assessment_id_fkey |
| 3 | `assessment_symptoms` | `assessment_id` | `assessments.id` | assessment_symptoms_assessment_id_fkey |
| 4 | `assessments` | `patient_id` | `patients.id` | assessments_patient_id_fkey |
| 5 | `care_plan_actions` | `care_plan_id` | `care_plans.id` | care_plan_actions_care_plan_id_fkey |
| 6 | `care_plan_providers` | `care_plan_id` | `care_plans.id` | care_plan_providers_care_plan_id_fkey |
| 7 | `care_plan_providers` | `provider_id` | `providers.id` | care_plan_providers_provider_id_fkey |
| 8 | `care_plans` | `patient_id` | `patients.id` | care_plans_patient_id_fkey |
| 9 | `care_plans` | `assessment_id` | `assessments.id` | care_plans_assessment_id_fkey |
| 10 | `care_plans` | `recommendation_id` | `care_recommendations.id` | care_plans_recommendation_id_fkey |
| 11 | `care_recommendations` | `assessment_id` | `assessments.id` | care_recommendations_assessment_id_fkey |
| 12 | `claims` | `patient_id` | `patients.id` | claims_patient_id_fkey |
| 13 | `claims` | `encounter_id` | `healthcare_encounters.id` | claims_encounter_id_fkey |
| 14 | `cms_users` | `user_id` | `users.id` | cms_users_user_id_fkey |
| 15 | `cms_users` | `payer_id` | `payer_organizations.id` | cms_users_payer_id_fkey |
| 16 | `daily_goals` | `care_plan_id` | `care_plans.id` | daily_goals_care_plan_id_fkey |
| 17 | `emergency_contacts` | `patient_id` | `patients.id` | emergency_contacts_patient_id_fkey |
| 18 | `emergency_requests` | `patient_id` | `patients.id` | emergency_requests_patient_id_fkey |
| 19 | `emergency_requests` | `assessment_id` | `assessments.id` | emergency_requests_assessment_id_fkey |
| 20 | `emergency_requests` | `recommendation_id` | `care_recommendations.id` | emergency_requests_recommendation_id_fkey |
| 21 | `file_ai_summaries` | `medical_file_id` | `medical_files.id` | file_ai_summaries_medical_file_id_fkey |
| 22 | `healthcare_encounters` | `patient_id` | `patients.id` | healthcare_encounters_patient_id_fkey |
| 23 | `healthcare_encounters` | `provider_id` | `providers.id` | healthcare_encounters_provider_id_fkey |
| 24 | `healthcare_encounters` | `source_record_id` | `patient_data_records.id` | healthcare_encounters_source_record_id_fkey |
| 25 | `hospital_staff` | `user_id` | `users.id` | hospital_staff_user_id_fkey |
| 26 | `hospital_staff` | `hospital_id` | `hospitals.id` | hospital_staff_hospital_id_fkey |
| 27 | `lab_results` | `patient_id` | `patients.id` | lab_results_patient_id_fkey |
| 28 | `lab_results` | `source_record_id` | `patient_data_records.id` | lab_results_source_record_id_fkey |
| 29 | `medical_files` | `patient_id` | `patients.id` | medical_files_patient_id_fkey |
| 30 | `medical_files` | `provider_id` | `providers.id` | medical_files_provider_id_fkey |
| 31 | `patient_activity_log` | `patient_id` | `patients.id` | patient_activity_log_patient_id_fkey |
| 32 | `patient_allergies` | `patient_id` | `patients.id` | patient_allergies_patient_id_fkey |
| 33 | `patient_conditions` | `patient_id` | `patients.id` | patient_conditions_patient_id_fkey |
| 34 | `patient_conditions` | `source_record_id` | `patient_data_records.id` | patient_conditions_source_record_id_fkey |
| 35 | `patient_data_records` | `patient_id` | `patients.id` | patient_data_records_patient_id_fkey |
| 36 | `patient_medications` | `patient_id` | `patients.id` | patient_medications_patient_id_fkey |
| 37 | `patient_medications` | `source_record_id` | `patient_data_records.id` | patient_medications_source_record_id_fkey |
| 38 | `patient_preferences` | `patient_id` | `patients.id` | patient_preferences_patient_id_fkey |
| 39 | `patient_procedures` | `patient_id` | `patients.id` | patient_procedures_patient_id_fkey |
| 40 | `patient_procedures` | `encounter_id` | `healthcare_encounters.id` | patient_procedures_encounter_id_fkey |
| 41 | `patients` | `user_id` | `users.id` | patients_user_id_fkey |
| 42 | `safety_protocols` | `care_plan_id` | `care_plans.id` | safety_protocols_care_plan_id_fkey |

---

## Schema Summary

| Domain | Tables | Columns | FKs | Rows (live) |
|---|---|---|---|---|
| Identity & Auth | 5 | 38 | 4 | 10 |
| Patient Health Records | 7 | 85 | 9 | 31 |
| Clinical Assessment Pipeline | 6 | 58 | 10 | 4 |
| Care Plans | 5 | 52 | 7 | 8 |
| Providers & Facilities | 2 | 22 | 0 | 0 |
| Encounters, Labs & Files | 6 | 77 | 9 | 60 |
| Hospital Analytics (read-only) | 5 | 50 | 0 | 25 |
| CMS Analytics (read-only) | 5 | 33 | 0 | 21 |
| **System** | **1** | **1** | **0** | **1** |
| **TOTAL** | **42** | **416** | **42** | **160** |
