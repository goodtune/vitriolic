from django.contrib.sitemaps import Sitemap
from orderedset import OrderedSet


class CustomSitemap(Sitemap):
    """
    Extend the provided GenericSitemap so that we can also pass in the
    Application instance. This then allows us to use the .reverse method to
    determine the right URL for the object with regard to the object.
    """
    def __init__(self, app, *args, **kwargs):
        self._items = OrderedSet()
        self.app = app

    def add(self, item):
        return self._items.add(item)

    def items(self):
        return self._items


class SeasonSitemap(CustomSitemap):
    def location(self, obj):
        return self.app.reverse('season', kwargs={
            'competition': obj.competition.slug,
            'season': obj.slug})


class DivisionSitemap(CustomSitemap):
    def location(self, obj):
        return self.app.reverse('division', kwargs={
            'competition': obj.season.competition.slug,
            'season': obj.season.slug,
            'division': obj.slug})


class MatchSitemap(CustomSitemap):
    def location(self, obj):
        return self.app.reverse('match', kwargs={
            'competition': obj.stage.division.season.competition.slug,
            'season': obj.stage.division.season.slug,
            'division': obj.stage.division.slug,
            'match': obj.pk})
