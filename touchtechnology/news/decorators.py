import datetime
import logging

from babel import Locale
from babel.dates import get_month_names
from dateutil.parser import parse as parse_datetime
from dateutil.relativedelta import relativedelta
from django.http import Http404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.functional import wraps
from django.views.decorators.http import last_modified

from touchtechnology.common.models import SitemapNode
from touchtechnology.news.models import Article, Category

logger = logging.getLogger(__name__)


def parse_month_name(month_str):
    """
    Parse month name from various formats including localized month names.

    Uses Babel library for comprehensive international month name support.

    Args:
        month_str (str): Month name in various formats (English short/full, localized)

    Returns:
        int: Month number (1-12)

    Raises:
        ValueError: If month name cannot be parsed
    """
    if not month_str:
        raise ValueError("Month string cannot be empty")

    month_str = str(month_str).strip()

    # Try numeric month first (1-12)
    try:
        month_num = int(month_str)
        if 1 <= month_num <= 12:
            return month_num
    except ValueError:
        pass

    # Use Babel for comprehensive international month name support
    month_lookup = {}

    # Common locales to support - covers most major languages
    locales = [
        "en",
        "fr",
        "de",
        "es",
        "it",
        "pt",
        "zh",
        "ja",
        "ko",
        "ru",
        "nl",
        "da",
        "sv",
        "no",
        "fi",
        "pl",
        "cs",
        "hu",
        "ro",
        "bg",
        "hr",
        "sl",
        "sk",
        "lt",
        "lv",
        "et",
        "ar",
        "he",
        "hi",
        "th",
        "vi",
        "id",
        "ms",
        "ru",
    ]

    for locale_code in locales:
        try:
            locale = Locale(locale_code)

            # Get full month names
            months = get_month_names("wide", locale=locale)
            for month_num, month_name in months.items():
                if month_name:
                    month_lookup[month_name.lower()] = month_num

            # Get abbreviated month names
            months_abbr = get_month_names("abbreviated", locale=locale)
            for month_num, month_name in months_abbr.items():
                if month_name and month_name.lower() not in month_lookup:
                    month_lookup[month_name.lower()] = month_num

        except Exception:
            # Skip this locale if it fails
            continue

    # Look up the month name
    month_lower = month_str.lower()
    if month_lower in month_lookup:
        return month_lookup[month_lower]

    # Last resort: try dateutil's parser
    try:
        test_date = parse_datetime(f"2000-{month_str}-01")
        return test_date.month
    except (ValueError, TypeError):
        pass

    raise ValueError(f"Unable to parse month name: {month_str}")


@method_decorator
def date_view(f, *a, **kw):
    @wraps(f)
    def _decorated(*args, **kwargs):
        year = kwargs.pop("year")
        month = kwargs.pop("month", "jan")
        day = kwargs.pop("day", 1)

        try:
            # Parse month name to get month number
            month_num = parse_month_name(month)

            # Create date using numeric values for reliable parsing
            value = timezone.make_aware(
                datetime.datetime(int(year), month_num, int(day)),
                datetime.timezone.utc,
            )
        except (ValueError, TypeError) as exc:
            logger.exception("invalid date value in path %s", args[0].path)
            raise Http404(str(exc))

        kwargs["date"] = value

        # So we can run an optimal query for finding the last modified time for
        # a view in other decorators, pass in the "delta" that should be used
        if day is None:
            kwargs["delta"] = "months"
        if month is None:
            kwargs["delta"] = "years"

        return f(*args, **kwargs)

    return _decorated


@method_decorator
@last_modified
def news_last_modified(request, **kwargs):
    last_modified_datetimes = []
    try:
        last_modified_datetimes.append(
            Article.objects.live().latest("last_modified").last_modified
        )
    except Article.DoesNotExist:
        ...
    try:
        last_modified_datetimes.append(
            Category.objects.latest("last_modified").last_modified
        )
    except Category.DoesNotExist:
        ...
    try:
        last_modified_datetimes.append(
            SitemapNode.objects.latest("last_modified").last_modified
        )
    except SitemapNode.DoesNotExist:
        ...
    return max(last_modified_datetimes)


@method_decorator
@last_modified
def last_modified_article(request, **kwargs):
    queryset = Article.objects.live()

    date = kwargs.get("date")
    if date is not None:
        delta = {kwargs.get("delta", "days"): 1}
        date_range = (date, date + relativedelta(**delta))
        queryset = queryset.filter(published__range=date_range)

    slug = kwargs.get("slug")
    if slug is not None:
        queryset = queryset.filter(slug=slug)

    if not queryset:
        return
    return queryset.latest("last_modified").last_modified
