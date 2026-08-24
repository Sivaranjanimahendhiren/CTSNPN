--
-- PostgreSQL database dump
--

\restrict 64386IRSgGxuGoDHhYw97Tmf9BLxawxMSjQThh1DvpW3cizuGEOR0epnwa511eg

-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: assessment_medical_context; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assessment_medical_context (
    id uuid NOT NULL,
    assessment_id uuid NOT NULL,
    context_type character varying NOT NULL,
    context_key character varying NOT NULL,
    context_value text NOT NULL,
    confirmed boolean,
    created_at timestamp without time zone
);


--
-- Name: assessment_safety_questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assessment_safety_questions (
    id uuid NOT NULL,
    assessment_id uuid NOT NULL,
    question_code character varying NOT NULL,
    question_text text NOT NULL,
    answer boolean NOT NULL,
    created_at timestamp without time zone
);


--
-- Name: assessment_symptoms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assessment_symptoms (
    id uuid NOT NULL,
    assessment_id uuid NOT NULL,
    symptom character varying NOT NULL,
    symptom_code character varying,
    selected boolean,
    created_at timestamp without time zone
);


--
-- Name: assessments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assessments (
    id uuid NOT NULL,
    patient_id uuid NOT NULL,
    status character varying NOT NULL,
    primary_symptom character varying NOT NULL,
    duration character varying NOT NULL,
    severity integer NOT NULL,
    worsening character varying NOT NULL,
    additional_notes text,
    medical_context_confirmed boolean,
    started_at timestamp without time zone,
    submitted_at timestamp without time zone,
    completed_at timestamp without time zone,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: care_plan_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.care_plan_actions (
    id uuid NOT NULL,
    care_plan_id uuid NOT NULL,
    title character varying NOT NULL,
    description text,
    action_type character varying NOT NULL,
    frequency character varying,
    status character varying NOT NULL,
    due_date date,
    sort_order integer,
    completed_at timestamp without time zone,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: care_plan_providers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.care_plan_providers (
    id uuid NOT NULL,
    care_plan_id uuid NOT NULL,
    provider_id uuid NOT NULL,
    role character varying NOT NULL,
    recommended boolean,
    created_at timestamp without time zone
);


--
-- Name: care_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.care_plans (
    id uuid NOT NULL,
    patient_id uuid NOT NULL,
    assessment_id uuid NOT NULL,
    recommendation_id uuid NOT NULL,
    title character varying NOT NULL,
    category character varying NOT NULL,
    subtitle character varying,
    description text NOT NULL,
    status character varying NOT NULL,
    active boolean,
    start_date date,
    end_date date,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: care_recommendations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.care_recommendations (
    id uuid NOT NULL,
    assessment_id uuid NOT NULL,
    recommendation_type character varying NOT NULL,
    title character varying NOT NULL,
    timeframe character varying NOT NULL,
    priority_level character varying NOT NULL,
    emergency_flag boolean,
    reason text NOT NULL,
    explanation text NOT NULL,
    safety_advisory text NOT NULL,
    model_name character varying NOT NULL,
    status character varying NOT NULL,
    generated_at timestamp without time zone,
    created_at timestamp without time zone
);


--
-- Name: claims; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.claims (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    claim_id character varying NOT NULL,
    patient_id uuid NOT NULL,
    encounter_id uuid,
    payer_name character varying,
    claim_type character varying,
    service_date date,
    claim_date date,
    diagnosis_icd10 character varying,
    procedure_cpt character varying,
    billed_amount numeric,
    allowed_amount numeric,
    paid_amount numeric,
    patient_responsibility numeric,
    status character varying DEFAULT 'Pending'::character varying NOT NULL,
    prior_auth_required boolean DEFAULT false,
    coverage_type character varying,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now()
);


--
-- Name: cms_engagement_trends; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cms_engagement_trends (
    id integer NOT NULL,
    "time" character varying NOT NULL,
    ed_visits integer NOT NULL,
    pcp_visits integer NOT NULL
);


--
-- Name: cms_engagement_trends_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cms_engagement_trends_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cms_engagement_trends_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cms_engagement_trends_id_seq OWNED BY public.cms_engagement_trends.id;


--
-- Name: cms_member_risks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cms_member_risks (
    id character varying NOT NULL,
    ed_visits integer NOT NULL,
    pcp_visits integer NOT NULL,
    urgent_visits integer NOT NULL,
    hosp_visits integer NOT NULL,
    last_discharge character varying,
    pattern character varying NOT NULL,
    priority character varying NOT NULL,
    created_at timestamp without time zone
);


--
-- Name: cms_metric_trends; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cms_metric_trends (
    id integer NOT NULL,
    week character varying NOT NULL,
    ed_visits integer NOT NULL,
    repeat_visits integer NOT NULL
);


--
-- Name: cms_metric_trends_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cms_metric_trends_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cms_metric_trends_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cms_metric_trends_id_seq OWNED BY public.cms_metric_trends.id;


--
-- Name: cms_provider_analytics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cms_provider_analytics (
    id integer NOT NULL,
    name character varying NOT NULL,
    code character varying NOT NULL,
    ed_visits character varying NOT NULL,
    repeat_rate character varying NOT NULL,
    post_discharge character varying NOT NULL,
    nav_rate character varying NOT NULL,
    trend character varying NOT NULL
);


--
-- Name: cms_provider_analytics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cms_provider_analytics_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cms_provider_analytics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cms_provider_analytics_id_seq OWNED BY public.cms_provider_analytics.id;


--
-- Name: cms_users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cms_users (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    payer_id uuid NOT NULL,
    role character varying NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: cms_visit_distributions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cms_visit_distributions (
    id integer NOT NULL,
    visits character varying NOT NULL,
    members integer NOT NULL,
    color character varying NOT NULL
);


--
-- Name: cms_visit_distributions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cms_visit_distributions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cms_visit_distributions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cms_visit_distributions_id_seq OWNED BY public.cms_visit_distributions.id;


--
-- Name: daily_goals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_goals (
    id uuid NOT NULL,
    care_plan_id uuid NOT NULL,
    goal_text character varying NOT NULL,
    frequency character varying NOT NULL,
    completed boolean,
    goal_date date NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: emergency_contacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.emergency_contacts (
    id uuid NOT NULL,
    patient_id uuid NOT NULL,
    name character varying NOT NULL,
    relationship character varying NOT NULL,
    phone character varying NOT NULL,
    email character varying,
    is_primary boolean,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: emergency_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.emergency_requests (
    id uuid NOT NULL,
    patient_id uuid NOT NULL,
    assessment_id uuid NOT NULL,
    recommendation_id uuid,
    priority character varying NOT NULL,
    status character varying NOT NULL,
    request_type character varying NOT NULL,
    notes text,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: file_ai_summaries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.file_ai_summaries (
    id uuid NOT NULL,
    medical_file_id uuid NOT NULL,
    overview text NOT NULL,
    key_findings text NOT NULL,
    model_name character varying NOT NULL,
    status character varying NOT NULL,
    generated_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: healthcare_encounters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.healthcare_encounters (
    id uuid NOT NULL,
    patient_id uuid NOT NULL,
    provider_id uuid,
    source_record_id uuid,
    encounter_type character varying NOT NULL,
    facility_name character varying NOT NULL,
    encounter_date date NOT NULL,
    status character varying NOT NULL,
    is_emergency boolean,
    ed_visits_last_12m integer,
    days_since_last_discharge integer,
    notes text,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    discharge_date date,
    primary_diagnosis character varying,
    icd10_code character varying
);


--
-- Name: hos_avoidable_diagnoses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hos_avoidable_diagnoses (
    id integer NOT NULL,
    code character varying NOT NULL,
    name character varying NOT NULL,
    count integer NOT NULL,
    percentage integer NOT NULL
);


--
-- Name: hos_avoidable_diagnoses_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.hos_avoidable_diagnoses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: hos_avoidable_diagnoses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.hos_avoidable_diagnoses_id_seq OWNED BY public.hos_avoidable_diagnoses.id;


--
-- Name: hos_care_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hos_care_actions (
    id character varying NOT NULL,
    patient_name character varying NOT NULL,
    initials character varying NOT NULL,
    mrn character varying NOT NULL,
    action_required character varying NOT NULL,
    action_subtitle character varying,
    status character varying NOT NULL,
    priority character varying NOT NULL,
    assigned_to json,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: hos_care_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hos_care_requests (
    id character varying NOT NULL,
    patient_id character varying NOT NULL,
    patient_name character varying NOT NULL,
    dob character varying,
    mrn character varying NOT NULL,
    type character varying NOT NULL,
    priority character varying NOT NULL,
    status character varying NOT NULL,
    requested_ago character varying,
    primary_care character varying,
    insurance character varying,
    conditions json,
    recent_utilization json,
    ai_assessment json,
    determination_notes text,
    auth_duration_days integer,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: hos_ed_trends; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hos_ed_trends (
    id integer NOT NULL,
    day character varying NOT NULL,
    total integer NOT NULL,
    avoidable integer NOT NULL
);


--
-- Name: hos_ed_trends_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.hos_ed_trends_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: hos_ed_trends_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.hos_ed_trends_id_seq OWNED BY public.hos_ed_trends.id;


--
-- Name: hos_request_volume; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hos_request_volume (
    id integer NOT NULL,
    day character varying NOT NULL,
    volume integer NOT NULL
);


--
-- Name: hos_request_volume_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.hos_request_volume_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: hos_request_volume_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.hos_request_volume_id_seq OWNED BY public.hos_request_volume.id;


--
-- Name: hospital_staff; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hospital_staff (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    hospital_id uuid NOT NULL,
    staff_role character varying NOT NULL,
    department character varying NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: hospitals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hospitals (
    id uuid NOT NULL,
    name character varying NOT NULL,
    facility_type character varying NOT NULL,
    address character varying,
    city character varying,
    state character varying,
    status character varying NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: lab_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lab_results (
    id uuid NOT NULL,
    patient_id uuid NOT NULL,
    source_record_id uuid,
    lab_date date NOT NULL,
    fasting_glucose numeric,
    hba1c numeric,
    systolic_bp numeric,
    cholesterol_ldl numeric,
    bun numeric,
    creatinine numeric,
    created_at timestamp without time zone
);


--
-- Name: medical_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.medical_files (
    id uuid NOT NULL,
    patient_id uuid NOT NULL,
    provider_id uuid,
    name character varying NOT NULL,
    description text,
    category character varying NOT NULL,
    file_url character varying,
    file_type character varying NOT NULL,
    file_size character varying NOT NULL,
    icon_type character varying,
    status character varying NOT NULL,
    document_date date,
    uploaded_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: patient_activity_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_activity_log (
    id uuid NOT NULL,
    patient_id uuid NOT NULL,
    activity_type character varying NOT NULL,
    reference_type character varying,
    reference_id uuid,
    title character varying NOT NULL,
    description text,
    activity_date timestamp without time zone,
    created_at timestamp without time zone
);


--
-- Name: patient_allergies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_allergies (
    id uuid NOT NULL,
    patient_id uuid NOT NULL,
    allergen character varying NOT NULL,
    reaction character varying,
    severity character varying,
    active boolean,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: patient_conditions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_conditions (
    id uuid NOT NULL,
    patient_id uuid NOT NULL,
    condition character varying NOT NULL,
    status character varying NOT NULL,
    first_seen_date date,
    last_seen_date date,
    source_record_id uuid,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: patient_data_records; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_data_records (
    id uuid NOT NULL,
    patient_id uuid NOT NULL,
    source_record_key character varying NOT NULL,
    source_patient_id integer NOT NULL,
    age integer NOT NULL,
    gender character varying NOT NULL,
    history_diabetes boolean,
    history_hypertension boolean,
    history_heart_disease boolean,
    history_copd boolean,
    history_asthma boolean,
    history_kidney_disease boolean,
    history_stroke_or_tia boolean,
    history_cancer boolean,
    facility_name character varying NOT NULL,
    hospital_visit_date date NOT NULL,
    num_ed_visits_last_12m integer,
    days_since_last_discharge integer,
    active_medication_count integer,
    on_immunosuppressants boolean,
    on_blood_thinners boolean,
    on_cardiac_meds boolean,
    on_insulin boolean,
    on_metformin boolean,
    on_albuterol_inhaler boolean,
    on_opioids boolean,
    last_lab_date date,
    fasting_glucose numeric,
    hba1c numeric,
    systolic_bp numeric,
    cholesterol_ldl numeric,
    bun numeric,
    creatinine numeric,
    imported_at timestamp without time zone
);


--
-- Name: patient_medications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_medications (
    id uuid NOT NULL,
    patient_id uuid NOT NULL,
    medication_name character varying NOT NULL,
    medication_code character varying,
    active boolean,
    first_seen_date date,
    last_seen_date date,
    source_record_id uuid,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: patient_preferences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_preferences (
    id uuid NOT NULL,
    patient_id uuid NOT NULL,
    ai_data_analysis boolean,
    share_with_specialists boolean,
    communication_preference character varying,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: patient_procedures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patient_procedures (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    patient_id uuid NOT NULL,
    encounter_id uuid,
    procedure_name character varying NOT NULL,
    cpt_code character varying,
    procedure_date date,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: patients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patients (
    id uuid NOT NULL,
    patient_id character varying NOT NULL,
    user_id uuid,
    name character varying NOT NULL,
    date_of_birth date,
    age integer NOT NULL,
    gender character varying NOT NULL,
    blood_group character varying,
    status character varying NOT NULL,
    phone character varying,
    email character varying,
    address text,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    profile_picture_url character varying
);


--
-- Name: payer_organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payer_organizations (
    id uuid NOT NULL,
    name character varying NOT NULL,
    organization_type character varying NOT NULL,
    status character varying NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: providers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.providers (
    id uuid NOT NULL,
    name character varying NOT NULL,
    provider_type character varying NOT NULL,
    specialty character varying NOT NULL,
    facility_name character varying NOT NULL,
    phone character varying,
    address character varying,
    latitude numeric,
    longitude numeric,
    available boolean,
    status character varying NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: safety_protocols; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.safety_protocols (
    id uuid NOT NULL,
    care_plan_id uuid NOT NULL,
    title character varying NOT NULL,
    description text NOT NULL,
    severity character varying NOT NULL,
    emergency_action text NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    email character varying NOT NULL,
    password_hash character varying NOT NULL,
    role character varying NOT NULL,
    is_active boolean,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: cms_engagement_trends id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_engagement_trends ALTER COLUMN id SET DEFAULT nextval('public.cms_engagement_trends_id_seq'::regclass);


--
-- Name: cms_metric_trends id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_metric_trends ALTER COLUMN id SET DEFAULT nextval('public.cms_metric_trends_id_seq'::regclass);


--
-- Name: cms_provider_analytics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_provider_analytics ALTER COLUMN id SET DEFAULT nextval('public.cms_provider_analytics_id_seq'::regclass);


--
-- Name: cms_visit_distributions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_visit_distributions ALTER COLUMN id SET DEFAULT nextval('public.cms_visit_distributions_id_seq'::regclass);


--
-- Name: hos_avoidable_diagnoses id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hos_avoidable_diagnoses ALTER COLUMN id SET DEFAULT nextval('public.hos_avoidable_diagnoses_id_seq'::regclass);


--
-- Name: hos_ed_trends id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hos_ed_trends ALTER COLUMN id SET DEFAULT nextval('public.hos_ed_trends_id_seq'::regclass);


--
-- Name: hos_request_volume id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hos_request_volume ALTER COLUMN id SET DEFAULT nextval('public.hos_request_volume_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: assessment_medical_context assessment_medical_context_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_medical_context
    ADD CONSTRAINT assessment_medical_context_pkey PRIMARY KEY (id);


--
-- Name: assessment_safety_questions assessment_safety_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_safety_questions
    ADD CONSTRAINT assessment_safety_questions_pkey PRIMARY KEY (id);


--
-- Name: assessment_symptoms assessment_symptoms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_symptoms
    ADD CONSTRAINT assessment_symptoms_pkey PRIMARY KEY (id);


--
-- Name: assessments assessments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessments
    ADD CONSTRAINT assessments_pkey PRIMARY KEY (id);


--
-- Name: care_plan_actions care_plan_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_plan_actions
    ADD CONSTRAINT care_plan_actions_pkey PRIMARY KEY (id);


--
-- Name: care_plan_providers care_plan_providers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_plan_providers
    ADD CONSTRAINT care_plan_providers_pkey PRIMARY KEY (id);


--
-- Name: care_plans care_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_plans
    ADD CONSTRAINT care_plans_pkey PRIMARY KEY (id);


--
-- Name: care_recommendations care_recommendations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_recommendations
    ADD CONSTRAINT care_recommendations_pkey PRIMARY KEY (id);


--
-- Name: claims claims_claim_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claims
    ADD CONSTRAINT claims_claim_id_key UNIQUE (claim_id);


--
-- Name: claims claims_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claims
    ADD CONSTRAINT claims_pkey PRIMARY KEY (id);


--
-- Name: cms_engagement_trends cms_engagement_trends_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_engagement_trends
    ADD CONSTRAINT cms_engagement_trends_pkey PRIMARY KEY (id);


--
-- Name: cms_engagement_trends cms_engagement_trends_time_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_engagement_trends
    ADD CONSTRAINT cms_engagement_trends_time_key UNIQUE ("time");


--
-- Name: cms_member_risks cms_member_risks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_member_risks
    ADD CONSTRAINT cms_member_risks_pkey PRIMARY KEY (id);


--
-- Name: cms_metric_trends cms_metric_trends_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_metric_trends
    ADD CONSTRAINT cms_metric_trends_pkey PRIMARY KEY (id);


--
-- Name: cms_metric_trends cms_metric_trends_week_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_metric_trends
    ADD CONSTRAINT cms_metric_trends_week_key UNIQUE (week);


--
-- Name: cms_provider_analytics cms_provider_analytics_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_provider_analytics
    ADD CONSTRAINT cms_provider_analytics_name_key UNIQUE (name);


--
-- Name: cms_provider_analytics cms_provider_analytics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_provider_analytics
    ADD CONSTRAINT cms_provider_analytics_pkey PRIMARY KEY (id);


--
-- Name: cms_users cms_users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_users
    ADD CONSTRAINT cms_users_pkey PRIMARY KEY (id);


--
-- Name: cms_visit_distributions cms_visit_distributions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_visit_distributions
    ADD CONSTRAINT cms_visit_distributions_pkey PRIMARY KEY (id);


--
-- Name: cms_visit_distributions cms_visit_distributions_visits_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_visit_distributions
    ADD CONSTRAINT cms_visit_distributions_visits_key UNIQUE (visits);


--
-- Name: daily_goals daily_goals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_goals
    ADD CONSTRAINT daily_goals_pkey PRIMARY KEY (id);


--
-- Name: emergency_contacts emergency_contacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emergency_contacts
    ADD CONSTRAINT emergency_contacts_pkey PRIMARY KEY (id);


--
-- Name: emergency_requests emergency_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emergency_requests
    ADD CONSTRAINT emergency_requests_pkey PRIMARY KEY (id);


--
-- Name: file_ai_summaries file_ai_summaries_medical_file_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_ai_summaries
    ADD CONSTRAINT file_ai_summaries_medical_file_id_key UNIQUE (medical_file_id);


--
-- Name: file_ai_summaries file_ai_summaries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_ai_summaries
    ADD CONSTRAINT file_ai_summaries_pkey PRIMARY KEY (id);


--
-- Name: healthcare_encounters healthcare_encounters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.healthcare_encounters
    ADD CONSTRAINT healthcare_encounters_pkey PRIMARY KEY (id);


--
-- Name: hos_avoidable_diagnoses hos_avoidable_diagnoses_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hos_avoidable_diagnoses
    ADD CONSTRAINT hos_avoidable_diagnoses_code_key UNIQUE (code);


--
-- Name: hos_avoidable_diagnoses hos_avoidable_diagnoses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hos_avoidable_diagnoses
    ADD CONSTRAINT hos_avoidable_diagnoses_pkey PRIMARY KEY (id);


--
-- Name: hos_care_actions hos_care_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hos_care_actions
    ADD CONSTRAINT hos_care_actions_pkey PRIMARY KEY (id);


--
-- Name: hos_care_requests hos_care_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hos_care_requests
    ADD CONSTRAINT hos_care_requests_pkey PRIMARY KEY (id);


--
-- Name: hos_ed_trends hos_ed_trends_day_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hos_ed_trends
    ADD CONSTRAINT hos_ed_trends_day_key UNIQUE (day);


--
-- Name: hos_ed_trends hos_ed_trends_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hos_ed_trends
    ADD CONSTRAINT hos_ed_trends_pkey PRIMARY KEY (id);


--
-- Name: hos_request_volume hos_request_volume_day_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hos_request_volume
    ADD CONSTRAINT hos_request_volume_day_key UNIQUE (day);


--
-- Name: hos_request_volume hos_request_volume_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hos_request_volume
    ADD CONSTRAINT hos_request_volume_pkey PRIMARY KEY (id);


--
-- Name: hospital_staff hospital_staff_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hospital_staff
    ADD CONSTRAINT hospital_staff_pkey PRIMARY KEY (id);


--
-- Name: hospitals hospitals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hospitals
    ADD CONSTRAINT hospitals_pkey PRIMARY KEY (id);


--
-- Name: lab_results lab_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lab_results
    ADD CONSTRAINT lab_results_pkey PRIMARY KEY (id);


--
-- Name: medical_files medical_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_files
    ADD CONSTRAINT medical_files_pkey PRIMARY KEY (id);


--
-- Name: patient_activity_log patient_activity_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_activity_log
    ADD CONSTRAINT patient_activity_log_pkey PRIMARY KEY (id);


--
-- Name: patient_allergies patient_allergies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_allergies
    ADD CONSTRAINT patient_allergies_pkey PRIMARY KEY (id);


--
-- Name: patient_conditions patient_conditions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_conditions
    ADD CONSTRAINT patient_conditions_pkey PRIMARY KEY (id);


--
-- Name: patient_data_records patient_data_records_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_data_records
    ADD CONSTRAINT patient_data_records_pkey PRIMARY KEY (id);


--
-- Name: patient_medications patient_medications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medications
    ADD CONSTRAINT patient_medications_pkey PRIMARY KEY (id);


--
-- Name: patient_preferences patient_preferences_patient_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_preferences
    ADD CONSTRAINT patient_preferences_patient_id_key UNIQUE (patient_id);


--
-- Name: patient_preferences patient_preferences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_preferences
    ADD CONSTRAINT patient_preferences_pkey PRIMARY KEY (id);


--
-- Name: patient_procedures patient_procedures_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT patient_procedures_pkey PRIMARY KEY (id);


--
-- Name: patients patients_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT patients_pkey PRIMARY KEY (id);


--
-- Name: payer_organizations payer_organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payer_organizations
    ADD CONSTRAINT payer_organizations_pkey PRIMARY KEY (id);


--
-- Name: providers providers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.providers
    ADD CONSTRAINT providers_pkey PRIMARY KEY (id);


--
-- Name: safety_protocols safety_protocols_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.safety_protocols
    ADD CONSTRAINT safety_protocols_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_assessments_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_assessments_created_at ON public.assessments USING btree (created_at);


--
-- Name: ix_assessments_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_assessments_patient_id ON public.assessments USING btree (patient_id);


--
-- Name: ix_care_plans_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_care_plans_active ON public.care_plans USING btree (active);


--
-- Name: ix_care_plans_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_care_plans_patient_id ON public.care_plans USING btree (patient_id);


--
-- Name: ix_emergency_requests_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_emergency_requests_patient_id ON public.emergency_requests USING btree (patient_id);


--
-- Name: ix_healthcare_encounters_encounter_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_healthcare_encounters_encounter_date ON public.healthcare_encounters USING btree (encounter_date);


--
-- Name: ix_healthcare_encounters_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_healthcare_encounters_patient_id ON public.healthcare_encounters USING btree (patient_id);


--
-- Name: ix_hos_care_actions_mrn; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_hos_care_actions_mrn ON public.hos_care_actions USING btree (mrn);


--
-- Name: ix_hos_care_requests_mrn; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_hos_care_requests_mrn ON public.hos_care_requests USING btree (mrn);


--
-- Name: ix_hos_care_requests_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_hos_care_requests_patient_id ON public.hos_care_requests USING btree (patient_id);


--
-- Name: ix_lab_results_lab_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_lab_results_lab_date ON public.lab_results USING btree (lab_date);


--
-- Name: ix_lab_results_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_lab_results_patient_id ON public.lab_results USING btree (patient_id);


--
-- Name: ix_medical_files_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_medical_files_patient_id ON public.medical_files USING btree (patient_id);


--
-- Name: ix_patient_activity_log_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_activity_log_patient_id ON public.patient_activity_log USING btree (patient_id);


--
-- Name: ix_patient_data_records_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_patient_data_records_patient_id ON public.patient_data_records USING btree (patient_id);


--
-- Name: ix_patient_data_records_source_record_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_patient_data_records_source_record_key ON public.patient_data_records USING btree (source_record_key);


--
-- Name: ix_patients_patient_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_patients_patient_id ON public.patients USING btree (patient_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: assessment_medical_context assessment_medical_context_assessment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_medical_context
    ADD CONSTRAINT assessment_medical_context_assessment_id_fkey FOREIGN KEY (assessment_id) REFERENCES public.assessments(id);


--
-- Name: assessment_safety_questions assessment_safety_questions_assessment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_safety_questions
    ADD CONSTRAINT assessment_safety_questions_assessment_id_fkey FOREIGN KEY (assessment_id) REFERENCES public.assessments(id);


--
-- Name: assessment_symptoms assessment_symptoms_assessment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_symptoms
    ADD CONSTRAINT assessment_symptoms_assessment_id_fkey FOREIGN KEY (assessment_id) REFERENCES public.assessments(id);


--
-- Name: assessments assessments_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessments
    ADD CONSTRAINT assessments_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: care_plan_actions care_plan_actions_care_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_plan_actions
    ADD CONSTRAINT care_plan_actions_care_plan_id_fkey FOREIGN KEY (care_plan_id) REFERENCES public.care_plans(id);


--
-- Name: care_plan_providers care_plan_providers_care_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_plan_providers
    ADD CONSTRAINT care_plan_providers_care_plan_id_fkey FOREIGN KEY (care_plan_id) REFERENCES public.care_plans(id);


--
-- Name: care_plan_providers care_plan_providers_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_plan_providers
    ADD CONSTRAINT care_plan_providers_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: care_plans care_plans_assessment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_plans
    ADD CONSTRAINT care_plans_assessment_id_fkey FOREIGN KEY (assessment_id) REFERENCES public.assessments(id);


--
-- Name: care_plans care_plans_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_plans
    ADD CONSTRAINT care_plans_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: care_plans care_plans_recommendation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_plans
    ADD CONSTRAINT care_plans_recommendation_id_fkey FOREIGN KEY (recommendation_id) REFERENCES public.care_recommendations(id);


--
-- Name: care_recommendations care_recommendations_assessment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.care_recommendations
    ADD CONSTRAINT care_recommendations_assessment_id_fkey FOREIGN KEY (assessment_id) REFERENCES public.assessments(id);


--
-- Name: claims claims_encounter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claims
    ADD CONSTRAINT claims_encounter_id_fkey FOREIGN KEY (encounter_id) REFERENCES public.healthcare_encounters(id);


--
-- Name: claims claims_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.claims
    ADD CONSTRAINT claims_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: cms_users cms_users_payer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_users
    ADD CONSTRAINT cms_users_payer_id_fkey FOREIGN KEY (payer_id) REFERENCES public.payer_organizations(id);


--
-- Name: cms_users cms_users_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cms_users
    ADD CONSTRAINT cms_users_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: daily_goals daily_goals_care_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_goals
    ADD CONSTRAINT daily_goals_care_plan_id_fkey FOREIGN KEY (care_plan_id) REFERENCES public.care_plans(id);


--
-- Name: emergency_contacts emergency_contacts_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emergency_contacts
    ADD CONSTRAINT emergency_contacts_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: emergency_requests emergency_requests_assessment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emergency_requests
    ADD CONSTRAINT emergency_requests_assessment_id_fkey FOREIGN KEY (assessment_id) REFERENCES public.assessments(id);


--
-- Name: emergency_requests emergency_requests_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emergency_requests
    ADD CONSTRAINT emergency_requests_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: emergency_requests emergency_requests_recommendation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emergency_requests
    ADD CONSTRAINT emergency_requests_recommendation_id_fkey FOREIGN KEY (recommendation_id) REFERENCES public.care_recommendations(id);


--
-- Name: file_ai_summaries file_ai_summaries_medical_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_ai_summaries
    ADD CONSTRAINT file_ai_summaries_medical_file_id_fkey FOREIGN KEY (medical_file_id) REFERENCES public.medical_files(id);


--
-- Name: healthcare_encounters healthcare_encounters_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.healthcare_encounters
    ADD CONSTRAINT healthcare_encounters_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: healthcare_encounters healthcare_encounters_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.healthcare_encounters
    ADD CONSTRAINT healthcare_encounters_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: healthcare_encounters healthcare_encounters_source_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.healthcare_encounters
    ADD CONSTRAINT healthcare_encounters_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES public.patient_data_records(id);


--
-- Name: hospital_staff hospital_staff_hospital_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hospital_staff
    ADD CONSTRAINT hospital_staff_hospital_id_fkey FOREIGN KEY (hospital_id) REFERENCES public.hospitals(id);


--
-- Name: hospital_staff hospital_staff_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hospital_staff
    ADD CONSTRAINT hospital_staff_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: lab_results lab_results_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lab_results
    ADD CONSTRAINT lab_results_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: lab_results lab_results_source_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lab_results
    ADD CONSTRAINT lab_results_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES public.patient_data_records(id);


--
-- Name: medical_files medical_files_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_files
    ADD CONSTRAINT medical_files_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: medical_files medical_files_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.medical_files
    ADD CONSTRAINT medical_files_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.providers(id);


--
-- Name: patient_activity_log patient_activity_log_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_activity_log
    ADD CONSTRAINT patient_activity_log_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_allergies patient_allergies_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_allergies
    ADD CONSTRAINT patient_allergies_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_conditions patient_conditions_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_conditions
    ADD CONSTRAINT patient_conditions_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_conditions patient_conditions_source_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_conditions
    ADD CONSTRAINT patient_conditions_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES public.patient_data_records(id);


--
-- Name: patient_data_records patient_data_records_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_data_records
    ADD CONSTRAINT patient_data_records_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_medications patient_medications_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medications
    ADD CONSTRAINT patient_medications_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_medications patient_medications_source_record_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_medications
    ADD CONSTRAINT patient_medications_source_record_id_fkey FOREIGN KEY (source_record_id) REFERENCES public.patient_data_records(id);


--
-- Name: patient_preferences patient_preferences_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_preferences
    ADD CONSTRAINT patient_preferences_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patient_procedures patient_procedures_encounter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT patient_procedures_encounter_id_fkey FOREIGN KEY (encounter_id) REFERENCES public.healthcare_encounters(id);


--
-- Name: patient_procedures patient_procedures_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patient_procedures
    ADD CONSTRAINT patient_procedures_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: patients patients_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT patients_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: safety_protocols safety_protocols_care_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.safety_protocols
    ADD CONSTRAINT safety_protocols_care_plan_id_fkey FOREIGN KEY (care_plan_id) REFERENCES public.care_plans(id);


--
-- PostgreSQL database dump complete
--

\unrestrict 64386IRSgGxuGoDHhYw97Tmf9BLxawxMSjQThh1DvpW3cizuGEOR0epnwa511eg

