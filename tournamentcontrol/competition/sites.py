from __future__ import unicode_literals

import operator
from datetime import timedelta
from operator import or_

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.conf.urls import include, url
from django.contrib import messages
from django.contrib.sitemaps import views as sitemaps_views
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Case, Count, F, Q, Sum, When
from django.http import Http404, HttpResponse, HttpResponseGone
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.module_loading import import_string
from django.utils.translation import ugettext, ugettext_lazy as _
from icalendar import Calendar, Event
from six.moves import reduce
from touchtechnology.common.decorators import login_required_m
from touchtechnology.common.sites import Application
from touchtechnology.common.utils import get_403_or_None, get_perms_for_model
from tournamentcontrol.competition import rank
from tournamentcontrol.competition.dashboard import (
    matches_require_basic_results, matches_require_details_results,
)
from tournamentcontrol.competition.decorators import competition_slug
from tournamentcontrol.competition.forms import (
    ConfigurationForm, MatchResultFormSet, MatchStatisticFormset,
    MultiConfigurationForm, RankingConfigurationForm,
)
from tournamentcontrol.competition.models import (
    Competition, Match, Person, SimpleScoreMatchStatistic,
)
from tournamentcontrol.competition.utils import FauxQueryset, team_needs_progressing


def permissions_required(request, model, instance=None, return_403=True,
                         accept_global_perms=True, create=False, perms=None):
    # If no perms are specified, build sensible default using built in
    # permission types that come batteries included with Django.
    if perms is None:
        perms = get_perms_for_model(model, change=True)

        # When we're doing a creation we should have permission to create the object.
        if create:
            perms = get_perms_for_model(model, add=True)

    # Determine the user's permission to edit this object using the
    # get_403_or_None - saves decorating view method with
    # @permission_required_or_403
    has_permission = get_403_or_None(
        request, perms, obj=instance, return_403=return_403,
        accept_global_perms=accept_global_perms)

    if has_permission is not None:
        return has_permission


class CompetitionAdminMixin(object):
    """
    Some administrative functions should be allowed to authenticated users on
    the front-end of the site. As long as we only use primitives from the base
    ``touchtechnology.common.sites.Application`` class it will integrate fine
    with both.
    """
    def day_runsheet(self, request, season, date, extra_context, templates=None, **kwargs):
        matches = season.matches.filter(date=date).order_by('is_bye', 'datetime', 'play_at')
        templates = self.template_path('runsheet.html', season.slug, season.competition.slug)
        return self.generic_list(request, matches,
                                 templates=templates,
                                 paginate_by=0,
                                 permission_required=False,
                                 extra_context=extra_context)

    def match_results(self, request, competition, season, date, extra_context, redirect_to,
                      division=None, time=None, **kwargs):
        matches = Match.objects.filter(
            stage__division__season=season,
            stage__division__season__competition=competition,
            date=date,
        )

        if division is not None:
            matches = matches.filter(stage__division=division)

        # ensure only matches with progressed teams are able to be updated
        matches = matches.exclude(team_needs_progressing, is_bye=False)
        matches = matches.exclude(home_team__isnull=True, away_team__isnull=True)

        # FIXME too complex, be verbose so we can all read and understand it
        if time is not None:
            base = Q(time=time)
            bye_kwargs = matches.filter(time=time) \
                                .values('stage', 'round')
            time_or_byes = reduce(
                operator.or_,
                map(lambda kw: Q(time__isnull=True, **kw), bye_kwargs),
                base)
            matches = matches.filter(time_or_byes)
        else:
            matches = matches.order_by('date', 'time', 'play_at')

        match_queryset = matches.filter(is_bye=False)
        bye_queryset = matches.filter(is_bye=True)

        if request.method == 'POST':
            match_formset = MatchResultFormSet(
                data=request.POST, queryset=match_queryset, prefix='matches')
            bye_formset = MatchResultFormSet(
                data=request.POST, queryset=bye_queryset, prefix='byes')

            if match_formset.is_valid() and bye_formset.is_valid():
                match_formset.save()
                bye_formset.save()
                messages.success(request, _("Your changes have been saved."))
                return self.redirect(redirect_to)
        else:
            match_formset = MatchResultFormSet(queryset=match_queryset, prefix='matches')
            bye_formset = MatchResultFormSet(queryset=bye_queryset, prefix='byes')

        context = {
            'competition': competition,
            'season': season,
            'date': date,
            'division': division,
            'match_formset': match_formset,
            'bye_formset': bye_formset,
            'matches': matches,
            'cancel_url': redirect_to,
        }
        context.update(extra_context)

        templates = self.template_path('match_results.html')
        return self.render(request, templates, context)

    def edit_match_detail(self, request, stage, match, extra_context, redirect_to, **kwargs):
        conditions = {
            'home_team__isnull': False,
            'away_team__isnull': False,
            'home_team_score__isnull': False,
            'away_team_score__isnull': False,
        }

        if match is None:
            match = get_object_or_404(stage.matches, pk=match.pk, **conditions)

        def team_faux_queryset(team):
            stats = FauxQueryset(SimpleScoreMatchStatistic, team=team)
            for player in team.people.filter(is_player=True):
                try:
                    statistic = SimpleScoreMatchStatistic.objects.get(
                        match=match,
                        player=player.person)
                except ObjectDoesNotExist:
                    statistic = SimpleScoreMatchStatistic(
                        match=match,
                        player=player.person,
                        number=player.number,
                        played=1)
                stats.append(statistic)
            return stats

        home_queryset = team_faux_queryset(match.home_team)
        away_queryset = team_faux_queryset(match.away_team)

        if request.method == 'POST':
            home = MatchStatisticFormset(data=request.POST,
                                         score=match.home_team_score,
                                         prefix='home',
                                         queryset=home_queryset)

            away = MatchStatisticFormset(data=request.POST,
                                         score=match.away_team_score,
                                         prefix='away',
                                         queryset=away_queryset)

            if home.is_valid() and away.is_valid():
                home.save()
                away.save()
                messages.success(request, _("Your changes have been saved."))
                return self.redirect(redirect_to)

        else:
            home = MatchStatisticFormset(prefix='home',
                                         score=match.home_team_score,
                                         queryset=home_queryset)
            away = MatchStatisticFormset(prefix='away',
                                         score=match.away_team_score,
                                         queryset=away_queryset)

        context = {
            'object': match,
            'formsets': (home, away),
        }
        context.update(extra_context)

        templates = self.template_path('match_detail.html')
        return self.render(request, templates, context)


class CompetitionSite(CompetitionAdminMixin, Application):

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

    def result_urls(self):
        return [
            url(r'^$', self.results, name='results'),
            url(r'^match/(?P<match>\d+)/$', self.edit_match_detail, name='match-details'),
            url(r'^(?P<datestr>\d{8})/$', self.results, name='results'),
            url(r'^(?P<datestr>\d{8})/(?P<timestr>\d{4})/$', self.match_results, name='match-results'),
        ]

    def runsheet_urls(self):
        return [
            url(r'^$', self.runsheet, name='runsheet'),
            url(r'^(?P<datestr>\d{8})/$', self.day_runsheet, name='runsheet'),
        ]

    def season_urls(self):
        return [
            url(r'^$', self.season, name='season'),
            url(r'^forfeit/$', self.forfeit_list, name='forfeit-list'),
            url(r'^forfeit/(?P<match>\d+)/$', self.forfeit, name='forfeit'),
            url(r'^videos/$', self.season_videos, name='season-videos'),
            url(r'^club:(?P<club>[\w-]+)/$', self.club, name='club'),
            url(r'^club:(?P<club>[\w-]+).ics$', self.calendar, name='calendar'),
            url(r'^results/', include(self.result_urls())),
            url(r'^runsheet/', include(self.runsheet_urls())),
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
    def runsheet(self, request, competition, season, extra_context, **kwargs):
        context = {
            'dates': season.matches.dates('date', 'day')
        }
        context.update(extra_context)
        templates = self.template_path('runsheet_list.html', competition.slug, season.slug)
        return self.render(request, templates, context)

    @competition_slug
    def day_runsheet(self, request, season, date, extra_context, **kwargs):
        return super(CompetitionSite, self).day_runsheet(
            request, season, date, extra_context, **kwargs)

    @competition_slug
    @login_required_m
    def results(self, request, competition, season, extra_context, date=None, **kwargs):
        has_permission = permissions_required(request, Match, return_403=False)
        if has_permission is not None:
            return has_permission

        if date is not None:
            matches = season.matches.filter(date=date)
        else:
            matches = season.matches

        # Allow super-user accounts visibility to look 1 year into the future.
        if request.user.is_superuser:
            now = timezone.now() + relativedelta(years=1)
        else:
            now = None

        # Filter the list of matches to those which require result entry
        basic_results = matches_require_basic_results(now, matches)
        details_results = matches_require_details_results(matches)

        context = {
            'datetimes': basic_results.datetimes('datetime', 'minute'),
            'details': details_results,
        }
        context.update(extra_context)
        templates = self.template_path('results.html', competition.slug, season.slug)
        return self.render(request, templates, context)

    @competition_slug
    @login_required_m
    def match_results(self, request, competition, season, date, time, extra_context, **kwargs):
        has_permission = permissions_required(request, Match, return_403=False)
        if has_permission is not None:
            return has_permission
        redirect_to = self.reverse('results', args=(competition.slug, season.slug))
        return super(CompetitionSite, self).match_results(
            request, competition=competition, season=season,
            date=date, time=time,
            extra_context=extra_context,
            redirect_to=redirect_to,
            **kwargs)

    @login_required_m
    @competition_slug
    def edit_match_detail(self, request, match, extra_context, **kwargs):
        has_permission = permissions_required(request, Match, instance=match, return_403=False)
        if has_permission is not None:
            return has_permission
        redirect_to = self.reverse(
            'results',
            args=(match.stage.division.season.competition.slug, match.stage.division.season.slug))
        return super(CompetitionSite, self).edit_match_detail(
            request, stage=match.stage, match=match, extra_context=extra_context,
            redirect_to=redirect_to, **kwargs)

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
        matches = matches.select_related(
            'stage__division__season__competition',
            'stage__follows',
            'stage_group__stage__follows',
            'play_at__ground__venue',
        )

        # Reduce the size of the data set to return from the database
        matches = matches.defer('stage__division__season__competition__copy')

        # Remove any matches that are part of a draft division unless being viewed
        # by a superuser.
        if not request.user.is_superuser:
            matches = matches.exclude(stage__division__draft=True)

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
            event['uid'] = match.uuid
            event.add('summary', match.title)
            if match.play_at.ground:
                event.add(
                    'location',
                    '{} ({})'.format(match.play_at.ground.venue, match.play_at),
                )
            else:
                event.add('location', match.play_at)
            event.add('geo', (match.play_at.latitude, match.play_at.longitude))
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
