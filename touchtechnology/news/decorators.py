from dateutil.parser import parse as parse_datetime
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.functional import wraps
from django.views.decorators.http import last_modified

from touchtechnology.common.models import SitemapNode
from touchtechnology.news.models import Article, Category


@method_decorator
def date_view(f, *a, **kw):
    @wraps(f)
    def _decorated(*args, **kwargs):
        year = kwargs.pop("year")
        month = kwargs.pop("month", "jan")
        day = kwargs.pop("day", 1)
        try:
            datetime = parse_datetime("{0}-{1}-{2}".format(year, month, day))
        except ValueError:
            raise Http404

        if settings.USE_TZ:
            datetime = timezone.make_aware(datetime, timezone.utc)

        kwargs["date"] = datetime

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
    except ObjectDoesNotExist:
        pass
    try:
        last_modified_datetimes.append(
            Category.objects.latest("last_modified").last_modified
        )
    except ObjectDoesNotExist:
        pass
    try:
        last_modified_datetimes.append(
            SitemapNode.objects.latest("last_modified").last_modified
        )
    except ObjectDoesNotExist:
        pass
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
