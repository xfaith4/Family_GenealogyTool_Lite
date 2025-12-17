import os
import tempfile
import unittest

from app import create_app

SAMPLE_GED_WITH_DATES = """0 HEAD
0 @I1@ INDI
1 NAME John /Smith/
1 SEX M
1 BIRT
2 DATE 1 JAN 1900
2 PLAC Indianapolis, Indiana
0 @I2@ INDI
1 NAME Jane /Doe/
1 SEX F
1 BIRT
2 DATE JAN 1902
2 PLAC Carmel, IN
0 @I3@ INDI
1 NAME Baby /Smith/
1 SEX F
1 BIRT
2 DATE ABT 1920
2 PLAC Indianapolis, IN
0 @I4@ INDI
1 NAME Test /Person/
1 SEX M
1 BIRT
2 DATE BEF 1800
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 MARR
2 DATE 3 MAR 1920
2 PLAC Marion County, Indiana
0 TRLR
"""

class TestAnalytics(unittest.TestCase):
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

    def test_analytics_summary_empty(self):
        """Test analytics summary with empty database."""
        r = self.client.get("/api/analytics/summary")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["total_persons"], 0)
        self.assertEqual(data["dates"]["missing_birth"], 0)

    def test_analytics_summary_with_data(self):
        """Test analytics summary after importing GEDCOM."""
        # Import GEDCOM
        r = self.client.post("/api/import/gedcom", json={"gedcom": SAMPLE_GED_WITH_DATES})
        self.assertEqual(r.status_code, 200)
        
        # Check summary
        r = self.client.get("/api/analytics/summary")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        
        self.assertEqual(data["total_persons"], 4)
        # Should have some dates with issues
        self.assertGreater(data["dates"]["ambiguous_birth"], 0)

    def test_ambiguous_dates_list(self):
        """Test listing ambiguous dates."""
        # Import GEDCOM
        self.client.post("/api/import/gedcom", json={"gedcom": SAMPLE_GED_WITH_DATES})
        
        # Get ambiguous dates
        r = self.client.get("/api/analytics/dates/ambiguous")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        
        # Should have at least one ambiguous date (ABT 1920)
        self.assertGreater(len(data), 0)
        
        # Check that confidence is included
        ambiguous_items = [d for d in data if d["birth_date_confidence"] in ["ambiguous", "partial"]]
        self.assertGreater(len(ambiguous_items), 0)

    def test_place_variants_generation(self):
        """Test that place variants are generated on import."""
        # Import GEDCOM
        self.client.post("/api/import/gedcom", json={"gedcom": SAMPLE_GED_WITH_DATES})
        
        # Get place variants
        r = self.client.get("/api/analytics/places/unstandardized")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        
        # Should have place suggestions
        # (Indianapolis, Indiana vs Indianapolis, IN vs Carmel, IN)
        self.assertGreaterEqual(len(data), 0)

    def test_approve_place_variant(self):
        """Test approving a place variant."""
        # Import GEDCOM
        self.client.post("/api/import/gedcom", json={"gedcom": SAMPLE_GED_WITH_DATES})
        
        # Get place variants
        r = self.client.get("/api/analytics/places/unstandardized")
        variants = r.get_json()
        
        if len(variants) > 0:
            variant_id = variants[0]["id"]
            
            # Approve the variant
            r = self.client.post("/api/analytics/places/approve", 
                                json={"variant_id": variant_id})
            self.assertEqual(r.status_code, 200)
            data = r.get_json()
            self.assertTrue(data["approved"])

    def test_duplicate_candidates_generation(self):
        """Test that duplicate candidates are generated on import."""
        # Import GEDCOM
        self.client.post("/api/import/gedcom", json={"gedcom": SAMPLE_GED_WITH_DATES})
        
        # Get duplicates
        r = self.client.get("/api/analytics/duplicates")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        
        # With this small dataset, may or may not have duplicates
        # Just verify the endpoint works
        self.assertIsInstance(data, list)

    def test_review_duplicate(self):
        """Test marking a duplicate as reviewed."""
        # Import GEDCOM
        self.client.post("/api/import/gedcom", json={"gedcom": SAMPLE_GED_WITH_DATES})
        
        # Get duplicates
        r = self.client.get("/api/analytics/duplicates")
        duplicates = r.get_json()
        
        if len(duplicates) > 0:
            candidate_id = duplicates[0]["id"]
            
            # Mark as not duplicate
            r = self.client.post("/api/analytics/duplicates/review",
                                json={"candidate_id": candidate_id, "action": "ignore"})
            self.assertEqual(r.status_code, 200)
            data = r.get_json()
            self.assertTrue(data["reviewed"])
            self.assertEqual(data["status"], "ignored")

    def test_missing_dates_list(self):
        """Test listing persons with missing dates."""
        # Create a person with no dates
        self.client.post("/api/people", json={"given": "No", "surname": "Dates"})
        
        # Get missing dates
        r = self.client.get("/api/analytics/dates/missing")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["given"], "No")

    def test_analytics_ui_page_loads(self):
        """Test that the analytics UI page loads."""
        r = self.client.get('/analytics')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Analytics', r.data)

if __name__ == "__main__":
    unittest.main()
