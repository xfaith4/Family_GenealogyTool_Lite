import os
import tempfile
import unittest

from app import create_app
from app.db import get_session, get_engine
from app.models import Base, Person, Family


class TestAnalyticsDrilldown(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.sqlite")
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.db_path,
                "MEDIA_DIR": os.path.join(self.tmpdir.name, "media"),
                "MEDIA_INGEST_DIR": os.path.join(self.tmpdir.name, "media_ingest"),
            }
        )
        with self.app.app_context():
            engine = get_engine()
            Base.metadata.create_all(engine)
            self._seed()
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _seed(self):
        session = get_session()
        p1 = Person(given="John", surname="Smith", birth_date="1 JAN 1980", death_date="1 JAN 2020", birth_place="Berlin", death_place="Paris")
        p2 = Person(given="Jane", surname="Smith", birth_date="1 FEB 1982", death_date=None, birth_place="Berlin", death_place=None)
        p3 = Person(given="Elena", surname="Garcia", birth_date="1 MAR 1955", death_date="1 JAN 2010", birth_place="Madrid", death_place="Paris")
        session.add_all([p1, p2, p3])
        session.flush()
        fam = Family(husband_person_id=p1.id, wife_person_id=p2.id, marriage_date="15 MAY 2005")
        session.add(fam)
        session.commit()

    def test_drilldown_by_surname(self):
        res = self.client.post("/api/analytics/drilldown", json={"type": "surname", "filters": {"surname": "Smith"}})
        body = res.get_json()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(body["total"], 2)
        ids = {item["surname"] for item in body["items"]}
        self.assertEqual(ids, {"Smith"})

    def test_drilldown_by_birth_place(self):
        res = self.client.post("/api/analytics/drilldown", json={"type": "birth_place", "filters": {"place": "berlin"}})
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["total"], 2)
        for item in body["items"]:
            self.assertEqual((item["birth_place"] or "").lower(), "berlin")

    def test_drilldown_marriage_decade(self):
        res = self.client.post("/api/analytics/drilldown", json={"type": "marriage_decade", "filters": {"decade": 2000}})
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        ids = {p["surname"] for p in body["items"]}
        self.assertIn("Smith", ids)
        self.assertEqual(body["total"], 2)
