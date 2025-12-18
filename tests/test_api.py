import io
import os
import tempfile
import unittest
from sqlalchemy import select

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

SAMPLE_RMTREE = """-- RMTree export sample
INSERT INTO Individuals (Id, GivenName, Surname, Gender, BirthDate, BirthPlace, Notes) VALUES
(1, 'John', 'Smith', 'M', '1 JAN 1980', 'Springfield', 'Patriarch'),
(2, 'Jane', 'Doe', 'F', '2 FEB 1982', 'Springfield', 'Matriarch'),
(3, 'Baby', 'Smith', 'F', '3 MAR 2005', 'Springfield', 'Child');
INSERT INTO Relationships (ParentID, ChildID) VALUES
(1, 3),
(2, 3);
INSERT INTO MediaLocations (MediaID, Path, OriginalName, Description) VALUES
(10, 'photos/john.png', 'John.png', 'Portrait'),
(11, 'photos/jane.png', 'Jane.jpg', 'Portrait');
INSERT INTO MediaAssociations (MediaID, OwnerType, OwnerID) VALUES
(10, 'Person', 1),
(11, 'Person', 2);
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
        
        # Create database tables using SQLAlchemy
        from app.db import get_engine
        from app.models import Base
        with self.app.app_context():
            engine = get_engine()
            Base.metadata.create_all(engine)
        
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_migration_creates_empty_db(self):
        """Test that migration creates an empty database with all required tables."""
        from app.db import get_engine
        from sqlalchemy import inspect
        
        with self.app.app_context():
            engine = get_engine()
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            
            # Check all required tables exist
            required_tables = [
                'persons', 'families', 'events', 'places', 'place_variants',
                'media_assets', 'media_links', 'notes', 'data_quality_flags',
                'family_children', 'relationships'
            ]
            for table in required_tables:
                self.assertIn(table, tables, f"Table {table} should exist")
            
            # Verify tables are empty
            from app.db import get_session
            from app.models import Person, Family
            session = get_session()
            self.assertEqual(session.query(Person).count(), 0)
            self.assertEqual(session.query(Family).count(), 0)

    def test_gedcom_import_populates_expected_rows(self):
        """Test that GEDCOM import populates expected rows in the database."""
        r = self.client.post("/api/import/gedcom", json={"gedcom": SAMPLE_GED})
        self.assertEqual(r.status_code, 200)
        summary = r.get_json()["imported"]
        self.assertEqual(summary["people"], 3)
        self.assertEqual(summary["families"], 1)
        
        # Verify data was actually written to database
        from app.db import get_session
        from app.models import Person, Family
        
        with self.app.app_context():
            session = get_session()
            
            # Check persons count
            persons = session.query(Person).all()
            self.assertEqual(len(persons), 3)
            
            # Check families count
            families = session.query(Family).all()
        self.assertEqual(len(families), 1)
        
        # Verify specific person data
        john = session.query(Person).filter(Person.given == "John", Person.surname == "Smith").first()
        self.assertIsNotNone(john)
        self.assertEqual(john.sex, "M")
        
        # Verify family structure
        family = families[0]
        self.assertIsNotNone(family.husband_person_id)
        self.assertIsNotNone(family.wife_person_id)

    def test_rmtree_import_populates_people_and_media(self):
        payload = {
            "file": (io.BytesIO(SAMPLE_RMTREE.encode("utf-8")), "sample.rmtree")
        }
        r = self.client.post(
            "/api/import/rmtree",
            data=payload,
            content_type="multipart/form-data"
        )
        self.assertEqual(r.status_code, 200)
        summary = r.get_json()["imported"]
        self.assertEqual(summary["people"], 3)
        self.assertEqual(summary["media_assets"], 2)
        self.assertEqual(summary["media_links"], 2)
        self.assertEqual(summary["relationships"], 2)

        with self.app.app_context():
            from app.db import get_session
            session = get_session()
            from app.models import MediaAsset, MediaLink, Person, relationships

            john = session.query(Person).filter(Person.given == "John").first()
            self.assertIsNotNone(john)

            assets = session.query(MediaAsset).all()
            self.assertEqual(len(assets), 2)

            john_links = session.query(MediaLink).filter(MediaLink.person_id == john.id).all()
            self.assertEqual(len(john_links), 1)
            self.assertEqual(john_links[0].description, "Portrait")

            rels = session.execute(select(relationships)).all()
            self.assertEqual(len(rels), 2)

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

    def test_graph_endpoint(self):
        # Import sample GEDCOM
        r = self.client.post("/api/import/gedcom", json={"gedcom": SAMPLE_GED})
        self.assertEqual(r.status_code, 200)
        
        # Find John Smith
        r = self.client.get("/api/people?q=John")
        people = r.get_json()
        john = next((p for p in people if p["given"] == "John"), None)
        self.assertIsNotNone(john, "John Smith should exist in imported GEDCOM")
        
        # Get graph with depth 2
        r = self.client.get(f"/api/graph?rootPersonId={john['id']}&depth=2")
        self.assertEqual(r.status_code, 200)
        
        graph = r.get_json()
        self.assertIn("nodes", graph)
        self.assertIn("edges", graph)
        self.assertEqual(graph["rootPersonId"], john["id"])
        self.assertEqual(graph["depth"], 2)
        
        # Check we have person nodes
        person_nodes = [n for n in graph["nodes"] if n["type"] == "person"]
        self.assertGreater(len(person_nodes), 0)
        
        # Check person node structure
        john_node = next((n for n in person_nodes if n["data"]["id"] == john["id"]), None)
        self.assertIsNotNone(john_node)
        self.assertIn("quality", john_node["data"])
        self.assertEqual(john_node["data"]["given"], "John")
        
        # Check we have family nodes
        family_nodes = [n for n in graph["nodes"] if n["type"] == "family"]
        self.assertGreater(len(family_nodes), 0)
        
        # Check edges exist
        self.assertGreater(len(graph["edges"]), 0)
        
    def test_graph_missing_person(self):
        r = self.client.get("/api/graph?rootPersonId=99999&depth=2")
        self.assertEqual(r.status_code, 404)
        
    def test_graph_missing_root_param(self):
        r = self.client.get("/api/graph?depth=2")
        self.assertEqual(r.status_code, 400)

if __name__ == "__main__":
    unittest.main()
