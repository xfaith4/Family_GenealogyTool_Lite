import os
import tempfile
import unittest

from sqlalchemy.orm import sessionmaker

from app import create_app
from app.models import Person, Event, EventType, DateNormalization, Family, MediaAsset, MediaLink, family_children, relationships
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

    def _person(self, given, surname, birth_date=None, birth_place=None, death_date=None, death_place=None):
        with self._session() as s:
            p = Person(
                given=given,
                surname=surname,
                birth_date=birth_date,
                birth_place=birth_place,
                death_date=death_date,
                death_place=death_place,
            )
            s.add(p)
            s.commit()
            return p.id

    def _event(self, person_id, raw_date=None, raw_place=None):
        with self._session() as s:
            ev = Event(event_type=EventType.BIRTH, person_id=person_id, date_raw=raw_date, place_raw=raw_place)
            s.add(ev)
            s.commit()
            return ev.id

    def _family(self, husband_id=None, wife_id=None, marriage_date=None, marriage_place=None, children=None):
        with self._session() as s:
            fam = Family(
                husband_person_id=husband_id,
                wife_person_id=wife_id,
                marriage_date=marriage_date,
                marriage_place=marriage_place,
            )
            s.add(fam)
            s.commit()
            if children:
                for cid in children:
                    s.execute(
                        family_children.insert().values(family_id=fam.id, child_person_id=cid)
                    )
                s.commit()
            return fam.id

    def _media_link(self, person_id):
        with self._session() as s:
            asset = MediaAsset(
                path="x.jpg",
                sha256="a" * 64,
                original_filename="x.jpg",
            )
            s.add(asset)
            s.commit()
            link1 = MediaLink(asset_id=asset.id, person_id=person_id)
            link2 = MediaLink(asset_id=asset.id, person_id=person_id)
            s.add_all([link1, link2])
            s.commit()
            return asset.id, [link1.id, link2.id]

    def _media_asset(self, filename, sha, size_bytes=1000):
        with self._session() as s:
            asset = MediaAsset(
                path=filename,
                sha256=sha,
                original_filename=filename,
                size_bytes=size_bytes,
            )
            s.add(asset)
            s.commit()
            return asset.id

    def test_scan_detects_duplicates(self):
        a = self._person("John", "Sample", "1980")
        b = self._person("Jon", "Sample", "1980")
        r = self.client.post("/api/dq/scan")
        self.assertEqual(r.status_code, 200)
        data = self.client.get("/api/dq/issues?type=duplicate_person").get_json()
        self.assertGreaterEqual(len(data["items"]), 1)

    def test_scan_detects_standardization_suggestions(self):
        pid = self._person("JOHN", "DOE ")
        r = self.client.post("/api/dq/scan")
        self.assertEqual(r.status_code, 200)
        data = self.client.get("/api/dq/issues?type=field_standardization").get_json()
        target = next((i for i in data["items"] if pid in i["entity_ids"]), None)
        self.assertIsNotNone(target)
        fields = target["explanation"].get("fields") or []
        suggestions = {f.get("field"): f.get("suggested") for f in fields}
        self.assertEqual(suggestions.get("given"), "John")
        self.assertEqual(suggestions.get("surname"), "Doe")

    def test_scan_detects_similar_places(self):
        pid = self._person("Mara", "Place", birth_place="Boston, Massachusett")
        self._event(pid, raw_place="Boston, Massachusetts")
        r = self.client.post("/api/dq/scan")
        self.assertEqual(r.status_code, 200)
        data = self.client.get("/api/dq/issues?type=place_similarity").get_json()
        self.assertGreaterEqual(len(data["items"]), 1)

    def test_scan_detects_duplicate_families(self):
        h = self._person("Henry", "Family")
        w = self._person("Helen", "Family")
        self._family(husband_id=h, wife_id=w, marriage_date="1900", marriage_place="Town")
        self._family(husband_id=h, wife_id=w, marriage_date="1900", marriage_place="Town")
        r = self.client.post("/api/dq/scan")
        self.assertEqual(r.status_code, 200)
        data = self.client.get("/api/dq/issues?type=duplicate_family").get_json()
        self.assertGreaterEqual(len(data["items"]), 1)

    def test_merge_families_moves_children(self):
        h = self._person("Gary", "Family")
        w = self._person("Gina", "Family")
        c = self._person("Greg", "Family")
        primary = self._family(husband_id=h, wife_id=w, marriage_date="1905", children=[c])
        secondary = self._family(husband_id=h, wife_id=w, marriage_date="1905")

        resp = self.client.post(
            "/api/dq/actions/mergeFamilies",
            json={"fromId": secondary, "intoId": primary, "user": "tester"},
        )
        self.assertEqual(resp.status_code, 200)
        with self._session() as s:
            rows = s.execute(
                family_children.select().where(family_children.c.family_id == primary)
            ).all()
            self.assertTrue(any(row.child_person_id == c for row in rows))
            self.assertIsNone(s.get(Family, secondary))

    def test_scan_detects_duplicate_media_links(self):
        pid = self._person("Mia", "Media")
        self._media_link(pid)
        r = self.client.post("/api/dq/scan")
        self.assertEqual(r.status_code, 200)
        data = self.client.get("/api/dq/issues?type=duplicate_media_link").get_json()
        self.assertGreaterEqual(len(data["items"]), 1)

    def test_scan_detects_duplicate_media_assets(self):
        self._media_asset("family_photo.jpg", "b" * 64, size_bytes=2048)
        self._media_asset("family photo.JPG", "c" * 64, size_bytes=2050)
        r = self.client.post("/api/dq/scan")
        self.assertEqual(r.status_code, 200)
        data = self.client.get("/api/dq/issues?type=duplicate_media_asset").get_json()
        self.assertGreaterEqual(len(data["items"]), 1)

    def test_merge_media_assets(self):
        pid = self._person("Nina", "Media")
        asset_keep = self._media_asset("scan1.jpg", "d" * 64, size_bytes=1111)
        asset_drop = self._media_asset("scan 1.JPG", "e" * 64, size_bytes=1111)
        with self._session() as s:
            link = MediaLink(asset_id=asset_drop, person_id=pid)
            s.add(link)
            s.commit()
            link_id = link.id

        resp = self.client.post(
            "/api/dq/actions/mergeMediaAssets",
            json={"fromId": asset_drop, "intoId": asset_keep, "user": "tester"},
        )
        self.assertEqual(resp.status_code, 200)
        action_id = resp.get_json()["action_id"]

        with self._session() as s:
            self.assertIsNotNone(s.get(MediaAsset, asset_keep))
            self.assertIsNone(s.get(MediaAsset, asset_drop))
            link = s.get(MediaLink, link_id)
            self.assertEqual(link.asset_id, asset_keep)

        undo = self.client.post("/api/dq/actions/undo", json={"action_id": action_id})
        self.assertEqual(undo.status_code, 200)
        with self._session() as s:
            self.assertIsNotNone(s.get(MediaAsset, asset_drop))
            link = s.get(MediaLink, link_id)
            self.assertEqual(link.asset_id, asset_drop)

    def test_scan_detects_duplicate_family_spouse_swaps(self):
        h1 = self._person("James", "Smith")
        w1 = self._person("Julia", "Smith")
        h2 = self._person("James", "Smith")
        w2 = self._person("Julia", "Smith")
        self._family(husband_id=h1, wife_id=w1, marriage_date="1920", marriage_place="Town")
        self._family(husband_id=h2, wife_id=w2, marriage_date="1920", marriage_place="Town")
        r = self.client.post("/api/dq/scan")
        self.assertEqual(r.status_code, 200)
        data = self.client.get("/api/dq/issues?type=duplicate_family_spouse_swap").get_json()
        self.assertGreaterEqual(len(data["items"]), 1)

    def test_scan_detects_integrity_warnings(self):
        parent = self._person("Paul", "Parent", birth_date="2000", death_date="2001")
        child = self._person("Chris", "Child", birth_date="2003")
        with self._session() as s:
            s.execute(relationships.insert().values(
                parent_person_id=parent,
                child_person_id=child,
                rel_type="parent",
            ))
            s.commit()
        self._family(marriage_date="1990")

        r = self.client.post("/api/dq/scan")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(
            len(self.client.get("/api/dq/issues?type=parent_child_age").get_json()["items"]), 1
        )
        self.assertGreaterEqual(
            len(self.client.get("/api/dq/issues?type=parent_child_death").get_json()["items"]), 1
        )
        self.assertGreaterEqual(
            len(self.client.get("/api/dq/issues?type=orphan_family").get_json()["items"]), 1
        )

    def test_scan_detects_marriage_timeline_issues(self):
        spouse = self._person("Mona", "Married", birth_date="2000", death_date="2005")
        self._family(husband_id=spouse, marriage_date="1995")
        self._family(husband_id=spouse, marriage_date="2010")

        r = self.client.post("/api/dq/scan")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(
            len(self.client.get("/api/dq/issues?type=marriage_too_early").get_json()["items"]), 1
        )
        self.assertGreaterEqual(
            len(self.client.get("/api/dq/issues?type=marriage_after_death").get_json()["items"]), 1
        )

    def test_normalize_dates_preserves_qualifier(self):
        pid = self._person("Ava", "About", birth_date="About 1900")
        r = self.client.post("/api/dq/scan")
        self.assertEqual(r.status_code, 200)
        issues = self.client.get("/api/dq/issues?type=date_normalization").get_json()["items"]
        target = next(
            (i for i in issues if i["entity_type"] == "person" and pid in i["entity_ids"]),
            None,
        )
        self.assertIsNotNone(target)
        explanation = target["explanation"]
        resp = self.client.post(
            "/api/dq/actions/normalizeDates",
            json={
                "items": [
                    {
                        "entity_type": "person",
                        "entity_id": pid,
                        "normalized": explanation.get("normalized"),
                        "precision": explanation.get("precision"),
                        "qualifier": explanation.get("qualifier"),
                        "raw": explanation.get("raw"),
                        "confidence": target.get("confidence"),
                        "ambiguous": explanation.get("ambiguous"),
                        "field": explanation.get("field"),
                    }
                ],
                "user": "tester",
            },
        )
        self.assertEqual(resp.status_code, 200)
        with self._session() as s:
            person = s.get(Person, pid)
            self.assertEqual(person.birth_date, "About 1900")

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

    def test_standardize_fields_action_and_undo(self):
        pid = self._person("JANE", "DOE ")
        resp = self.client.post(
            "/api/dq/actions/standardizeFields",
            json={
                "items": [
                    {
                        "entity_type": "person",
                        "entity_id": pid,
                        "updates": {"given": "Jane", "surname": "Doe"},
                    }
                ],
                "user": "tester",
            },
        )
        self.assertEqual(resp.status_code, 200)
        action_id = resp.get_json()["action_id"]

        with self._session() as s:
            person = s.get(Person, pid)
            self.assertEqual(person.given, "Jane")
            self.assertEqual(person.surname, "Doe")

        undo = self.client.post("/api/dq/actions/undo", json={"action_id": action_id})
        self.assertEqual(undo.status_code, 200)
        with self._session() as s:
            person = s.get(Person, pid)
            self.assertEqual(person.given, "JANE")
            self.assertEqual(person.surname, "DOE ")


if __name__ == "__main__":
    unittest.main()
