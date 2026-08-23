import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# Resolve Paths
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

DATA_ROOT = PROJECT_ROOT / "data"
SOURCE_DIR = DATA_ROOT / "source"
SOURCE_DOCUMENTS_DIR = SOURCE_DIR / "documents"
SOURCE_WORKBOOK = SOURCE_DIR / "ParcelPilot_Assessment_Data.xlsx"

PROCESSED_DATA_DIR = DATA_ROOT / "processed"
DATABASE_DIR = DATA_ROOT / "database"
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(DATABASE_DIR / "parcelpilot.db")))
VECTORSTORE_PATH = Path(os.getenv("VECTORSTORE_PATH", str(DATA_ROOT / "vectorstore" / "chroma")))
GENERATED_DATA_DIR = DATA_ROOT / "generated"

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")

# LLM Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-1.5-flash")

# Centralized Dataset Snapshot Time (default fallback, updated upon ingestion)
# Expected to be parsed from Excel README.
DATASET_SNAPSHOT_TIME = os.getenv("DATASET_SNAPSHOT_TIME", "2024-03-31T23:59:59Z")

# Required Assessment Files
REQUIRED_PDFS = [
    "01_Support_Policy_v3_CURRENT.pdf",
    "02_Support_Policy_v2_DEPRECATED.pdf",
    "03_Cancellation_and_Service_Credit_SOP_v4.pdf",
    "04_Product_Operations_Guide_and_Known_Issues.pdf",
    "05_Northstar_Logistics_Enterprise_Agreement.pdf",
    "06_LumenWorks_Service_Agreement.pdf"
]

def check_missing_files() -> List[str]:
    """
    Checks if all required assessment files are present.
    Returns a list of missing file path strings.
    """
    missing = []
    
    # Check workbook
    if not SOURCE_WORKBOOK.exists():
        missing.append(str(SOURCE_WORKBOOK.relative_to(PROJECT_ROOT)))
        
    # Check PDFs
    for pdf in REQUIRED_PDFS:
        pdf_path = SOURCE_DOCUMENTS_DIR / pdf
        if not pdf_path.exists():
            missing.append(str(pdf_path.relative_to(PROJECT_ROOT)))
            
    return missing

def validate_environment():
    """
    Validates that the source files exist.
    Raises FileNotFoundError with a clear error listing all missing files.
    """
    missing = check_missing_files()
    if missing:
        missing_str = "\n".join(f"- data/source/{m.split('data/source/')[-1]}" for m in missing)
        raise FileNotFoundError(
            f"Missing required assessment file(s):\n{missing_str}\n"
            f"Please place them in the correct location under data/source/"
        )
