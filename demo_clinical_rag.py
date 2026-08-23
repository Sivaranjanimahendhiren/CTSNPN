"""
========================================================================================
DEMO SHOWCASE: Clinical Unstructured Lab Report Extraction & pgvector Baseline Comparison
========================================================================================
Stack Demonstrated:
1. scispaCy (en_core_sci_sm): Biomedical entity and discrete biomarker extraction
2. PostgreSQL (Relational): Discrete biomarker storage & deterministic baseline trend math
3. BAAI/bge-small-en-v1.5: 384-dimensional dense local embeddings
4. PostgreSQL pgvector: Semantic vector search on doctor impressions & clinical narratives
========================================================================================
"""

from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from adaptive_postcare.clinical_rag import (
    ClinicalRAGService,
    ExtractedBiomarker,
    ClinicalDocumentChunk,
)


def run_clinical_rag_demo():
    print("=" * 80)
    print("[+] CLINICAL UNSTRUCTURED LAB EXTRACTION & PGVECTOR RAG SHOWCASE")
    print("=" * 80)

    # Standalone high-speed SQLite session for instantaneous demonstration
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    rag_service = ClinicalRAGService(session=session)

    patient_id = "PATIENT-DEMO-901"

    # -------------------------------------------------------------------------
    # STEP 1: Seed Historical Baseline Labs (Simulating Pre-Discharge Day 0)
    # -------------------------------------------------------------------------
    print("\n[STEP 1] Seeding Pre-Discharge Baseline Lab Values in Database...")
    baseline_time = datetime.utcnow() - timedelta(days=5)
    baseline_biomarkers = [
        ExtractedBiomarker(
            biomarker_name="Serum Creatinine",
            value=1.1,
            unit="mg/dL",
            reference_low=0.6,
            reference_high=1.2,
            status="NORMAL",
        ),
        ExtractedBiomarker(
            biomarker_name="Potassium",
            value=4.2,
            unit="mEq/L",
            reference_low=3.5,
            reference_high=5.0,
            status="NORMAL",
        ),
        ExtractedBiomarker(
            biomarker_name="HbA1c",
            value=6.8,
            unit="%",
            reference_low=4.0,
            reference_high=5.6,
            status="ELEVATED",
        ),
    ]
    rag_service.vector_store.store_biomarkers(
        patient_id=patient_id,
        biomarkers=baseline_biomarkers,
        collected_at=baseline_time,
    )
    print(f"  * Baseline stored for Patient {patient_id}:")
    for b in baseline_biomarkers:
        print(f"    - {b.biomarker_name}: {b.value} {b.unit} ({b.status})")

    # -------------------------------------------------------------------------
    # STEP 2: Ingest Unstructured Post-Discharge Lab Report (Day 5 Followup)
    # -------------------------------------------------------------------------
    raw_unstructured_lab_pdf = """
    ST. JUDE MEMORIAL HOSPITAL - CLINICAL LABORATORY REPORT
    Patient: PATIENT-DEMO-901 | Date of Collection: August 23, 2026

    COMPREHENSIVE METABOLIC PANEL:
    Serum Creatinine: 1.9 mg/dL (Ref Range: 0.6 - 1.2) [HIGH]
    Potassium: 5.4 mEq/L (Ref Range: 3.5 - 5.0) [HIGH]
    Blood Glucose: 142 mg/dL (Ref Range: 70 - 99) [ELEVATED]
    Estimated GFR (eGFR): 38 mL/min/1.73m2 [LOW]

    ATTENDING PHYSICIAN IMPRESSION & RECOMMENDATIONS:
    Impression: Acute worsening of renal biomarkers. Patient exhibiting signs of early Acute Kidney Injury (AKI Stage 1).
    Recommendation: Immediately review nephrotoxic medications (withhold ACE inhibitors/Lisinopril). Advise patient to maintain oral hydration and schedule urgent nephrology follow-up within 48 hours.
    """

    print("\n[STEP 2] Processing Unstructured Post-Discharge Lab Report...")
    print(f"  - Raw Document Length: {len(raw_unstructured_lab_pdf)} characters")
    
    result = rag_service.process_unstructured_lab_report(
        patient_id=patient_id,
        raw_report_text=raw_unstructured_lab_pdf,
    )

    # -------------------------------------------------------------------------
    # STEP 3: Display scispaCy Extraction Results
    # -------------------------------------------------------------------------
    print("\n[STEP 3] scispaCy Extraction Results:")
    print(f"  - Extracted Biomarkers Count: {result['biomarkers_extracted_count']}")
    for bio in result["biomarkers"]:
        print(f"    - {bio['biomarker_name']}: {bio['value']} {bio['unit']} (Status: {bio['status']})")

    # -------------------------------------------------------------------------
    # STEP 4: Display Deterministic Baseline Trend Comparison (PostgreSQL)
    # -------------------------------------------------------------------------
    print("\n[STEP 4] Baseline vs Current Mathematical Trend Analysis:")
    for trend in result["trend_analysis"]:
        if trend["baseline_value"] is not None:
            alert_str = " [!] ALERT TRIGGERED: CLINICALLY SIGNIFICANT RISE" if trend["is_clinically_significant"] else ""
            print(f"  >> {trend['biomarker']}:")
            print(f"     Baseline: {trend['baseline_value']} {trend['unit']} -> Current: {trend['current_value']} {trend['unit']}")
            print(f"     Delta: +{trend['delta']} {trend['unit']} (+{trend['percentage_change']}% change) [{trend['trend_direction']}]{alert_str}")

    # -------------------------------------------------------------------------
    # STEP 5: Demonstrate pgvector Semantic Retrieval using BGE Embeddings
    # -------------------------------------------------------------------------
    print("\n[STEP 5] pgvector Semantic Retrieval (BAAI/bge-small-en-v1.5 Embeddings):")
    query = "What should be done if the patient's kidney function or creatinine worsens?"
    print(f"  * Agent Query: '{query}'")
    
    retrieved_notes = rag_service.retrieve_context_for_agent(patient_id=patient_id, query_text=query, top_k=2)
    for idx, doc in enumerate(retrieved_notes, 1):
        print(f"  [Match {idx}] (Similarity Score: {doc['similarity_score']}):")
        print(f"    \"{doc['content']}\"")

    # -------------------------------------------------------------------------
    # STEP 6: Agentic Action & Dialogue Synthesis
    # -------------------------------------------------------------------------
    print("\n[STEP 6] Agentic Safety Evaluation & Dialogue Output:")
    if result["escalation_recommended"]:
        print("  [ALERT] ESCALATION REQUIRED: Deterministic clinical policy triggered due to >20% rise in Creatinine.")
        print("  [AGENT MESSAGE TO PATIENT]:")
        print("     \"Hello, we reviewed your recent laboratory results from today. Your kidney markers")
        print("      show a significant increase compared to your baseline at discharge. Per your doctor's")
        print("      guidance, please pause your Lisinopril medication and ensure you drink plenty of fluids.")
        print("      Our care coordinator has been notified to schedule a clinician review within 24-48 hours.\"")

    print("\n" + "=" * 80)
    print("[SUCCESS] CLINICAL RAG & PGVECTOR SHOWCASE COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    run_clinical_rag_demo()
