"""
Clinical RAG & Extraction Package:
- scispaCy Clinical Extraction (en_core_sci_sm)
- BAAI/bge-small-en-v1.5 Local Embeddings
- PostgreSQL pgvector Semantic Store & Baseline Lab Result Repository
"""

from .schemas import ExtractedBiomarker, ClinicalDocumentChunk, LabReportAnalysis
from .scispacy_extractor import SciSpacyLabExtractor
from .bge_embedder import BGEClinicalEmbedder
from .pgvector_store import PGVectorClinicalStore
from .service import ClinicalRAGService

__all__ = [
    "ExtractedBiomarker",
    "ClinicalDocumentChunk",
    "LabReportAnalysis",
    "SciSpacyLabExtractor",
    "BGEClinicalEmbedder",
    "PGVectorClinicalStore",
    "ClinicalRAGService",
]
