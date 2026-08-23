import sys
from pathlib import Path

# Add backend to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.app.config import validate_environment, SOURCE_DIR, DATABASE_PATH, VECTORSTORE_PATH

def run_initialization():
    print("ParcelPilot AI Support Agent Ingestion Pipeline starting...")
    
    try:
        # Validate that the necessary files are placed in data/source/
        validate_environment()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
        
    print("\n--- [1/3] Generating Manifest ---")
    from scripts.create_manifest import generate_manifest
    generate_manifest()
    
    print("\n--- [2/3] Seeding SQLite Database ---")
    from scripts.load_excel import load_excel
    load_excel()
    
    print("\n--- [3/3] Ingesting PDFs into Vector Database ---")
    from scripts.ingest_documents import ingest_documents
    ingest_documents()
    
    print("\n=============================================")
    print("INGESTION SUMMARY")
    print("=============================================")
    print(f"Manifest:       {SOURCE_DIR}/MANIFEST.json")
    print(f"SQLite DB:      {DATABASE_PATH}")
    print(f"Vector Store:   {VECTORSTORE_PATH}")
    print("Status:         Success (Initial Phase 1 structures ready for actual files)")
    print("=============================================\n")

if __name__ == "__main__":
    run_initialization()
