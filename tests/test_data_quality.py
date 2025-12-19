import os
import tempfile
import unittest

from sqlalchemy.orm import sessionmaker

from app import create_app
from app.models import Person, Event, EventType, DateNormalization
from app.db import get_engine


class TestDataQuality(unittest.TestCase):
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
        self.Session = sessionmaker(bind=get_engine())

    def tearDown(self):
        self.tmpdir.cleanup()

    def _session(self):
        return self.Session()

    def _person(self, given, surname, birth_date=None, birth_place=None):
        with self._session() as s:
            p = Person(given=given, surname=surname, birth_date=birth_date, birth_place=birth_place)
            s.add(p)
            s.commit()
            return p.id

    def _event(self, person_id, raw_date=None, raw_place=None):
        with self._session() as s:
            ev = Event(event_type=EventType.BIRTH, person_id=person_id, date_raw=raw_date, place_raw=raw_place)
            s.add(ev)
            s.commit()
            return ev.id

    def test_scan_detects_duplicates(self):
        a = self._person("John", "Sample", "1980")
        b = self._person("Jon", "Sample", "1980")
        r = self.client.post("/api/dq/scan")
        self.assertEqual(r.status_code, 200)
        data = self.client.get("/api/dq/issues?type=duplicate_person").get_json()
        self.assertGreaterEqual(len(data["items"]), 1)

    def test_merge_people_moves_relationships(self):
        primary = self._person("Alice", "Merge", "1975")
        secondary = self._person("Alicia", "Merge", "1976")
        ev_id = self._event(secondary, raw_date="1 JAN 1999")

        resp = self.client.post(
            "/api/dq/actions/mergePeople",
            json={"fromId": secondary, "intoId": primary, "user": "tester"},
        )
        self.assertEqual(resp.status_code, 200)

        with self._session() as s:
            ev = s.get(Event, ev_id)
            self.assertEqual(ev.person_id, primary)
            self.assertIsNone(s.get(Person, secondary))

    def test_normalize_places_updates_references_and_undo(self):
        pid = self._person("Bob", "Place", birth_place="boston, mass")
        ev_id = self._event(pid, raw_place="boston, mass")

        resp = self.client.post(
            "/api/dq/actions/normalizePlaces",
            json={"canonical": "Boston, Massachusetts", "variants": ["boston, mass"], "user": "tester"},
        )
        self.assertEqual(resp.status_code, 200)
        action_id = resp.get_json()["action_id"]

        with self._session() as s:
            ev = s.get(Event, ev_id)
            self.assertIsNotNone(ev.place_id)
            person = s.get(Person, pid)
            self.assertEqual(person.birth_place, "Boston, Massachusetts")

        undo = self.client.post("/api/dq/actions/undo", json={"action_id": action_id})
        self.assertEqual(undo.status_code, 200)
        with self._session() as s:
            ev = s.get(Event, ev_id)
            self.assertIsNone(ev.place_id)

    def test_normalize_dates_and_undo(self):
        pid = self._person("Cara", "Dates")
        ev_id = self._event(pid, raw_date="3/4/1881")

        resp = self.client.post(
            "/api/dq/actions/normalizeDates",
            json={
                "items": [
                    {
                        "entity_type": "event",
                        "entity_id": ev_id,
                        "normalized": "1881-03-04",
                        "precision": "day",
                        "qualifier": None,
                        "raw": "3/4/1881",
                        "confidence": 0.9,
                        "ambiguous": False,
                    }
                ],
                "user": "tester",
            },
        )
        self.assertEqual(resp.status_code, 200)
        action_id = resp.get_json()["action_id"]

        with self._session() as s:
            dn = s.query(DateNormalization).filter_by(entity_id=ev_id, entity_type="event").first()
            self.assertIsNotNone(dn)
            ev = s.get(Event, ev_id)
            self.assertIsNotNone(ev.date_canonical)
            self.assertEqual(dn.normalized, "1881-03-04")

        undo = self.client.post("/api/dq/actions/undo", json={"action_id": action_id})
        self.assertEqual(undo.status_code, 200)
        with self._session() as s:
            dn = s.query(DateNormalization).filter_by(entity_id=ev_id, entity_type="event").first()
            self.assertIsNone(dn)
            ev = s.get(Event, ev_id)
            self.assertIsNone(ev.date_canonical)


if __name__ == "__main__":
    unittest.main()
