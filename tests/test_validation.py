import unittest
from backend.app.config import check_missing_files, validate_environment

class TestValidation(unittest.TestCase):
    def test_missing_files_detection(self):
        # Since files are now present in data/source, check_missing_files must return empty
        missing = check_missing_files()
        self.assertEqual(len(missing), 0)

    def test_validate_environment_does_not_raise(self):
        # Should not raise since environment is fully set up
        validate_environment()

if __name__ == "__main__":
    unittest.main()
