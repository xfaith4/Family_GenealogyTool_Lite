import os
import io
import tempfile
import unittest
from PIL import Image

from app import create_app

class TestMediaV2(unittest.TestCase):
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

    def create_test_image(self, width=100, height=100, color=(255, 0, 0), format='PNG'):
        """Create a test image in memory."""
        img = Image.new('RGB', (width, height), color)
        img_io = io.BytesIO()
        img.save(img_io, format)
        img_io.seek(0)
        return img_io

    def test_upload_image_creates_thumbnail(self):
        """Test that uploading an image creates a thumbnail."""
        # Create a test image
        img_data = self.create_test_image(width=800, height=600)
        
        # Upload without linking
        r = self.client.post(
            "/api/media/upload",
            data={
                "file": (img_data, "test.png", "image/png"),
            },
            content_type="multipart/form-data"
        )
        
        self.assertEqual(r.status_code, 201)
        result = r.get_json()
        
        self.assertIn("asset_id", result)
        self.assertIn("sha256", result)
        self.assertIn("thumbnail_path", result)
        self.assertIsNotNone(result["thumbnail_path"])
        
        # Check thumbnail file exists
        thumb_path = os.path.join(self.media_dir, result["thumbnail_path"])
        self.assertTrue(os.path.exists(thumb_path))

    def test_upload_with_person_link(self):
        """Test uploading media and linking to a person."""
        # Create a person
        r = self.client.post("/api/people", json={"given": "Test", "surname": "User"})
        person_id = r.get_json()["id"]
        
        # Upload image and link to person
        img_data = self.create_test_image()
        r = self.client.post(
            "/api/media/upload",
            data={
                "file": (img_data, "portrait.jpg", "image/jpeg"),
                "person_id": str(person_id),
            },
            content_type="multipart/form-data"
        )
        
        self.assertEqual(r.status_code, 201)
        result = r.get_json()
        self.assertIsNotNone(result["link_id"])
        
        # Verify link was created
        r = self.client.get(f"/api/people/{person_id}/media/v2")
        self.assertEqual(r.status_code, 200)
        media_list = r.get_json()
        self.assertEqual(len(media_list), 1)
        self.assertEqual(media_list[0]["asset_id"], result["asset_id"])

    def test_deduplication_by_hash(self):
        """Test that uploading the same file twice doesn't duplicate the asset."""
        # Create a test image
        img_data1 = self.create_test_image(color=(100, 100, 100))
        img_data2 = self.create_test_image(color=(100, 100, 100))
        
        # Upload same image twice
        r1 = self.client.post(
            "/api/media/upload",
            data={"file": (img_data1, "test1.png", "image/png")},
            content_type="multipart/form-data"
        )
        sha1 = r1.get_json()["sha256"]
        
        r2 = self.client.post(
            "/api/media/upload",
            data={"file": (img_data2, "test2.png", "image/png")},
            content_type="multipart/form-data"
        )
        sha2 = r2.get_json()["sha256"]
        
        # Should have same hash and asset_id
        self.assertEqual(sha1, sha2)
        self.assertEqual(r1.get_json()["asset_id"], r2.get_json()["asset_id"])

    def test_unassigned_media_list(self):
        """Test listing unassigned media."""
        # Upload without linking
        img_data = self.create_test_image()
        r = self.client.post(
            "/api/media/upload",
            data={"file": (img_data, "unassigned.png", "image/png")},
            content_type="multipart/form-data"
        )
        self.assertEqual(r.status_code, 201)
        
        # Check unassigned list
        r = self.client.get("/api/media/unassigned")
        self.assertEqual(r.status_code, 200)
        unassigned = r.get_json()
        self.assertEqual(len(unassigned), 1)

    def test_link_unlink_workflow(self):
        """Test linking and unlinking media to a person."""
        # Create person and upload media
        r = self.client.post("/api/people", json={"given": "Jane", "surname": "Doe"})
        person_id = r.get_json()["id"]
        
        img_data = self.create_test_image()
        r = self.client.post(
            "/api/media/upload",
            data={"file": (img_data, "photo.png", "image/png")},
            content_type="multipart/form-data"
        )
        asset_id = r.get_json()["asset_id"]
        
        # Verify it's unassigned
        r = self.client.get("/api/media/unassigned")
        self.assertEqual(len(r.get_json()), 1)
        
        # Link to person
        r = self.client.post(
            "/api/media/link",
            json={"asset_id": asset_id, "person_id": person_id}
        )
        self.assertEqual(r.status_code, 201)
        link_id = r.get_json()["link_id"]
        
        # Verify no longer unassigned
        r = self.client.get("/api/media/unassigned")
        self.assertEqual(len(r.get_json()), 0)
        
        # Verify appears in person's media
        r = self.client.get(f"/api/people/{person_id}/media/v2")
        self.assertEqual(len(r.get_json()), 1)
        
        # Unlink
        r = self.client.delete(f"/api/media/link/{link_id}")
        self.assertEqual(r.status_code, 200)
        
        # Verify it's unassigned again
        r = self.client.get("/api/media/unassigned")
        self.assertEqual(len(r.get_json()), 1)

    def test_analytics_orphaned_media(self):
        """Test analytics for orphaned media."""
        # Upload 2 images without linking
        for i in range(2):
            img_data = self.create_test_image(color=(i*10, i*10, i*10))
            self.client.post(
                "/api/media/upload",
                data={"file": (img_data, f"test{i}.png", "image/png")},
                content_type="multipart/form-data"
            )
        
        # Check analytics
        r = self.client.get("/api/analytics/orphaned-media")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["orphaned_count"], 2)

    def test_analytics_people_without_media(self):
        """Test analytics for people without media."""
        # Create 3 people
        for i in range(3):
            self.client.post("/api/people", json={"given": f"Person{i}", "surname": "Test"})
        
        # Check analytics - all should have no media
        r = self.client.get("/api/analytics/people-without-media")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["people_without_media"], 3)
        
        # Link media to one person
        r = self.client.get("/api/people")
        person_id = r.get_json()[0]["id"]
        
        img_data = self.create_test_image()
        r = self.client.post(
            "/api/media/upload",
            data={"file": (img_data, "test.png", "image/png"), "person_id": str(person_id)},
            content_type="multipart/form-data"
        )
        
        # Check analytics again - should be 2 without media
        r = self.client.get("/api/analytics/people-without-media")
        self.assertEqual(r.get_json()["people_without_media"], 2)

    def test_upload_non_image_file(self):
        """Test uploading non-image files (PDF, video) without thumbnail generation."""
        # Create a fake PDF
        pdf_data = io.BytesIO(b"%PDF-1.4\nfake pdf content")
        
        r = self.client.post(
            "/api/media/upload",
            data={"file": (pdf_data, "document.pdf", "application/pdf")},
            content_type="multipart/form-data"
        )
        
        self.assertEqual(r.status_code, 201)
        result = r.get_json()
        
        # Should have no thumbnail
        self.assertIsNone(result["thumbnail_path"])

    def test_list_all_assets(self):
        """Test listing all media assets."""
        # Upload 3 different images
        for i in range(3):
            img_data = self.create_test_image(color=(i*50, i*50, i*50))
            self.client.post(
                "/api/media/upload",
                data={"file": (img_data, f"photo{i}.png", "image/png")},
                content_type="multipart/form-data"
            )
        
        # List all assets
        r = self.client.get("/api/media/assets")
        self.assertEqual(r.status_code, 200)
        assets = r.get_json()
        self.assertEqual(len(assets), 3)
        
        # Check each has expected fields
        for asset in assets:
            self.assertIn("id", asset)
            self.assertIn("path", asset)
            self.assertIn("sha256", asset)
            self.assertIn("link_count", asset)

    def test_thumbnail_dimensions(self):
        """Test that thumbnails have correct maximum dimensions."""
        # Create large image
        img_data = self.create_test_image(width=2000, height=1500)
        
        r = self.client.post(
            "/api/media/upload",
            data={"file": (img_data, "large.png", "image/png")},
            content_type="multipart/form-data"
        )
        
        result = r.get_json()
        
        # Get asset details
        r = self.client.get("/api/media/assets")
        assets = r.get_json()
        asset = next(a for a in assets if a["id"] == result["asset_id"])
        
        # Thumbnail should be scaled down but maintain aspect ratio
        self.assertIsNotNone(asset["thumb_width"])
        self.assertIsNotNone(asset["thumb_height"])
        self.assertLessEqual(asset["thumb_width"], 300)
        self.assertLessEqual(asset["thumb_height"], 300)

if __name__ == "__main__":
    unittest.main()
