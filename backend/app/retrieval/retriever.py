from typing import List, Optional
from pydantic import BaseModel, Field
import os

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

class LexicalRetriever:
    _cached_pages = None
    
    @classmethod
    def _load_pages(cls):
        if cls._cached_pages is not None:
            return cls._cached_pages
            
        import fitz
        import json
        from backend.app.config import SOURCE_DOCUMENTS_DIR, SOURCE_DIR
        
        manifest_path = SOURCE_DIR / "MANIFEST.json"
        manifest_data = {}
        if manifest_path.exists():
            with open(manifest_path, "r") as f:
                manifest_data = json.load(f)
                
        doc_metadata_map = {doc["filename"]: doc for doc in manifest_data.get("documents", [])}
        
        pages = []
        for pdf_path in sorted(SOURCE_DOCUMENTS_DIR.glob("*.pdf")):
            filename = pdf_path.name
            doc_meta = doc_metadata_map.get(filename, {})
            try:
                doc = fitz.open(pdf_path)
                for page_idx, page in enumerate(doc):
                    page_text = page.get_text()
                    pages.append({
                        "text": page_text,
                        "filename": filename,
                        "page": page_idx + 1,
                        "document_type": doc_meta.get("document_type") or "",
                        "status": doc_meta.get("status") or "",
                        "authority_level": int(doc_meta.get("authority_level") or 0),
                        "effective_date": doc_meta.get("effective_date") or "",
                        "customer_account_id": doc_meta.get("customer_account_id") or "null"
                    })
            except Exception as e:
                print(f"LexicalRetriever: Error loading {filename}: {e}")
                
        cls._cached_pages = pages
        return cls._cached_pages

    def search(
        self,
        query: str,
        n_results: int = 5,
        customer_account_id: Optional[str] = None,
        status: Optional[str] = "CURRENT",
        document_type: Optional[str] = None
    ) -> List[DocumentSearchResult]:
        pages = self._load_pages()
        query_words = [w.lower() for w in query.split() if len(w) > 2]
        
        results = []
        for p in pages:
            # Apply metadata filters
            if status and p["status"] != status:
                continue
            if document_type and p["document_type"] != document_type:
                continue
            if customer_account_id:
                # Match customer account or "null"
                if p["customer_account_id"] not in (customer_account_id, "null"):
                    continue
                    
            # Calculate simple word overlap score
            text_lower = p["text"].lower()
            score = 0.0
            if query_words:
                matches = sum(1 for w in query_words if w in text_lower)
                score = matches / len(query_words)
                
            cust_id = p["customer_account_id"]
            if cust_id == "null":
                cust_id = None
                
            results.append(
                DocumentSearchResult(
                    content=p["text"],
                    source_name=p["filename"],
                    page=p["page"],
                    section=None,
                    document_status=p["status"],
                    document_type=p["document_type"],
                    customer_account_id=cust_id,
                    effective_date=p["effective_date"],
                    authority_level=p["authority_level"],
                    relevance_score=round(score, 4)
                )
            )
            
        results.sort(key=lambda x: (x.authority_level, x.relevance_score), reverse=True)
        return results[:n_results]

class DocumentRetriever:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DocumentRetriever, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        pass

    def _lazy_init(self):
        if getattr(self, "_initialized", False):
            return
        import chromadb
        from chromadb.utils import embedding_functions
        from backend.app.config import VECTORSTORE_PATH
        
        self.chroma_client = chromadb.PersistentClient(path=str(VECTORSTORE_PATH))
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
        self.collection = self.chroma_client.get_collection(
            name="documents",
            embedding_function=self.embedding_fn
        )
        self._initialized = True

    def search(
        self,
        query: str,
        n_results: int = 5,
        customer_account_id: Optional[str] = None,
        status: Optional[str] = "CURRENT",
        document_type: Optional[str] = None
    ) -> List[DocumentSearchResult]:
        if os.getenv("RENDER_FREE_MODE", "false").lower() == "true":
            return LexicalRetriever().search(
                query=query,
                n_results=n_results,
                customer_account_id=customer_account_id,
                status=status,
                document_type=document_type
            )
            
        self._lazy_init()
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
