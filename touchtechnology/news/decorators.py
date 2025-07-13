import datetime
import logging
import calendar

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
    
    Args:
        month_str (str): Month name in various formats (English short/full, localized)
    
    Returns:
        int: Month number (1-12)
    
    Raises:
        ValueError: If month name cannot be parsed
    """
    if not month_str:
        raise ValueError("Month string cannot be empty")
    
    month_str = str(month_str).strip().lower()
    
    # Try English short names first (jan, feb, mar, etc.)
    english_short_names = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }
    if month_str in english_short_names:
        return english_short_names[month_str]
    
    # Try English full names (january, february, etc.)
    english_full_names = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    if month_str in english_full_names:
        return english_full_names[month_str]
    
    # Comprehensive localized month names mapping
    localized_month_names = {
        # Chinese (Traditional and Simplified)
        '一月': 1, '二月': 2, '三月': 3, '四月': 4, '五月': 5, '六月': 6,
        '七月': 7, '八月': 8, '九月': 9, '十月': 10, '十一月': 11, '十二月': 12,
        
        # Japanese
        '1月': 1, '2月': 2, '3月': 3, '4月': 4, '5月': 5, '6月': 6,
        '7月': 7, '8月': 8, '9月': 9, '10月': 10, '11月': 11, '12月': 12,
        
        # Spanish
        'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
        'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
        
        # French
        'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6,
        'juillet': 7, 'août': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12,
        
        # German
        'januar': 1, 'februar': 2, 'märz': 3, 'april': 4, 'mai': 5, 'juni': 6,
        'juli': 7, 'august': 8, 'september': 9, 'oktober': 10, 'november': 11, 'dezember': 12,
        
        # Italian
        'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4, 'maggio': 5, 'giugno': 6,
        'luglio': 7, 'agosto': 8, 'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12,
        
        # Portuguese
        'janeiro': 1, 'fevereiro': 2, 'março': 3, 'abril': 4, 'maio': 5, 'junho': 6,
        'julho': 7, 'agosto': 8, 'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12,
        
        # Russian (transliterated)
        'январь': 1, 'февраль': 2, 'март': 3, 'апрель': 4, 'май': 5, 'июнь': 6,
        'июль': 7, 'август': 8, 'сентябрь': 9, 'октябрь': 10, 'ноябрь': 11, 'декабрь': 12,
        
        # Dutch
        'januari': 1, 'februari': 2, 'maart': 3, 'april': 4, 'mei': 5, 'juni': 6,
        'juli': 7, 'augustus': 8, 'september': 9, 'oktober': 10, 'november': 11, 'december': 12,
        
        # Korean
        '1월': 1, '2월': 2, '3월': 3, '4월': 4, '5월': 5, '6월': 6,
        '7월': 7, '8월': 8, '9월': 9, '10월': 10, '11월': 11, '12월': 12,
    }
    
    # Check localized names (case-insensitive for ASCII, exact for non-ASCII)
    if month_str in localized_month_names:
        return localized_month_names[month_str]
    
    # Try numeric month (1-12)
    try:
        month_num = int(month_str)
        if 1 <= month_num <= 12:
            return month_num
    except ValueError:
        pass
    
    # Last resort: try dateutil's parser with just the month
    try:
        # Try with dateutil parser as fallback
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
