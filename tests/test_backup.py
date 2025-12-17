import os
import tempfile
import unittest
import shutil

from app import create_app

class TestBackup(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.sqlite")
        self.media_dir = os.path.join(self.tmpdir.name, "media")
        os.makedirs(self.media_dir, exist_ok=True)

        self.app = create_app({
            "TESTING": True,
            "DATABASE": self.db_path,
            "MEDIA_DIR": self.media_dir,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_backup_creation(self):
        # Create some test data
        r = self.client.post("/api/people", json={"given":"Test","surname":"Person","sex":"M"})
        self.assertEqual(r.status_code, 201)
        
        # Create a backup
        r = self.client.post("/api/backup")
        self.assertEqual(r.status_code, 201)
        data = r.get_json()
        
        self.assertTrue(data["success"])
        self.assertIn("backup_name", data)
        self.assertIn("backup_path", data)
        self.assertGreater(data["db_size_bytes"], 0)
        
        # Verify backup files exist
        backup_path = data["backup_path"]
        self.assertTrue(os.path.exists(backup_path))
        self.assertTrue(os.path.exists(os.path.join(backup_path, "family_tree.sqlite")))

    def test_diagnostics_endpoint(self):
        # Add some test data
        self.client.post("/api/people", json={"given":"John","surname":"Doe"})
        
        # Call diagnostics
        r = self.client.get("/api/diagnostics")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        
        self.assertIn("app_version", data)
        self.assertIn("db_path", data)
        self.assertIn("schema_version", data)
        self.assertIn("counts", data)
        self.assertEqual(data["counts"]["people"], 1)

if __name__ == "__main__":
    unittest.main()
