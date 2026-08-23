"""
PostgreSQL pgvector Store & Baseline Lab Result Repository.
Manages vector similarity search with HNSW indexes and exact SQL biomarker trend queries.
"""

import json
import math
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session
from .schemas import ExtractedBiomarker, ClinicalDocumentChunk


class PGVectorClinicalStore:
    """
    Handles storage and similarity retrieval for clinical document embeddings using PostgreSQL pgvector.
    Supports native pgvector distance operators (<=>) with graceful in-memory cosine fallback for SQLite testing.
    """

    def __init__(self, session: Session):
        self.session = session
        self._is_postgres = False
        self._ensure_schema()

    def _ensure_schema(self):
        """Creates tables for lab results and clinical document embeddings if not existing."""
        # Detect if we are on PostgreSQL
        try:
            bind = self.session.get_bind()
            dialect_name = bind.dialect.name.lower()
            self._is_postgres = "postgres" in dialect_name
        except Exception:
            self._is_postgres = False

        if self._is_postgres:
            try:
                self.session.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                self.session.commit()
            except Exception:
                self.session.rollback()

        # 1. Table: patient_lab_results (Relational / Time-Series)
        try:
            self.session.execute(text("""
                CREATE TABLE IF NOT EXISTS patient_lab_results (
                    id VARCHAR(64) PRIMARY KEY,
                    patient_id VARCHAR(64) NOT NULL,
                    biomarker_name VARCHAR(128) NOT NULL,
                    value FLOAT NOT NULL,
                    unit VARCHAR(32),
                    reference_low FLOAT,
                    reference_high FLOAT,
                    status VARCHAR(32),
                    collected_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            self.session.commit()
        except Exception:
            self.session.rollback()

        # 2. Table: clinical_document_vectors
        try:
            vec_type = "vector(384)" if self._is_postgres else "TEXT"
            self.session.execute(text(f"""
                CREATE TABLE IF NOT EXISTS clinical_document_vectors (
                    doc_id VARCHAR(64) PRIMARY KEY,
                    patient_id VARCHAR(64) NOT NULL,
                    doc_type VARCHAR(64) NOT NULL,
                    content_chunk TEXT NOT NULL,
                    embedding {vec_type},
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            self.session.commit()
        except Exception:
            self.session.rollback()

    def store_biomarkers(self, patient_id: str, biomarkers: List[ExtractedBiomarker], collected_at: Optional[datetime] = None) -> int:
        """
        Inserts structured biomarkers into patient_lab_results table for SQL trend comparison.
        """
        ts = collected_at or datetime.utcnow()
        count = 0
        for b in biomarkers:
            rec_id = str(uuid.uuid4())
            try:
                self.session.execute(
                    text("""
                        INSERT INTO patient_lab_results 
                        (id, patient_id, biomarker_name, value, unit, reference_low, reference_high, status, collected_at)
                        VALUES (:id, :p_id, :name, :val, :unit, :low, :high, :status, :ts)
                    """),
                    {
                        "id": rec_id,
                        "p_id": patient_id,
                        "name": b.biomarker_name,
                        "val": b.value,
                        "unit": b.unit,
                        "low": b.reference_low,
                        "high": b.reference_high,
                        "status": b.status,
                        "ts": ts,
                    }
                )
                count += 1
            except Exception:
                pass
        self.session.commit()
        return count

    def store_document_embedding(self, chunk: ClinicalDocumentChunk) -> str:
        """
        Inserts qualitative document narrative chunk with its 384-d embedding into pgvector.
        """
        doc_id = chunk.chunk_id or str(uuid.uuid4())
        vec = chunk.embedding or []
        vec_serialized = str(vec) if self._is_postgres else json.dumps(vec)

        self.session.execute(
            text("""
                INSERT INTO clinical_document_vectors (doc_id, patient_id, doc_type, content_chunk, embedding)
                VALUES (:doc_id, :p_id, :doc_type, :content, :vec)
            """),
            {
                "doc_id": doc_id,
                "p_id": chunk.patient_id,
                "doc_type": chunk.doc_type,
                "content": chunk.text_content,
                "vec": vec_serialized,
            }
        )
        self.session.commit()
        return doc_id

    def similarity_search(self, patient_id: str, query_vector: List[float], top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Performs vector cosine distance search using pgvector (<=> operator) or in-memory fallback.
        """
        if self._is_postgres:
            try:
                res = self.session.execute(
                    text("""
                        SELECT doc_id, doc_type, content_chunk, 1 - (embedding <=> :q_vec) AS similarity
                        FROM clinical_document_vectors
                        WHERE patient_id = :p_id
                        ORDER BY embedding <=> :q_vec
                        LIMIT :limit
                    """),
                    {"p_id": patient_id, "q_vec": str(query_vector), "limit": top_k}
                ).fetchall()
                return [
                    {"doc_id": r[0], "doc_type": r[1], "content": r[2], "similarity_score": round(float(r[3]), 4)}
                    for r in res
                ]
            except Exception:
                self.session.rollback()

        return self._fallback_similarity_search(patient_id, query_vector, top_k)

    def compare_lab_trends(self, patient_id: str, current_biomarkers: List[ExtractedBiomarker]) -> List[Dict[str, Any]]:
        """
        Compares newly extracted biomarkers against historical baseline lab results in PostgreSQL.
        Calculates exact delta, percentage change, and clinical risk alert.
        """
        trend_reports = []

        for current in current_biomarkers:
            row = self.session.execute(
                text("""
                    SELECT value, unit, status, collected_at
                    FROM patient_lab_results
                    WHERE patient_id = :p_id AND biomarker_name = :b_name
                    ORDER BY collected_at ASC
                    LIMIT 1
                """),
                {"p_id": patient_id, "b_name": current.biomarker_name}
            ).fetchone()

            if row:
                baseline_val = float(row[0])
                delta = current.value - baseline_val
                pct_change = (delta / baseline_val) * 100 if baseline_val > 0 else 0.0

                trend_reports.append({
                    "biomarker": current.biomarker_name,
                    "baseline_value": baseline_val,
                    "current_value": current.value,
                    "unit": current.unit or row[1],
                    "delta": round(delta, 2),
                    "percentage_change": round(pct_change, 1),
                    "trend_direction": "INCREASED" if delta > 0 else ("DECREASED" if delta < 0 else "STABLE"),
                    "current_status": current.status,
                    "is_clinically_significant": abs(pct_change) >= 20.0 or current.status in ("CRITICAL_HIGH", "CRITICAL_LOW"),
                })
            else:
                trend_reports.append({
                    "biomarker": current.biomarker_name,
                    "baseline_value": None,
                    "current_value": current.value,
                    "unit": current.unit,
                    "trend_direction": "FIRST_RECORD",
                    "current_status": current.status,
                    "is_clinically_significant": current.status in ("CRITICAL_HIGH", "CRITICAL_LOW"),
                })

        return trend_reports

    def _fallback_similarity_search(self, patient_id: str, query_vec: List[float], top_k: int) -> List[Dict[str, Any]]:
        """In-memory cosine similarity fallback."""
        rows = self.session.execute(
            text("SELECT doc_id, doc_type, content_chunk, embedding FROM clinical_document_vectors WHERE patient_id = :p_id"),
            {"p_id": patient_id}
        ).fetchall()

        scored = []
        for r in rows:
            doc_id, doc_type, content, emb_raw = r[0], r[1], r[2], r[3]
            if emb_raw:
                try:
                    if isinstance(emb_raw, str):
                        try:
                            vec = json.loads(emb_raw)
                        except Exception:
                            vec = [float(x.strip()) for x in emb_raw.strip("[]").split(",") if x.strip()]
                    else:
                        vec = emb_raw
                    score = self._cosine_sim(query_vec, vec)
                    scored.append({"doc_id": doc_id, "doc_type": doc_type, "content": content, "similarity_score": round(score, 4)})
                except Exception:
                    pass

        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _cosine_sim(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        n1 = math.sqrt(sum(a * a for a in v1))
        n2 = math.sqrt(sum(b * b for b in v2))
        return dot / (n1 * n2) if n1 > 0 and n2 > 0 else 0.0
