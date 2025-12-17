import unittest
from app.date_parser import parse_date

class TestDateParser(unittest.TestCase):
    def test_exact_dates(self):
        """Test parsing of exact GEDCOM dates."""
        canonical, confidence = parse_date("1 JAN 1900")
        self.assertEqual(canonical, "1900-01-01")
        self.assertEqual(confidence, "exact")
        
        canonical, confidence = parse_date("25 DEC 2000")
        self.assertEqual(canonical, "2000-12-25")
        self.assertEqual(confidence, "exact")
    
    def test_partial_dates_month_year(self):
        """Test dates with only month and year."""
        canonical, confidence = parse_date("JAN 1900")
        self.assertEqual(canonical, "1900-01-01")
        self.assertEqual(confidence, "partial")
        
        canonical, confidence = parse_date("DEC 1950")
        self.assertEqual(canonical, "1950-12-01")
        self.assertEqual(confidence, "partial")
    
    def test_partial_dates_year_only(self):
        """Test dates with only year."""
        canonical, confidence = parse_date("1900")
        self.assertEqual(canonical, "1900-01-01")
        self.assertEqual(confidence, "partial")
        
        canonical, confidence = parse_date("2024")
        self.assertEqual(canonical, "2024-01-01")
        self.assertEqual(confidence, "partial")
    
    def test_ambiguous_dates(self):
        """Test dates with qualifiers."""
        canonical, confidence = parse_date("ABT 1900")
        self.assertEqual(canonical, "1900-01-01")
        self.assertEqual(confidence, "ambiguous")
        
        canonical, confidence = parse_date("EST 15 MAR 1920")
        self.assertEqual(canonical, "1920-03-15")
        self.assertEqual(confidence, "ambiguous")
        
        canonical, confidence = parse_date("CAL JAN 1800")
        self.assertEqual(canonical, "1800-01-01")
        self.assertEqual(confidence, "ambiguous")
    
    def test_unparseable_ranges(self):
        """Test that range dates are not parsed."""
        canonical, confidence = parse_date("BEF 1900")
        self.assertIsNone(canonical)
        self.assertEqual(confidence, "ambiguous")
        
        canonical, confidence = parse_date("AFT 1920")
        self.assertIsNone(canonical)
        self.assertEqual(confidence, "ambiguous")
        
        canonical, confidence = parse_date("BET 1900 AND 1910")
        self.assertIsNone(canonical)
        self.assertEqual(confidence, "ambiguous")
    
    def test_empty_dates(self):
        """Test empty or invalid dates."""
        canonical, confidence = parse_date("")
        self.assertIsNone(canonical)
        self.assertEqual(confidence, "unparseable")
        
        canonical, confidence = parse_date(None)
        self.assertIsNone(canonical)
        self.assertEqual(confidence, "unparseable")
        
        canonical, confidence = parse_date("invalid text")
        self.assertIsNone(canonical)
        self.assertEqual(confidence, "unparseable")
    
    def test_iso_format(self):
        """Test ISO 8601 format dates."""
        canonical, confidence = parse_date("1900-01-15")
        self.assertEqual(canonical, "1900-01-15")
        self.assertEqual(confidence, "exact")
    
    def test_invalid_date_values(self):
        """Test dates with invalid day/month combinations."""
        canonical, confidence = parse_date("32 JAN 1900")
        self.assertIsNone(canonical)
        self.assertEqual(confidence, "unparseable")
        
        canonical, confidence = parse_date("29 FEB 1900")  # Not a leap year
        self.assertIsNone(canonical)
        self.assertEqual(confidence, "unparseable")

if __name__ == "__main__":
    unittest.main()
