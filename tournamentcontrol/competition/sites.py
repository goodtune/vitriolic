import base64
import collections
import os.path
from datetime import timedelta
from operator import or_

from django.conf import settings
from django.conf.urls import include, url
from django.contrib import messages
from django.contrib.sitemaps import views as sitemaps_views
from django.db.models import Q
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseGone,
)
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.module_loading import import_string
from django.utils.translation import ugettext, ugettext_lazy as _
from icalendar import Calendar, Event

from touchtechnology.common.decorators import login_required_m
from touchtechnology.common.sites import Application
from tournamentcontrol.competition import rank
from tournamentcontrol.competition.decorators import (
    competition_slug,
)
from tournamentcontrol.competition.forms import (
    ConfigurationForm,
    MultiConfigurationForm,
)
from tournamentcontrol.competition.models import (
    Competition,
    Person,
)
from tournamentcontrol.competition.sitemaps import (
    SeasonSitemap,
    DivisionSitemap,
    MatchSitemap,
)


class CompetitionSite(Application):

    kwargs_form_class = ConfigurationForm

    def __init__(self, name='competition', app_name='competition', **kwargs):
        # store the node for future reference
        self.node = kwargs.get('node')
        super(CompetitionSite, self).__init__(
            name=name, app_name=app_name, **kwargs)
        self._competitions = Competition.objects.filter(enabled=True)
        if 'competition' in kwargs:
            self._competitions = self._competitions.filter(
                slug=kwargs['competition'])

    def season_urls(self):
        return [
            url(r'^$', self.season, name='season'),
            url(r'^forfeit/$', self.forfeit_list, name='forfeit-list'),
            url(r'^forfeit/(?P<match>\d+)/$', self.forfeit, name='forfeit'),
            url(r'^videos/$', self.season_videos, name='season-videos'),
            url(r'^club:(?P<club>[\w-]+)/$', self.club, name='club'),
            url(r'^club:(?P<club>[\w-]+).ics$', self.calendar, name='calendar'),
            url(r'^(?P<division>[\w-]+).ics$', self.calendar, name='calendar'),
            url(r'^(?P<division>[\w-]+)/$', self.division, name='division'),
            url(r'^(?P<division>[\w-]+):(?P<stage>[\w-]+)/$', self.stage, name='stage'),
            url(r'^(?P<division>[\w-]+):(?P<stage>[\w-]+):(?P<pool>[\w-]+)/$', self.pool, name='pool'),
            url(r'^(?P<division>[\w-]+)/match:(?P<match>\d+)/$', self.match, name='match'),
            url(r'^(?P<division>[\w-]+)/match:(?P<match>\d+)/video/$', self.match_video, name='match-video'),
            url(r'^(?P<division>[\w-]+)/(?P<team>[\w-]+).ics$', self.calendar, name='calendar'),
            url(r'^(?P<division>[\w-]+)/(?P<team>[\w-]+)/$', self.team, name='team'),
        ]

    def competition_urls(self):
        return [
            url(r'^$', self.competition, name='competition'),
            url(r'^(?P<season>[\w-]+).ics$', self.calendar, name='calendar'),
            url(r'^(?P<season>[\w-]+)/', include(self.season_urls())),
        ]

    def get_urls(self):
        sitemaps = collections.OrderedDict()

        if 'season' in self.kwargs:
            c = get_object_or_404(self._competitions,
                                  slug=self.kwargs['competition'])
            s = get_object_or_404(c.seasons, slug=self.kwargs['season'])

            for d in s.divisions.all():
                sitemaps[d.slug] = MatchSitemap({
                    'queryset': d.matches.all(),
                    'app': self}, priority=0.9)

            urlpatterns = [
                url(r'^', include(self.season_urls()),
                    kwargs=self.kwargs),
            ]
        elif 'competition' in self.kwargs:
            c = get_object_or_404(self._competitions,
                                  slug=self.kwargs['competition'])

            for s in c.seasons.all():
                sitemaps[s.slug] = DivisionSitemap({
                    'queryset': s.divisions.all(),
                    'app': self}, priority=0.7)
                for d in s.divisions.all():
                    d_key = os.path.join(s.slug, d.slug)
                    sitemaps[d_key] = MatchSitemap({
                        'queryset': d.matches.all(),
                        'app': self}, priority=0.9)

            urlpatterns = [
                url(r'^', include(self.competition_urls()),
                    kwargs=self.kwargs),
            ]
        else:
            for c in self._competitions.prefetch_related('seasons__divisions'):
                sitemaps[c.slug] = SeasonSitemap({
                    'queryset': c.seasons.all(),
                    'app': self}, priority=0.6)
                for s in c.seasons.all():
                    s_key = os.path.join(c.slug, s.slug)
                    sitemaps[s_key] = DivisionSitemap({
                        'queryset': s.divisions.all(),
                        'app': self}, priority=0.7)
                    for d in s.divisions.all():
                        d_key = os.path.join(c.slug, s.slug, d.slug)
                        sitemaps[d_key] = MatchSitemap({
                            'queryset': d.matches.all(),
                            'app': self}, priority=0.9)

            urlpatterns = [
                url(r'^$', self.index, name='index'),
                url(r'^(?P<competition>[\w-]+)/',
                    include(self.competition_urls())),
            ]

        urlpatterns += [
            url(r'^sitemap\.xml$', self.sitemap_index,
                {'sitemaps': sitemaps,
                 'sitemap_url_name': "competition:sitemap"}),
            url(r'^(?P<section>.+)/sitemap\.xml$', self.sitemap_section,
                {'sitemaps': sitemaps}, name='sitemap'),
        ]
        return urlpatterns

    def sitemap_index(self, request, node=None, competition=None, season=None, division=None, *args, **kwargs):
        # We need to "pop" the node keyword argument
        return sitemaps_views.index(request, *args, **kwargs)

    def sitemap_section(self, request, node=None, competition=None, season=None, division=None, *args, **kwargs):
        # We need to "pop" the node keyword argument
        return sitemaps_views.sitemap(request, *args, **kwargs)

    @property
    def urls(self):
        return self.get_urls(), self.app_name, self.name

    @property
    def competitions(self):
        return self._competitions.prefetch_related('seasons')

    def index(self, request, **kwargs):
        return self.generic_list(request, self._competitions,
                                 templates=self.template_path('index.html'),
                                 paginate_by=self._competitions.count(),
                                 extra_context=kwargs)

    @competition_slug
    def competition(self, request, competition, extra_context, **kwargs):
        templates = self.template_path('competition.html', competition.slug)
        return self.generic_detail(request, self._competitions,
                                   slug=competition.slug,
                                   templates=templates,
                                   extra_context=extra_context)

    @competition_slug
    def season(self, request, competition, season, extra_context, **kwargs):
        templates = self.template_path(
            'season.html', competition.slug, season.slug)
        return self.generic_detail(request, competition.seasons,
                                   slug=season.slug,
                                   templates=templates,
                                   extra_context=extra_context)

    @competition_slug
    def season_videos(self, request, competition, season, extra_context, **kwargs):
        templates = self.template_path(
            'season_videos.html', competition.slug, season.slug)
        return self.generic_detail(request, competition.seasons,
                                   slug=season.slug,
                                   templates=templates,
                                   extra_context=extra_context)

    @competition_slug
    def club(self, request, competition, season, club, extra_context,
             **kwargs):
        templates = self.template_path(
            'club.html', competition.slug, season.slug, club.slug)
        return self.generic_detail(request, season.clubs,
                                   slug=club.slug,
                                   templates=templates,
                                   extra_context=extra_context)

    @competition_slug
    def division(self, request, competition, season, division, extra_context,
                 **kwargs):
        templates = self.template_path(
            'division.html', competition.slug, season.slug, division.slug)
        return self.generic_detail(request, season.divisions,
                                   slug=division.slug,
                                   templates=templates,
                                   extra_context=extra_context)

    @competition_slug
    def stage(self, request, competition, season, division, stage,
              extra_context, **kwargs):
        templates = self.template_path(
            'stage.html',
            competition.slug, season.slug, division.slug, stage.slug)
        extra_context['parent'] = stage
        return self.generic_detail(request, division.stages,
                                   slug=stage.slug,
                                   templates=templates,
                                   extra_context=extra_context)

    @competition_slug
    def pool(self, request, competition, season, division, stage, pool,
             extra_context, **kwargs):
        # FIXME sadly the template name was not changed when we refactored
        #       pools to be subordinates of Stage.
        templates = self.template_path(
            'divisiongroup.html', competition.slug, season.slug, division.slug,
            stage.slug, pool.slug)
        return self.generic_detail(request, stage.pools,
                                   slug=pool.slug,
                                   templates=templates,
                                   extra_context=extra_context)

    @competition_slug
    def team(self, request, competition, season, division, team, extra_context,
             **kwargs):
        templates = self.template_path(
            'team.html', competition.slug, season.slug, division.slug,
            team.slug)
        return self.generic_detail(request, division.teams,
                                   slug=team.slug,
                                   templates=templates,
                                   extra_context=extra_context)

    @competition_slug
    def calendar(self, request, season, club=None, division=None, team=None,
                 **kwargs):
        if team is not None:
            matches = team.matches
        elif division is not None:
            matches = division.matches
        elif club is not None:
            matches = club.matches.filter(stage__division__season=season)
        else:
            matches = season.matches

        # Do not include matches which have not had the time scheduled
        matches = matches.exclude(datetime__isnull=True)

        # For development server turn back plain text to make debugging easier
        if settings.DEBUG:
            content_type = 'text/plain'
        else:
            content_type = 'text/calendar'

        response = HttpResponse(content_type=content_type)

        cal = Calendar()
        cal.add('prodid', '-//Tournament Control//%s//' % request.get_host())
        cal.add('version', '2.0')

        for match in matches.order_by('datetime', 'play_at'):
            # Determine the resource path to the detailed match view
            path = self.reverse('match', kwargs={
                'match': match.pk,
                'division': match.stage.division.slug,
                'season': match.stage.division.season.slug,
                'competition': match.stage.division.season.competition.slug,
            })

            # Combine the resource path with our current request context
            url = request.build_absolute_uri(unicode(path))

            event = Event()
            event['uid'] = '%s@%s' % (
                base64.b64encode(url), request.get_host())
            event.add('summary', match.title)
            event.add('location', '{0} ({1})'.format(
                match.stage.division.title, match.stage.title))
            event.add('description', url)
            event.add('dtstart', match.datetime)
            # FIXME match duration should not be hardcoded
            event.add('dtend', match.datetime + timedelta(minutes=45))
            # FIXME should be the last modified time of the match
            event.add('dtstamp', timezone.now())

            cal.add_component(event)

        response.write(cal.to_ical())
        return response

    @competition_slug
    def match(self, request, competition, season, division, match,
              extra_context, **kwargs):
        if match.is_bye or match.home_team is None or match.away_team is None:
            # Temporary, realistically nobody should ever have this URL but we
            # will use GONE so that Google removes it from their index.
            return HttpResponseGone()
        templates = self.template_path(
            'match.html', competition.slug, season.slug, division.slug)
        return self.generic_detail(request, division.matches,
                                   pk=match.pk,
                                   templates=templates,
                                   extra_context=extra_context)

    @competition_slug
    def match_video(self, request, competition, season, division, match,
                    extra_context, **kwargs):
        if match.is_bye or match.home_team is None or match.away_team is None:
            # Temporary, realistically nobody should ever have this URL but we
            # will use GONE so that Google removes it from their index.
            return HttpResponseGone()
        templates = self.template_path(
            'videos.html', competition.slug, season.slug, division.slug)
        return self.generic_detail(request, division.matches,
                                   pk=match.pk,
                                   templates=templates,
                                   extra_context=extra_context)

        # TODO add related model to record videos
        # return self.generic_list(request, match.videos,
        #                          templates=templates,
        #                          extra_context=extra_context)

    @login_required_m
    @competition_slug
    def forfeit_list(self, request, competition, season, extra_context,
                     **kwargs):
        """
        List the matches that the visitor is permitted to forfeit. Must only
        show matches for teams that they are a registered member of (either as
        a player or other role).
        """
        try:
            teams = request.user.person.teams
        except Person.DoesNotExist:
            raise Http404

        matches = season.matches.filter(
            Q(home_team=teams) | Q(away_team=teams))

        context = {
            'matches': matches,
        }
        context.update(extra_context)

        templates = self.template_path('forfeit_list.html')
        return self.render(request, templates, context)

    @login_required_m
    @competition_slug
    def forfeit(self, request, competition, season, extra_context, match,
                **kwargs):
        """
        View that will allow a team member to forfeit a match they are due to
        be playing in.
        """
        try:
            teams = request.user.person.teams
        except Person.DoesNotExist:
            raise Http404

        matches = season.matches.filter(
            Q(home_team=teams) | Q(away_team=teams))

        redirect = self.redirect(self.reverse('forfeit-list', kwargs={
            'competition': competition.slug,
            'season': season.slug,
        }))

        if match not in matches:
            messages.add_message(
                request, messages.ERROR,
                "Attempting to forfeit a match you are not involved in.")
            return redirect

        # decide which team to forfeit
        if match.home_team in teams and match.away_team in teams:
            messages.add_message(
                request, messages.WARNING,
                _("You are a member of both teams for this match, please "
                  "contact the competition manager."))
            return redirect

        elif match.home_team in teams:
            team = match.home_team
        elif match.away_team in teams:
            team = match.away_team
        else:
            messages.add_message(
                request, messages.ERROR,
                _("You are not a member of either team, please contact the "
                  "competition manager."))
            return redirect

        if request.method == 'POST':
            # use the forfeit API to advise who made lodged the forfeit
            UNABLE_TO_POST = _("Unable to post forfeit, please contact the "
                               "competition manager.")
            try:
                success = match.forfeit(team, request.user.person)
            except AssertionError:
                # logger.exception("Failed precondition checks")
                messages.add_message(request, messages.ERROR, UNABLE_TO_POST)

            if success:
                messages.add_message(
                    request, messages.INFO,
                    _("The match has been forfeit, notifications will be sent "
                      "to affected parties shortly."))
            else:
                messages.add_message(request, messages.ERROR, UNABLE_TO_POST)

            return redirect

        context = {
            'match': match,
            'team': team,
        }
        context.update(extra_context)

        templates = self.template_path('forfeit.html')
        return self.render(request, templates, context)


class MultiCompetitionSite(CompetitionSite):

    kwargs_form_class = MultiConfigurationForm

    @classmethod
    def verbose_name(cls):
        return ugettext("Multiple Competitions")

    def __init__(self, name='competition', app_name='competition', **kwargs):
        self.node = kwargs.get('node')  # store the node for future reference
        super(CompetitionSite, self).__init__(name=name, app_name=app_name, **kwargs)
        self._competitions = Competition.objects.filter(enabled=True)
        if 'competition' in kwargs:
            q = reduce(or_, [Q(slug=slug) for slug in kwargs['competition']])
            self._competitions = self._competitions.filter(q)

    def get_urls(self):
        return patterns(
            '',
            url(r'^$', self.index, name='index'),
            url(r'^(?P<competition>[\w-]+)/', include(self.competition_urls())),
        )


class RegistrationSite(Application):

    def __init__(self, name='rego', app_name='rego', **kwargs):
        super(RegistrationSite, self).__init__(
            name=name, app_name=app_name, **kwargs)

    def get_urls(self):
        return []


class TournamentCalculatorSite(Application):

    def __init__(self, name='calculator', app_name='calculator', **kwargs):
        self.form_class = import_string(kwargs.pop(
            'form_class',
            'tournamentcontrol.competition.forms.TournamentScheduleForm'))
        super(TournamentCalculatorSite, self).__init__(
            name=name, app_name=app_name, **kwargs)

    def get_urls(self):
        urlpatterns = [
            url(r'^$', self.index, name='index',
                kwargs={'form_class': self.form_class}),
            url(r'^live/$', self.index, name='division',
                kwargs={
                    'template_name': 'live.html',
                    'form_class': import_string(
                    'tournamentcontrol.competition.forms.'
                    'DivisionTournamentScheduleForm')}),
        ]
        return urlpatterns

    def index(self, request, form_class, template_name='index.html',
              **extra_context):
        context = {}

        if request.GET:
            form = form_class(data=request.GET)
        else:
            form = form_class()

        if form.is_valid():
            context.setdefault('data', form.get_context())

        context.setdefault('form', form)
        context.update(extra_context)

        templates = self.template_path(template_name)
        return self.render(request, templates, context)


class RankingSite(Application):

    def __init__(self, name='ranking', app_name='ranking', **kwargs):
        super(RankingSite, self).__init__(
            name=name, app_name=app_name, **kwargs)

    def get_urls(self):

        urlpatterns = [
            url(r'^$', rank.IndexView.as_view(), name='index'),
            url(r'^(?P<year>\d{4})/', include([
                url(r'^$', rank.YearView.as_view(), name='year'),
                url(r'^(?P<month>[a-z]{3})/', include([
                    url(r'^$', rank.MonthView.as_view(), name='month'),
                    url(r'^(?P<day>\d{1,2})/', include([
                        url(r'^$', rank.DayView.as_view(), name='day'),
                        url(r'^(?P<slug>[^/]+)/$',
                            rank.DivisionView.as_view(), name='rank'),
                    ])),
                ])),
            ])),
        ]
        return urlpatterns

    def ranking(self, request, *args, **kwargs):
        raise ValueError('STOP')


competition = CompetitionSite()
registration = RegistrationSite()
calculator = TournamentCalculatorSite()
ranking = RankingSite()
