import os
import io
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from app import create_app


def _write_image(path: Path, color=(10, 20, 30)):
    img = Image.new("RGB", (32, 32), color)
    with open(path, "wb") as fh:
        img.save(fh, format="PNG")


class TestMediaIngest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.sqlite")
        self.media_dir = os.path.join(self.tmpdir.name, "media")
        self.media_ingest = os.path.join(self.tmpdir.name, "media_ingest")
        os.makedirs(self.media_dir, exist_ok=True)
        os.makedirs(self.media_ingest, exist_ok=True)

        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.db_path,
                "MEDIA_DIR": self.media_dir,
                "MEDIA_INGEST_DIR": self.media_ingest,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_ingest_scan_populates_unassigned(self):
        img_path = Path(self.media_ingest) / "ingest.png"
        _write_image(img_path)

        r = self.client.get("/api/media/unassigned")
        self.assertEqual(r.status_code, 200)
        unassigned = r.get_json()
        self.assertEqual(len(unassigned), 1)
        asset = unassigned[0]
        self.assertEqual(asset["status"], "unassigned")
        # second call should not duplicate
        r = self.client.get("/api/media/unassigned")
        self.assertEqual(len(r.get_json()), 1)

    def test_assign_endpoint_sets_status(self):
        img_path = Path(self.media_ingest) / "to_assign.png"
        _write_image(img_path, color=(200, 10, 10))

        r = self.client.get("/api/media/unassigned")
        asset_id = r.get_json()[0]["id"]

        r = self.client.post("/api/people", json={"given": "Assign", "surname": "Target"})
        person_id = r.get_json()["id"]

        r = self.client.post(
            "/api/media/assign",
            json={"media_id": asset_id, "person_id": person_id},
        )
        self.assertIn(r.status_code, (200, 201))

        r = self.client.get("/api/media/unassigned")
        self.assertEqual(len(r.get_json()), 0)

        r = self.client.get("/api/media/assets")
        asset = next(a for a in r.get_json() if a["id"] == asset_id)
        self.assertEqual(asset["status"], "assigned")


if __name__ == "__main__":
    unittest.main()
