# ParcelPilot Data Directory

This directory contains all source, processed, and generated data for the ParcelPilot Customer Support AI Agent.

## Directory Structure

- `source/`: Contains raw assessment inputs.
  - `documents/`: Raw PDF policy and agreement documents. Place the 6 required PDFs here.
  - `ParcelPilot_Assessment_Data.xlsx`: Raw database workbook. Place it in the root of `source/`.
- `processed/`: Intermediate processed output (extracted PDF text, chunks, and metadata).
- `database/`: SQLite databases (`parcelpilot.db`).
- `vectorstore/`: Chroma vector database directories.
- `generated/`: Output directories for agent actions (escalations, followups, reports, analytics).

## Setup & Ingestion Instructions

1. **Place Source Files**:
   Copy the following files to `data/source/documents/`:
   - `01_Support_Policy_v3_CURRENT.pdf`
   - `02_Support_Policy_v2_DEPRECATED.pdf`
   - `03_Cancellation_and_Service_Credit_SOP_v4.pdf`
   - `04_Product_Operations_Guide_and_Known_Issues.pdf`
   - `05_Northstar_Logistics_Enterprise_Agreement.pdf`
   - `06_LumenWorks_Service_Agreement.pdf`

   Copy the Excel workbook to `data/source/`:
   - `ParcelPilot_Assessment_Data.xlsx`

2. **Run Initialization**:
   Once the source files are placed, run the initialization command from the project root:
   ```bash
   python scripts/initialize.py
   ```
   This script will validate all files, load the SQLite database, chunk PDFs, build the vector store, and generate `MANIFEST.json`.

3. **Rebuilding Specific Components**:
   - To rebuild ONLY the SQLite database from Excel:
     ```bash
     python scripts/load_excel.py
     ```
   - To rebuild ONLY the Chroma vector store from PDFs:
     ```bash
     python scripts/ingest_documents.py
     ```
   - To regenerate the manifest:
     ```bash
     python scripts/create_manifest.py
     ```
