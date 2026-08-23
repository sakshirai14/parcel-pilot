import unittest
from pathlib import Path
from backend.app.config import DATA_ROOT, SOURCE_DIR, SOURCE_DOCUMENTS_DIR, SOURCE_WORKBOOK, DATABASE_PATH

class TestConfig(unittest.TestCase):
    def test_config_paths(self):
        self.assertEqual(DATA_ROOT.name, "data")
        self.assertEqual(SOURCE_DIR.name, "source")
        self.assertEqual(SOURCE_DOCUMENTS_DIR.name, "documents")
        self.assertEqual(SOURCE_WORKBOOK.name, "ParcelPilot_Assessment_Data.xlsx")
        self.assertEqual(DATABASE_PATH.name, "parcelpilot.db")

if __name__ == "__main__":
    unittest.main()
