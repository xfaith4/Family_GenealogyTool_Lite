import os
import tempfile
import unittest

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
        self.backup_paths = []

    def tearDown(self):
        # Clean up any backups created during tests
        import shutil
        for backup_path in self.backup_paths:
            if os.path.exists(backup_path):
                shutil.rmtree(backup_path)
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
        self.backup_paths.append(backup_path)
        self.assertTrue(os.path.exists(backup_path))
        self.assertTrue(os.path.exists(os.path.join(backup_path, "family_tree.sqlite")))

    def test_backup_and_restore(self):
        # Create some test data
        r = self.client.post("/api/people", json={"given":"Original","surname":"Person","sex":"M"})
        self.assertEqual(r.status_code, 201)
        original_id = r.get_json()["id"]
        
        # Create a backup
        r = self.client.post("/api/backup")
        self.assertEqual(r.status_code, 201)
        backup_data = r.get_json()
        backup_name = backup_data["backup_name"]
        self.backup_paths.append(backup_data["backup_path"])
        
        # Modify the database
        r = self.client.post("/api/people", json={"given":"New","surname":"Person","sex":"F"})
        self.assertEqual(r.status_code, 201)
        
        # Verify we have 2 people
        r = self.client.get("/api/people")
        self.assertEqual(len(r.get_json()), 2)
        
        # Restore from backup
        r = self.client.post("/api/restore", json={"backup_name": backup_name})
        self.assertEqual(r.status_code, 200)
        restore_data = r.get_json()
        self.assertTrue(restore_data["success"])
        
        # Verify we're back to 1 person
        r = self.client.get("/api/people")
        people = r.get_json()
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0]["given"], "Original")

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
