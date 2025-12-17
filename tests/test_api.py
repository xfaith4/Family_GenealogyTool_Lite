import os
import tempfile
import unittest

from app import create_app

SAMPLE_GED = """0 HEAD
0 @I1@ INDI
1 NAME John /Smith/
1 SEX M
0 @I2@ INDI
1 NAME Jane /Doe/
1 SEX F
0 @I3@ INDI
1 NAME Baby /Smith/
1 SEX F
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 TRLR
"""

class TestApi(unittest.TestCase):
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

    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_crud_person(self):
        r = self.client.post("/api/people", json={"given":"Ada","surname":"Lovelace","sex":"F"})
        self.assertEqual(r.status_code, 201)
        pid = r.get_json()["id"]

        r = self.client.get(f"/api/people/{pid}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["given"], "Ada")

        r = self.client.put(f"/api/people/{pid}", json={"given":"Ada","surname":"King","sex":"F"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["surname"], "King")

        r = self.client.get("/api/people?q=King")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()), 1)

        r = self.client.delete(f"/api/people/{pid}")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["deleted"])

    def test_gedcom_import_and_tree(self):
        r = self.client.post("/api/import/gedcom", json={"gedcom": SAMPLE_GED})
        self.assertEqual(r.status_code, 200)
        summary = r.get_json()["imported"]
        self.assertEqual(summary["people"], 3)
        self.assertEqual(summary["families"], 1)

        r = self.client.get("/api/people?q=Smith")
        self.assertEqual(r.status_code, 200)
        smiths = r.get_json()
        john = next(p for p in smiths if p["given"] == "John")

        r = self.client.get(f"/api/tree/{john['id']}")
        self.assertEqual(r.status_code, 200)
        t = r.get_json()
        child_names = [c["given"] for c in t["children"]]
        self.assertIn("Baby", child_names)

    def test_notes(self):
        r = self.client.post("/api/people", json={"given":"Note","surname":"Tester"})
        pid = r.get_json()["id"]

        r = self.client.post(f"/api/people/{pid}/notes", json={"text":"hello"})
        self.assertEqual(r.status_code, 201)

        r = self.client.get(f"/api/people/{pid}")
        self.assertEqual(r.status_code, 200)
        notes = r.get_json()["notes"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["text"], "hello")


    def test_ui_index(self):
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Family Genealogy Tool', r.data)

if __name__ == "__main__":
    unittest.main()