import sys
import json
from pathlib import Path

# Add backend to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.app.config import SOURCE_DOCUMENTS_DIR, SOURCE_DIR, check_missing_files

def generate_manifest():
    missing = check_missing_files()
    if missing:
        print(f"Error: Missing files for manifest generation: {missing}", file=sys.stderr)
        sys.exit(1)
        
    manifest_path = SOURCE_DIR / "MANIFEST.json"
    
    # Metadata extracted and hardcoded according to the rules and files,
    # mapping documents to status, effective dates, versions, etc.
    manifest_data = {
        "documents": [
            {
                "filename": "01_Support_Policy_v3_CURRENT.pdf",
                "document_type": "Support Policy",
                "status": "CURRENT",
                "authority_level": 80,
                "effective_date": "2024-03-01",
                "version": "3.0",
                "supersedes": "02_Support_Policy_v2_DEPRECATED.pdf"
            },
            {
                "filename": "02_Support_Policy_v2_DEPRECATED.pdf",
                "document_type": "Support Policy",
                "status": "DEPRECATED",
                "authority_level": 0,
                "effective_date": "2022-01-01",
                "version": "2.0",
                "supersedes": None
            },
            {
                "filename": "03_Cancellation_and_Service_Credit_SOP_v4.pdf",
                "document_type": "Standard Operating Procedure",
                "status": "CURRENT",
                "authority_level": 70,
                "effective_date": "2024-01-15",
                "version": "4.0",
                "supersedes": None
            },
            {
                "filename": "04_Product_Operations_Guide_and_Known_Issues.pdf",
                "document_type": "Product Documentation",
                "status": "CURRENT",
                "authority_level": 60,
                "effective_date": "2024-02-01",
                "version": "1.0",
                "supersedes": None
            },
            {
                "filename": "05_Northstar_Logistics_Enterprise_Agreement.pdf",
                "document_type": "Customer Agreement",
                "status": "CURRENT",
                "authority_level": 100,
                "customer_account_id": "ACCT-001",  # This will be verified in Phase 2
                "effective_date": "2023-06-01",
                "version": "1.0",
                "supersedes": None
            },
            {
                "filename": "06_LumenWorks_Service_Agreement.pdf",
                "document_type": "Customer Agreement",
                "status": "CURRENT",
                "authority_level": 100,
                "customer_account_id": "ACCT-002",  # This will be verified in Phase 2
                "effective_date": "2023-09-01",
                "version": "1.0",
                "supersedes": None
            }
        ]
    }
    
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f, indent=4)
        
    print(f"Manifest successfully generated at {manifest_path}")

if __name__ == "__main__":
    generate_manifest()
