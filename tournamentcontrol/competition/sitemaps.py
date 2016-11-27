from django.contrib.sitemaps import GenericSitemap


class CustomGenericSitemap(GenericSitemap):
    """
    Extend the provided GenericSitemap so that we can also pass in the
    Application instance. This then allows us to use the .reverse method to
    determine the right URL for the object with regard to the object.
    """
    def __init__(self, info_dict, *args, **kwargs):
        super(CustomGenericSitemap, self).__init__(info_dict, *args, **kwargs)
        self.app = info_dict['app']


class SeasonSitemap(CustomGenericSitemap):
    def location(self, obj):
        return self.app.reverse('season', kwargs={
            'competition': obj.competition.slug,
            'season': obj.slug})


class DivisionSitemap(CustomGenericSitemap):
    def location(self, obj):
        return self.app.reverse('division', kwargs={
            'competition': obj.season.competition.slug,
            'season': obj.season.slug,
            'division': obj.slug})


class MatchSitemap(CustomGenericSitemap):
    def items(self):
        "Only return matches that have known opponents, will exclude Byes"
        return self.queryset.filter(home_team__isnull=False,
                                    away_team__isnull=False)

    def location(self, obj):
        return self.app.reverse('match', kwargs={
            'competition': obj.stage.division.season.competition.slug,
            'season': obj.stage.division.season.slug,
            'division': obj.stage.division.slug,
            'match': obj.pk})
