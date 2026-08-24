# CarePath AI — Entity Relationship Diagram

> **DBMS:** PostgreSQL 18 &nbsp;|&nbsp; **Database:** `carepath` &nbsp;|&nbsp; **42 Tables · 42 FK Constraints**

---

## Full Entity Relationship Map

```
╔══════════════════════════════════════════════════════════════════════════════════════╗
║                    CarePath AI — Entity Relationship Diagram                        ║
║                    PostgreSQL 18 · carepath database · 42 tables                    ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                      ║
║  ╔══════════════════════════════════════════════════════╗                            ║
║  ║           DOMAIN 1 — IDENTITY & AUTH                 ║                            ║
║  ╠══════════════════════════════════════════════════════╣                            ║
║  ║                                                      ║                            ║
║  ║  ┌─────────────────┐   ┌──────────────────────────┐ ║                            ║
║  ║  │     USERS       │   │    PAYER_ORGANIZATIONS   │ ║                            ║
║  ║  │─────────────────│   │──────────────────────────│ ║                            ║
║  ║  │ PK id (uuid)    │   │ PK id (uuid)             │ ║                            ║
║  ║  │    email        │   │    name                  │ ║                            ║
║  ║  │    password_hash│   │    organization_type     │ ║                            ║
║  ║  │    role         │   │    status                │ ║                            ║
║  ║  │    is_active    │   └────────────┬─────────────┘ ║                            ║
║  ║  └──────┬──────────┘                │ FK payer_id   ║                            ║
║  ║         │                           ▼               ║                            ║
║  ║         │  ┌────────────────────────────────┐       ║                            ║
║  ║         │  │         CMS_USERS              │       ║                            ║
║  ║         ├─►│  FK user_id  │  FK payer_id   │       ║                            ║
║  ║         │  │  role                          │       ║                            ║
║  ║         │  └────────────────────────────────┘       ║                            ║
║  ║         │                                            ║                            ║
║  ║         │  ┌──────────────────────────────────┐     ║                            ║
║  ║         │  │         HOSPITAL_STAFF           │     ║                            ║
║  ║         ├─►│  FK user_id  │  FK hospital_id  │     ║                            ║
║  ║         │  │  staff_role  │  department      │     ║                            ║
║  ║         │  └──────────────────────────────────┘     ║                            ║
║  ║         │              FK hospital_id ──────────────╬──► HOSPITALS               ║
║  ║         │                                            ║                            ║
║  ║         │  ┌───────────────────────────────────────┐║                            ║
║  ║         └─►│              PATIENTS                 │║                            ║
║  ║            │  PK id (uuid)                         │║                            ║
║  ║            │  FK user_id  (optional)                │║                            ║
║  ║            │  patient_id · name · age · gender      │║                            ║
║  ║            │  blood_group · status · phone · email  │║                            ║
║  ║            └────────────────────┬──────────────────┘║                            ║
║  ╚════════════════════════════════╪══════════════════════╝                           ║
║                                   │                                                  ║
║              FK patient_id (all domains below connect here)                         ║
║                                   │                                                  ║
╠══════════════════════════════════╪═══════════════════════════════════════════════════╣
║         DOMAIN 2 — PATIENT HEALTH RECORDS                                           ║
╠══════════════════════════════════╪═══════════════════════════════════════════════════╣
║                                   │                                                  ║
║         ┌─────────────────────────┼──────────────────────────────┐                  ║
║         │                         │                              │                  ║
║         ▼                         ▼                              ▼                  ║
║  ┌──────────────────┐  ┌───────────────────┐  ┌─────────────────────────────────┐  ║
║  │PATIENT_DATA_     │  │PATIENT_CONDITIONS │  │       PATIENT_MEDICATIONS       │  ║
║  │RECORDS (34 cols) │  │ FK patient_id     │  │  FK patient_id                  │  ║
║  │ FK patient_id    │  │ FK source_rec_id─►│  │  FK source_record_id ──────────►│  ║
║  │ 8 comorbidities  │◄─┘ condition,status  │  │  medication_name · active       │  ║
║  │ 7 med flags      │  └───────────────────┘  └─────────────────────────────────┘  ║
║  │ 6 lab values     │                                                               ║
║  │ visit metadata   │  ┌───────────────────┐  ┌─────────────────────────────────┐  ║
║  └──────┬───────────┘  │PATIENT_ALLERGIES  │  │      PATIENT_PREFERENCES        │  ║
║         │              │ FK patient_id     │  │  FK patient_id (UNIQUE)         │  ║
║         ▼              │ allergen·severity │  │  ai_data_analysis               │  ║
║  ┌──────────────┐      └───────────────────┘  │  share_with_specialists         │  ║
║  │  LAB_RESULTS │                              └─────────────────────────────────┘  ║
║  │FK patient_id │      ┌───────────────────┐  ┌─────────────────────────────────┐  ║
║  │FK source_rec │      │EMERGENCY_CONTACTS │  │      PATIENT_ACTIVITY_LOG       │  ║
║  │glucose·hba1c │      │ FK patient_id     │  │  FK patient_id                  │  ║
║  │bp·ldl·creat  │      │ name·relationship │  │  activity_type · reference_id   │  ║
║  └──────────────┘      └───────────────────┘  └─────────────────────────────────┘  ║
║                                                                                      ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║         DOMAIN 3 — CLINICAL ASSESSMENT PIPELINE                                     ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                      ║
║  patients.id ──────────────────────────────────────────────────────────────────┐    ║
║                                                                                 │    ║
║  ┌──────────────────────────────────────────────────────────────────────────┐  │    ║
║  │                           ASSESSMENTS                                    │◄─┘    ║
║  │  PK id · FK patient_id                                                   │       ║
║  │  primary_symptom · severity (1–10) · duration · worsening · status      │       ║
║  │  started_at · submitted_at · completed_at                                │       ║
║  └──────────────────────────┬───────────────────────────────────────────────┘       ║
║                              │  FK assessment_id (3 child tables)                   ║
║          ┌───────────────────┼──────────────────────────┐                           ║
║          ▼                   ▼                          ▼                           ║
║  ┌──────────────────┐ ┌─────────────────────┐ ┌────────────────────────────┐        ║
║  │ASSESSMENT_       │ │ASSESSMENT_SAFETY_   │ │ASSESSMENT_MEDICAL_CONTEXT  │        ║
║  │SYMPTOMS          │ │QUESTIONS            │ │ context_type · context_key │        ║
║  │ symptom          │ │ question_code       │ │ context_value · confirmed  │        ║
║  │ symptom_code     │ │ question_text       │ │ (EHR history key-value)    │        ║
║  │ (OMOP code)      │ │ answer (bool)       │ └────────────────────────────┘        ║
║  └──────────────────┘ │ (ESI gate inputs)   │                                       ║
║                        └─────────────────────┘                                       ║
║                              │  FK assessment_id                                     ║
║                              ▼                                                       ║
║  ┌───────────────────────────────────────────────────────────────────────────┐       ║
║  │                      CARE_RECOMMENDATIONS                                 │       ║
║  │  FK assessment_id                                                         │       ║
║  │  recommendation_type: Emergency | Urgent Care | Primary Care | Telehealth│       ║
║  │  priority_level: Critical | High | Medium | Low                           │       ║
║  │  emergency_flag ──────► if TRUE → creates EMERGENCY_REQUESTS row         │       ║
║  │  timeframe · reason · explanation · safety_advisory                       │       ║
║  │  model_name (AI traceability) · status                                    │       ║
║  └──────────────────────────────┬────────────────────────────────────────────┘       ║
║                                 │                        │                           ║
║                  emergency_flag=true                FK recommendation_id             ║
║                                 │                        │                           ║
║                                 ▼                        ▼                           ║
║                  ┌──────────────────────┐   ┌────────────────────────────────────┐  ║
║                  │  EMERGENCY_REQUESTS  │   │          CARE_PLANS                │  ║
║                  │  FK patient_id       │   │  FK patient_id                     │  ║
║                  │  FK assessment_id    │   │  FK assessment_id                  │  ║
║                  │  FK recommendation_id│   │  FK recommendation_id              │  ║
║                  │  priority · status   │   │  title · category · status · active│  ║
║                  │  request_type        │   │  start_date · end_date             │  ║
║                  └──────────────────────┘   └────────────────┬───────────────────┘  ║
║                                                               │                      ║
╠══════════════════════════════════════════════════════════════╪═══════════════════════╣
║         DOMAIN 4 — CARE PLANS                                │                      ║
╠══════════════════════════════════════════════════════════════╪═══════════════════════╣
║                                                               │ FK care_plan_id      ║
║                         ┌─────────────────────────────────────┤                     ║
║                         │                                     │                     ║
║         ┌───────────────┼──────────────┬──────────────────────┼──────────────┐     ║
║         │               │              │                      │              │     ║
║         ▼               ▼              ▼                      ▼              ▼     ║
║  ┌────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────┐  ║
║  │CARE_PLAN_  │ │CARE_PLAN_    │ │ DAILY_GOALS  │ │  SAFETY_     │ │(PROVIDERS│  ║
║  │ACTIONS     │ │PROVIDERS     │ │ goal_text    │ │  PROTOCOLS   │ │ via FK)  │  ║
║  │ title·type │ │ FK provider_id│ │ frequency    │ │  severity    │ └──────────┘  ║
║  │ status     │ │ role         │ │ completed    │ │  emergency_  │             ║
║  │ due_date   │ │ recommended  │ │ goal_date    │ │  action      │             ║
║  └────────────┘ └──────────────┘ └──────────────┘ └──────────────┘             ║
║                                                                                      ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║         DOMAIN 6 — ENCOUNTERS, LABS & FILES                                         ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                      ║
║  patients.id ──────────────────────────────────────────────────────┐                ║
║                                                                     │                ║
║  ┌──────────────────────────────────────────────────────────────┐  │                ║
║  │                  HEALTHCARE_ENCOUNTERS                       │◄─┘                ║
║  │  FK patient_id · FK provider_id · FK source_record_id       │                   ║
║  │  encounter_type · facility_name · encounter_date             │                   ║
║  │  discharge_date · status · is_emergency                      │                   ║
║  │  primary_diagnosis · icd10_code                              │                   ║
║  └──────────────────────────────┬───────────────────────────────┘                   ║
║                                  │                                                   ║
║                  ┌───────────────┴──────────────────┐                               ║
║                  ▼                                   ▼                               ║
║  ┌───────────────────────┐           ┌─────────────────────────┐                    ║
║  │   PATIENT_PROCEDURES  │           │         CLAIMS          │                    ║
║  │  FK patient_id        │           │  FK patient_id          │                    ║
║  │  FK encounter_id      │           │  FK encounter_id        │                    ║
║  │  procedure_name       │           │  claim_id · payer_name  │                    ║
║  │  cpt_code             │           │  diagnosis_icd10        │                    ║
║  └───────────────────────┘           │  billed/paid amounts    │                    ║
║                                       │  prior_auth_required    │                    ║
║                                       └─────────────────────────┘                    ║
║                                                                                      ║
║  patients.id ──────────────────────────────────┐                                    ║
║                                                 │                                    ║
║  ┌──────────────────────────────────────────┐  │                                    ║
║  │            MEDICAL_FILES                 │◄─┘                                    ║
║  │  FK patient_id · FK provider_id          │                                       ║
║  │  name · category · file_type · file_size │                                       ║
║  │  file_url (path on disk) · status        │                                       ║
║  └──────────────────────┬───────────────────┘                                       ║
║                          │ 1:1 FK medical_file_id                                   ║
║                          ▼                                                           ║
║  ┌──────────────────────────────────────────┐                                       ║
║  │           FILE_AI_SUMMARIES              │                                       ║
║  │  FK medical_file_id (UNIQUE)             │                                       ║
║  │  overview · key_findings                 │                                       ║
║  │  model_name (AI traceability)            │                                       ║
║  │  status · generated_at                   │                                       ║
║  └──────────────────────────────────────────┘                                       ║
║                                                                                      ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║         DOMAIN 7 & 8 — READ-ONLY ANALYTICS (no FK constraints)                      ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                      ║
║  HOSPITAL PORTAL DASHBOARD          CMS PAYER ANALYTICS DASHBOARD                   ║
║  ┌──────────────────────────┐       ┌──────────────────────────────┐                ║
║  │ hos_ed_trends            │       │ cms_metric_trends            │                ║
║  │  day|total|avoidable     │       │  week|ed_visits|repeat_vis   │                ║
║  ├──────────────────────────┤       ├──────────────────────────────┤                ║
║  │ hos_request_volume       │       │ cms_engagement_trends        │                ║
║  │  day|volume              │       │  time|ed_visits|pcp_visits   │                ║
║  ├──────────────────────────┤       ├──────────────────────────────┤                ║
║  │ hos_avoidable_diagnoses  │       │ cms_member_risks             │                ║
║  │  code|name|count|pct     │       │  id|pattern|priority         │                ║
║  ├──────────────────────────┤       ├──────────────────────────────┤                ║
║  │ hos_care_actions         │       │ cms_provider_analytics       │                ║
║  │  patient|action|priority │       │  name|ed_visits|nav_rate     │                ║
║  │  assigned_to (JSON)      │       ├──────────────────────────────┤                ║
║  ├──────────────────────────┤       │ cms_visit_distributions      │                ║
║  │ hos_care_requests        │       │  visits|members|color        │                ║
║  │  type|priority|insurance │       └──────────────────────────────┘                ║
║  │  conditions (JSON)       │                                                        ║
║  │  ai_assessment (JSON)    │       Populated by: seed_hos_cms.py                   ║
║  └──────────────────────────┘       Never written by live API                       ║
║                                                                                      ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
```

---

## Relationship Cardinality Table

| Parent Table | Child Table | Cardinality | FK Column in Child |
|---|---|---|---|
| `users` | `patients` | 1 : 0..1 | `patients.user_id` |
| `users` | `hospital_staff` | 1 : many | `hospital_staff.user_id` |
| `users` | `cms_users` | 1 : many | `cms_users.user_id` |
| `hospitals` | `hospital_staff` | 1 : many | `hospital_staff.hospital_id` |
| `payer_organizations` | `cms_users` | 1 : many | `cms_users.payer_id` |
| `patients` | `patient_data_records` | 1 : many | `patient_data_records.patient_id` |
| `patients` | `patient_conditions` | 1 : many | `patient_conditions.patient_id` |
| `patients` | `patient_medications` | 1 : many | `patient_medications.patient_id` |
| `patients` | `patient_allergies` | 1 : many | `patient_allergies.patient_id` |
| `patients` | `patient_preferences` | 1 : 1 | `patient_preferences.patient_id` |
| `patients` | `emergency_contacts` | 1 : many | `emergency_contacts.patient_id` |
| `patients` | `patient_activity_log` | 1 : many | `patient_activity_log.patient_id` |
| `patients` | `assessments` | 1 : many | `assessments.patient_id` |
| `patients` | `care_plans` | 1 : many | `care_plans.patient_id` |
| `patients` | `emergency_requests` | 1 : many | `emergency_requests.patient_id` |
| `patients` | `healthcare_encounters` | 1 : many | `healthcare_encounters.patient_id` |
| `patients` | `lab_results` | 1 : many | `lab_results.patient_id` |
| `patients` | `medical_files` | 1 : many | `medical_files.patient_id` |
| `patients` | `claims` | 1 : many | `claims.patient_id` |
| `patients` | `patient_procedures` | 1 : many | `patient_procedures.patient_id` |
| `patient_data_records` | `patient_conditions` | 1 : many | `patient_conditions.source_record_id` |
| `patient_data_records` | `patient_medications` | 1 : many | `patient_medications.source_record_id` |
| `patient_data_records` | `healthcare_encounters` | 1 : many | `healthcare_encounters.source_record_id` |
| `patient_data_records` | `lab_results` | 1 : many | `lab_results.source_record_id` |
| `assessments` | `assessment_symptoms` | 1 : many | `assessment_symptoms.assessment_id` |
| `assessments` | `assessment_safety_questions` | 1 : many | `assessment_safety_questions.assessment_id` |
| `assessments` | `assessment_medical_context` | 1 : many | `assessment_medical_context.assessment_id` |
| `assessments` | `care_recommendations` | 1 : 1 | `care_recommendations.assessment_id` |
| `assessments` | `care_plans` | 1 : 1 | `care_plans.assessment_id` |
| `assessments` | `emergency_requests` | 1 : 0..1 | `emergency_requests.assessment_id` |
| `care_recommendations` | `care_plans` | 1 : 1 | `care_plans.recommendation_id` |
| `care_recommendations` | `emergency_requests` | 1 : 0..1 | `emergency_requests.recommendation_id` |
| `care_plans` | `care_plan_actions` | 1 : many | `care_plan_actions.care_plan_id` |
| `care_plans` | `care_plan_providers` | 1 : many | `care_plan_providers.care_plan_id` |
| `care_plans` | `daily_goals` | 1 : many | `daily_goals.care_plan_id` |
| `care_plans` | `safety_protocols` | 1 : many | `safety_protocols.care_plan_id` |
| `providers` | `care_plan_providers` | 1 : many | `care_plan_providers.provider_id` |
| `providers` | `healthcare_encounters` | 1 : many | `healthcare_encounters.provider_id` |
| `providers` | `medical_files` | 1 : many | `medical_files.provider_id` |
| `medical_files` | `file_ai_summaries` | 1 : 1 | `file_ai_summaries.medical_file_id` |
| `healthcare_encounters` | `claims` | 1 : many | `claims.encounter_id` |
| `healthcare_encounters` | `patient_procedures` | 1 : many | `patient_procedures.encounter_id` |

---

## Assessment → Care Plan Data Flow

```
Patient submits symptoms
         │
         ▼
    assessments ────────────────────────────────────────────────────┐
         │                                                           │
         ├──► assessment_symptoms          (one row per symptom)    │
         ├──► assessment_safety_questions  (ESI safety gate inputs)  │
         └──► assessment_medical_context  (confirmed EHR context)   │
                                                                     │
         ▼  AI pipeline runs (care_navigation.py)                    │
    care_recommendations                                             │
         │  recommendation_type = "Urgent Care"                     │
         │  priority_level = "Medium"                               │
         │  model_name = "care-nav-rules-v1"                        │
         │  emergency_flag = false                                   │
         │                                                           │
         │  IF emergency_flag = true ──────────► emergency_requests  │
         │                                                           │
         ▼                                                           │
    care_plans ◄───────────────────────────────────────────────────┘
         │
         ├──► care_plan_actions    (step-by-step action items)
         ├──► care_plan_providers  (assigned doctors / facilities)
         ├──► daily_goals          (patient daily checklist)
         └──► safety_protocols     (when to go to ED)
```

---

## Primary Key Type Reference

| PK Type | Applied To | Reason |
|---|---|---|
| `UUID` (app-generated) | All 22 transactional tables | Distributed insert safety · No sequential API enumeration |
| `INTEGER` (auto-increment) | 7 read-only analytics tables | Seed-data only · No distributed insert concern |
| `VARCHAR` (human-readable) | `cms_member_risks`, `hos_care_actions`, `hos_care_requests` | Display-ready IDs e.g. `"PT-1024"`, `"REQ-3321"` |
