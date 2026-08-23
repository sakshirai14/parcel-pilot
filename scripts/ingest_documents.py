import sys
import json
# pyrefly: ignore [missing-import]
import fitz  # PyMuPDF
import chromadb
from chromadb.utils import embedding_functions
from pathlib import Path

# Add backend to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.app.config import SOURCE_DOCUMENTS_DIR, VECTORSTORE_PATH, check_missing_files, SOURCE_DIR

def ingest_documents():
    missing = check_missing_files()
    if missing:
        print(f"Error: Missing files for PDF ingestion: {missing}", file=sys.stderr)
        sys.exit(1)
        
    manifest_path = SOURCE_DIR / "MANIFEST.json"
    if not manifest_path.exists():
        print(f"Error: Manifest file not found at {manifest_path}. Please run create_manifest first.", file=sys.stderr)
        sys.exit(1)
        
    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)
        
    print(f"Ingesting documents from {SOURCE_DOCUMENTS_DIR}...")
    
    # Initialize Chroma client
    chroma_client = chromadb.PersistentClient(path=str(VECTORSTORE_PATH))
    
    # Create or get collection
    # Use sentence-transformers embedding function
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    collection = chroma_client.get_or_create_collection(
        name="documents",
        embedding_function=embedding_fn
    )
    
    # We will clear existing documents first to avoid duplicates
    try:
        # Get all IDs in the collection
        existing = collection.get()
        if existing and existing.get("ids"):
            collection.delete(ids=existing["ids"])
            print("Cleared existing vector store documents.")
    except Exception as e:
        print(f"Note: Could not clear collection (might be new/empty): {e}")

    documents_metadata_map = {doc["filename"]: doc for doc in manifest_data["documents"]}
    
    for pdf_path in sorted(SOURCE_DOCUMENTS_DIR.glob("*.pdf")):
        filename = pdf_path.name
        if filename not in documents_metadata_map:
            print(f"Warning: {filename} not in manifest. Skipping.")
            continue
            
        doc_meta = documents_metadata_map[filename]
        
        print(f"Ingesting {filename}...")
        doc = fitz.open(pdf_path)
        
        for page_idx, page in enumerate(doc):
            page_text = page.get_text()
            page_num = page_idx + 1
            
            # Formulate a unique ID
            chunk_id = f"{filename}_page_{page_num}"
            
            # Setup metadata, matching requirements:
            # - filename
            # - document_type
            # - status
            # - authority_level
            # - effective_date
            # - version
            # - customer_account_id
            metadata = {
                "filename": filename,
                "document_type": doc_meta.get("document_type") or "",
                "status": doc_meta.get("status") or "",
                "authority_level": int(doc_meta.get("authority_level") or 0),
                "effective_date": doc_meta.get("effective_date") or "",
                "version": doc_meta.get("version") or "",
                "customer_account_id": doc_meta.get("customer_account_id") or "null",
                "page": page_num
            }
            
            collection.add(
                documents=[page_text],
                metadatas=[metadata],
                ids=[chunk_id]
            )
            print(f"  Added page {page_num} as chunk {chunk_id}")
            
    print("Vector ingestion completed successfully.")

if __name__ == "__main__":
    ingest_documents()
