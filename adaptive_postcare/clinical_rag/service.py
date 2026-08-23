"""
High-Level Clinical RAG & Lab Extraction Service.
Integrates scispaCy biomedical extraction, BAAI/bge-small-en-v1.5 embeddings, and PostgreSQL pgvector store.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from .schemas import ExtractedBiomarker, ClinicalDocumentChunk, LabReportAnalysis
from .scispacy_extractor import SciSpacyLabExtractor
from .bge_embedder import BGEClinicalEmbedder
from .pgvector_store import PGVectorClinicalStore


class ClinicalRAGService:
    """
    Unified service for:
    1. Parsing unstructured lab reports using scispaCy.
    2. Storing discrete biomarkers in PostgreSQL for exact baseline arithmetic comparison.
    3. Generating 384-d dense embeddings with BAAI/bge-small-en-v1.5 and storing in pgvector.
    4. Comparing current lab biomarkers with pre-discharge baselines.
    5. Querying semantic medical context using pgvector cosine distance.
    """

    def __init__(self, session: Session):
        self.session = session
        self.extractor = SciSpacyLabExtractor()
        self.embedder = BGEClinicalEmbedder()
        self.vector_store = PGVectorClinicalStore(session)

    def process_unstructured_lab_report(
        self,
        patient_id: str,
        raw_report_text: str,
        collected_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        End-to-end ingestion of an unstructured clinical lab report.
        """
        # 1. Extract discrete biomarkers and doctor impressions via scispaCy
        analysis: LabReportAnalysis = self.extractor.extract_from_report(
            raw_report_text=raw_report_text,
            patient_id=patient_id,
        )

        # 2. Store structured biomarkers in PostgreSQL
        stored_count = self.vector_store.store_biomarkers(
            patient_id=patient_id,
            biomarkers=analysis.biomarkers,
            collected_at=collected_at,
        )

        # 3. Compare current biomarkers against historical baseline in PostgreSQL
        trend_analysis = self.vector_store.compare_lab_trends(
            patient_id=patient_id,
            current_biomarkers=analysis.biomarkers,
        )

        # 4. Embed qualitative impressions via BAAI/bge-small-en-v1.5 and store in pgvector
        embedded_doc_ids = []
        for impression in analysis.clinical_impressions:
            embedding_vec = self.embedder.embed_text(impression)
            chunk = ClinicalDocumentChunk(
                patient_id=patient_id,
                doc_type="LAB_IMPRESSION",
                text_content=impression,
                embedding=embedding_vec,
            )
            doc_id = self.vector_store.store_document_embedding(chunk)
            embedded_doc_ids.append(doc_id)

        # 5. Determine if any critical clinical escalation is needed
        critical_alerts = [
            t for t in trend_analysis
            if t.get("is_clinically_significant") or t.get("current_status") in ("CRITICAL_HIGH", "CRITICAL_LOW")
        ]

        return {
            "patient_id": patient_id,
            "status": "PROCESSED_SUCCESSFULLY",
            "biomarkers_extracted_count": stored_count,
            "biomarkers": [b.model_dump() for b in analysis.biomarkers],
            "qualitative_chunks_embedded": len(embedded_doc_ids),
            "trend_analysis": trend_analysis,
            "escalation_recommended": len(critical_alerts) > 0,
            "critical_alerts": critical_alerts,
        }

    def retrieve_context_for_agent(self, patient_id: str, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieves relevant qualitative clinical notes from pgvector for agent reasoning.
        """
        query_vector = self.embedder.embed_text(query_text)
        return self.vector_store.similarity_search(
            patient_id=patient_id,
            query_vector=query_vector,
            top_k=top_k,
        )
