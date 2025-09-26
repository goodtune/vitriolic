import base64
import collections
import functools
import logging
import operator
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.db import models
from django.db.models import Case, F, Q, Sum, When
from django.forms.models import _get_foreign_key
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseGone,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import include, path, re_path, reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _, ngettext
from googleapiclient.errors import HttpError

from touchtechnology.admin.base import AdminComponent
from touchtechnology.common.decorators import (
    csrf_exempt_m,
    staff_login_required_m,
)
from touchtechnology.common.prince import prince
from tournamentcontrol.competition.dashboard import (
    BasicResultWidget,
    DetailResultWidget,
    MostValuableWidget,
    ProgressStageWidget,
    ScoresheetWidget,
)
from tournamentcontrol.competition.decorators import (
    competition_by_pk_m,
    registration,
)
from tournamentcontrol.competition.forms import (
    ClubAssociationForm,
    ClubRoleForm,
    CompetitionForm,
    DivisionForm,
    DivisionStructureJSONFormSet,
    DrawFormatForm,
    DrawGenerationFormSet,
    DrawGenerationMatchFormSet,
    GroundForm,
    MatchEditForm,
    MatchRefereeForm,
    MatchScheduleFormSet,
    MatchStreamForm,
    MatchWashoutFormSet,
    PersonEditForm,
    PersonMergeForm,
    RescheduleDateFormSet,
    SeasonAssociationFormSet,
    SeasonForm,
    SeasonMatchTimeFormSet,
    StageForm,
    StageGroupForm,
    TeamAssociationForm,
    TeamAssociationFormSet,
    TeamForm,
    TeamRoleForm,
    UndecidedTeamForm,
    VenueForm,
)
from tournamentcontrol.competition.models import (
    Club,
    ClubAssociation,
    ClubRole,
    Competition,
    Division,
    DivisionExclusionDate,
    DrawFormat,
    Ground,
    LadderEntry,
    LadderSummary,
    Match,
    MatchScoreSheet,
    Person,
    Place,
    Season,
    SeasonAssociation,
    SeasonExclusionDate,
    SeasonMatchTime,
    SeasonReferee,
    SimpleScoreMatchStatistic,
    Stage,
    StageGroup,
    Team,
    TeamAssociation,
    TeamRole,
    UndecidedTeam,
    Venue,
)
from tournamentcontrol.competition.sites import CompetitionAdminMixin
from tournamentcontrol.competition.tasks import (
    generate_pdf_grid,
    generate_pdf_scorecards,
    set_youtube_thumbnail,
)
from tournamentcontrol.competition.utils import (
    FauxQueryset,
    generate_fixture_grid,
    generate_scorecards,
    legitimate_bye_match,
    match_unplayed,
)
from tournamentcontrol.competition.wizards import DrawGenerationWizard

SCORECARD_PDF_WAIT = getattr(settings, "TOURNAMENTCONTROL_SCORECARD_PDF_WAIT", 5)

log = logging.getLogger(__name__)


def next_related_factory(model, parent=None, fk_name=None):
    kw = {}
    if parent is not None:
        if fk_name is None:
            fk = _get_foreign_key(parent.__class__, model)
            kw = {fk.name: parent}
        else:
            kw = {fk_name: parent}
    last = (
        model.objects.filter(**kw).aggregate(order=models.Max("order")).get("order")
        or 0
    )
    return model(order=last + 1, **kw)


class CompetitionAdminComponent(CompetitionAdminMixin, AdminComponent):
    verbose_name = _("Tournament Control")
    unprotected = False

    def __init__(self, app, name="fixja", app_name="competition"):
        super(CompetitionAdminComponent, self).__init__(app, name, app_name)

    def dropdowns(self):
        dl = (
            (_("Competitions"), self.reverse("competition:list"), "trophy"),
            (_("Clubs"), self.reverse("club:list"), "shield"),
            (_("Draw Formats"), self.reverse("format:list"), "wrench"),
            (_("Reports"), self.reverse("scorecard-report"), "book"),
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
        context.update(
            {
                "base": "tournamentcontrol/rego/admin/base.html",
            }
        )
        return super(CompetitionAdminComponent, self).render(
            request, templates, context, *args, **kwargs
        )

    def get_urls(self):
        stub_urls = (
            # Used to prevent template rendering failures; all uses *should* be marked
            # with a FIXME comment.
            [
                path("add/", self.index, name="add"),
            ],
            self.app_name,
        )

        matchscoresheet_urls = (
            [
                path("add/", self.edit_matchscoresheet, name="add"),
                path("<int:pk>/", self.edit_matchscoresheet, name="edit"),
                path("<int:pk>/delete/", self.delete_matchscoresheet, name="delete"),
            ],
            self.app_name,
        )

        match_urls = (
            [
                path("add/", self.edit_match, name="add"),
                path("<int:match_id>/", self.edit_match, name="edit"),
                path("<int:match_id>/delete/", self.delete_match, name="delete"),
                path("<int:match_id>/detail/", self.edit_match_detail, name="detail"),
                path(
                    "<int:match_id>/referee/",
                    self.referee_appointments,
                    name="referees",
                ),
                path(
                    "<int:match_id>/scoresheet/",
                    include(matchscoresheet_urls, namespace="matchscoresheet"),
                ),
                # FIXME - these just prevent template rendering failures
                path(
                    "<int:match_id>/ladder/",
                    include(stub_urls, namespace="ladderentry"),
                ),
                path(
                    "<int:match_id>/statistic/",
                    include(stub_urls, namespace="simplescorematchstatistic"),
                ),
            ],
            self.app_name,
        )

        role_patterns = (
            [
                path("add/", self.edit_role, name="add"),
                path("<int:pk>/", self.edit_role, name="edit"),
                path("<int:pk>/delete/", self.delete_role, name="delete"),
            ],
            self.app_name,
        )

        timeslot_urls = (
            [
                path("add/", self.edit_timeslot, name="add"),
                path("<int:pk>/", self.edit_timeslot, name="edit"),
                path("<int:pk>/delete/", self.delete_timeslot, name="delete"),
            ],
            self.app_name,
        )

        referees_urls = (
            [
                path("add/", self.edit_seasonreferee, name="add"),
                path("<int:pk>/", self.edit_seasonreferee, name="edit"),
                path("<int:pk>/delete/", self.delete_seasonreferee, name="delete"),
            ],
            self.app_name,
        )

        ground_urls = (
            [
                path(r"add/", self.edit_ground, name="add"),
                path("<int:ground_id>/", self.edit_ground, name="edit"),
                path("<int:ground_id>/delete/", self.delete_ground, name="delete"),
            ],
            self.app_name,
        )

        venue_urls = (
            [
                path("add/", self.edit_venue, name="add"),
                path("<int:venue_id>/", self.edit_venue, name="edit"),
                path("<int:venue_id>/delete/", self.delete_venue, name="delete"),
                path(
                    "<int:venue_id>/ground/", include(ground_urls, namespace="ground")
                ),
            ],
            self.app_name,
        )

        seasonexclusion_urls = (
            [
                path("add/", self.edit_seasonexclusiondate, name="add"),
                path("<int:pk>/", self.edit_seasonexclusiondate, name="edit"),
                path(
                    "<int:pk>/delete/", self.delete_seasonexclusiondate, name="delete"
                ),
            ],
            self.app_name,
        )

        divisionexclusion_urls = (
            [
                path("add/", self.edit_divisionexclusiondate, name="add"),
                path("<int:pk>/", self.edit_divisionexclusiondate, name="edit"),
                path(
                    "<int:pk>/delete/", self.delete_divisionexclusiondate, name="delete"
                ),
            ],
            self.app_name,
        )

        undecidedteam_urls = (
            [
                path(r"add/", self.edit_team, name="add"),
                path(r"<int:team_id>/", self.edit_team, name="edit"),
                path(r"<int:team_id>/delete/", self.delete_team, name="delete"),
                path(r"<int:team_id>/match/", include(match_urls, namespace="match")),
            ],
            self.app_name,
        )

        stagegroup_urls = (
            [
                # path("", self.list_pools, name="list"),
                path("add/", self.edit_pool, name="add"),
                path("<int:pool_id>/", self.edit_pool, name="edit"),
                path("<int:pool_id>/delete/", self.delete_pool, name="delete"),
                path("<int:pool_id>/match/", include(match_urls, namespace="match")),
            ],
            self.app_name,
        )

        stage_urls = (
            [
                path("add/", self.edit_stage, name="add"),
                path("<int:stage_id>/", self.edit_stage, name="edit"),
                path("<int:stage_id>/build/", self.generate_draw, name="build"),
                path("<int:stage_id>/undo/", self.undo_draw, name="undo"),
                path("<int:stage_id>/progress/", self.progress_teams, name="progress"),
                path("<int:stage_id>/delete/", self.delete_stage, name="delete"),
                path("<int:stage_id>/match/", include(match_urls, namespace="match")),
                path(
                    "<int:stage_id>/team/",
                    include(undecidedteam_urls, namespace="undecidedteam"),
                ),
                path(
                    "<int:stage_id>/scorecards.<mode>",
                    self.scorecards,
                    name="scorecards",
                ),
                path(
                    "<int:stage_id>/pool/",
                    include(stagegroup_urls, namespace="stagegroup"),
                ),
            ],
            self.app_name,
        )

        teamassociation_urls = (
            [
                path("add/", self.edit_teamassociation, name="add"),
                path("<int:pk>/", self.edit_teamassociation, name="edit"),
                path("<int:pk>/delete/", self.delete_teamassociation, name="delete"),
            ],
            self.app_name,
        )

        team_urls = (
            [
                path("add/", self.edit_team, name="add"),
                path("<int:team_id>/", self.edit_team, name="edit"),
                path("<int:team_id>/delete/", self.delete_team, name="delete"),
                path("<int:team_id>/permissions/", self.perms_team, name="perms"),
                path("<int:team_id>/match/", include(match_urls, namespace="match")),
                path(
                    "<int:team_id>/association/",
                    include(teamassociation_urls, namespace="teamassociation"),
                ),
            ],
            self.app_name,
        )

        division_urls = (
            [
                path(r"add/", self.edit_division, name="add"),
                path("<int:division_id>/", self.edit_division, name="edit"),
                path("<int:division_id>/delete/", self.delete_division, name="delete"),
                path(
                    "<int:division_id>/stage/", include(stage_urls, namespace="stage")
                ),
                path("<int:division_id>/teams/", include(team_urls, namespace="team")),
                path(
                    "<int:division_id>/scorers/",
                    self.highest_point_scorer,
                    name="scorers",
                ),
                path(
                    "<int:division_id>/exclusion/",
                    include(divisionexclusion_urls, namespace="divisionexclusiondate"),
                ),
                path(
                    "<int:division_id>/export.json",
                    self.division_export_json,
                    name="export-json",
                ),
            ],
            self.app_name,
        )

        season_urls = (
            [
                path("add/", self.edit_season, name="add"),
                path("<int:season_id>/", self.edit_season, name="edit"),
                path(
                    "<int:season_id>/authorize", self.oauth_authorize, name="authorize"
                ),
                path("<int:season_id>/callback", self.oauth_callback, name="callback"),
                path("<int:season_id>/delete/", self.delete_season, name="delete"),
                path(
                    "<int:season_id>/json-builder/",
                    self.json_division_builder,
                    name="json-builder",
                ),
                path(
                    "<int:season_id>/reschedule/",
                    self.match_reschedule,
                    name="reschedule",
                ),
                path(
                    "<int:season_id>/timeslot/",
                    include(timeslot_urls, namespace="seasonmatchtime"),
                ),
                path(
                    "<int:season_id>/referees/",
                    include(referees_urls, namespace="seasonreferee"),
                ),
                path("<int:season_id>/permission/", self.perms_season, name="perms"),
                path("<int:season_id>/venue/", include(venue_urls, namespace="venue")),
                path(
                    "<int:season_id>/exclusion/",
                    include(seasonexclusion_urls, namespace="seasonexclusiondate"),
                ),
                path(
                    "<int:season_id>/division/",
                    include(division_urls, namespace="division"),
                ),
                path(
                    "<int:season_id>/scorecards/<result_id>.pdf",
                    self.scorecards_async,
                    name="scorecards-async",
                ),
                # previously was not in this namespace
                path("<int:season_id>/report.html", self.season_report, name="report"),
                path(
                    "<int:season_id>/summary.html", self.season_summary, name="summary"
                ),
                path(
                    "<int:season_id>/matches/grid.<mode>",
                    self.season_grid,
                    name="match-grid",
                ),
                path(
                    "<int:season_id>/matches/<result_id>.pdf",
                    self.grid_async,
                    name="grid-async",
                ),
                path(
                    "<int:season_id>/progress/",
                    self.progression_list,
                    name="progression-list",
                ),
            ],
            self.app_name,
        )

        competition_urls = (
            [
                path("", self.list_competitions, name="list"),  # KEEP
                path("add/", self.edit_competition, name="add"),
                path("<int:competition_id>/", self.edit_competition, name="edit"),
                path(
                    "<int:competition_id>/delete/",
                    self.delete_competition,
                    name="delete",
                ),
                path(
                    "<int:competition_id>/permission/",
                    self.perms_competition,
                    name="perms",
                ),
                path(
                    "<int:competition_id>/seasons/",
                    include(season_urls, namespace="season"),
                ),
                path(
                    "<int:competition_id>/role-club/",
                    include(role_patterns, namespace="clubrole"),
                    {"cls": "club"},
                ),
                path(
                    "<int:competition_id>/role-team/",
                    include(role_patterns, namespace="teamrole"),
                    {"cls": "team"},
                ),
            ],
            self.app_name,
        )

        person_urls = (
            [
                path("add/", self.edit_person, name="add"),
                path("<uuid:person_id>/", self.edit_person, name="edit"),
                path("<uuid:person_id>/delete/", self.delete_person, name="delete"),
                path("<uuid:person_id>/merge/", self.merge_person, name="merge"),
                path(
                    "<uuid:person_id>/transfer/", self.transfer_person, name="transfer"
                ),
            ],
            self.app_name,
        )

        clubassociation_urls = (
            [
                path("add/", self.edit_clubassociation, name="add"),
                path(
                    "<int:clubassociation_id>/", self.edit_clubassociation, name="edit"
                ),
            ],
            self.app_name,
        )

        club_urls = (
            [
                path("", self.list_clubs, name="list"),
                path("add/", self.edit_club, name="add"),
                path("<int:club_id>/", self.edit_club, name="edit"),
                path("<int:club_id>/delete/", self.delete_club, name="delete"),
                path("<int:club_id>/person/", include(person_urls, namespace="person")),
                # From RegistrationBase
                path(
                    "<int:club_id>/officials/<season_id>/",
                    self.officials,
                    name="officials",
                ),
                path(
                    "<int:club_id>/<season_id>/registration.<mode>",
                    self.registration_form,
                    name="registration-form",
                ),
                # FIXME should have a 'season' namespace
                path(
                    "<int:club_id>/<season_id>/team/",
                    include(
                        (
                            [
                                # path("add/", self.edit_team_members, name="add"),
                                path(
                                    "<int:team_id>/",
                                    self.edit_team_members,
                                    name="edit",
                                ),
                            ],
                            self.app_name,
                        ),
                        namespace="team",
                    ),
                ),
                path(
                    "<int:club_id>/clubassociation/",
                    include(clubassociation_urls, namespace="clubassociation"),
                ),
            ],
            self.app_name,
        )

        drawformat_urls = (
            [
                path("", self.list_drawformat, name="list"),
                path("add/", self.edit_drawformat, name="add"),
                path("<int:pk>/", self.edit_drawformat, name="edit"),
                path("<int:pk>/delete/", self.delete_drawformat, name="delete"),
            ],
            self.app_name,
        )

        matchdatetime_urls = [
            path("results/", self.match_results, name="match-results"),
            path(
                "results:<int:division_id>/", self.match_results, name="match-results"
            ),
            path("washout/", self.match_washout, name="match-washout"),
            path("schedule/", self.match_schedule, name="match-schedule"),
            path(
                "schedule/<int:division_id>/",
                self.match_schedule,
                name="match-schedule",
            ),
            path(
                "schedule/<int:division_id>/<int:stage_id>/",
                self.match_schedule,
                name="match-schedule",
            ),
            path(
                "schedule/<int:division_id>/<int:stage_id>/<int:round>/",
                self.match_schedule,
                name="match-schedule",
            ),
            path(
                "visual-schedule/",
                self.match_visual_schedule,
                name="match-visual-schedule",
            ),
            path("scorecards.<mode>", self.scorecards, name="scorecards"),
            path("runsheet.html", self.day_runsheet, name="match-runsheet"),
            path("grid.<mode>", self.day_grid, name="match-grid"),
        ]

        urlpatterns = [
            path("", self.index, name="index"),
            path("competition/", include(competition_urls, namespace="competition")),
            path(
                "competition/<int:competition_id>/seasons/<int:season_id>/<datestr>/",
                include(matchdatetime_urls),
            ),
            path(
                "<int:competition_id>/seasons/<int:season_id>:<timestr>/<datestr>/",
                include(matchdatetime_urls),
            ),
            path("club/", include(club_urls, namespace="club")),
            path("scorecards/", self.scorecard_report, name="scorecard-report"),
            path("draw-format/", include(drawformat_urls, namespace="format")),
            re_path(
                r"^reorder/(?P<model>[^/:]+)(?::(?P<parent>[^/]+))?/(?P<pk>\d+)/(?P<direction>\w+)/$",  # noqa: E501
                self.reorder,
                name="reorder",
            ),
        ]

        return urlpatterns

    @staff_login_required_m
    def reorder(self, request, model, pk, direction, parent=None, **kwargs):
        # Determine where to redirect back to following the reordering
        redirect_to = request.META.get("HTTP_REFERER", None)
        if redirect_to is None:
            raise Http404

        # Reconstruct the object from the keyword arguments
        cls = apps.get_model("competition", model)
        obj = cls.objects.get(pk=pk)

        # Determine the neighbouring order values based on direction
        if direction == "up":
            orders = obj.order, obj.order - 1
        elif direction == "down":
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

        fmt = _('The %(model)s "%(title)s" has been reordered %(direction)s the list.')
        messages.info(
            request,
            fmt
            % dict(model=cls._meta.verbose_name, title=obj.title, direction=direction),
        )

        return self.redirect(redirect_to)

    @staff_login_required_m
    def index(self, request, **kwargs):
        messages.warning(
            request,
            _(
                "We're moving a few things around, please "
                "update any bookmarks you may find that "
                "have broken."
            ),
        )
        return self.redirect(self.reverse("competition:list"))

    @competition_by_pk_m
    @staff_login_required_m
    def edit_role(self, request, cls, pk=None, **extra_context):
        if cls == "club":
            model, form_class = ClubRole, ClubRoleForm
        elif cls == "team":
            model, form_class = TeamRole, TeamRoleForm
        else:
            raise Http404  # noqa

        competition = extra_context.get("competition")

        if pk is None:
            instance = model(competition=competition)
        else:
            instance = get_object_or_404(model, pk=pk, competition=competition)

        return self.generic_edit(
            request,
            model,
            instance=instance,
            form_class=form_class,
            permission_required=True,
            post_save_redirect=self.redirect(competition.urls["edit"]),
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_role(self, request, cls, pk, extra_context, **kwargs):
        if cls == "club":
            model = ClubRole
        elif cls == "team":
            model = TeamRole
        else:
            raise Http404
        competition = extra_context.get("competition")
        queryset = model.objects.filter(competition=competition)
        post_delete_redirect = self.redirect(
            competition.urls["edit"] + "#%s_roles-tab" % cls
        )
        return self.generic_delete(
            request,
            queryset,
            pk=pk,
            permission_required=True,
            post_delete_redirect=post_delete_redirect,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def edit_matchscoresheet(self, request, pk=None, **extra_context):
        match = extra_context.get("match")

        if pk is None:
            instance = MatchScoreSheet(match=match)
        else:
            instance = get_object_or_404(MatchScoreSheet, pk=pk, match=match)

        return self.generic_edit(
            request,
            MatchScoreSheet,
            instance=instance,
            form_fields=("image",),
            permission_required=True,
            post_save_redirect=self.redirect(match.urls["edit"]),
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_matchscoresheet(self, request, pk, **extra_context):
        return self.generic_delete(
            request, MatchScoreSheet, pk=pk, permission_required=True
        )

    @staff_login_required_m
    def list_drawformat(self, request, **extra_context):
        return self.generic_list(
            request,
            DrawFormat,
            paginate_by=0,
            permission_required=True,
            extra_context=extra_context,
        )

    @staff_login_required_m
    def edit_drawformat(self, request, pk=None, **extra_context):
        post_save_redirect = self.redirect(self.reverse("format:list"))
        return self.generic_edit(
            request,
            DrawFormat,
            pk=pk,
            form_class=DrawFormatForm,
            permission_required=True,
            post_save_redirect=post_save_redirect,
            extra_context=extra_context,
        )

    @staff_login_required_m
    def delete_drawformat(self, request, pk, **kwargs):
        return self.generic_delete(request, DrawFormat, pk=pk, permission_required=True)

    @staff_login_required_m
    def list_competitions(self, request, **extra_context):
        return self.generic_list(
            request,
            Competition,
            paginate_by=0,
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def perms_competition(self, request, competition, **kwargs):
        return self.generic_permissions(
            request, Competition, instance=competition, **kwargs
        )

    @competition_by_pk_m
    @staff_login_required_m
    def edit_competition(self, request, extra_context, competition=None, **kwargs):
        if competition is None:
            competition = next_related_factory(Competition)
        return self.generic_edit(
            request,
            Competition,
            instance=competition,
            form_class=CompetitionForm,
            form_kwargs={"user": request.user},
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_competition(self, request, competition, extra_context, **kwargs):
        return self.generic_delete(
            request,
            Competition,
            pk=competition.pk,
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def edit_season(self, request, competition, extra_context, season=None, **kwargs):
        if season is None:
            season = next_related_factory(Season, competition)
            dates = []
        else:
            dates = season.matches.dates("date", "day")

        extra_context.setdefault("dates", dates)

        return self.generic_edit(
            request,
            Season,
            instance=season,
            related=(
                "exclusions",
                "divisions",
                "venues",
                "timeslots",
                "referees",
            ),
            form_class=SeasonForm,
            form_kwargs={"user": request.user},
            post_save_redirect=self.redirect(competition.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def oauth_authorize(self, request, competition, season, **kwargs):
        if not (
            season.live_stream_client_id
            and season.live_stream_client_secret
            and season.live_stream_project_id
        ):
            messages.error(request, "OAuth2 application is not configured.")
            return self.redirect(season.urls["edit"])
        flow = season.flow()
        flow.redirect_uri = request.build_absolute_uri(
            self.reverse(
                "competition:season:callback", args=(competition.pk, season.pk)
            )
        )
        authorization_url, state = flow.authorization_url(
            # Enable offline access so that you can refresh an access token without
            # re-prompting the user for permission.
            access_type="offline",
            # Provide a hint to the Google Authentication Server. This is an
            # authenticated page so provide the user email address.
            login_hint=request.user.email,
            # Prompt the user to select an account.
            prompt="consent",  # Needs to be consent to get refresh token?
        )
        request.session["oauth_state"] = state
        return self.redirect(authorization_url)

    @competition_by_pk_m
    @staff_login_required_m
    def oauth_callback(self, request, competition, season, **kwargs):
        state = request.session["oauth_state"]
        flow = season.flow(state=state)
        flow.redirect_uri = request.build_absolute_uri(
            self.reverse(
                "competition:season:callback", args=(competition.pk, season.pk)
            )
        )
        authorization_response = (
            f"{request.build_absolute_uri(request.path)}?{request.META['QUERY_STRING']}"
        )
        flow.fetch_token(authorization_response=authorization_response)
        season.live_stream_refresh_token = flow.credentials.refresh_token
        season.live_stream_token_uri = flow.credentials.token_uri
        season.live_stream_client_id = flow.credentials.client_id
        season.live_stream_client_secret = flow.credentials.client_secret
        season.live_stream_scopes = flow.credentials.scopes
        season.save(
            update_fields=[
                "live_stream_refresh_token",
                "live_stream_token_uri",
                "live_stream_client_id",
                "live_stream_client_secret",
                "live_stream_scopes",
            ]
        )
        return self.redirect(season.urls["edit"])

    @competition_by_pk_m
    @staff_login_required_m
    def delete_season(self, request, extra_context, season, **kwargs):
        return self.generic_delete(
            request,
            Season,
            pk=season.pk,
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def perms_season(self, request, season, **kwargs):
        post_save_redirect = self.redirect(season.competition.urls["edit"])
        return self.generic_permissions(
            request,
            Season,
            instance=season,
            post_save_redirect=post_save_redirect,
            **kwargs,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def season_report(self, request, season, extra_context, **kwargs):
        teams = (
            Team.objects.filter(division__season=season)
            .order_by("club", "division", "order")
            .select_related("club")
        )
        return self.generic_list(
            request,
            teams,
            templates=self.template_path("season_report.html"),
            paginate_by=0,
            permission_required=False,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def season_summary(self, request, competition, season, extra_context, **kwargs):
        teams = (
            Team.objects.select_related("club", "division")
            .filter(division__season=season)
            .order_by("club__title", "division__order")
            .annotate(
                player_count=Sum(
                    Case(
                        When(people__is_player=True, then=1),
                        output_field=models.IntegerField(),
                    )
                ),
                non_player_count=Sum(
                    Case(
                        When(people__is_player=False, then=1),
                        output_field=models.IntegerField(),
                    )
                ),
            )
        )

        context = {
            "teams": teams,
            "season": season,
            "competition": competition,
        }
        context.update(extra_context)

        templates = self.template_path("season_summary.html")
        return self.render(request, templates, context)

    @competition_by_pk_m
    @staff_login_required_m
    def edit_timeslot(self, request, extra_context, season, pk=None, **kwargs):
        instance = SeasonMatchTime(season=season) if pk is None else None
        return self.generic_edit(
            request,
            season.timeslots,
            pk=pk,
            instance=instance,
            form_fields=(
                "start_date",
                "end_date",
                "start",
                "interval",
                "count",
            ),
            post_save_redirect=self.redirect(season.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_timeslot(self, request, season, pk, **kwargs):
        post_delete_redirect = self.redirect(season.urls["edit"] + "#timeslots-tab")
        return self.generic_delete(
            request,
            SeasonMatchTime,
            pk=pk,
            permission_required=True,
            post_delete_redirect=post_delete_redirect,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def edit_seasonexclusiondate(
        self, request, season, extra_context, pk=None, **kwargs
    ):
        instance = SeasonExclusionDate(season=season) if pk is None else None
        return self.generic_edit(
            request,
            SeasonExclusionDate,
            pk=pk,
            instance=instance,
            form_fields=("date",),
            post_save_redirect=self.redirect(season.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_seasonexclusiondate(self, request, season, pk, **kwargs):
        post_delete_redirect = self.redirect(season.urls["edit"] + "#exclusions-tab")
        return self.generic_delete(
            request,
            season.exclusions,
            pk=pk,
            permission_required=True,
            post_delete_redirect=post_delete_redirect,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def timeslots(self, request, competition, season, extra_context, **kwargs):
        return self.generic_edit_multiple(
            request,
            SeasonMatchTime,
            formset_class=SeasonMatchTimeFormSet,
            formset_kwargs={"instance": season},
            post_save_redirect_args=(competition.pk, season.pk),
            post_save_redirect="competition:season:edit",
            templates=self.template_path("timeslots.html", "season"),
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def edit_venue(self, request, season, extra_context, venue=None, **kwargs):
        if venue is None:
            venue = next_related_factory(Venue, season)
            # By default timezone should inherit from the season
            venue.timezone = season.timezone

        return self.generic_edit(
            request,
            Venue,
            instance=venue,
            related=("grounds",),
            form_class=VenueForm,
            form_kwargs={"user": request.user},
            # formset_class=GroundFormSet,
            post_save_redirect=self.redirect(season.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_venue(self, request, season, venue, extra_context=None, **kwargs):
        post_delete_redirect = self.redirect(season.urls["edit"] + "#venues-tab")
        return self.generic_delete(
            request,
            Venue,
            pk=venue.pk,
            permission_required=True,
            post_delete_redirect=post_delete_redirect,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def edit_ground(self, request, season, venue, extra_context, ground=None, **kwargs):
        if ground is None:
            ground = next_related_factory(Ground, venue, "venue")
            # By default timezone and geo should inherit from the venue
            ground.timezone = venue.timezone
            ground.latlng = venue.latlng

        def pre_save_callback(obj: Ground):
            body = {
                "snippet": {
                    "title": f"{venue.season.competition} {venue.season} ({obj.title})",
                },
                "cdn": {
                    "ingestionType": "rtmp",
                    "frameRate": "variable",
                    "resolution": "variable",
                },
            }

            try:
                stream = None
                if obj.external_identifier:
                    if not obj.live_stream:
                        stream_id = obj.external_identifier
                        season.youtube.liveStreams().delete(
                            id=obj.external_identifier
                        ).execute()
                        obj.external_identifier = None
                        log.info("YouTube stream %(id)r deleted", stream_id)
                        return

                    else:
                        body["id"] = obj.external_identifier
                        stream = (
                            season.youtube.liveStreams()
                            .update(part="snippet,cdn", body=body)
                            .execute()
                        )
                        log.info("YouTube stream %(id)r updated", stream)

                elif obj.live_stream:
                    stream = (
                        season.youtube.liveStreams()
                        .insert(part="snippet,cdn", body=body)
                        .execute()
                    )
                    obj.external_identifier = stream["id"]
                    log.info("YouTube stream %(id)r inserted", stream)

                if stream is not None:
                    obj.stream_key = stream["cdn"]["ingestionInfo"]["streamName"]

            except HttpError as exc:
                messages.error(request, exc.reason)
                return self.redirect(".")

        return self.generic_edit(
            request,
            venue.grounds,
            instance=ground,
            related=(),
            form_class=GroundForm,
            form_kwargs={"user": request.user},
            always_save=season.live_stream,
            pre_save_callback=pre_save_callback if season.live_stream else lambda o: o,
            post_save_redirect=self.redirect(venue.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_ground(self, request, venue, ground, extra_context=None, **kwargs):
        post_delete_redirect = self.redirect(venue.urls["edit"] + "#grounds-tab")
        return self.generic_delete(
            request,
            Ground,
            pk=ground.pk,
            permission_required=True,
            post_delete_redirect=post_delete_redirect,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def edit_division(self, request, season, extra_context, division=None, **kwargs):
        if division is None:
            division = next_related_factory(Division, season)

        return self.generic_edit(
            request,
            Division,
            instance=division,
            related=(
                "teams",
                "stages",
                "exclusions",
            ),
            form_class=DivisionForm,
            form_kwargs={"user": request.user},
            post_save_redirect=self.redirect(season.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_division(self, request, season, division, **kwargs):
        post_delete_redirect = self.redirect(season.urls["edit"] + "#divisions-tab")
        return self.generic_delete(
            request,
            Division,
            pk=division.pk,
            permission_required=True,
            post_delete_redirect=post_delete_redirect,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def division_export_json(self, request, competition, season, division, **kwargs):
        """Export division as JSON DivisionStructure."""
        try:
            division_structure = division.to_division_structure()
        except Exception as e:
            messages.error(request, f"Failed to export division: {e}")
            return self.redirect(division.urls["edit"])

        response = HttpResponse(
            division_structure.model_dump_json(),
            content_type="application/json",
        )
        response["Content-Disposition"] = (
            "attachment; "
            f'filename="{competition.slug}_{season.slug}_{division.slug}.json"'
        )

        return response

    @competition_by_pk_m
    @staff_login_required_m
    def edit_divisionexclusiondate(
        self, request, division, extra_context, pk=None, **kwargs
    ):
        if pk is None:
            instance = DivisionExclusionDate(division=division)
        else:
            instance = None
        return self.generic_edit(
            request,
            DivisionExclusionDate,
            pk=pk,
            instance=instance,
            form_fields=("date",),
            post_save_redirect=self.redirect(division.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_divisionexclusiondate(self, request, division, pk, **kwargs):
        post_delete_redirect = self.redirect(division.urls["edit"] + "#exclusions-tab")
        return self.generic_delete(
            request,
            division.exclusions,
            pk=pk,
            permission_required=True,
            post_delete_redirect=post_delete_redirect,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def edit_stage(self, request, division, extra_context, stage=None, **kwargs):
        if stage is None:
            stage = next_related_factory(Stage, division)

        def post_save_callback(obj):
            return self.redirect(obj.urls["edit"])

        return self.generic_edit(
            request,
            division.stages.select_related(
                "matches__home_team",
                "matches__away_team",
            ),
            pk=stage.pk,
            instance=stage,
            related=(
                "pools",
                "undecided_teams",
                "matches",
            ),
            form_class=StageForm,
            form_kwargs={"user": request.user},
            post_save_callback=post_save_callback,
            post_save_redirect=self.redirect(division.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_stage(self, request, division, stage, **kwargs):
        post_delete_redirect = self.redirect(division.urls["edit"] + "#stages-tab")
        return self.generic_delete(
            request,
            division.stages,
            pk=stage.pk,
            permission_required=True,
            post_delete_redirect=post_delete_redirect,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def edit_pool(self, request, stage, extra_context, pool=None, **kwargs):
        if pool is None:
            pool = next_related_factory(StageGroup, stage)

        def post_save_callback(obj):
            if pool:
                return self.redirect(obj.urls["edit"])

        return self.generic_edit(
            request,
            StageGroup,
            instance=pool,
            related=(),
            form_class=StageGroupForm,
            form_kwargs={"user": request.user},
            post_save_callback=post_save_callback,
            post_save_redirect=self.redirect(stage.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_pool(self, request, stage, pool, **kwargs):
        post_delete_redirect = self.redirect(stage.urls["edit"] + "#pools-tab")
        return self.generic_delete(
            request,
            stage.pools,
            pk=pool.pk,
            permission_required=True,
            post_delete_redirect=post_delete_redirect,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def edit_team(
        self,
        request,
        competition,
        season,
        division,
        extra_context,
        stage=None,
        team=None,
        **kwargs,
    ):
        """
        This view gets mounted twice, first at the division level and secondly
        at the stage level. When at the competition level it will deal with
        `Team` instances and with `UndecidedTeam` instances at the stage level.

         * raise a `Http404` when `Stage.order` == 1
        """
        related = ()

        if stage:
            model = UndecidedTeam
            post_save_redirect = self.redirect(stage.urls["edit"])
            form_class, form_kwargs = UndecidedTeamForm, {}
            if team is None:
                team = UndecidedTeam(stage=stage)
        else:
            model = Team
            post_save_redirect = self.redirect(division.urls["edit"])
            form_class, form_kwargs = TeamForm, {"division": division}
            if team is None:
                team = next_related_factory(Team, division)
            # only "real" teams have people in them
            related = ("people",)

        return self.generic_edit(
            request,
            model,
            instance=team,
            related=related,
            form_class=form_class,
            form_kwargs=form_kwargs,
            post_save_redirect=post_save_redirect,
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def perms_team(self, request, team, **kwargs):
        competition = kwargs.get("competition")
        season = kwargs.get("season")
        division = kwargs.get("division")
        return self.generic_permissions(
            request,
            Team,
            instance=team,
            post_save_redirect="admin:fixja:competition:season:division:team:list",
            post_save_redirect_args=(
                competition.pk,
                season.pk,
                division.pk,
            ),
            permission_required=True,
            **kwargs,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_team(
        self,
        request,
        competition,
        season,
        division,
        team,
        extra_context,
        stage=None,
        **kwargs,
    ):
        if team.matches.exists():
            return HttpResponseGone("The team has matches associated with it.")

        if stage:
            manager = stage.undecided_teams
            post_delete_redirect_url = self.reverse(
                "competition:season:division:stage:edit",
                args=(competition.pk, season.pk, division.pk, stage.pk),
            )
        else:
            manager = division.teams
            post_delete_redirect_url = self.reverse(
                "competition:season:division:edit",
                args=(competition.pk, season.pk, division.pk),
            )

        return self.generic_delete(
            request,
            manager,
            pk=team.pk,
            post_delete_redirect=self.redirect(post_delete_redirect_url),
            permission_required=False,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def edit_teamassociation(self, request, team, extra_context, pk=None, **kwargs):
        if pk is None:
            instance = TeamAssociation(team=team)
        else:
            instance = get_object_or_404(team.people, pk=pk)

        return self.generic_edit(
            request,
            team.people,
            instance=instance,
            form_class=TeamAssociationForm,
            form_kwargs={
                "team": team,
            },
            post_save_redirect=self.redirect(team.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_teamassociation(self, request, team, pk, **kwargs):
        post_delete_redirect = self.redirect(team.urls["edit"] + "#people-tab")
        return self.generic_delete(
            request,
            team.people,
            pk=pk,
            permission_required=True,
            post_delete_redirect=post_delete_redirect,
        )

    @competition_by_pk_m
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
        return self.generic_edit(
            request,
            season.referees,
            instance=instance,
            form_fields=("person", "club"),
            post_save_redirect=self.redirect(season.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_seasonreferee(self, request, season, pk, **kwargs):
        post_delete_redirect = self.redirect(season.urls["edit"] + "#officials-tab")
        return self.generic_delete(
            request,
            season.referees,
            pk=pk,
            permission_required=True,
            post_delete_redirect=post_delete_redirect,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def generate_draw(
        self, request, competition, season, division, stage, extra_context, **kwargs
    ):
        form_list = [
            DrawGenerationFormSet,
            DrawGenerationMatchFormSet,
        ]

        redirect_to = self.reverse(
            "competition:season:division:edit",
            args=(competition.pk, season.pk, division.pk),
        )

        view = DrawGenerationWizard.as_view(
            form_list, extra_context=extra_context, redirect_to=redirect_to, stage=stage
        )

        return view(request)

    @competition_by_pk_m
    @staff_login_required_m
    def undo_draw(self, request, division, stage, **kwargs):
        LadderSummary.objects.filter(stage=stage).delete()
        LadderEntry.objects.filter(match__stage=stage).delete()

        # Multi-stage deletion to handle complex eval_related dependencies
        # Keep deleting matches until all are gone, starting with the most dependent ones
        while stage.matches.exists():
            # Find matches that have eval_related fields (dependent matches)
            dependent_matches = stage.matches.filter(
                Q(home_team_eval_related__isnull=False)
                | Q(away_team_eval_related__isnull=False)
            )

            if dependent_matches.exists():
                # Find matches that are NOT referenced by other matches
                # These are the "leaf" matches in the dependency tree that can be safely deleted
                referenced_match_ids = set()
                for match in dependent_matches:
                    if match.home_team_eval_related_id:
                        referenced_match_ids.add(match.home_team_eval_related_id)
                    if match.away_team_eval_related_id:
                        referenced_match_ids.add(match.away_team_eval_related_id)

                # Delete dependent matches that are not referenced by others
                deletable_dependent = dependent_matches.exclude(
                    pk__in=referenced_match_ids
                )
                if deletable_dependent.exists():
                    deletable_dependent.delete()
                else:
                    # If no dependent matches can be deleted, try deleting non-dependent ones
                    non_dependent_matches = stage.matches.filter(
                        home_team_eval_related__isnull=True,
                        away_team_eval_related__isnull=True,
                    )
                    if non_dependent_matches.exists():
                        non_dependent_matches.delete()
                    else:
                        # This shouldn't happen, but break to avoid infinite loop
                        break
            else:
                # No dependent matches left, delete all remaining matches
                stage.matches.all().delete()

        messages.success(request, _("Your draw has been undone."))
        return self.redirect(division.urls["edit"])

    @competition_by_pk_m
    @staff_login_required_m
    def edit_match(
        self,
        request,
        competition,
        season,
        division,
        stage,
        extra_context,
        match=None,
        **kwargs,
    ):
        if match is None:
            match = Match(stage=stage, include_in_ladder=stage.keep_ladder)

        def pre_save_callback(obj: Match):
            # Check if YouTube credentials are configured before attempting anything else,
            # we can't interact with the YouTube API without them.
            if not (season.live_stream_client_id and season.live_stream_client_secret):
                return obj

            # Build match video URL for description
            # Only build the URL if the match has been saved and has a primary key
            match_url = None
            if obj.pk is not None:
                match_url = request.build_absolute_uri(
                    reverse(
                        "competition:match-video",
                        kwargs={
                            "competition": competition.slug,
                            "season": season.slug,
                            "division": division.slug,
                            "match": obj.pk,
                        },
                    )
                )

            # Create context for template rendering
            template_context = {
                "match": obj,
                "competition": competition,
                "season": season,
                "division": division,
                "stage": stage,
                "match_url": match_url,
            }

            # Render title from template with hierarchical fallback
            title_templates = [
                f"tournamentcontrol/competition/{stage.slug}/{division.slug}/{season.slug}/{competition.slug}/match/live_stream/title.txt",
                f"tournamentcontrol/competition/{stage.slug}/{division.slug}/{season.slug}/match/live_stream/title.txt",
                f"tournamentcontrol/competition/{stage.slug}/{division.slug}/match/live_stream/title.txt",
                f"tournamentcontrol/competition/{stage.slug}/match/live_stream/title.txt",
                "tournamentcontrol/competition/match/live_stream/title.txt",
            ]
            title = render_to_string(title_templates, template_context, request).strip()

            # Render description from template with hierarchical fallback
            description_templates = [
                f"tournamentcontrol/competition/{stage.slug}/{division.slug}/{season.slug}/{competition.slug}/match/live_stream/description.txt",
                f"tournamentcontrol/competition/{stage.slug}/{division.slug}/{season.slug}/match/live_stream/description.txt",
                f"tournamentcontrol/competition/{stage.slug}/{division.slug}/match/live_stream/description.txt",
                f"tournamentcontrol/competition/{stage.slug}/match/live_stream/description.txt",
                "tournamentcontrol/competition/match/live_stream/description.txt",
            ]
            description = render_to_string(
                description_templates, template_context, request
            ).strip()

            start_time = obj.get_datetime(ZoneInfo("UTC"))

            # Skip YouTube API interaction if we don't have valid start time
            # This can happen for new matches that don't have complete date/time data
            if start_time is None:
                return

            stop_time = start_time + relativedelta(minutes=50)  # FIXME: hard coded

            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "scheduledStartTime": start_time.isoformat(),
                    "scheduledEndTime": stop_time.isoformat(),
                },
                "status": {
                    "privacyStatus": season.live_stream_privacy,
                    "selfDeclaredMadeForKids": False,
                },
                "contentDetails": {
                    "enableAutoStart": False,
                    "enableAutoStop": False,
                    "monitorStream": {
                        "broadcastStreamDelayMs": 0,
                        "enableMonitorStream": True,
                    },
                },
            }

            try:
                if obj.external_identifier:
                    # If we have disabled live-streaming where it was previously
                    # enabled, we need to remove it using the YouTube API.
                    if not obj.live_stream:
                        video_id = obj.external_identifier
                        season.youtube.liveBroadcasts().delete(id=video_id).execute()
                        if obj.videos is not None:
                            obj.videos.remove(f"https://youtu.be/{video_id}")
                        if not obj.videos:
                            obj.videos = None
                        obj.external_identifier = None
                        log.info("YouTube video %(id)r deleted", video_id)
                        return

                    # Alternatively we're making sure the representation on the backend
                    # is consistent with the current status.
                    else:
                        body["id"] = obj.external_identifier
                        broadcast = (
                            season.youtube.liveBroadcasts()
                            .update(part="snippet,status,contentDetails", body=body)
                            .execute()
                        )
                        set_youtube_thumbnail.s(obj.pk).apply_async(countdown=10)
                        log.info("YouTube video %(id)r updated", broadcast)

                # If we have enabled live-streaming, but don't have an external id, we
                # need to create an event with the YouTube API and store the external
                # id.
                elif obj.live_stream:
                    broadcast = (
                        season.youtube.liveBroadcasts()
                        .insert(
                            part="id,snippet,status,contentDetails",
                            body=body,
                        )
                        .execute()
                    )
                    obj.external_identifier = broadcast["id"]
                    set_youtube_thumbnail.s(obj.pk).apply_async(countdown=10)
                    video_link = f"https://youtu.be/{obj.external_identifier}"
                    obj.videos = (
                        [video_link]
                        if obj.videos is None
                        else obj.videos.append(video_link)
                    )
                    log.info("YouTube video %(id)r inserted", broadcast)

                # We need to bind to a liveStream resource. This is only supported on
                # a Ground, not a Venue. Only attempt binding if external_identifier exists.
                if obj.external_identifier and obj.play_at.ground.external_identifier:
                    bind = (
                        season.youtube.liveBroadcasts()
                        .bind(
                            part="id,snippet,contentDetails,status",
                            id=obj.external_identifier,
                            streamId=obj.play_at.ground.external_identifier,
                        )
                        .execute()
                    )
                    obj.live_stream_bind = bind["contentDetails"].get("boundStreamId")

            except HttpError as exc:
                messages.error(request, exc.reason)
                return self.redirect(".")

        return self.generic_edit(
            request,
            Match,
            instance=match,
            form_class=MatchStreamForm if season.live_stream else MatchEditForm,
            always_save=season.live_stream,
            post_save_redirect=self.redirect(
                request.GET.get("next") or stage.urls["edit"]
            ),
            pre_save_callback=pre_save_callback if season.live_stream else lambda o: o,
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def referee_appointments(
        self,
        request,
        competition,
        season,
        division,
        stage,
        extra_context,
        match,
        **kwargs,
    ):
        return self.generic_edit(
            request,
            Match,
            instance=match,
            form_class=MatchRefereeForm,
            always_save=season.live_stream,
            post_save_redirect=self.redirect(
                request.GET.get("next") or stage.urls["edit"]
            ),
            permission_required=True,
            extra_context=extra_context,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def delete_match(self, request, stage, match, **kwargs):
        post_delete_redirect = self.redirect(stage.urls["edit"] + "#matches-tab")
        return self.generic_delete(
            request,
            stage.matches,
            pk=match.pk,
            permission_required=True,
            post_delete_redirect=post_delete_redirect,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def edit_match_detail(self, request, stage, match, extra_context, **kwargs):
        redirect_to = reverse("admin:index")
        return super(CompetitionAdminComponent, self).edit_match_detail(
            request,
            stage=stage,
            match=match,
            extra_context=extra_context,
            redirect_to=redirect_to,
            **kwargs,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def progression_list(self, request, competition, season, extra_context, **kwargs):
        return super().progression_list(
            request, competition, season, extra_context, **kwargs
        )

    @competition_by_pk_m
    @staff_login_required_m
    def progress_teams(
        self, request, competition, season, division, stage, extra_context, **kwargs
    ):
        return super().progress_teams(
            request, competition, season, division, stage, extra_context, **kwargs
        )

    @competition_by_pk_m
    @staff_login_required_m
    def day_runsheet(self, request, season, date, extra_context, **kwargs):
        return super(CompetitionAdminComponent, self).day_runsheet(
            request, season, date, extra_context, **kwargs
        )

    @competition_by_pk_m
    @csrf_exempt_m
    @staff_login_required_m
    def season_grid(self, request, season, mode, extra_context, **kwargs):
        # pass query string parameters along to the context
        for key, val in request.GET.items():
            extra_context.setdefault(key, val)

        if (
            getattr(settings, "TOURNAMENTCONTROL_ASYNC_PDF_GRID", False)
            and mode == "pdf"
        ):
            result = generate_pdf_grid.delay(season, extra_context)
            redirect_to = self.reverse(
                "competition:season:grid-async",
                kwargs={
                    "competition_id": season.competition_id,
                    "season_id": season.pk,
                    "result_id": result.id,
                },
            )
            return self.redirect(redirect_to)

        return generate_fixture_grid(season, format=mode, extra_context=extra_context)

    @competition_by_pk_m
    @csrf_exempt_m
    @staff_login_required_m
    def day_grid(self, request, season, date, mode, extra_context, **kwargs):
        if (
            getattr(settings, "TOURNAMENTCONTROL_ASYNC_PDF_GRID", False)
            and mode == "pdf"
        ):
            extra_context.pop("admin", None)
            extra_context.pop("component", None)
            result = generate_pdf_grid.delay(season, extra_context, date)
            redirect_to = self.reverse(
                "competition:season:grid-async",
                kwargs={
                    "competition_id": season.competition_id,
                    "season_id": season.pk,
                    "result_id": result.id,
                },
            )
            return self.redirect(redirect_to)

        return generate_fixture_grid(
            season,
            format=mode,
            extra_context=extra_context,
            dates=[date],
        )

    @competition_by_pk_m
    @staff_login_required_m
    def grid_async(self, request, result_id, extra_context, **kwargs):
        result = generate_pdf_grid.AsyncResult(result_id)

        if result.ready():
            data = result.wait()
            return HttpResponse(base64.b64decode(data), content_type="application/pdf")

        templates = self.template_path("wait.html", "scorecards")
        response = self.render(request, templates, extra_context)
        response["Refresh"] = SCORECARD_PDF_WAIT
        return response

    @competition_by_pk_m
    @staff_login_required_m
    def match_reschedule(self, request, competition, season, extra_context, **kwargs):
        matches = Match.objects.filter(
            match_unplayed,
            stage__division__season=season,
            stage__division__season__competition=competition,
        )

        dates = matches.dates("date", "day")

        if not dates:
            messages.error(request, _("No matches are available for rescheduling."))
            return self.redirect(season.urls["edit"])

        redirect_to = season.urls["edit"]

        if request.method == "POST":
            formset = RescheduleDateFormSet(
                matches=matches, dates=dates, data=request.POST
            )
            if formset.is_valid():
                changes = formset.save()
                if changes:
                    message = ngettext(
                        "Your change to %(count)d match has been saved.",
                        "Your changes to %(count)d matches have been saved.",
                        changes,
                    ) % {"count": changes}
                    messages.success(request, message)
                else:
                    messages.info(request, _("No matches were rescheduled."))
                return self.redirect(redirect_to)
        else:
            formset = RescheduleDateFormSet(matches=matches, dates=dates)

        context = {
            "dates": dates,
            "formset": formset,
            "model": matches.none(),
            "cancel_url": redirect_to,
        }
        context.update(extra_context)

        templates = self.template_path("reschedule.html")
        return self.render(request, templates, context)

    def _build_match_queryset(
        self,
        season,
        date,
        time=None,
        division=None,
        stage=None,
        round=None,
        visual=False,
    ):
        """Build queryset for match scheduling."""
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

        # Visual schedule uses different ordering and includes play_at
        if visual:
            queryset = (
                season.matches.select_related("stage__division__season", "play_at")
                .filter(where)
                .order_by("stage__division__order", "stage__order", "round")
            )
        else:
            queryset = (
                manager.select_related("stage__division__season")
                .filter(where)
                .order_by("stage__division__order", "round", "datetime", "play_at")
            )

        return queryset

    def _build_venues_and_places(self, season):
        """Build venues and places data structures."""
        venues = collections.OrderedDict()
        for venue in season.venues.all():
            venues.setdefault(venue, [])

        for ground in Ground.objects.select_related("venue").filter(venue__in=venues):
            venues[ground.venue].append(ground)

        places = FauxQueryset(Place)
        for venue, grounds in venues.items():
            places.append(venue)
            for ground in grounds:
                places.append(ground)

        return venues, places

    def _build_visual_context(self, queryset):
        """Build visual-specific context data."""
        matches_hierarchy = collections.OrderedDict()
        unscheduled_matches = []
        scheduled_matches = []

        for match in queryset:
            division = match.stage.division
            stage = match.stage

            if division not in matches_hierarchy:
                matches_hierarchy[division] = collections.OrderedDict()
            if stage not in matches_hierarchy[division]:
                matches_hierarchy[division][stage] = []

            matches_hierarchy[division][stage].append(match)

            if match.time is None or match.play_at is None:
                unscheduled_matches.append(match)
            else:
                scheduled_matches.append(match)

        return {
            "matches_hierarchy": matches_hierarchy,
            "unscheduled_matches": unscheduled_matches,
            "scheduled_matches": scheduled_matches,
        }

    def _handle_visual_schedule_form(
        self, request, queryset, places, timeslots, extra_context, templates, season
    ):
        """Handle form processing for visual schedule."""
        if request.method == "POST":
            formset = MatchScheduleFormSet(
                data=request.POST,
                queryset=queryset,
                places=places,
                timeslots=timeslots,
            )

            if formset.is_valid():
                changes = 0
                for form in formset:
                    if form.has_changed():
                        form.save()
                        changes += 1

                if changes:
                    message = ngettext(
                        "Your change to %(count)d match has been saved.",
                        "Your changes to %(count)d matches have been saved.",
                        changes,
                    ) % {"count": changes}
                    messages.success(request, message)
                else:
                    messages.info(request, _("No matches were updated."))

                # Check if we should redirect back to self (visual schedule)
                if request.POST.get("redirect_to_self"):
                    return self.redirect(request.path)
                else:
                    return self.redirect(season.urls["edit"])
        else:
            formset = MatchScheduleFormSet(
                queryset=queryset,
                places=places,
                timeslots=timeslots,
            )

        return formset

    @competition_by_pk_m
    @staff_login_required_m
    def match_schedule(
        self,
        request,
        competition,
        season,
        date,
        time=None,
        division=None,
        stage=None,
        round=None,
        visual=False,
        **kwargs,
    ):
        """Match scheduling interface - supports both standard and visual modes."""
        # Extract extra_context from kwargs (injected by decorator)
        extra_context = kwargs.pop("extra_context", {})

        queryset = self._build_match_queryset(
            season,
            date,
            time=time,
            division=division,
            stage=stage,
            round=round,
            visual=visual,
        )

        venues, places = self._build_venues_and_places(season)

        # Get timeslots for the day
        timeslots = season.get_timeslots(date)

        if visual:
            # Visual schedule specific validation
            if not timeslots:
                messages.error(
                    request,
                    _(
                        "The visual scheduler can only be used when timeslots are specified for this season."
                    ),
                )
                return self.redirect(season.urls["edit"])

            # Handle visual schedule form processing and build context
            formset = self._handle_visual_schedule_form(
                request,
                queryset,
                places,
                timeslots,
                extra_context,
                self.template_path("match/visual_schedule.html"),
                season,
            )

            # If POST resulted in redirect, return it
            if isinstance(formset, HttpResponseRedirect):
                return formset

            # Build visual-specific context
            visual_context = self._build_visual_context(queryset)

            context = {
                "formset": formset,
                "season": season,
                "date": date,
                "dates": season.matches.dates("date", "day"),
                "places": places,
                "timeslots": timeslots,
                "venues": venues,
                **visual_context,
            }
            context.update(extra_context)

            templates = self.template_path("match/visual_schedule.html")
            return self.render(request, templates, context)
        else:
            # Standard schedule using generic_edit_multiple
            return self.generic_edit_multiple(
                request,
                queryset,
                formset_class=MatchScheduleFormSet,
                formset_kwargs={
                    "places": places,
                    "timeslots": timeslots,
                },
                post_save_redirect=self.redirect(season.urls["edit"]),
                templates=self.template_path("match/schedule.html"),
                extra_context=extra_context,
            )

    @competition_by_pk_m
    @staff_login_required_m
    def match_visual_schedule(
        self,
        request,
        competition,
        season,
        date,
        extra_context,
        **kwargs,
    ):
        """
        Visual drag-and-drop match scheduling interface.
        Delegates to match_schedule with visual=True.
        """
        return self.match_schedule(
            request,
            competition,
            season,
            date,
            visual=True,
            **kwargs,
        )

    @competition_by_pk_m
    @staff_login_required_m
    def match_results(
        self,
        request,
        competition,
        season,
        date,
        extra_context,
        division=None,
        time=None,
        **kwargs,
    ):
        redirect_to = reverse("admin:index", current_app=self.app)
        return super(CompetitionAdminComponent, self).match_results(
            request,
            competition,
            season,
            date,
            extra_context,
            division=division,
            time=time,
            redirect_to=redirect_to,
            **kwargs,
        )

    # FIXME
    @competition_by_pk_m
    @staff_login_required_m
    def match_washout(
        self, request, competition, season, date, extra_context, time=None, **kwargs
    ):
        matches = Match.objects.filter(
            stage__division__season__id=season.pk,
            stage__division__season__competition__id=competition.pk,
            date=date,
        ).order_by("stage__division__order", "is_bye", "datetime", "play_at")

        # ensure only matches with progressed teams are able to be updated
        matches = matches.filter(match_unplayed)

        # FIXME too complex, be verbose so we can all read and understand it
        if time is not None:
            base = Q(time=time)
            bye_kwargs = matches.filter(time=time).values("stage", "round")
            time_or_byes = functools.reduce(
                operator.or_, [Q(time__isnull=True, **kw) for kw in bye_kwargs], base
            )
            matches = matches.filter(time_or_byes)

        return self.generic_edit_multiple(
            request,
            matches,
            formset_class=MatchWashoutFormSet,
            templates=self.template_path("match_washout.html"),
            post_save_redirect=self.redirect(season.urls["edit"]),
            extra_context=extra_context,
        )

    @staff_login_required_m
    def scorecard_report(self, request, **extra_context):
        from tournamentcontrol.competition.wizards import (
            FilterForm,
            SeasonForm,
            scorecardwizard_factory,
        )

        ScorecardWizard = scorecardwizard_factory(app=self, extra_context=extra_context)
        wizard = ScorecardWizard.as_view(form_list=[SeasonForm, FilterForm])
        return wizard(request)

    @staff_login_required_m
    @competition_by_pk_m
    def json_division_builder(self, request, competition, season, **extra_context):
        """JSON-based division structure builder for power users."""
        return self.generic_edit_multiple(
            request,
            season.divisions,  # Use season's divisions manager
            formset_class=DivisionStructureJSONFormSet,
            formset_kwargs={"instance": season},  # Pass season as instance
            post_save_redirect=self.redirect(season.urls["edit"]),
            templates=self.template_path("json_division_builder.html"),
            extra_context={
                **extra_context,
                "season": season,
                "competition": competition,
                "cancel_url": season.urls["edit"],
            },
        )

    @competition_by_pk_m
    @staff_login_required_m
    def scorecards(
        self,
        request,
        competition,
        season,
        mode,
        stage=None,
        date=None,
        time=None,
        **kwargs,
    ):
        if stage is not None:
            if stage.matches_needing_printing.count():
                matches = stage.matches_needing_printing.all()
            else:
                matches = stage.matches.all()
        else:
            matches = season.matches.all()

        # legacy/undocumented, remove this?
        if "d" in request.GET:
            matches = matches.filter(stage__division__slug=request.GET["d"])

        if date is not None:
            matches = matches.filter(date=date)

        if time is not None:
            matches = matches.filter(time=time)

        matches = matches.exclude(legitimate_bye_match)

        extra_context = {
            "competition": competition,
            "season": season,
            "date": date,
            "time": time,
            "stage": stage,
            "filtered": round is not None,
            "round": round,
        }

        templates = self.template_path("scorecards.html", competition.slug, season.slug)

        if mode == "pdf":
            kw = {
                "match_pks": [pk for pk in matches.values_list("pk", flat=True)],
                "templates": templates,
                "extra_context": extra_context,
            }
            if stage is not None:
                kw["stage_pk"] = stage.pk
            if hasattr(request, "tenant"):
                kw["_schema_name"] = request.tenant.schema_name
                kw["base_url"] = request.build_absolute_uri("/")

            result = generate_pdf_scorecards.delay(**kw)

            reverse_kwargs = {
                "competition_id": competition.pk,
                "season_id": season.pk,
                "result_id": result.id,
            }

            redirect_to = self.reverse(
                "competition:season:scorecards-async", kwargs=reverse_kwargs
            )
            response = self.redirect(redirect_to)
        else:
            output = generate_scorecards(matches, templates, mode, extra_context, stage)
            response = HttpResponse(output)

        return response

    @competition_by_pk_m
    @staff_login_required_m
    def scorecards_async(self, request, result_id, extra_context, **kwargs):
        result = generate_pdf_scorecards.AsyncResult(result_id)

        if result.ready():
            data = result.wait()
            return HttpResponse(base64.b64decode(data), content_type="application/pdf")

        templates = self.template_path("wait.html", "scorecards")
        response = self.render(request, templates, extra_context)
        response["Refresh"] = SCORECARD_PDF_WAIT
        return response

    @competition_by_pk_m
    @staff_login_required_m
    def highest_point_scorer(self, request, division, extra_context, **kwargs):
        # Get the statistics directly and group by person
        # This approach avoids GROUP BY issues by working with the statistics model directly
        statistics = (
            SimpleScoreMatchStatistic.objects.filter(match__stage__division=division)
            .values(
                "player__uuid",
                "player__first_name",
                "player__last_name",
                "player__club__title",
            )
            .annotate(
                uuid=F("player__uuid"),
                first_name=F("player__first_name"),
                last_name=F("player__last_name"),
                club__title=F("player__club__title"),
                played=Sum("played"),
                points=Sum("points"),
                mvp=Sum("mvp"),
            )
            .exclude(played__isnull=True)
            .exclude(played=0)
            .values(
                "uuid",
                "first_name",
                "last_name",
                "club__title",
                "played",
                "points",
                "mvp",
            )
            .order_by("-points", "played")
        )

        # Create separate querysets for different ordering
        scorers = statistics.order_by("-points", "played")
        mvp = statistics.order_by("-mvp", "played")

        context = {
            "scorers": scorers,
            "mvp": mvp,
        }
        context.update(extra_context)

        templates = self.template_path("scorers.html")
        return self.render(request, templates, context)

    # from RegistrationBase

    @staff_login_required_m
    def list_clubs(self, request, **extra_context):
        return self.generic_list(
            request,
            Club,
            paginate_by=0,
            permission_required=True,
            extra_context=extra_context,
        )

    @registration
    def edit_club(self, request, extra_context, club=None, **kwargs):
        templates = {
            Team: "tournamentcontrol/competition/admin/club/team.inc.html",
        }
        extra_context.setdefault("templates", templates)
        return self.generic_edit(
            request,
            Club,
            instance=club,
            form_fields=(
                "title",
                "short_title",
                "abbreviation",
                "email",
                "website",
                "twitter",
                "facebook",
                "youtube",
                "primary",
                "primary_position",
                "status",
                "slug",
                "slug_locked",
            ),
            related=(
                "members",
                "teams",
            ),
            permission_required=True,
            extra_context=extra_context,
        )

    @staff_login_required_m
    def delete_club(self, request, club_id, **kwargs):
        return self.generic_delete(request, Club, pk=club_id, permission_required=True)

    @staff_login_required_m
    def edit_person(self, request, club_id, person_id=None, **kwargs):
        club = get_object_or_404(Club, pk=club_id)

        if person_id is None:
            person = Person(club=club)
        else:
            person = get_object_or_404(Person, pk=person_id)

        extra_context = kwargs.pop("extra_context", {})
        extra_context.update({"club": club, "person": person, "component": self})
        return self.generic_edit(
            request,
            Person,
            instance=person,
            form_class=PersonEditForm,
            related=("statistics",),
            post_save_redirect=self.redirect(person.club.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
        )

    @staff_login_required_m
    def transfer_person(self, request, club_id, person_id, **kwargs):
        club = get_object_or_404(Club, pk=club_id)
        person = get_object_or_404(Person, pk=person_id)

        extra_context = kwargs.pop("extra_context", {})
        extra_context.update({"club": club, "person": person, "component": self})

        return self.generic_edit(
            request,
            Person,
            instance=person,
            form_fields=("club",),
            related=(),
            post_save_redirect=self.redirect(club.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
            changed_messages=(
                (messages.SUCCESS, _("The {model} has been transferred successfully.")),
            ),
        )

    @registration
    @staff_login_required_m
    def merge_person(self, request, club, extra_context, person, **kwargs):
        return self.generic_edit(
            request,
            club.members,
            instance=person,
            form_class=PersonMergeForm,
            related=(),
            post_save_redirect=self.redirect(person.club.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
        )

    @registration
    @staff_login_required_m
    def delete_person(self, request, club, person, extra_context, **kwargs):
        now = timezone.now().replace(second=0, microsecond=0)
        queryset = Person.objects.filter(club=club)

        # Ensure the person does not have any statistical data recorded and
        # that we're not attempting to delete someone mid-season.
        queryset = queryset.exclude(statistics__isnull=False)
        queryset = queryset.exclude(
            teamassociation__team__division__season__start_date__lt=now
        )

        return self.generic_delete(
            request,
            queryset,
            pk=person.pk,
            post_delete_redirect=self.redirect(club.urls["edit"]),
            permission_required=True,
            extra_context=extra_context,
        )

    @registration
    def edit_clubassociation(
        self, request, club, extra_context, clubassociation_id=None, **kwargs
    ):
        return self.generic_edit(
            request,
            ClubAssociation,
            pk=clubassociation_id,
            form_class=ClubAssociationForm,
            form_kwargs={
                "user": request.user,
                "club": club,
            },
            permission_required=True,
            extra_context=extra_context,
        )

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
                request,
                messages.INFO,
                _("This season is now read-only to club administrators."),
            )
        elif scheduled_read_only:
            sro = {
                "time": scheduled_read_only.strftime("%H:%M"),
                "date": scheduled_read_only.strftime("%d/%m/%Y"),
            }
            messages.add_message(
                request,
                messages.WARNING,
                _(
                    "This season will become read-only to club administrators "
                    "at %(time)s on %(date)s."
                )
                % sro,
            )

        if read_only:
            templates = self.template_path("officials_list.html")
            return self.render(request, templates, extra_context)

        templates = self.template_path("officials.html")
        return self.generic_edit_multiple(
            request,
            SeasonAssociation,
            queryset=season.officials.filter(club=club),
            formset_class=SeasonAssociationFormSet,
            formset_kwargs={
                "user": request.user,
                "club": club,
                "season": season,
            },
            post_save_redirect="club-teams",
            post_save_redirect_kwargs={"club_id": club.pk},
            templates=templates,
            extra_context=extra_context,
        )

    @registration
    def edit_team_members(self, request, club, team, extra_context, **kwargs):
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
                request,
                messages.INFO,
                _("This team is now read-only to club administrators."),
            )
        elif scheduled_read_only:
            sro = {
                "time": scheduled_read_only.strftime("%H:%M"),
                "date": scheduled_read_only.strftime("%d/%m/%Y"),
            }
            messages.add_message(
                request,
                messages.WARNING,
                _(
                    "This team will become read-only to club administrators at "
                    "%(time)s on %(date)s."
                )
                % sro,
            )

        if read_only and not request.user.is_superuser:
            templates = self.template_path("team_members.html")
            return self.render(request, templates, extra_context)

        return self.generic_edit_multiple(
            request,
            TeamAssociation,
            formset_class=TeamAssociationFormSet,
            formset_kwargs={"user": request.user, "instance": team},
            post_save_redirect="club-teams",
            post_save_redirect_kwargs={"club_id": club.pk},
            permission_required=True,
            extra_context=extra_context,
        )

    @registration
    @staff_login_required_m
    def registration_form(
        self, request, club, season, teams, competition, mode, extra_context, **kwargs
    ):
        data = collections.OrderedDict()

        for team in teams:
            for pa in team.people.filter(is_player=True, person__isnull=False):
                data.setdefault(team, collections.OrderedDict()).setdefault(
                    "players", []
                ).append(
                    (
                        pa.number or "",
                        pa.person.first_name.encode("utf-8").strip(),
                        pa.person.last_name.encode("utf-8").strip(),
                        pa.person.date_of_birth,
                        pa.person.email,
                    )
                )

            for pa in team.people.filter(
                roles__isnull=False, person__isnull=False
            ).order_by("roles__id", "person__last_name", "person__first_name"):
                for role in pa.roles.all():
                    data.setdefault(team, collections.OrderedDict()).setdefault(
                        "staff", collections.OrderedDict()
                    ).setdefault(role.name, set()).add(
                        (
                            pa.person.first_name.encode("utf-8").strip(),
                            pa.person.last_name.encode("utf-8").strip(),
                            pa.person.date_of_birth,
                            pa.person.email,
                        )
                    )

        extra_context["data"] = data

        templates = [
            "tournamentcontrol/rego/%s/%s/registration_form.html"
            % (competition.slug, season.slug),
            "tournamentcontrol/rego/%s/registration_form.html" % (competition.slug,),
            "tournamentcontrol/rego/registration_form.html",
        ]

        res = TemplateResponse(request, templates, extra_context)

        if mode == "pdf":
            pdf = prince(res.render().content)
            return HttpResponse(pdf, content_type="application/pdf")

        return res
