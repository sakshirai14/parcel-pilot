import sys
import pandas as pd
import sqlite3
from pathlib import Path

# Add backend to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.app.config import SOURCE_WORKBOOK, DATABASE_PATH, DATABASE_DIR, check_missing_files

def load_excel():
    missing = check_missing_files()
    if missing:
        print(f"Error: Missing files for Excel loading: {missing}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Inspecting and seeding data from {SOURCE_WORKBOOK}...")
    
    # Create DB dir if it doesn't exist
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Connect to SQLite database
    conn = sqlite3.connect(DATABASE_PATH)
    
    try:
        # Load sheets
        for sheet_name in ["accounts", "orders", "tickets"]:
            print(f"Loading sheet: {sheet_name}")
            df = pd.read_excel(SOURCE_WORKBOOK, sheet_name=sheet_name)
            
            # Write to SQL
            df.to_sql(sheet_name, conn, if_exists="replace", index=False)
            print(f"Seeded table '{sheet_name}' with {len(df)} records.")
            
        print("Database seeding completed successfully.")
    except Exception as e:
        print(f"Error seeding database: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    load_excel()
