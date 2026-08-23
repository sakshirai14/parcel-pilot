from typing import List, Optional
from pydantic import BaseModel, Field
import chromadb
from chromadb.utils import embedding_functions
from backend.app.config import VECTORSTORE_PATH

class DocumentSearchResult(BaseModel):
    content: str
    source_name: str
    page: int
    section: Optional[str] = None
    document_status: str
    document_type: str
    customer_account_id: Optional[str] = None
    effective_date: str
    authority_level: int
    relevance_score: float

class DocumentRetriever:
    def __init__(self):
        self.chroma_client = chromadb.PersistentClient(path=str(VECTORSTORE_PATH))
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self.collection = self.chroma_client.get_collection(
            name="documents",
            embedding_function=self.embedding_fn
        )

    def search(
        self,
        query: str,
        n_results: int = 5,
        customer_account_id: Optional[str] = None,
        status: Optional[str] = "CURRENT",
        document_type: Optional[str] = None
    ) -> List[DocumentSearchResult]:
        """
        Search documents in ChromaDB with support for semantic similarity and metadata filtering.
        """
        where_clauses = []
        
        if status:
            where_clauses.append({"status": status})
            
        if document_type:
            where_clauses.append({"document_type": document_type})
            
        if customer_account_id:
            # Match customer-specific agreement or global agreements ("null")
            where_clauses.append({
                "$or": [
                    {"customer_account_id": customer_account_id},
                    {"customer_account_id": "null"}
                ]
            })
            
        # Combine filters
        if len(where_clauses) > 1:
            where = {"$and": where_clauses}
        elif len(where_clauses) == 1:
            where = where_clauses[0]
        else:
            where = None

        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where
        )

        search_results = []
        
        if not results or not results["documents"]:
            return search_results

        # Extract items
        docs = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0] if "distances" in results and results["distances"] else [0.5] * len(docs)
        
        for doc_text, meta, dist in zip(docs, metadatas, distances):
            # Compute a normalized relevance score between 0.0 and 1.0.
            # ChromaDB cosine/L2 distance can be converted to similarity.
            relevance_score = max(0.0, min(1.0, 1.0 - (dist / 2.0))) if dist is not None else 0.5
            
            cust_id = meta.get("customer_account_id")
            if cust_id == "null" or cust_id is None:
                cust_id = None
                
            search_results.append(
                DocumentSearchResult(
                    content=doc_text,
                    source_name=meta.get("filename", "unknown"),
                    page=int(meta.get("page", 1)),
                    section=meta.get("section"),
                    document_status=meta.get("status", "unknown"),
                    document_type=meta.get("document_type", "unknown"),
                    customer_account_id=cust_id,
                    effective_date=meta.get("effective_date", ""),
                    authority_level=int(meta.get("authority_level", 0)),
                    relevance_score=round(relevance_score, 4)
                )
            )
            
        # Sort results by authority_level descending, and relevance_score descending
        search_results.sort(key=lambda x: (x.authority_level, x.relevance_score), reverse=True)
        return search_results
