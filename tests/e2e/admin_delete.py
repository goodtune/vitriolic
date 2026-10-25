"""
What every delete confirmation of the admin must say, written out.

A ``Case`` is one delete route of the admin: the object to create, where a
person finds it, and the words its confirmation must use for it. The words are
written here, not worked out from the models, so that a name that regresses to
Django's ``Thing object (7)`` (or to anything else) fails the test.

``CASES`` is every delete route that a page of the admin links to.
``UNLINKED`` is every delete route that no page links to, with the reason: the
same view is mounted again under another parent, and the object's own pages
only ever link to the first.
"""

import datetime
from collections.abc import Callable
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.urls import reverse
from enrolment import models as enrolment

from touchtechnology.common.models import SitemapNode
from touchtechnology.content.models import Chunk, Page, Placeholder
from touchtechnology.content.tests.factories import RedirectFactory
from touchtechnology.news.tests.factories import (
    ArticleFactory,
    CategoryFactory,
    TranslationFactory,
)
from tournamentcontrol.competition.models import MatchScoreSheet
from tournamentcontrol.competition.tests import factories

NEWS_SITE = "touchtechnology.news.sites.NewsSite"


@dataclass(frozen=True)
class Opening:
    """Where a person finds the object: a page, and a list on it."""

    path: str
    #: The related list (a tab) of the page that the object is in, if it is in one.
    tab: str | None = None
    #: Some text of the object's row, when the list has other rows.
    row: str | None = None


@dataclass(frozen=True)
class Case:
    """What the confirmation must say of one object, for one delete route."""

    id: str
    #: The namespace of the delete route that the object's row posts to.
    route: str
    #: What the confirmation calls the kind of object.
    kind: str
    #: What the confirmation must call this object.
    name: str
    #: Create the object, and say where it is listed.
    make: Callable[[], Opening]
    #: The title and text that one shell shows, when they are not the usual.
    workbook: tuple[str, str] | None = None
    explorer: tuple[str, str] | None = None

    def __repr__(self):
        return self.id


def listed(url_name):
    """The page of a list of its own."""
    return Opening(reverse(url_name))


def tab(parent, name, row=None):
    """A list in a tab of the page that edits ``parent``."""
    return Opening(str(parent.urls["edit"]), tab=name, row=row)


def person(club, first_name="Alex", last_name="Smith"):
    return factories.PersonFactory.create(
        club=club, first_name=first_name, last_name=last_name
    )


def match(stage):
    return factories.MatchFactory.create(
        stage=stage,
        home_team=factories.TeamFactory.create(division=stage.division, title="Eagles"),
        away_team=factories.TeamFactory.create(division=stage.division, title="Hawks"),
    )


def school_class():
    year = enrolment.SchoolYear.objects.create(
        title="2026",
        start_date=datetime.date(2026, 1, 27),
        end_date=datetime.date(2026, 12, 11),
    )
    grade = enrolment.Grade.objects.create(title="Year 3", ordinal=3)
    return enrolment.ClassGroup.objects.create(year=year, grade=grade, title="3B")


def student():
    return enrolment.Student.objects.create(
        first_name="Mia",
        last_name="Tran",
        date_of_birth=datetime.date(2017, 5, 3),
        guardian_name="Linh Tran",
    )


def competition():
    return factories.CompetitionFactory.create(title="Spec Cup")


def season(**kwargs):
    return factories.SeasonFactory.create(title="2026", **kwargs)


def division():
    return factories.DivisionFactory.create(title="Mixed Open")


def stage():
    return factories.StageFactory.create(title="Pool Stage")


def make_competition():
    competition()
    return listed("admin:fixja:competition:list")


def make_season():
    parent = competition()
    factories.SeasonFactory.create(competition=parent, title="2026")
    return tab(parent, "seasons")


def make_club_role():
    parent = competition()
    factories.ClubRoleFactory.create(competition=parent, name="Manager")
    return tab(parent, "club_roles")


def make_team_role():
    parent = competition()
    factories.TeamRoleFactory.create(competition=parent, name="Coach")
    return tab(parent, "team_roles")


def make_division():
    parent = season()
    factories.DivisionFactory.create(season=parent, title="Mixed Open")
    return tab(parent, "divisions")


def make_season_match_time():
    parent = season()
    factories.SeasonMatchTimeFactory.create(
        season=parent, start=datetime.time(9), interval=30, count=4
    )
    return tab(parent, "timeslots")


def make_venue():
    parent = season()
    factories.VenueFactory.create(season=parent, title="Central Park")
    return tab(parent, "venues")


def make_season_exclusion_date():
    parent = season()
    factories.SeasonExclusionDateFactory.create(
        season=parent, date=datetime.date(2026, 12, 25)
    )
    return tab(parent, "exclusions")


def make_season_referee():
    parent = season()
    club = factories.ClubFactory.create(title="Eagles")
    factories.SeasonRefereeFactory.create(season=parent, club=club, person=person(club))
    return tab(parent, "referees")


def make_live_stream_event():
    parent = season(live_stream=True)
    factories.LiveStreamEventFactory.create(season=parent, title="Opening ceremony")
    return tab(parent, "live_stream_events")


def make_live_stream_key():
    parent = season(live_stream=True)
    factories.LiveStreamKeyFactory.create(
        season=parent, title="Camera 1", stream_key="abcd-1234"
    )
    return tab(parent, "live_stream_keys")


def make_ground():
    venue = factories.VenueFactory.create(title="Central Park")
    factories.GroundFactory.create(venue=venue, title="Field 1")
    return tab(venue, "grounds")


def make_division_exclusion_date():
    parent = division()
    factories.DivisionExclusionDateFactory.create(
        division=parent, date=datetime.date(2026, 5, 2)
    )
    return tab(parent, "exclusions")


def make_team():
    parent = division()
    factories.TeamFactory.create(division=parent, title="Eagles")
    return tab(parent, "teams")


def make_stage():
    parent = division()
    factories.StageFactory.create(division=parent, title="Pool Stage")
    return tab(parent, "stages")


def make_stage_group():
    parent = stage()
    factories.StageGroupFactory.create(stage=parent, title="Pool A")
    return tab(parent, "pools")


def make_undecided_team():
    parent = stage()
    factories.UndecidedTeamFactory.create(stage=parent, label="Winner Pool A")
    return tab(parent, "undecided_teams")


def make_match():
    parent = stage()
    match(parent)
    return tab(parent, "matches")


def make_match_score_sheet():
    parent = match(stage())
    # What Cloudinary names an upload: a run of letters and numbers.
    MatchScoreSheet.objects.create(match=parent, image="s3gtb4jsjlafyynh7xzx")
    return tab(parent, "scoresheets")


def make_team_association():
    team = factories.TeamFactory.create(title="Eagles")
    factories.TeamAssociationFactory.create(team=team, person=person(team.club))
    return tab(team, "people")


def make_club():
    factories.ClubFactory.create(title="Eagles")
    return listed("admin:fixja:club:list")


def make_person():
    club = factories.ClubFactory.create(title="Eagles")
    person(club)
    return tab(club, "members")


def make_draw_format():
    factories.DrawFormatFactory.create(teams=4, name="Round robin of four")
    return listed("admin:fixja:format:list")


def make_page():
    SitemapNode.objects.create(
        title="About us", slug="about-us", object=Page.objects.create()
    )
    return listed("admin:content:index")


def make_folder():
    SitemapNode.objects.create(title="Archive", slug="archive")
    return listed("admin:content:index")


def make_application():
    placeholder, _ = Placeholder.objects.get_or_create(path=NEWS_SITE, namespace="news")
    SitemapNode.objects.create(title="News", slug="news", object=placeholder)
    return listed("admin:content:index")


def make_redirect():
    RedirectFactory.create(
        source_url="/old-results/", destination_url="/results/", label="Old results"
    )
    return listed("admin:content:redirect:list")


def make_placeholder():
    Placeholder.objects.get_or_create(path=NEWS_SITE, namespace="news")
    # The applications the site installs are listed with it.
    return Opening(reverse("admin:content:real_placeholder:list"), row=NEWS_SITE)


def make_chunk():
    Chunk.objects.create(slug="footer", copy="<p>Thanks for visiting.</p>")
    return listed("admin:content:chunk:list")


def make_file():
    default_storage.save("minutes.pdf", ContentFile(b"%PDF-1.4"))
    return listed("admin:content:media:list")


def make_media_folder():
    default_storage.save("reports/minutes.pdf", ContentFile(b"%PDF-1.4"))
    return listed("admin:content:media:list")


def make_article():
    ArticleFactory.create(headline="Eagles win the Spec Cup")
    return listed("admin:news:article:list")


def make_translation():
    article = ArticleFactory.create(headline="Eagles win the Spec Cup")
    TranslationFactory.create(
        article=article, locale="fr", headline="Les Aigles gagnent la Spec Cup"
    )
    return tab(article, "translations")


def make_category():
    CategoryFactory.create(title="Results")
    return listed("admin:news:category:list")


def make_user():
    get_user_model().objects.create_user(
        username="jfairweather", first_name="Jordan", last_name="Fairweather"
    )
    return Opening(reverse("admin:auth:users:list"), row="Jordan Fairweather")


def make_group():
    Group.objects.create(name="Referees")
    return listed("admin:auth:groups:list")


def make_school_year():
    school_class()
    return listed("admin:enrolment:schoolyear:list")


def make_grade():
    enrolment.Grade.objects.create(title="Year 3", ordinal=3)
    return listed("admin:enrolment:grade:list")


def make_teacher():
    enrolment.Teacher.objects.create(first_name="Priya", last_name="Nair")
    return listed("admin:enrolment:teacher:list")


def make_student():
    student()
    return listed("admin:enrolment:student:list")


def make_class_group():
    return tab(school_class().year, "classes")


def make_enrolment():
    class_group = school_class()
    enrolment.Enrolment.objects.create(student=student(), class_group=class_group)
    return tab(class_group, "enrolments")


def make_assessment():
    class_group = school_class()
    enrolment.Assessment.objects.create(
        class_group=class_group,
        title="Fractions quiz",
        date=datetime.date(2026, 3, 12),
        maximum_mark=20,
    )
    return tab(class_group, "assessments")


def make_attendance_record():
    record = enrolment.Enrolment.objects.create(
        student=student(), class_group=school_class()
    )
    enrolment.AttendanceRecord.objects.create(
        enrolment=record, date=datetime.date(2026, 3, 12)
    )
    return tab(record, "attendance")


def make_report_card():
    record = enrolment.Enrolment.objects.create(
        student=student(), class_group=school_class()
    )
    enrolment.ReportCard.objects.create(enrolment=record, term=2)
    return tab(record, "report_cards")


COMPETITION = "admin:fixja:competition"
SEASON = f"{COMPETITION}:season"
DIVISION = f"{SEASON}:division"
STAGE = f"{DIVISION}:stage"

CASES = [
    Case("competition", COMPETITION, "competition", "Spec Cup", make_competition),
    Case("season", SEASON, "season", "2026", make_season),
    Case(
        "club-role", f"{COMPETITION}:clubrole", "club role", "Manager", make_club_role
    ),
    Case("team-role", f"{COMPETITION}:teamrole", "team role", "Coach", make_team_role),
    Case("division", DIVISION, "division", "Mixed Open", make_division),
    Case(
        "season-match-time",
        f"{SEASON}:seasonmatchtime",
        "time slot",
        "09:00",
        make_season_match_time,
    ),
    Case("venue", f"{SEASON}:venue", "venue", "Central Park", make_venue),
    Case(
        "season-exclusion-date",
        f"{SEASON}:seasonexclusiondate",
        "exclusion date",
        "Friday 25 December 2026",
        make_season_exclusion_date,
    ),
    Case(
        "season-referee",
        f"{SEASON}:seasonreferee",
        "referee",
        "Smith, Alex",
        make_season_referee,
    ),
    Case(
        "live-stream-event",
        f"{SEASON}:livestreamevent",
        "live stream event",
        "Opening ceremony",
        make_live_stream_event,
    ),
    Case(
        "live-stream-key",
        f"{SEASON}:livestreamkey",
        "stream key",
        "Camera 1 (abcd-1234)",
        make_live_stream_key,
    ),
    Case("ground", f"{SEASON}:venue:ground", "ground", "Field 1", make_ground),
    Case(
        "division-exclusion-date",
        f"{DIVISION}:divisionexclusiondate",
        "exclusion date",
        "Saturday 2 May 2026",
        make_division_exclusion_date,
    ),
    Case("team", f"{DIVISION}:team", "team", "Eagles", make_team),
    Case("stage", STAGE, "stage", "Pool Stage", make_stage),
    Case("stage-group", f"{STAGE}:stagegroup", "pool", "Pool A", make_stage_group),
    Case(
        "undecided-team",
        f"{STAGE}:undecidedteam",
        "undecided team",
        "Winner Pool A",
        make_undecided_team,
    ),
    Case("match", f"{STAGE}:match", "match", "Eagles vs Hawks", make_match),
    Case(
        "match-score-sheet",
        f"{STAGE}:match:matchscoresheet",
        "match score sheet",
        "Score sheet for Eagles vs Hawks",
        make_match_score_sheet,
    ),
    Case(
        "team-association",
        f"{DIVISION}:team:teamassociation",
        "linked person",
        "Smith, Alex",
        make_team_association,
    ),
    Case("club", "admin:fixja:club", "club", "Eagles", make_club),
    Case("person", "admin:fixja:club:person", "person", "Smith, Alex", make_person),
    Case(
        "draw-format",
        "admin:fixja:format",
        "draw format",
        "Round robin of four",
        make_draw_format,
    ),
    Case("page", "admin:content:page", "page", "About us", make_page),
    Case("folder", "admin:content:folder", "folder", "Archive", make_folder),
    Case(
        "application",
        "admin:content:placeholder",
        "application",
        "News",
        make_application,
    ),
    Case(
        "redirect",
        "admin:content:redirect",
        "redirect",
        "Old results",
        make_redirect,
    ),
    Case(
        "placeholder",
        "admin:content:real_placeholder",
        "placeholder",
        "News",
        make_placeholder,
    ),
    Case("chunk", "admin:content:chunk", "chunk", "footer", make_chunk),
    # The Explorer names no kind of thing, and has no title for these.
    Case(
        "file",
        "admin:content:media",
        "file",
        "minutes.pdf",
        make_file,
        explorer=("Are you sure?", "“minutes.pdf” will be removed for good."),
    ),
    Case(
        "media-folder",
        "admin:content:media",
        "folder",
        "reports",
        make_media_folder,
        explorer=("Are you sure?", "“reports” will be removed for good."),
    ),
    Case(
        "article",
        "admin:news:article",
        "article",
        "Eagles win the Spec Cup",
        make_article,
    ),
    Case(
        "translation",
        "admin:news:article:translation",
        "translation",
        "Les Aigles gagnent la Spec Cup",
        make_translation,
    ),
    Case("category", "admin:news:category", "category", "Results", make_category),
    Case(
        "user",
        "admin:auth:users",
        "user",
        "Jordan Fairweather",
        make_user,
        explorer=(
            "Are you sure?",
            "The account of Jordan Fairweather will be removed for good.",
        ),
    ),
    Case(
        "group",
        "admin:auth:groups",
        "group",
        "Referees",
        make_group,
        explorer=("Are you sure?", "The group “Referees” will be removed for good."),
    ),
    Case(
        "school-year",
        "admin:enrolment:schoolyear",
        "school year",
        "2026",
        make_school_year,
    ),
    Case("grade", "admin:enrolment:grade", "grade", "Year 3", make_grade),
    Case("teacher", "admin:enrolment:teacher", "teacher", "Priya Nair", make_teacher),
    Case("student", "admin:enrolment:student", "student", "Mia Tran", make_student),
    Case(
        "class-group",
        "admin:enrolment:classgroup",
        "class group",
        "3B (2026)",
        make_class_group,
    ),
    Case(
        "enrolment",
        "admin:enrolment:enrolment",
        "enrolment",
        "Mia Tran in 3B (2026)",
        make_enrolment,
    ),
    Case(
        "assessment",
        "admin:enrolment:assessment",
        "assessment",
        "Fractions quiz",
        make_assessment,
    ),
    Case(
        "attendance-record",
        "admin:enrolment:attendancerecord",
        "attendance record",
        "2026-03-12: present",
        make_attendance_record,
    ),
    Case(
        "report-card",
        "admin:enrolment:reportcard",
        "report card",
        "Term 2",
        make_report_card,
    ),
]

#: Delete routes that no page links to. ``Match.urls`` and the other models
#: of a match only ever name the routes under the stage; the same views are
#: mounted again under a team, a pool and an undecided team.
UNLINKED = {
    route: "the same view is mounted under another parent that no page links to"
    for route in (
        f"{DIVISION}:team:match",
        f"{DIVISION}:team:match:matchscoresheet",
        f"{STAGE}:stagegroup:match",
        f"{STAGE}:stagegroup:match:matchscoresheet",
        f"{STAGE}:undecidedteam:match",
        f"{STAGE}:undecidedteam:match:matchscoresheet",
    )
}
