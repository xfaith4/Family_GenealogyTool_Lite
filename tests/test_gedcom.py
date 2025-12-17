import unittest
from app.gedcom import parse_gedcom

SAMPLE = """0 HEAD
1 SOUR TEST
0 @I1@ INDI
1 NAME John /Smith/
1 SEX M
1 BIRT
2 DATE 1 JAN 1900
2 PLAC Indianapolis, Indiana
1 NOTE A sample note.
0 @I2@ INDI
1 NAME Jane /Doe/
1 SEX F
1 BIRT
2 DATE 2 FEB 1902
2 PLAC Carmel, Indiana
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 MARR
2 DATE 3 MAR 1920
2 PLAC Marion County
0 @I3@ INDI
1 NAME Baby /Smith/
1 SEX F
0 TRLR
"""

class TestGedcomParser(unittest.TestCase):
    def test_parse_counts(self):
        indis, fams = parse_gedcom(SAMPLE)
        self.assertEqual(len(indis), 3)
        self.assertEqual(len(fams), 1)

    def test_person_fields(self):
        indis, _ = parse_gedcom(SAMPLE)
        i1 = indis["@I1@"]
        self.assertEqual(i1.given, "John")
        self.assertEqual(i1.surname, "Smith")
        self.assertEqual(i1.sex, "M")
        self.assertEqual(i1.birth_date, "1 JAN 1900")
        self.assertIn("Indianapolis", i1.birth_place)
        self.assertTrue(any("sample note" in n.lower() for n in i1.notes))

    def test_family_fields(self):
        _, fams = parse_gedcom(SAMPLE)
        f1 = fams["@F1@"]
        self.assertEqual(f1.husb, "@I1@")
        self.assertEqual(f1.wife, "@I2@")
        self.assertEqual(f1.chil, ["@I3@"])
        self.assertEqual(f1.marriage_date, "3 MAR 1920")
        self.assertIn("Marion", f1.marriage_place)

if __name__ == "__main__":
    unittest.main()
