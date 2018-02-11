from __future__ import unicode_literals

import base64
from datetime import timedelta
from operator import or_

from django.conf import settings
from django.conf.urls import include, url
from django.contrib import messages
from django.contrib.sitemaps import views as sitemaps_views
from django.db.models import Case, Count, F, Q, Sum, When
from django.http import Http404, HttpResponse, HttpResponseGone
from django.utils import timezone
from django.utils.encoding import smart_bytes
from django.utils.module_loading import import_string
from django.utils.translation import ugettext, ugettext_lazy as _
from icalendar import Calendar, Event
from six.moves import reduce
from touchtechnology.common.decorators import login_required_m
from touchtechnology.common.sites import Application
from tournamentcontrol.competition import rank
from tournamentcontrol.competition.decorators import competition_slug
from tournamentcontrol.competition.forms import (
    ConfigurationForm, MultiConfigurationForm, RankingConfigurationForm,
)
from tournamentcontrol.competition.models import Competition, Person


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
        if 'season' in self.kwargs:
            urlpatterns = [
                url(r'^', include(self.season_urls()),
                    kwargs=self.kwargs),
            ]
        elif 'competition' in self.kwargs:
            urlpatterns = [
                url(r'^', include(self.competition_urls()),
                    kwargs=self.kwargs),
            ]
        else:
            urlpatterns = [
                url(r'^$', self.index, name='index'),
                url(r'^(?P<competition>[\w-]+)/',
                    include(self.competition_urls())),
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
        extra_context.update(season.matches.exclude(is_bye=True).aggregate(
            timeslot_count=Count('datetime', distinct=True),
            match_count=Count('pk', distinct=True),
            points_scored=Sum(
                Case(
                    When(
                        statistics__match__stage__division__season=season,
                        then=F('statistics__points')))),
            caps_awarded=Sum(
                Case(
                    When(
                        statistics__match__stage__division__season=season,
                        then=F('statistics__played')))),
        ))
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
        extra_context.update(division.matches.exclude(is_bye=True).aggregate(
            timeslot_count=Count('datetime', distinct=True),
            match_count=Count('pk', distinct=True),
            points_scored=Sum(
                Case(
                    When(
                        statistics__match__stage__division=division,
                        then=F('statistics__points')))),
            caps_awarded=Sum(
                Case(
                    When(
                        statistics__match__stage__division=division,
                        then=F('statistics__played')))),
        ))
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
        extra_context.update(stage.matches.exclude(is_bye=True).aggregate(
            timeslot_count=Count('datetime', distinct=True),
            match_count=Count('pk', distinct=True),
            points_scored=Sum(
                Case(
                    When(
                        statistics__match__stage=stage,
                        then=F('statistics__points')))),
            caps_awarded=Sum(
                Case(
                    When(
                        statistics__match__stage=stage,
                        then=F('statistics__played')))),
        ))
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
        extra_context.update(pool.matches.exclude(is_bye=True).aggregate(
            timeslot_count=Count('datetime', distinct=True),
            match_count=Count('pk', distinct=True),
            points_scored=Sum(
                Case(
                    When(
                        statistics__match__stage_group=pool,
                        then=F('statistics__points')))),
            caps_awarded=Sum(
                Case(
                    When(
                        statistics__match__stage_group=pool,
                        then=F('statistics__played')))),
        ))
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

        extra_context.update(team.matches.exclude(is_bye=True).aggregate(
            timeslot_count=Count('datetime', distinct=True),
            match_count=Count('pk', distinct=True),
            points_scored=Sum(
                Case(
                    When(
                        statistics__player__teamassociation__team=team,
                        then=F('statistics__points')))),
            caps_awarded=Sum(
                Case(
                    When(
                        statistics__player__teamassociation__team=team,
                        then=F('statistics__played')))),
        ))
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

        # Perform select_related to reduce extra queries
        matches = matches.select_related('stage__division__season')

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
            url = request.build_absolute_uri(str(path))

            event = Event()
            event['uid'] = '%s@%s' % (
                base64.b64encode(smart_bytes(url)), request.get_host())
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
        urlpatterns = [
            url(r'^$', self.index, name='index'),
            url(r'^(?P<competition>[^/]+)/', include(self.competition_urls())),
        ]
        return urlpatterns


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
        live_form_class = import_string('tournamentcontrol.competition.forms.'
                                        'DivisionTournamentScheduleForm')
        urlpatterns = [
            url(r'^$', self.index,
                name='index',
                kwargs={
                    'form_class': self.form_class,
                }),
            url(r'^live/$', self.index,
                name='division',
                kwargs={
                    'form_class': live_form_class,
                    'template_name': 'live.html',
                }),
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

    kwargs_form_class = RankingConfigurationForm

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
                        url(r'^(?P<slug>[^/]+)/', include([
                            url(r'^$', rank.DivisionView.as_view(), name='rank'),
                            url(r'^(?P<team>[^/]+)/$', rank.TeamView.as_view(), name='team'),
                        ])),
                    ])),
                ])),
            ])),
        ]
        return urlpatterns


competition = CompetitionSite()
registration = RegistrationSite()
calculator = TournamentCalculatorSite()
ranking = RankingSite()
