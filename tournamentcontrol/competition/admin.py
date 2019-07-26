from __future__ import unicode_literals

import collections
import logging
import operator

from django.apps import apps
from django.conf import settings
from django.conf.urls import include, url
from django.contrib import messages
from django.db import models
from django.db.models import Case, F, Q, Sum, When
from django.forms.models import _get_foreign_key
from django.http import Http404, HttpResponse, HttpResponseGone
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _, ungettext
from six.moves import reduce
from touchtechnology.admin.base import AdminComponent
from touchtechnology.admin.sites import site
from touchtechnology.common.decorators import csrf_exempt_m, staff_login_required_m
from touchtechnology.common.prince import prince
from tournamentcontrol.competition.dashboard import (
    BasicResultWidget, DetailResultWidget, MostValuableWidget, ProgressStageWidget,
    ScoresheetWidget,
)
from tournamentcontrol.competition.decorators import competition, registration
from tournamentcontrol.competition.forms import (
    ClubAssociationForm, ClubRoleForm, CompetitionForm, DivisionForm, DrawFormatForm,
    DrawGenerationFormSet, DrawGenerationMatchFormSet, GroundForm, MatchEditForm,
    MatchScheduleFormSet, MatchWashoutFormSet, PersonEditForm, PersonMergeForm,
    ProgressMatchesFormSet, ProgressTeamsFormSet, RescheduleDateFormSet,
    SeasonAssociationFormSet, SeasonForm, SeasonMatchTimeFormSet, StageForm,
    StageGroupForm, TeamAssociationForm, TeamAssociationFormSet, TeamForm, TeamRoleForm,
    UndecidedTeamForm, VenueForm,
)
from tournamentcontrol.competition.models import (
    Club, ClubAssociation, ClubRole, Competition, Division, DivisionExclusionDate,
    DrawFormat, Ground, LadderEntry, LadderSummary, Match, MatchScoreSheet, Person,
    Season, SeasonAssociation, SeasonExclusionDate, SeasonMatchTime, SeasonReferee,
    SimpleScoreMatchStatistic, Stage, StageGroup, Team, TeamAssociation, TeamRole,
    UndecidedTeam, Venue,
)
from tournamentcontrol.competition.sites import CompetitionAdminMixin
from tournamentcontrol.competition.tasks import generate_pdf_scorecards
from tournamentcontrol.competition.utils import (
    generate_fixture_grid, generate_scorecards, legitimate_bye_match, match_unplayed,
    team_needs_progressing,
)
from tournamentcontrol.competition.wizards import DrawGenerationWizard

SCORECARD_PDF_WAIT = getattr(
    settings, 'TOURNAMENTCONTROL_SCORECARD_PDF_WAIT', 5)

log = logging.getLogger(__name__)


def next_related_factory(model, parent=None, fk_name=None):
    kw = {}
    if parent is not None:
        if fk_name is None:
            fk = _get_foreign_key(parent.__class__, model)
            kw = {fk.name: parent}
        else:
            kw = {fk_name: parent}
    last = model.objects.filter(**kw) \
                .aggregate(order=models.Max('order')) \
                .get('order') or 0
    return model(order=last + 1, **kw)


class CompetitionAdminComponent(CompetitionAdminMixin, AdminComponent):
    verbose_name = _('Tournament Control')
    unprotected = False

    def __init__(self, app, name="fixja", app_name="competition"):
        super(CompetitionAdminComponent, self).__init__(app, name, app_name)

    def dropdowns(self):
        dl = (
            (_('Competitions'), self.reverse('competition:list'), 'trophy'),
            (_('Clubs'), self.reverse('club:list'), 'shield'),
            (_('Draw Formats'), self.reverse('format:list'), 'wrench'),
            (_('Reports'), self.reverse('scorecard-report'), 'book'),
        )
        return dl

    @property
    def widgets(self):
        widget_classes = (
            BasicResultWidget,
            ProgressStageWidget,
            ScoresheetWidget,
            DetailResultWidget,
            MostValuableWidget,
        )
        return widget_classes

    def render(self, request, templates, context, *args, **kwargs):
        context.update({
            'base': 'tournamentcontrol/rego/admin/base.html',
        })
        return super(CompetitionAdminComponent, self).render(
            request, templates, context, *args, **kwargs)

    def get_urls(self):
        matchscoresheet_urls = ([
            url(r"add/$", self.edit_matchscoresheet, name="add"),
            url(r"(?P<pk>[^/]+)/$", self.edit_matchscoresheet, name="edit"),
            url(r"(?P<pk>[^/]+)/delete/$", self.delete_matchscoresheet, name="delete"),
        ], self.app_name)

        match_urls = include(([
            url(r'^add/$', self.edit_match, name='add'),
            url(r'^(?P<match_id>\d+)/', include([
                url(r'^$', self.edit_match, name='edit'),
                url(r'^delete/$', self.delete_match, name='delete'),
                url(r'^detail/$', self.edit_match_detail, name='detail'),

                url(r'^scoresheet/', include(matchscoresheet_urls,
                                             namespace='matchscoresheet')),

                # FIXME - these just prevent template rendering failures
                url(r'^ladder/', include(([
                    url(r'^add/$', self.index, name='add'),
                ], self.app_name), namespace='ladderentry')),
                url(r'^statistic/', include(([
                    url(r'^add/$', self.index, name='add'),
                ], self.app_name), namespace='simplescorematchstatistic')),
            ])),
        ], self.app_name), namespace='match')

        role_patterns = ([
            url(r'^add/$', self.edit_role, name='add'),
            url(r'^(?P<pk>\d+)/$',
                self.edit_role, name='edit'),
            url(r'^(?P<pk>\d+)/delete/$',
                self.delete_role, name='delete'),
        ], self.app_name)

        urlpatterns = [
            url(r'^$', self.index, name='index'),

            url(r'^competition/', include(([
                url(r'^$', self.list_competitions, name='list'),  # KEEP
                url(r'^add/$', self.edit_competition, name='add'),

                url(r'^(?P<competition_id>\d+)/', include([
                    url(r'^$', self.edit_competition, name='edit'),
                    url(r'^delete/$', self.delete_competition, name='delete'),
                    url(r'^permission/$', self.perms_competition, name='perms'),
                    url(r'^seasons/', include(([
                        url(r'^add/$', self.edit_season, name='add'),
                        url(r'^(?P<season_id>\d+)/', include([
                            url(r'^$', self.edit_season, name='edit'),
                            url(r'^delete/$', self.delete_season, name='delete'),
                            url(r'^reschedule/$', self.match_reschedule, name='reschedule'),
                            url(r'^timeslot/', include(([
                                url(r'^add/$', self.edit_timeslot, name='add'),
                                url(r'^(?P<pk>\d+)/$', self.edit_timeslot, name='edit'),
                                url(r'^(?P<pk>\d+)/delete/$', self.delete_timeslot, name='delete'),
                            ], self.app_name), namespace='seasonmatchtime')),

                            url(r'^referees/', include(([
                                url(r'^add/$', self.edit_seasonreferee, name='add'),
                                url(r'^(?P<pk>\d+)/', include([
                                    url(r'^$', self.edit_seasonreferee, name='edit'),
                                    url(r'^delete/$', self.delete_seasonreferee, name='delete'),
                                ])),
                            ], self.app_name), namespace='seasonreferee')),

                            url(r'^permission/$', self.perms_season, name='perms'),

                            url(r'^venue/', include(([
                                url(r'^add/$', self.edit_venue, name='add'),
                                url(r'^(?P<venue_id>\d+)/', include([
                                    url(r'^$', self.edit_venue, name='edit'),
                                    url(r'^delete/$', self.delete_venue, name='delete'),
                                    url(r'^ground/', include(([
                                        url(r'^add/$', self.edit_ground, name='add'),
                                        url(r'^(?P<ground_id>\d+)/$', self.edit_ground, name='edit'),
                                        url(r'^(?P<ground_id>\d+)/delete/$', self.delete_ground, name='delete'),
                                    ], self.app_name), namespace='ground')),
                                ])),
                            ], self.app_name), namespace='venue')),

                            url(r'^exclusion/', include(([
                                url(r'^add/$', self.edit_seasonexclusiondate, name='add'),
                                url(r'^(?P<pk>\d+)/$', self.edit_seasonexclusiondate, name='edit'),
                                url(r'^(?P<pk>\d+)/delete/$', self.delete_seasonexclusiondate, name='delete'),
                            ], self.app_name), namespace='seasonexclusiondate')),

                            url(r'^division/', include(([
                                url(r'^add/$', self.edit_division, name='add'),
                                url(r'^(?P<division_id>\d+)/', include([
                                    url(r'^$', self.edit_division, name='edit'),
                                    url(r'^delete/$', self.delete_division, name='delete'),
                                    url(r'^stage/', include(([
                                        url(r'^add/$', self.edit_stage, name='add'),
                                        url(r'^(?P<stage_id>\d+)/', include([
                                            url(r'^$', self.edit_stage, name='edit'),
                                            url(r'^delete/$', self.delete_stage, name='delete'),
                                            url(r'^match/', match_urls),  # is namespaces "match"

                                            url(r'^', include(([
                                                # url(r'^draw/$', self.index, name='list'),
                                                url(r'^draw/build/$', self.generate_draw, name='build'),
                                                url(r'^draw/undo/$', self.undo_draw, name='undo'),
                                                url(r'^progress/$', self.progress_teams, name='progress'),
                                            ], self.app_name), namespace='draw')),

                                            url(r'^team/', include(([
                                                url(r'^add/$', self.edit_team, name='add'),
                                                url(r'^(?P<team_id>\d+)/$', self.edit_team, name='edit'),
                                                url(r'^(?P<team_id>\d+)/delete/$', self.delete_team, name='delete'),
                                                url(r'^(?P<team_id>\d+)/match/', match_urls),  # is namespaces "match"
                                            ], self.app_name), namespace='undecidedteam')),

                                            url(r'^scorecards.(?P<mode>(pdf|html))$', self.scorecards, name='scorecards'),

                                            url(r'^pool/', include(([
                                                # url(r'^$', self.list_pools, name='list'),
                                                url(r'^add/$', self.edit_pool, name='add'),
                                                url(r'^(?P<pool_id>\d+)/', include([
                                                    url(r'^$', self.edit_pool, name='edit'),
                                                    url(r'^delete/$', self.delete_pool, name='delete'),

                                                    url(r'^match/', match_urls),
                                                ])),
                                            ], self.app_name), namespace='stagegroup')),
                                        ])),
                                    ], self.app_name), namespace='stage')),

                                    url(r'^teams/', include(([
                                        url(r'^add/$', self.edit_team, name='add'),
                                        url(r'^(?P<team_id>\d+)/', include([
                                            url(r'^$', self.edit_team, name='edit'),
                                            url(r'^delete/$', self.delete_team, name='delete'),
                                            url(r'^permissions/$', self.perms_team, name='perms'),

                                            url(r'^match/', match_urls),

                                            url(r'^association/', include(([
                                                url(r'^add/$', self.edit_teamassociation, name='add'),
                                                url(r'^(?P<pk>\d+)/', include([
                                                    url(r'^$', self.edit_teamassociation, name='edit'),
                                                    url(r'^delete/$', self.delete_teamassociation, name='delete'),
                                                ])),
                                            ], self.app_name), namespace='teamassociation')),
                                        ])),
                                    ], self.app_name), namespace='team')),

                                    url(r'^scorers/$', self.highest_point_scorer, name='scorers'),

                                    # FIXME
                                    url(r'^exclusion/', include(([
                                        url(r'^add/$', self.edit_divisionexclusiondate, name='add'),
                                        url(r'^(?P<pk>\d+)/$', self.edit_divisionexclusiondate, name='edit'),
                                        url(r'^(?P<pk>\d+)/delete/$', self.delete_divisionexclusiondate, name='delete'),
                                    ], self.app_name), namespace='divisionexclusiondate')),

                                ])),
                            ], self.app_name), namespace='division')),

                            url(r'^scorecards/(?P<result_id>[^/]+)\.pdf$', self.scorecards_async, name='scorecards-async'),
                        ])),

                    ], self.app_name), namespace='season')),

                    url(r'^role-', include([
                        url(r'^club/', include(role_patterns, namespace='clubrole'), {'cls': 'club'}),
                        url(r'^team/', include(role_patterns, namespace='teamrole'), {'cls': 'team'}),
                    ])),
                ])),
            ], self.app_name), namespace='competition')),

            url(r'^(?P<competition_id>\d+)/seasons/(?P<season_id>\d+)/report.html$', self.season_report, name='season-report'),
            url(r'^(?P<competition_id>\d+)/seasons/(?P<season_id>\d+)/summary.html$', self.season_summary, name='season-summary'),

            url(r'^(?P<competition_id>\d+)/seasons/(?P<season_id>\d+)/matches/grid.(?P<mode>(pdf|html))$', self.season_grid, name='match-grid'),
            url(r'^(?P<competition_id>\d+)/seasons/(?P<season_id>\d+)/matches/(?P<datestr>\d{8})(?::(?P<timestr>\d{4}))?/', include(
                [
                    url(r'^results(?::(?P<division_id>\d+))?/$', self.match_results, name='match-results'),
                    url(r'^washout/$', self.match_washout, name='match-washout'),
                    url(r'^schedule/$', self.match_schedule, name='match-schedule'),
                    url(r'^schedule/(?P<division_id>\d+)/$', self.match_schedule, name='match-schedule'),
                    url(r'^schedule/(?P<division_id>\d+)/(?P<stage_id>\d+)/$', self.match_schedule, name='match-schedule'),
                    url(r'^schedule/(?P<division_id>\d+)/(?P<stage_id>\d+)/(?P<round>\d+)/$', self.match_schedule, name='match-schedule'),
                    url(r'^scorecards.(?P<mode>(pdf|html))$', self.scorecards, name='scorecards'),
                    url(r'^runsheet.html$', self.day_runsheet, name='match-runsheet'),
                    url(r'^grid.(?P<mode>(pdf|html))$', self.day_grid, name='match-grid'),
                ]
            )),

            url(r'^club/', include(([
                url(r'^$', self.list_clubs, name='list'),
                url(r'^add/$', self.edit_club, name='add'),
                url(r'^(?P<club_id>\d+)/$', self.edit_club, name='edit'),
                url(r'^(?P<club_id>\d+)/delete/$', self.delete_club, name='delete'),
                url(r'^(?P<club_id>\d+)/', include([
                    url(r'^person/', include(([
                        url(r'^add/$', self.edit_person, name='add'),
                        url(r'^(?P<person_id>[^/]+)/$', self.edit_person, name='edit'),
                        url(r'^(?P<person_id>[^/]+)/delete/$', self.delete_person, name='delete'),
                        url(r'^(?P<person_id>[^/]+)/merge/$', self.merge_person, name='merge'),
                    ], self.app_name), namespace='person')),
                    # From RegistrationBase
                    url(r'officials/(?P<season_id>\d+)/$', self.officials, name='officials'),
                    url(r'(?P<season_id>\d+)/registration.(?P<mode>html|pdf)$', self.registration_form, name='registration-form'),

                    # FIXME should have a 'season' namespace
                    url(r'^(?P<season_id>\d+)/team/(?P<team_id>\d+)/', include(([
                        url(r'^$', self.edit_team_members, name='edit'),
                        # url(r'^add/$', self.edit_team_members, name='add'),
                    ], self.app_name), namespace='team')),
                    url(r'^clubassociation/', include(([
                        url(r'^add/$', self.edit_clubassociation, name='add'),
                        url(r'^(?P<clubassociation_id>\d+)/$', self.edit_clubassociation, name='edit'),
                    ], self.app_name), namespace='clubassociation')),
                ])),
            ], self.app_name), namespace='club')),

            url(r'^scorecards/$', self.scorecard_report, name='scorecard-report'),

            url(r'^draw-format/', include(([
                url(r'^$', self.list_drawformat, name='list'),
                url(r'^add/$', self.edit_drawformat, name='add'),
                url(r'^(?P<pk>\d+)/$', self.edit_drawformat, name='edit'),
                url(r'^(?P<pk>\d+)/delete/$', self.delete_drawformat, name='delete'),
            ], self.app_name), namespace='format')),

            url(r'^reorder/(?P<model>[^/:]+)(?::(?P<parent>[^/]+))?/(?P<pk>\d+)/(?P<direction>\w+)/$', self.reorder, name='reorder'),
        ]

        return urlpatterns

    @staff_login_required_m
    def reorder(self, request, model, pk, direction, parent=None, **kwargs):
        # Determine where to redirect back to following the reordering
        redirect_to = request.META.get('HTTP_REFERER', None)
        if redirect_to is None:
            raise Http404

        # Reconstruct the object from the keyword arguments
        cls = apps.get_model('competition', model)
        obj = cls.objects.get(pk=pk)

        # Determine the neighbouring order values based on direction
        if direction == 'up':
            orders = obj.order, obj.order - 1
        elif direction == 'down':
            orders = obj.order, obj.order + 1
        else:
            raise Http404

        # Get our OrderedSitemapNode queryset for the given model
        queryset = cls.objects.filter(order__in=orders)
        if parent is not None:
            queryset = queryset.filter(**{str(parent): getattr(obj, parent)})

        # We can't reorder the first item up or the last item down; throw
        # a 404 when trying to do so.
        if queryset.count() != 2:
            raise Http404

        # Swap the order value of the two neighbours and write to db.
        # 1) Hang onto the original ordering of a and b
        a, b = queryset
        ao, bo = a.order, b.order

        # 2) Set a.order to 0 to allow b.order to assume that value
        a.order = 0
        a.save()

        # 3) Assign the new value to b.order
        b.order = ao
        b.save()

        # 4) Assign the new value to a.order
        a.order = bo
        a.save()

        fmt = _('The %(model)s "%(title)s" has been '
                'reordered %(direction)s the list.')
        messages.info(request, fmt % dict(model=cls._meta.verbose_name,
                                          title=obj.title,
                                          direction=direction))

        return self.redirect(redirect_to)

    @staff_login_required_m
    def index(self, request, **kwargs):
        messages.warning(request, _("We're moving a few things around, please "
                                    "update any bookmarks you may find that "
                                    "have broken."))
        return self.redirect(self.reverse('competition:list'))

    @competition
    @staff_login_required_m
    def edit_role(self, request, cls, pk=None, **extra_context):
        if cls == 'club':
            model, form_class = ClubRole, ClubRoleForm
        elif cls == 'team':
            model, form_class = TeamRole, TeamRoleForm
        else:
            raise Http404  # noqa

        competition = extra_context.get('competition')

        if pk is None:
            instance = model(competition=competition)
        else:
            instance = get_object_or_404(model, pk=pk, competition=competition)

        return self.generic_edit(request, model, instance=instance,
                                 form_class=form_class,
                                 permission_required=True,
                                 post_save_redirect=self.redirect(
                                     competition.urls['edit']),
                                 extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_role(self, request, cls, pk, extra_context, **kwargs):
        if cls == 'club':
            model = ClubRole
        elif cls == 'team':
            model = TeamRole
        else:
            raise Http404
        competition = extra_context.get('competition')
        queryset = model.objects.filter(competition=competition)
        post_delete_redirect = self.redirect(
            competition.urls['edit'] + '#%s_roles-tab' % cls)
        return self.generic_delete(request, queryset, pk=pk,
                                   permission_required=True,
                                   post_delete_redirect=post_delete_redirect)

    @competition
    @staff_login_required_m
    def edit_matchscoresheet(self, request, pk=None, **extra_context):
        match = extra_context.get("match")

        if pk is None:
            instance = MatchScoreSheet(match=match)
        else:
            instance = get_object_or_404(MatchScoreSheet, pk=pk, match=match)

        return self.generic_edit(request, MatchScoreSheet, instance=instance,
                                 form_fields=("image",),
                                 permission_required=True,
                                 post_save_redirect=self.redirect(match.urls["edit"]),
                                 extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_matchscoresheet(self, request, pk, **extra_context):
        return self.generic_delete(request, MatchScoreSheet, pk=pk,
                                   permission_required=True)

    @staff_login_required_m
    def list_drawformat(self, request, **extra_context):
        return self.generic_list(request, DrawFormat,
                                 paginate_by=0,
                                 permission_required=True,
                                 extra_context=extra_context)

    @staff_login_required_m
    def edit_drawformat(self, request, pk=None, **extra_context):
        post_save_redirect = self.redirect(self.reverse('format:list'))
        return self.generic_edit(request, DrawFormat, pk=pk,
                                 form_class=DrawFormatForm,
                                 permission_required=True,
                                 post_save_redirect=post_save_redirect,
                                 extra_context=extra_context)

    @staff_login_required_m
    def delete_drawformat(self, request, pk, **kwargs):
        return self.generic_delete(request, DrawFormat, pk=pk,
                                   permission_required=True)

    @staff_login_required_m
    def list_competitions(self, request, **extra_context):
        return self.generic_list(request, Competition,
                                 paginate_by=0,
                                 permission_required=True,
                                 extra_context=extra_context)

    @competition
    @staff_login_required_m
    def perms_competition(self, request, competition, **kwargs):
        return self.generic_permissions(request, Competition,
                                        instance=competition,
                                        **kwargs)

    @competition
    @staff_login_required_m
    def edit_competition(self, request, extra_context, competition=None,
                         **kwargs):
        if competition is None:
            competition = next_related_factory(Competition)
        return self.generic_edit(request, Competition,
                                 instance=competition,
                                 form_class=CompetitionForm,
                                 form_kwargs={'user': request.user},
                                 permission_required=True,
                                 extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_competition(self, request, competition, extra_context,
                           **kwargs):
        return self.generic_delete(request, Competition,
                                   pk=competition.pk,
                                   permission_required=True,
                                   extra_context=extra_context)

    @competition
    @staff_login_required_m
    def edit_season(self, request, competition, extra_context, season=None,
                    **kwargs):
        if season is None:
            season = next_related_factory(Season, competition)

        dates = season.matches.dates('date', 'day')
        extra_context.setdefault('dates', dates)

        return self.generic_edit(
            request, Season,
            instance=season,
            related=(
                'exclusions',
                'divisions',
                'venues',
                'timeslots',
                'referees',
            ),
            form_class=SeasonForm,
            form_kwargs={'user': request.user},
            post_save_redirect=self.redirect(competition.urls['edit']),
            permission_required=True,
            extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_season(self, request, extra_context, season, **kwargs):
        return self.generic_delete(request, Season,
                                   pk=season.pk,
                                   permission_required=True,
                                   extra_context=extra_context)

    @competition
    @staff_login_required_m
    def perms_season(self, request, season, **kwargs):
        post_save_redirect = self.redirect(season.competition.urls['edit'])
        return self.generic_permissions(request, Season,
                                        instance=season,
                                        post_save_redirect=post_save_redirect,
                                        **kwargs)

    @competition
    @staff_login_required_m
    def season_report(self, request, season, extra_context, **kwargs):
        teams = Team.objects.filter(division__season=season) \
                            .order_by('club', 'division', 'order') \
                            .select_related('club')
        return self.generic_list(
            request, teams,
            templates=self.template_path('season_report.html'),
            paginate_by=0,
            permission_required=False,
            extra_context=extra_context)

    @competition
    @staff_login_required_m
    def season_summary(self, request, competition, season, extra_context,
                       **kwargs):
        teams = (
            Team.objects
            .select_related('club', 'division')
            .filter(division__season=season)
            .order_by('club__title', 'division__order')
            .annotate(
                player_count=Sum(
                    Case(
                        When(people__is_player=True, then=1),
                        output_field=models.IntegerField())),
                non_player_count=Sum(
                    Case(
                        When(people__is_player=False, then=1),
                        output_field=models.IntegerField())),
            )
        )

        context = {
            'teams': teams,
            'season': season,
            'competition': competition,
        }
        context.update(extra_context)

        templates = self.template_path('season_summary.html')
        return self.render(request, templates, context)

    @competition
    @staff_login_required_m
    def edit_timeslot(self, request, extra_context, season, pk=None,
                      **kwargs):
        instance = SeasonMatchTime(season=season) if pk is None else None
        return self.generic_edit(request, season.timeslots,
                                 pk=pk, instance=instance,
                                 form_fields=(
                                     'start_date',
                                     'end_date',
                                     'start',
                                     'interval',
                                     'count',
                                 ),
                                 post_save_redirect=self.redirect(
                                     season.urls['edit']),
                                 permission_required=True,
                                 extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_timeslot(self, request, season, pk, **kwargs):
        post_delete_redirect = self.redirect(
            season.urls['edit'] + '#timeslots-tab')
        return self.generic_delete(request, SeasonMatchTime, pk=pk,
                                   permission_required=True,
                                   post_delete_redirect=post_delete_redirect)

    @competition
    @staff_login_required_m
    def edit_seasonexclusiondate(self, request, season, extra_context, pk=None,
                                 **kwargs):
        instance = SeasonExclusionDate(season=season) if pk is None else None
        return self.generic_edit(request, SeasonExclusionDate,
                                 pk=pk, instance=instance,
                                 form_fields=('date',),
                                 post_save_redirect=self.redirect(
                                     season.urls['edit']),
                                 permission_required=True,
                                 extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_seasonexclusiondate(self, request, season, pk, **kwargs):
        post_delete_redirect = self.redirect(
            season.urls['edit'] + '#exclusions-tab')
        return self.generic_delete(request, season.exclusions, pk=pk,
                                   permission_required=True,
                                   post_delete_redirect=post_delete_redirect)

    @competition
    @staff_login_required_m
    def timeslots(self, request, competition, season, extra_context, **kwargs):
        return self.generic_edit_multiple(
            request, SeasonMatchTime,
            formset_class=SeasonMatchTimeFormSet,
            formset_kwargs={'instance': season},
            post_save_redirect_args=(competition.pk, season.pk),
            post_save_redirect='competition:season:edit',
            templates=self.template_path('timeslots.html', 'season'),
            extra_context=extra_context)

    @competition
    @staff_login_required_m
    def edit_venue(self, request, season, extra_context, venue=None, **kwargs):
        if venue is None:
            venue = next_related_factory(Venue, season)
            # By default timezone should inherit from the season
            venue.timezone = season.timezone

        return self.generic_edit(request, Venue,
                                 instance=venue,
                                 related=(
                                     'grounds',
                                 ),
                                 form_class=VenueForm,
                                 form_kwargs={'user': request.user},
                                 # formset_class=GroundFormSet,
                                 post_save_redirect=self.redirect(
                                     season.urls['edit']),
                                 permission_required=True,
                                 extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_venue(self, request, season, venue, extra_context=None, **kwargs):
        post_delete_redirect = self.redirect(
            season.urls['edit'] + '#venues-tab')
        return self.generic_delete(request, Venue,
                                   pk=venue.pk,
                                   permission_required=True,
                                   post_delete_redirect=post_delete_redirect,
                                   extra_context=extra_context)

    @competition
    @staff_login_required_m
    def edit_ground(self, request, venue, extra_context, ground=None,
                    **kwargs):
        if ground is None:
            ground = next_related_factory(Ground, venue, 'venue')
            # By default timezone and geo should inherit from the venue
            ground.timezone = venue.timezone
            ground.latlng = venue.latlng

        return self.generic_edit(request, venue.grounds,
                                 instance=ground,
                                 related=(),
                                 form_class=GroundForm,
                                 form_kwargs={'user': request.user},
                                 post_save_redirect=self.redirect(
                                     venue.urls['edit']),
                                 permission_required=True,
                                 extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_ground(self, request, venue, ground, extra_context=None, **kwargs):
        post_delete_redirect = self.redirect(
            venue.urls['edit'] + '#grounds-tab')
        return self.generic_delete(request, Ground,
                                   pk=ground.pk,
                                   permission_required=True,
                                   post_delete_redirect=post_delete_redirect,
                                   extra_context=extra_context)

    @competition
    @staff_login_required_m
    def edit_division(self, request, season, extra_context, division=None,
                      **kwargs):
        if division is None:
            division = next_related_factory(Division, season)

        return self.generic_edit(
            request, Division,
            instance=division,
            related=(
                'teams',
                'stages',
                'exclusions',
            ),
            form_class=DivisionForm,
            form_kwargs={'user': request.user},
            post_save_redirect=self.redirect(season.urls['edit']),
            permission_required=True,
            extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_division(self, request, season, division, **kwargs):
        post_delete_redirect = self.redirect(
            season.urls['edit'] + '#divisions-tab')
        return self.generic_delete(request, Division,
                                   pk=division.pk,
                                   permission_required=True,
                                   post_delete_redirect=post_delete_redirect)

    @competition
    @staff_login_required_m
    def edit_divisionexclusiondate(self, request, division, extra_context,
                                   pk=None, **kwargs):
        if pk is None:
            instance = DivisionExclusionDate(division=division)
        else:
            instance = None
        return self.generic_edit(
            request, DivisionExclusionDate,
            pk=pk, instance=instance,
            form_fields=(
                'date',
            ),
            post_save_redirect=self.redirect(division.urls['edit']),
            permission_required=True,
            extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_divisionexclusiondate(self, request, division, pk, **kwargs):
        post_delete_redirect = self.redirect(
            division.urls['edit'] + '#exclusions-tab')
        return self.generic_delete(request, division.exclusions, pk=pk,
                                   permission_required=True,
                                   post_delete_redirect=post_delete_redirect)

    @competition
    @staff_login_required_m
    def edit_stage(self, request, division, extra_context, stage=None, **kwargs):
        if stage is None:
            stage = next_related_factory(Stage, division)

        def post_save_callback(obj):
            return self.redirect(obj.urls['edit'])

        return self.generic_edit(
            request, division.stages.select_related(
                'matches__home_team',
                'matches__away_team',
            ),
            pk=stage.pk,
            instance=stage,
            related=(
                'pools',
                'undecided_teams',
                'matches',
            ),
            form_class=StageForm, form_kwargs={'user': request.user},
            post_save_callback=post_save_callback,
            post_save_redirect=self.redirect(division.urls['edit']),
            permission_required=True,
            extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_stage(self, request, division, stage, **kwargs):
        post_delete_redirect = self.redirect(
            division.urls['edit'] + '#stages-tab')
        return self.generic_delete(request, division.stages, pk=stage.pk,
                                   permission_required=True,
                                   post_delete_redirect=post_delete_redirect)

    @competition
    @staff_login_required_m
    def edit_pool(self, request, stage, extra_context, pool=None, **kwargs):
        if pool is None:
            pool = next_related_factory(StageGroup, stage)

        def post_save_callback(obj):
            if pool:
                return self.redirect(obj.urls['edit'])

        return self.generic_edit(
            request, StageGroup,
            instance=pool,
            related=(),
            form_class=StageGroupForm,
            form_kwargs={'user': request.user},
            post_save_callback=post_save_callback,
            post_save_redirect=self.redirect(stage.urls['edit']),
            permission_required=True,
            extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_pool(self, request, stage, pool, **kwargs):
        post_delete_redirect = self.redirect(stage.urls['edit'] + '#pools-tab')
        return self.generic_delete(request, stage.pools, pk=pool.pk,
                                   permission_required=True,
                                   post_delete_redirect=post_delete_redirect)

    @competition
    @staff_login_required_m
    def edit_team(self, request, competition, season, division, extra_context,
                  stage=None, team=None, **kwargs):
        """
        This view gets mounted twice, first at the division level and secondly
        at the stage level. When at the competition level it will deal with
        `Team` instances and with `UndecidedTeam` instances at the stage level.

         * raise a `Http404` when `Stage.order` == 1
        """
        related = ()

        if stage:
            model = UndecidedTeam
            post_save_redirect = self.redirect(stage.urls['edit'])
            form_class, form_kwargs = UndecidedTeamForm, {}
            if team is None:
                team = UndecidedTeam(stage=stage)
        else:
            model = Team
            post_save_redirect = self.redirect(division.urls['edit'])
            form_class, form_kwargs = TeamForm, {'division': division}
            if team is None:
                team = next_related_factory(Team, division)
            # only "real" teams have people in them
            related = ('people',)

        return self.generic_edit(
            request, model,
            instance=team,
            related=related,
            form_class=form_class, form_kwargs=form_kwargs,
            post_save_redirect=post_save_redirect,
            permission_required=True,
            extra_context=extra_context)

    @competition
    @staff_login_required_m
    def perms_team(self, request, team, **kwargs):
        competition = kwargs.get('competition')
        season = kwargs.get('season')
        division = kwargs.get('division')
        return self.generic_permissions(
            request, Team,
            instance=team,
            post_save_redirect='admin:fixja:competition:season:'
                               'division:team:list',
            post_save_redirect_args=(
                competition.pk,
                season.pk,
                division.pk,
            ),
            permission_required=True,
            **kwargs)

    @competition
    @staff_login_required_m
    def delete_team(self, request, competition, season, division, team,
                    extra_context, stage=None, **kwargs):
        if team.matches.exists():
            return HttpResponseGone('The team has matches associated with it.')

        if stage:
            manager = stage.undecided_teams
            post_delete_redirect_url = self.reverse(
                'competition:season:division:stage:edit',
                args=(competition.pk, season.pk, division.pk, stage.pk))
        else:
            manager = division.teams
            post_delete_redirect_url = self.reverse(
                'competition:season:division:edit',
                args=(competition.pk, season.pk, division.pk))

        return self.generic_delete(
            request, manager, pk=team.pk,
            post_delete_redirect=self.redirect(post_delete_redirect_url),
            permission_required=False,
            extra_context=extra_context)

    @competition
    @staff_login_required_m
    def edit_teamassociation(self, request, team, extra_context, pk=None,
                             **kwargs):
        if pk is None:
            instance = TeamAssociation(team=team)
        else:
            instance = get_object_or_404(team.people, pk=pk)

        return self.generic_edit(
            request, team.people, instance=instance,
            form_class=TeamAssociationForm,
            form_kwargs={
                'team': team,
            },
            post_save_redirect=self.redirect(team.urls['edit']),
            permission_required=True,
            extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_teamassociation(self, request, team, pk, **kwargs):
        post_delete_redirect = self.redirect(team.urls['edit'] + '#people-tab')
        return self.generic_delete(request, team.people, pk=pk,
                                   permission_required=True,
                                   post_delete_redirect=post_delete_redirect)

    @competition
    @staff_login_required_m
    def edit_seasonreferee(self, request, season, extra_context, pk=None, **kwargs):
        # FIXME this dance to establish an instance on a related object
        #       feels like it's broken to me. If provided with a related
        #       manager it should create against that? I might be over
        #       simplifying that - django.contrib.admin probably doesn't
        #       do that since they use a very flat admin (no nesting).
        if pk is None:
            instance = SeasonReferee(season=season)
        else:
            instance = get_object_or_404(season.referees, pk=pk)
        return self.generic_edit(request, season.referees,
                                 instance=instance,
                                 form_fields=('person', 'club'),
                                 post_save_redirect=self.redirect(
                                     season.urls['edit']),
                                 permission_required=True,
                                 extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_seasonreferee(self, request, season, pk, **kwargs):
        post_delete_redirect = self.redirect(season.urls['edit'] + '#officials-tab')
        return self.generic_delete(request, season.referees, pk=pk,
                                   permission_required=True,
                                   post_delete_redirect=post_delete_redirect)

    @competition
    @staff_login_required_m
    def generate_draw(self, request, competition, season, division, stage,
                      extra_context, **kwargs):

        form_list = [
            DrawGenerationFormSet,
            DrawGenerationMatchFormSet,
        ]

        redirect_to = self.reverse(
            'competition:season:division:edit', args=(competition.pk, season.pk, division.pk))

        view = DrawGenerationWizard.as_view(
            form_list,
            extra_context=extra_context,
            redirect_to=redirect_to,
            stage=stage)

        return view(request)

    @competition
    @staff_login_required_m
    def undo_draw(self, request, division, stage, **kwargs):
        LadderSummary.objects.filter(stage=stage).delete()
        LadderEntry.objects.filter(match__stage=stage).delete()
        Match.objects.filter(stage=stage).delete()
        messages.success(request, _("Your draw has been undone."))
        return self.redirect(division.urls['edit'])

    @competition
    @staff_login_required_m
    def edit_match(self, request, competition, season, division, stage,
                   extra_context, match=None, **kwargs):
        if match is None:
            match = Match(stage=stage, include_in_ladder=stage.keep_ladder)

        return self.generic_edit(
            request, Match,
            instance=match,
            form_class=MatchEditForm,
            post_save_redirect=self.redirect(stage.urls['edit']),
            permission_required=True,
            extra_context=extra_context)

    @competition
    @staff_login_required_m
    def delete_match(self, request, stage, match, **kwargs):
        post_delete_redirect = self.redirect(
            stage.urls['edit'] + '#matches-tab')
        return self.generic_delete(request, stage.matches,
                                   pk=match.pk,
                                   permission_required=True,
                                   post_delete_redirect=post_delete_redirect)

    @competition
    @staff_login_required_m
    def edit_match_detail(self, request, stage, match, extra_context, **kwargs):
        redirect_to = reverse('admin:index')
        return super(CompetitionAdminComponent, self).edit_match_detail(
            request, stage=stage, match=match, extra_context=extra_context,
            redirect_to=redirect_to, **kwargs)

    @competition
    @staff_login_required_m
    def day_runsheet(self, request, season, date, extra_context, **kwargs):
        return super(CompetitionAdminComponent, self).day_runsheet(
            request, season, date, extra_context, **kwargs)

    @competition
    @csrf_exempt_m
    @staff_login_required_m
    def season_grid(self, request, season, mode, extra_context, **kwargs):
        # pass query string parameters along to the context
        for key, val in request.GET.items():
            extra_context.setdefault(key, val)

        return generate_fixture_grid(season, format=mode, request=request,
                                     extra_context=extra_context)

    @competition
    @csrf_exempt_m
    @staff_login_required_m
    def day_grid(self, request, season, date, mode, extra_context, **kwargs):
        return generate_fixture_grid(season, format=mode, request=request,
                                     extra_context=extra_context, dates=[date])

    @competition
    @staff_login_required_m
    def progress_teams(self, request, competition, season, division, stage,
                       extra_context, **kwargs):
        matches = (
            stage.matches
                .filter(team_needs_progressing)
                .exclude(legitimate_bye_match)
        )
        teams = stage.undecided_teams.all()

        if not matches:
            return HttpResponseGone()

        elif matches.filter(
                Q(home_team_undecided__isnull=False, home_team__isnull=True) |
                Q(away_team_undecided__isnull=False, away_team__isnull=True)):
            follows = stage.comes_after

            ladders = collections.OrderedDict()
            if follows.pools.count():
                for pool in follows.pools.all():
                    ladders.setdefault(
                        pool, pool.ladder_summary.select_related('team__club'))
            else:
                ladders.setdefault(
                    None, follows.ladder_summary.select_related('team__club'))

            extra_context['ladders'] = ladders

            generic_edit_kwargs = {
                'formset_class': ProgressTeamsFormSet,
                'formset_kwargs': {
                    'stage': stage,
                },
                'model_or_manager': teams.model,
                'templates': self.template_path('progress_teams.html'),
            }
        else:
            generic_edit_kwargs = {
                'formset_class': ProgressMatchesFormSet,
                'formset_kwargs': {
                    'queryset': matches,
                },
                'model_or_manager': matches.model,
                'templates': self.template_path('progress_matches.html'),
            }

        return self.generic_edit_multiple(
            request,
            post_save_redirect=self.redirect(season.urls['edit']),
            permission_required=False,
            extra_context=extra_context,
            **generic_edit_kwargs)

    @competition
    @staff_login_required_m
    def match_reschedule(self, request, competition, season, extra_context,
                         **kwargs):
        matches = Match.objects.filter(
            match_unplayed,
            stage__division__season=season,
            stage__division__season__competition=competition,
        )

        dates = matches.dates('date', 'day')
        redirect_to = season.urls['edit']

        if request.method == 'POST':
            formset = RescheduleDateFormSet(
                matches=matches, dates=dates, data=request.POST)
            if formset.is_valid():
                changes = formset.save()
                if changes:
                    message = ungettext(
                        "Your change to %(count)d match has been saved.",
                        "Your changes to %(count)d matches have been saved.",
                        changes) % {'count': changes}
                    messages.success(request, message)
                else:
                    messages.info(request, _("No matches were rescheduled."))
                return self.redirect(redirect_to)
        else:
            formset = RescheduleDateFormSet(matches=matches, dates=dates)

        context = {
            'dates': dates,
            'formset': formset,
            'model': matches.none(),
            'cancel_url': redirect_to,
        }
        context.update(extra_context)

        templates = self.template_path('reschedule.html')
        return self.render(request, templates, context)

    # FIXME
    @competition
    @staff_login_required_m
    def match_schedule(self, request, competition, season, date, extra_context,
                       time=None, division=None, stage=None, round=None,
                       **kwargs):
        where = Q(date=date, is_bye=False)

        if stage:
            manager = stage.matches
            if round:
                where &= Q(round=round)
        elif division:
            manager = division.matches
        elif season:
            manager = season.matches

        if time is not None:
            where &= Q(time=time)

        queryset = manager.filter(where) \
                          .order_by('stage__division__order',
                                    'round', 'datetime', 'play_at')

        return self.generic_edit_multiple(
            request, queryset,
            formset_class=MatchScheduleFormSet,
            post_save_redirect=self.redirect(season.urls['edit']),
            templates=self.template_path('match/schedule.html'),
            extra_context=extra_context)

    @competition
    @staff_login_required_m
    def match_results(self, request, competition, season, date, extra_context,
                      division=None, time=None, **kwargs):
        redirect_to = reverse('admin:index', current_app=self.app)
        return super(CompetitionAdminComponent, self).match_results(
            request, competition, season, date, extra_context,
            division=division, time=time, redirect_to=redirect_to, **kwargs)

    # FIXME
    @competition
    @staff_login_required_m
    def match_washout(self, request, competition, season, date, extra_context,
                      time=None, **kwargs):
        matches = Match.objects.filter(
            stage__division__season__id=season.pk,
            stage__division__season__competition__id=competition.pk,
            date=date,
        ).order_by('stage__division__order', 'is_bye', 'datetime', 'play_at')

        # ensure only matches with progressed teams are able to be updated
        matches = matches.filter(match_unplayed)

        # FIXME too complex, be verbose so we can all read and understand it
        if time is not None:
            base = Q(time=time)
            bye_kwargs = matches.filter(time=time).values('stage', 'round')
            time_or_byes = reduce(
                operator.or_,
                map(lambda kw: Q(time__isnull=True, **kw), bye_kwargs),
                base)
            matches = matches.filter(time_or_byes)

        return self.generic_edit_multiple(
            request, matches,
            formset_class=MatchWashoutFormSet,
            templates=self.template_path('match_washout.html'),
            post_save_redirect=self.redirect(season.urls['edit']),
            extra_context=extra_context)

    @staff_login_required_m
    def scorecard_report(self, request, **extra_context):
        from .wizards import scorecardwizard_factory, SeasonForm, FilterForm
        ScorecardWizard = scorecardwizard_factory(
            app=self, extra_context=extra_context)
        wizard = ScorecardWizard.as_view(form_list=[SeasonForm, FilterForm])
        return wizard(request)

    @competition
    @staff_login_required_m
    def scorecards(self, request, competition, season, mode, stage=None,
                   date=None, time=None, **kwargs):
        if stage is not None:
            if stage.matches_needing_printing.count():
                matches = stage.matches_needing_printing.all()
            else:
                matches = stage.matches.all()
        else:
            matches = season.matches.all()

        # legacy/undocumented, remove this?
        if 'd' in request.GET:
            matches = matches.filter(stage__division__slug=request.GET['d'])

        if date is not None:
            matches = matches.filter(date=date)

        if time is not None:
            matches = matches.filter(time=time)

        matches = matches.exclude(legitimate_bye_match)

        extra_context = {
            'competition': competition,
            'season': season,
            'date': date,
            'time': time,
            'stage': stage,
            'filtered': round is not None,
            'round': round,
        }

        templates = self.template_path(
            'scorecards.html', competition.slug, season.slug)

        if mode == 'pdf':
            kw = {
                'matches': matches,
                'templates': templates,
                'extra_context': extra_context,
                'stage': stage,
            }
            if hasattr(request, 'tenant'):
                kw['_schema_name'] = request.tenant.schema_name
                kw['base_url'] = request.build_absolute_uri('/')

            result = generate_pdf_scorecards.delay(**kw)

            reverse_kwargs = {
                'competition_id': competition.pk,
                'season_id': season.pk,
                'result_id': result.id,
            }

            redirect_to = self.reverse(
                'competition:season:scorecards-async', kwargs=reverse_kwargs)
            response = self.redirect(redirect_to)
        else:
            output = generate_scorecards(matches, templates, mode,
                                         extra_context, stage)
            response = HttpResponse(output)

        return response

    @competition
    @staff_login_required_m
    def scorecards_async(self, request, result_id, extra_context, **kwargs):
        result = generate_pdf_scorecards.AsyncResult(result_id)

        if result.ready():
            return HttpResponse(result.wait(), content_type="application/pdf")

        templates = self.template_path('wait.html', 'scorecards')
        response = self.render(request, templates, extra_context)
        response['Refresh'] = SCORECARD_PDF_WAIT
        return response

    @competition
    @staff_login_required_m
    def highest_point_scorer(self, request, division, extra_context, **kwargs):
        def _get_clause(field, aggregate=Sum):
            """
            Local function to produce a Aggregate(Case(When())) instance which
            can be used to extract individual totals for the division.
            """
            return aggregate(
                Case(
                    When(
                        statistics__match__stage__division=division,
                        then=F(field))))

        people = (
            Person.objects
            .select_related('club')
            .annotate(
                played=_get_clause('statistics__played'),
                points=_get_clause('statistics__points'),
                mvp=_get_clause('statistics__mvp'),
            )
            .exclude(played=None)
        )

        scorers = people.order_by('-points', 'played')
        mvp = people.order_by('-mvp', 'played')

        context = {
            'scorers': scorers,
            'mvp': mvp,
        }
        context.update(extra_context)

        templates = self.template_path('scorers.html')
        return self.render(request, templates, context)

    # from RegistrationBase

    @staff_login_required_m
    def list_clubs(self, request, **extra_context):
        return self.generic_list(
            request, Club,
            paginate_by=0,
            permission_required=True,
            extra_context=extra_context)

    @registration
    def edit_club(self, request, extra_context, club=None, **kwargs):
        templates = {
            Team: 'tournamentcontrol/competition/admin/club/team.inc.html',
        }
        extra_context.setdefault('templates', templates)
        return self.generic_edit(
            request, Club,
            instance=club,
            form_fields=(
                'title',
                'short_title',
                'abbreviation',
                'email',
                'website',
                'twitter',
                'facebook',
                'youtube',
                'primary',
                'primary_position',
                'slug',
                'slug_locked',
            ),
            related=(
                'members',
                'teams',
            ),
            permission_required=True,
            extra_context=extra_context)

    @staff_login_required_m
    def delete_club(self, request, club_id, **kwargs):
        return self.generic_delete(
            request, Club,
            pk=club_id,
            permission_required=True)

    @registration
    @staff_login_required_m
    def edit_person(self, request, club, extra_context, person=None, **kwargs):
        if person is None:
            person = Person(club=club)
        # todo
        readonly_fields = (
            'first_name',
            'last_name',
            'gender',
            'date_of_birth',
        )
        return self.generic_edit(
            request, club.members,
            instance=person,
            form_class=PersonEditForm,
            related=(
                'statistics',
            ),
            post_save_redirect=self.redirect(person.club.urls['edit']),
            permission_required=True,
            extra_context=extra_context)

    @registration
    @staff_login_required_m
    def merge_person(self, request, club, extra_context, person, **kwargs):
        return self.generic_edit(
                request, club.members,
                instance=person,
                form_class=PersonMergeForm,
                related=(),
                post_save_redirect=self.redirect(person.club.urls['edit']),
                permission_required=True,
                extra_context=extra_context)

    @registration
    @staff_login_required_m
    def delete_person(self, request, club, person, extra_context, **kwargs):
        now = timezone.now().replace(second=0, microsecond=0)
        queryset = Person.objects.filter(club=club)

        # Ensure the person does not have any statistical data recorded and
        # that we're not attempting to delete someone mid-season.
        queryset = queryset.exclude(statistics__isnull=False)
        queryset = queryset.exclude(
            teamassociation__team__division__season__start_date__lt=now)

        return self.generic_delete(
            request, queryset,
            pk=person.pk,
            post_delete_redirect=self.redirect(club.urls['edit']),
            permission_required=True,
            extra_context=extra_context)

    @registration
    def edit_clubassociation(self, request, club, extra_context, clubassociation_id=None, **kwargs):
        return self.generic_edit(request, ClubAssociation,
                                 pk=clubassociation_id,
                                 form_class=ClubAssociationForm,
                                 form_kwargs={
                                     'user': request.user,
                                     'club': club,
                                 },
                                 permission_required=True,
                                 extra_context=extra_context)

    @registration
    def officials(self, request, club, season, extra_context, **kwargs):
        # Read only is presently applied to the entire application, but we
        # really need to be able to provide granular control for specific
        # seasons.  FIXME
        read_only, scheduled_read_only = self.read_only
        if season.complete:
            if not request.user.is_superuser:
                read_only = True

        if read_only:
            messages.add_message(
                request, messages.INFO,
                _('This season is now read-only to club administrators.'))
        elif scheduled_read_only:
            sro = {'time': scheduled_read_only.strftime('%H:%M'),
                   'date': scheduled_read_only.strftime('%d/%m/%Y')}
            messages.add_message(
                request, messages.WARNING,
                _('This season will become read-only to club administrators '
                  'at %(time)s on %(date)s.') % sro)

        if read_only:
            templates = self.template_path('officials_list.html')
            return self.render(request, templates, extra_context)

        templates = self.template_path('officials.html')
        return self.generic_edit_multiple(
            request, SeasonAssociation,
            queryset=season.officials.filter(club=club),
            formset_class=SeasonAssociationFormSet,
            formset_kwargs={
                'user': request.user,
                'club': club,
                'season': season,
            },
            post_save_redirect='club-teams',
            post_save_redirect_kwargs={'club_id': club.pk},
            templates=templates,
            extra_context=extra_context)

    @registration
    def edit_team_members(self, request, club, team, extra_context, **kwargs):
        statistics = SimpleScoreMatchStatistic.objects.filter(
            Q(player__teamassociation__team=team) &
            Q(match__home_team=team) | Q(match__away_team=team))

        # FIXME this is a hangover from before we had permissions on generics
        read_only, scheduled_read_only = request.user.is_superuser, False

        # Read only is presently applied to the entire application, but we
        # really need to be able to provide granular control for specific
        # seasons.  FIXME
        if team.division.season.complete:
            if not request.user.is_superuser:
                read_only = True

        if read_only:
            messages.add_message(
                request, messages.INFO,
                _('This team is now read-only to club administrators.'))
        elif scheduled_read_only:
            sro = {'time': scheduled_read_only.strftime('%H:%M'),
                   'date': scheduled_read_only.strftime('%d/%m/%Y')}
            messages.add_message(
                request, messages.WARNING,
                _('This team will become read-only to club administrators at '
                  '%(time)s on %(date)s.') % sro)

        if read_only and not request.user.is_superuser:
            templates = self.template_path('team_members.html')
            return self.render(request, templates, extra_context)

        return self.generic_edit_multiple(
            request, TeamAssociation,
            formset_class=TeamAssociationFormSet,
            formset_kwargs={'user': request.user, 'instance': team},
            post_save_redirect='club-teams',
            post_save_redirect_kwargs={'club_id': club.pk},
            permission_required=True,
            extra_context=extra_context)

    @registration
    @staff_login_required_m
    def registration_form(self, request, club, season, teams, competition,
                          mode, extra_context, **kwargs):
        data = collections.OrderedDict()

        for team in teams:
            for pa in team.people.filter(is_player=True, person__isnull=False):
                data.setdefault(team, collections.OrderedDict()) \
                    .setdefault('players', []) \
                    .append((pa.number or '',
                             pa.person.first_name.encode('utf-8').strip(),
                             pa.person.last_name.encode('utf-8').strip(),
                             pa.person.date_of_birth,
                             pa.person.email))

            for pa in team.people.filter(roles__isnull=False,
                                         person__isnull=False) \
                                 .order_by('roles__id', 'person__last_name',
                                           'person__first_name'):
                for role in pa.roles.all():
                    data.setdefault(team, collections.OrderedDict()) \
                        .setdefault('staff', collections.OrderedDict()) \
                        .setdefault(role.name, set()) \
                        .add((pa.person.first_name.encode('utf-8').strip(),
                              pa.person.last_name.encode('utf-8').strip(),
                              pa.person.date_of_birth,
                              pa.person.email))

        extra_context['data'] = data

        templates = [
            'tournamentcontrol/rego/%s/%s/registration_form.html' % (
                competition.slug, season.slug),
            'tournamentcontrol/rego/%s/registration_form.html' % (
                competition.slug,),
            'tournamentcontrol/rego/registration_form.html',
        ]

        res = TemplateResponse(request, templates, extra_context)

        if mode == 'pdf':
            pdf = prince(res.render().content)
            return HttpResponse(pdf, content_type="application/pdf")

        return res


site.register(CompetitionAdminComponent)
