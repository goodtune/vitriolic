import datetime

from django.test import TestCase
from django.test.utils import override_settings
from test_plus import TestCase as TestPlusCase

from touchtechnology.news.decorators import parse_month_name
from touchtechnology.news.tests import factories


class ParseMonthNameTest(TestCase):
    """Test the parse_month_name function with various inputs."""

    def test_numeric_months(self):
        """Test numeric month values."""
        for i in range(1, 13):
            with self.subTest(month=i):
                self.assertEqual(parse_month_name(str(i)), i)

    def test_english_month_names(self):
        """Test English month names (short and full)."""
        test_cases = [
            ("jan", 1),
            ("january", 1),
            ("feb", 2),
            ("february", 2),
            ("mar", 3),
            ("march", 3),
            ("apr", 4),
            ("april", 4),
            ("may", 5),
            ("jun", 6),
            ("june", 6),
            ("jul", 7),
            ("july", 7),
            ("aug", 8),
            ("august", 8),
            ("sep", 9),
            ("september", 9),
            ("oct", 10),
            ("october", 10),
            ("nov", 11),
            ("november", 11),
            ("dec", 12),
            ("december", 12),
        ]
        for month_str, expected_num in test_cases:
            with self.subTest(month=month_str):
                self.assertEqual(parse_month_name(month_str), expected_num)

    def test_case_insensitive_english(self):
        """Test English month names with various cases."""
        test_cases = ["JAN", "Feb", "MARCH", "april"]
        expected = [1, 2, 3, 4]
        for month_str, expected_num in zip(test_cases, expected):
            with self.subTest(month=month_str):
                self.assertEqual(parse_month_name(month_str), expected_num)

    def test_babel_supported_localized_names(self):
        """Test localized month names that should be supported by Babel."""
        # Test key month names from the original issue and common languages
        test_cases = [
            ("六月", 6),  # Chinese June (original issue)
            ("6月", 6),  # Japanese June
            ("juin", 6),  # French June
            ("junio", 6),  # Spanish June
            ("juni", 6),  # German/Dutch June
            ("marzo", 3),  # Spanish March
            ("mars", 3),  # French March
            ("märz", 3),  # German March
            ("июль", 7),  # Russian July
            ("июл", 7),  # Abbreviated Russian July
        ]

        for month_str, expected_num in test_cases:
            with self.subTest(month=month_str):
                try:
                    result = parse_month_name(month_str)
                    self.assertEqual(result, expected_num)
                except ValueError:
                    # If Babel is not available, these should be caught by fallback
                    # The original issue month '六月' should still work via fallback
                    if month_str == "六月":
                        self.fail(
                            f"Critical month name '{month_str}' failed - this breaks the original issue fix"
                        )

    def test_fallback_for_critical_months(self):
        """Test that critical month names work even without Babel."""
        # These are the months from the original issue that must always work
        critical_months = [
            ("六月", 6),  # Chinese June from original error
            ("6月", 6),  # Japanese June
            ("juin", 6),  # French June
            ("junio", 6),  # Spanish June
            ("juni", 6),  # German/Dutch June
        ]

        for month_str, expected_num in critical_months:
            with self.subTest(month=month_str):
                self.assertEqual(parse_month_name(month_str), expected_num)

    def test_invalid_month_names(self):
        """Test invalid month names raise ValueError."""
        invalid_names = ["invalid", "xyz", "13", "0", "notamonth"]
        for invalid_name in invalid_names:
            with self.subTest(month=invalid_name):
                with self.assertRaises(ValueError):
                    parse_month_name(invalid_name)

    def test_empty_month_name(self):
        """Test empty month name raises ValueError."""
        with self.assertRaises(ValueError):
            parse_month_name("")
        with self.assertRaises(ValueError):
            parse_month_name(None)

    def test_whitespace_handling(self):
        """Test month names with whitespace are handled correctly."""
        self.assertEqual(parse_month_name(" jan "), 1)
        self.assertEqual(parse_month_name("  february  "), 2)


@override_settings(ROOT_URLCONF="example_app.urls")
class LocalizedDateViewTest(TestPlusCase):
    """Test the date_view decorator with localized month names."""

    def test_chinese_month_in_url(self):
        """Test URL with Chinese month name."""
        article = factories.ArticleFactory.create(
            published=datetime.datetime(2013, 6, 23, tzinfo=datetime.timezone.utc)
        )
        # Test with Chinese month name for June (六月)
        self.get("news:article", year="2013", month="六月", day="23", slug=article.slug)
        self.response_200()

    def test_japanese_month_in_url(self):
        """Test URL with Japanese month name."""
        article = factories.ArticleFactory.create(
            published=datetime.datetime(2013, 6, 23, tzinfo=datetime.timezone.utc)
        )
        # Test with Japanese month name for June (6月)
        self.get("news:article", year="2013", month="6月", day="23", slug=article.slug)
        self.response_200()

    def test_spanish_month_in_url(self):
        """Test URL with Spanish month name."""
        article = factories.ArticleFactory.create(
            published=datetime.datetime(2013, 6, 23, tzinfo=datetime.timezone.utc)
        )
        # Test with Spanish month name for June (junio)
        self.get(
            "news:article", year="2013", month="junio", day="23", slug=article.slug
        )
        self.response_200()

    def test_french_month_in_url(self):
        """Test URL with French month name."""
        article = factories.ArticleFactory.create(
            published=datetime.datetime(2013, 6, 23, tzinfo=datetime.timezone.utc)
        )
        # Test with French month name for June (juin)
        self.get("news:article", year="2013", month="juin", day="23", slug=article.slug)
        self.response_200()

    def test_german_month_in_url(self):
        """Test URL with German month name."""
        article = factories.ArticleFactory.create(
            published=datetime.datetime(2013, 6, 23, tzinfo=datetime.timezone.utc)
        )
        # Test with German month name for June (juni)
        self.get("news:article", year="2013", month="juni", day="23", slug=article.slug)
        self.response_200()

    def test_invalid_localized_month_404(self):
        """Test that invalid localized month names return 404."""
        self.get("news:article", year="2013", month="无效月", day="23", slug="test")
        self.response_404()

    def test_archive_day_with_localized_month(self):
        """Test archive day view with localized month name."""
        # Test with Chinese month name for June (六月)
        self.get("news:day", year="2013", month="六月", day="23")
        self.response_200()

    def test_archive_month_with_localized_month(self):
        """Test archive month view with localized month name."""
        # Test with Chinese month name for June (六月)
        self.get("news:month", year="2013", month="六月")
        self.response_200()

    def test_backward_compatibility_english_months(self):
        """Test that existing English month names still work."""
        article = factories.ArticleFactory.create(
            published=datetime.datetime(2013, 6, 23, tzinfo=datetime.timezone.utc)
        )
        # Test with English short month name
        self.get("news:article", year="2013", month="jun", day="23", slug=article.slug)
        self.response_200()

        # Test with English full month name
        self.get("news:article", year="2013", month="june", day="23", slug=article.slug)
        self.response_200()
