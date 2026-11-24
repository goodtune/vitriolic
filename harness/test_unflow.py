import datetime

import pytest
from django.apps import apps
from enrolment.models import (
    Assessment,
    AttendanceRecord,
    ClassGroup,
    Enrolment,
    Grade,
    ReportCard,
    SchoolYear,
    Score,
    Student,
    Teacher,
)

from harness.flow import State
from harness.unflow import STAMP, main, school_year, unflow
from touchtechnology.common.models import SitemapNode
from touchtechnology.content.models import Page, PageContent
from touchtechnology.content.tests.factories import RedirectFactory
from touchtechnology.news.tests.factories import (
    ArticleFactory,
    CategoryFactory,
    TranslationFactory,
)
from tournamentcontrol.competition import models
from tournamentcontrol.competition.tests import factories as f

APPS = ("common", "competition", "content", "enrolment", "news")


def counts() -> dict[str, int]:
    """Rows in every model of the apps the flow writes to."""
    return {
        model._meta.label: model._base_manager.count()
        for model in apps.get_models()
        if model._meta.app_label in APPS
    }


def make_run(suffix: str, ordinal: int) -> None:
    """
    What one run of the flow leaves behind, made through the models: every
    title and last name ends with ``suffix``, as the flow's do.
    """
    competition = f.CompetitionFactory(title="Flow Cup" + suffix)
    f.ClubRoleFactory(competition=competition, name="Delegate" + suffix)
    f.TeamRoleFactory(competition=competition, name="Manager" + suffix)
    season = f.SeasonFactory(
        competition=competition,
        title="Flow Season" + suffix,
        timezone="Australia/Sydney",
    )
    f.SeasonExclusionDateFactory(season=season)
    f.SeasonMatchTimeFactory(season=season, count=2, interval=45)
    venue = f.VenueFactory(season=season, title="Flow Park" + suffix)
    ground = f.GroundFactory(venue=venue, title="Field A" + suffix)
    division = f.DivisionFactory(season=season, title="Flow Open" + suffix)
    f.DivisionExclusionDateFactory(division=division)

    club_a = f.ClubFactory(title="Flow Harriers" + suffix)
    club_b = f.ClubFactory(title="Flow Mariners" + suffix)
    person = f.PersonFactory(
        club=club_a, first_name="Ottoline", last_name="Fairwind" + suffix, user=None
    )
    referee = f.PersonFactory(
        club=club_b, first_name="Peregrine", last_name="Fairwind" + suffix, user=None
    )
    competition.clubs.add(club_a, club_b)
    f.SeasonRefereeFactory(season=season, club=club_b, person=referee)

    stage = f.StageFactory(division=division, title="Flow Regular Season" + suffix)
    finals = f.StageFactory(division=division, title="Flow Finals" + suffix)
    f.StageGroupFactory(stage=finals, title="Flow Pool" + suffix)
    f.UndecidedTeamFactory(stage=finals, formula="P1", label="Minor premiers" + suffix)
    home = f.TeamFactory(division=division, club=club_a, title="Flow Hawks" + suffix)
    away = f.TeamFactory(division=division, club=club_b, title="Flow Herons" + suffix)
    f.TeamAssociationFactory(team=home, person=person)
    match = f.MatchFactory(stage=stage, home_team=home, away_team=away, play_at=ground)
    models.LadderEntry.objects.create(match=match, team=home, opponent=away)
    f.SimpleScoreMatchStatisticFactory(match=match, player=person)
    f.DrawFormatFactory(name="Flow round robin" + suffix, teams=4)

    category = CategoryFactory(title="Flow Club news" + suffix)
    article = ArticleFactory(headline="Flow Cup begins" + suffix)
    article.categories.add(category)
    TranslationFactory(article=article, locale="fr", headline="La Flow Cup" + suffix)
    RedirectFactory(label="Flow old fixtures" + suffix)
    page = Page.objects.create()
    PageContent.objects.create(page=page, label="copy", sequence=1, copy="<p>x</p>")
    SitemapNode.objects.create(
        title="Flow About" + suffix, slug="flow-about" + suffix.strip(), object=page
    )

    year = SchoolYear.objects.create(
        title="9" + suffix[-3:],
        start_date=datetime.date(2026, 1, 1),
        end_date=datetime.date(2026, 12, 1),
    )
    grade = Grade.objects.create(title="Flow Grade" + suffix, ordinal=ordinal)
    teacher = Teacher.objects.create(first_name="Odette", last_name="Marlowe" + suffix)
    student = Student.objects.create(
        first_name="Ptolemy",
        last_name="Quillfeather" + suffix,
        date_of_birth=datetime.date(2016, 5, 4),
        guardian_name="A. Guardian",
    )
    group = ClassGroup.objects.create(
        year=year, grade=grade, title="Fc" + suffix, teacher=teacher
    )
    enrolment = Enrolment.objects.create(student=student, class_group=group)
    AttendanceRecord.objects.create(enrolment=enrolment, date=datetime.date(2026, 3, 1))
    assessment = Assessment.objects.create(
        class_group=group,
        title="Flow Reading" + suffix,
        date=datetime.date(2026, 3, 1),
        maximum_mark=20,
    )
    Score.objects.create(assessment=assessment, enrolment=enrolment, mark=16)
    ReportCard.objects.create(enrolment=enrolment, term=1)


@pytest.mark.django_db(transaction=True)
def test_unflow_removes_exactly_the_rows_of_one_stamp():
    # What is there already: a run of the flow with another stamp, and rows
    # that no run made. None of it is the stamp's, and all of it must stay.
    make_run(" 111111", ordinal=2001)
    f.CompetitionFactory(title="Harbour Touch League")
    f.ClubFactory(title="Seacliff Sharks")
    Grade.objects.create(title="Grade 1", ordinal=1)
    before = counts()

    make_run(" 123456", ordinal=2002)
    during = counts()
    assert all(during[label] >= before[label] for label in before)
    assert any(during[label] > before[label] for label in before)

    removed = unflow("123456")

    assert counts() == before
    assert removed["competition.Competition"] == 1
    assert removed["competition.Match"] == 1
    assert removed["competition.Club"] == 2
    assert removed["competition.Person"] == 2
    assert removed["competition.DrawFormat"] == 1
    assert removed["news.Article"] == 1
    assert removed["news.Translation"] == 1
    assert removed["news.Category"] == 1
    assert removed["content.Redirect"] == 1
    assert removed["content.Page"] == 1
    assert removed["common.SitemapNode"] == 1
    assert removed["enrolment.SchoolYear"] == 1
    assert removed["enrolment.Score"] == 1
    assert removed["enrolment.Grade"] == 1


@pytest.mark.django_db(transaction=True)
def test_unflow_twice_finds_nothing_the_second_time():
    make_run(" 123456", ordinal=2002)
    assert sum(unflow("123456").values()) > 0
    assert sum(unflow("123456").values()) == 0


@pytest.mark.django_db(transaction=True)
def test_unflow_leaves_a_school_year_that_has_a_class_of_anyone_elses():
    make_run(" 123456", ordinal=2002)
    year = SchoolYear.objects.get(title=school_year("123456"))
    other = Grade.objects.create(title="Grade 1", ordinal=1)
    ClassGroup.objects.create(year=year, grade=other, title="Kept")
    unflow("123456")
    # The year has a class that is not the flow's, so the year stays with it;
    # the flow's own class and grade are gone.
    assert SchoolYear.objects.filter(pk=year.pk).exists()
    assert list(year.classes.values_list("title", flat=True)) == ["Kept"]
    assert Grade.objects.filter(pk=other.pk).exists()
    assert not Grade.objects.filter(title__endswith="123456").exists()
    assert not Student.objects.filter(last_name__endswith="123456").exists()


@pytest.mark.django_db(transaction=True)
def test_unflow_with_nothing_to_remove_changes_nothing():
    f.CompetitionFactory(title="Harbour Touch League")
    before = counts()
    assert sum(unflow("123456").values()) == 0
    assert counts() == before


@pytest.mark.parametrize("stamp", ["", " ", "12345", "1234567", "12345a", "abcdef"])
def test_unflow_refuses_anything_but_six_digits(stamp):
    # An empty suffix would match every title there is.
    assert not STAMP.fullmatch(stamp)
    with pytest.raises(ValueError):
        unflow(stamp)


def test_the_school_year_is_the_one_the_flow_derives():
    state = State(page=None, base="", width=1440, stamp="123456", today=None)
    assert school_year("123456") == state.year == "9456"


@pytest.mark.django_db(transaction=True)
def test_main_says_what_it_removed(capsys):
    make_run(" 123456", ordinal=2002)
    assert main(["123456"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("unflow 123456: removed ")
    assert "Competition 1" in out
    assert main(["123456"]) == 0
    assert "removed 0 rows" in capsys.readouterr().out
    assert main([]) == 64
    assert main(["12"]) == 64
