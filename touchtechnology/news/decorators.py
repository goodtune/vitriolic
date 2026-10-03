import datetime
import logging

from dateutil.parser import parse as parse_datetime
from dateutil.relativedelta import relativedelta
from django.http import Http404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.functional import wraps
from django.views.decorators.http import last_modified

from touchtechnology.common.models import SitemapNode
from touchtechnology.news.models import Article, Category
from touchtechnology.news.month_names import MONTH_NUMBERS

logger = logging.getLogger(__name__)


def parse_month_name(month_str):
    """
    Parse month name from various formats including localized month names.

    Month names are looked up in a table generated from Babel's locale data, so
    Babel itself is not needed at request time.

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

    # Month names in the languages the URLs may use (see month_names.py)
    month_num = MONTH_NUMBERS.get(month_str.lower())
    if month_num is not None:
        return month_num

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
