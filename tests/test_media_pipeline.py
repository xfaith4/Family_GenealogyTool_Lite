import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app import create_app
from app.db import get_engine
from app.media_pipeline import MediaIngestService, MediaPaths, normalize_path, match_candidates
from app.models import MediaAsset


class TestMediaPipeline(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.sqlite")
        self.media_dir = os.path.join(self.tmpdir.name, "media")
        self.ingest_dir = os.path.join(self.tmpdir.name, "media_ingest")
        os.makedirs(self.media_dir, exist_ok=True)
        os.makedirs(self.ingest_dir, exist_ok=True)

        self.app = create_app({
            "TESTING": True,
            "DATABASE": self.db_path,
            "MEDIA_DIR": self.media_dir,
            "MEDIA_INGEST_DIR": self.ingest_dir,
        })
        self.Session = sessionmaker(bind=get_engine())

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_register_asset_idempotent(self):
        file_path = Path(self.ingest_dir) / "sample.txt"
        file_path.write_text("hello", encoding="utf-8")
        paths = MediaPaths(Path(self.media_dir), Path(self.ingest_dir))

        with self.app.app_context():
            session = self.Session()
            try:
                ingest = MediaIngestService(session, paths)
                ingest.register_asset(file_path)
                ingest.register_asset(file_path)
                count = session.query(MediaAsset).count()
                self.assertEqual(count, 1)
            finally:
                session.close()

    def test_normalize_path_windows(self):
        win_path = r"C:\Users\Me\Media\Photo.JPG"
        posix_path = "/Users/Me/Media/photo.jpg"
        self.assertEqual(normalize_path(win_path), "users/me/media/photo.jpg")
        self.assertEqual(normalize_path(posix_path), "users/me/media/photo.jpg")

    def test_legacy_match_basename(self):
        file_path = Path(self.media_dir) / "photo.png"
        file_path.write_bytes(b"fake-image")
        paths = MediaPaths(Path(self.media_dir), Path(self.ingest_dir))

        with self.app.app_context():
            session = self.Session()
            try:
                ingest = MediaIngestService(session, paths)
                asset, _ = ingest.register_asset(file_path)
                assets = [asset]
                candidates = match_candidates(r"C:\legacy\Photo.png", None, assets, Path(self.media_dir), Path(self.ingest_dir))
                self.assertTrue(any(c["method"] == "basename" for c in candidates))
                self.assertGreaterEqual(max(c["confidence"] for c in candidates), 0.8)
            finally:
                session.close()


if __name__ == "__main__":
    unittest.main()
