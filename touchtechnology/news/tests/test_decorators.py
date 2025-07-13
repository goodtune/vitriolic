import datetime

from django.test import TestCase
from django.test.utils import override_settings
from django.http import Http404
from test_plus import TestCase as TestPlusCase

from touchtechnology.news.decorators import parse_month_name
from touchtechnology.news.tests import factories


class ParseMonthNameTest(TestCase):
    """Test the parse_month_name function with various inputs."""
    
    def test_english_short_names(self):
        """Test English short month names (jan, feb, etc.)."""
        expected = [
            ('jan', 1), ('feb', 2), ('mar', 3), ('apr', 4),
            ('may', 5), ('jun', 6), ('jul', 7), ('aug', 8),
            ('sep', 9), ('oct', 10), ('nov', 11), ('dec', 12)
        ]
        for month_str, expected_num in expected:
            with self.subTest(month=month_str):
                self.assertEqual(parse_month_name(month_str), expected_num)
    
    def test_english_short_names_case_insensitive(self):
        """Test English short month names with various cases."""
        test_cases = ['JAN', 'Feb', 'MAR', 'apr']
        expected = [1, 2, 3, 4]
        for month_str, expected_num in zip(test_cases, expected):
            with self.subTest(month=month_str):
                self.assertEqual(parse_month_name(month_str), expected_num)
    
    def test_english_full_names(self):
        """Test English full month names."""
        expected = [
            ('january', 1), ('february', 2), ('march', 3), ('april', 4),
            ('may', 5), ('june', 6), ('july', 7), ('august', 8),
            ('september', 9), ('october', 10), ('november', 11), ('december', 12)
        ]
        for month_str, expected_num in expected:
            with self.subTest(month=month_str):
                self.assertEqual(parse_month_name(month_str), expected_num)
    
    def test_chinese_month_names(self):
        """Test Chinese month names."""
        expected = [
            ('一月', 1), ('二月', 2), ('三月', 3), ('四月', 4),
            ('五月', 5), ('六月', 6), ('七月', 7), ('八月', 8),
            ('九月', 9), ('十月', 10), ('十一月', 11), ('十二月', 12)
        ]
        for month_str, expected_num in expected:
            with self.subTest(month=month_str):
                self.assertEqual(parse_month_name(month_str), expected_num)
    
    def test_japanese_month_names(self):
        """Test Japanese month names."""
        expected = [
            ('1月', 1), ('2月', 2), ('3月', 3), ('4月', 4),
            ('5月', 5), ('6月', 6), ('7月', 7), ('8月', 8),
            ('9月', 9), ('10月', 10), ('11月', 11), ('12月', 12)
        ]
        for month_str, expected_num in expected:
            with self.subTest(month=month_str):
                self.assertEqual(parse_month_name(month_str), expected_num)
    
    def test_spanish_month_names(self):
        """Test Spanish month names."""
        expected = [
            ('enero', 1), ('febrero', 2), ('marzo', 3), ('abril', 4),
            ('mayo', 5), ('junio', 6), ('julio', 7), ('agosto', 8),
            ('septiembre', 9), ('octubre', 10), ('noviembre', 11), ('diciembre', 12)
        ]
        for month_str, expected_num in expected:
            with self.subTest(month=month_str):
                self.assertEqual(parse_month_name(month_str), expected_num)
    
    def test_french_month_names(self):
        """Test French month names."""
        expected = [
            ('janvier', 1), ('février', 2), ('mars', 3), ('avril', 4),
            ('mai', 5), ('juin', 6), ('juillet', 7), ('août', 8),
            ('septembre', 9), ('octobre', 10), ('novembre', 11), ('décembre', 12)
        ]
        for month_str, expected_num in expected:
            with self.subTest(month=month_str):
                self.assertEqual(parse_month_name(month_str), expected_num)
    
    def test_german_month_names(self):
        """Test German month names."""
        expected = [
            ('januar', 1), ('februar', 2), ('märz', 3), ('april', 4),
            ('mai', 5), ('juni', 6), ('juli', 7), ('august', 8),
            ('september', 9), ('oktober', 10), ('november', 11), ('dezember', 12)
        ]
        for month_str, expected_num in expected:
            with self.subTest(month=month_str):
                self.assertEqual(parse_month_name(month_str), expected_num)
    
    def test_numeric_month(self):
        """Test numeric month values."""
        for i in range(1, 13):
            with self.subTest(month=i):
                self.assertEqual(parse_month_name(str(i)), i)
    
    def test_invalid_month_names(self):
        """Test invalid month names raise ValueError."""
        invalid_names = ['invalid', 'xyz', '13', '0', '', 'notamonth']
        for invalid_name in invalid_names:
            with self.subTest(month=invalid_name):
                with self.assertRaises(ValueError):
                    parse_month_name(invalid_name)
    
    def test_empty_month_name(self):
        """Test empty month name raises ValueError."""
        with self.assertRaises(ValueError):
            parse_month_name('')
        with self.assertRaises(ValueError):
            parse_month_name(None)
    
    def test_whitespace_handling(self):
        """Test month names with whitespace are handled correctly."""
        self.assertEqual(parse_month_name(' jan '), 1)
        self.assertEqual(parse_month_name('  february  '), 2)


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
        self.get("news:article", year="2013", month="junio", day="23", slug=article.slug)
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