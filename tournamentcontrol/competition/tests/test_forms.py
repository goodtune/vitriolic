from unittest import skip

from dateutil.rrule import WEEKLY
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _
from test_plus import TestCase
from touchtechnology.common.models import SitemapNode

from tournamentcontrol.competition.forms import (
    CompetitionForm,
    ConfigurationForm,
    DivisionForm,
    GroundForm,
    SeasonForm,
    StageForm,
    StageGroupForm,
    VenueForm,
)
from tournamentcontrol.competition.models import (
    Division,
    Season,
    Stage,
    StageGroup,
    Team,
)


class FormTests(TestCase):

    fixtures = [
        'competition.json',
        'club.json',
        'person.json',
        'season.json',
        'division.json',
        'team.json',
        'stage.json',
    ]

    def setUp(self):
        self.user = User.objects.create(username='normal')
        self.staff = User.objects.create(
            username='staff', is_staff=True)
        self.superuser = User.objects.create(
            username='superuser', is_staff=True, is_superuser=True)
        self.sitemapnode = SitemapNode.objects.create()

    # ConfigurationForm

    def test_configuration_form_1(self):
        data = {
            'competition': 'sydney-university',
            'season': 'summer-2012',
        }
        form = ConfigurationForm(
            user=self.superuser, instance=self.sitemapnode, data=data)
        self.assertEqual(form.is_valid(), True)

    def test_configuration_form_2(self):
        data = {
            'competition': '',
            'season': 'summer-2012',
        }
        form = ConfigurationForm(
            user=self.superuser, instance=self.sitemapnode, data=data)
        self.failIf(form.is_valid())
        self.assertEqual(form.errors['season'],
                         [_("You can't select a season without a "
                            "competition.")])

    def test_configuration_form_3(self):
        data = {
            'competition': 'edinburgh-touch-superleague',
            'season': 'summer-2012',
        }
        form = ConfigurationForm(
            user=self.superuser, instance=self.sitemapnode, data=data)
        self.failIf(form.is_valid())
        self.assertEqual(form.errors['season'],
                         [_("Invalid season for this competition.")])

    # SeasonForm

    def test_season_form(self):
        data = {
            'title': '',
            'short_title': '',
            'hashtag': 'x y z',
            'complete': '0',
            'enabled': '1',
            'start_date_0': '1',
            'start_date_1': '9',
            'start_date_2': '2012',
            'mode': WEEKLY,
            'statistics': '0',
            'mvp_results_public': '0',
            'slug': '',
            'slug_locked': '0',
            'timezone': '',
        }
        form = SeasonForm(user=self.user, data=data)
        self.failIf(form.is_valid())
        self.assertEqual(form.errors['title'], [u'This field is required.'])
        self.assertEqual(
            form.errors['hashtag'],
            [u'Enter a valid value. Make sure you include the # symbol.'],
        )
        self.assertEqual(form.errors['timezone'], [u'This field is required.'])

        data.update({
            'title': 'Test Season',
            'hashtag': '#test',
            'timezone': 'Australia/Sydney',
        })
        form = SeasonForm(user=self.user, data=data)
        self.assertEqual(form.is_valid(), True)

    # VenueForm, GroundForm

    def place_form(self, form_class):
        data = {
            'title': '',
            'short_title': '',
            'abbreviation': '',
            'latlng_0': '',
            'latlng_1': '',
            'latlng_2': '',
            'slug': '',
            'slug_locked': '0',
            'timezone': '',
        }
        form = form_class(user=self.user, data=data)
        self.failIf(form.is_valid())
        self.assertEqual(form.errors['title'], [u'This field is required.'])
        self.assertEqual(form.errors['latlng'], [u'This field is required.'])
        self.assertEqual(form.errors['timezone'], [u'This field is required.'])

        data.update({
            'title': 'Test Place',
            'latlng_0': 'x',
            'latlng_1': 'y',
            'latlng_2': 'z',
            'timezone': 'Australia/Sydney',
        })
        form = form_class(user=self.user, data=data)
        # LocationField should not accept dimensions that are of bound values.
        self.assertEqual(form.is_valid(), True)  # FIXME
        # self.failIf(form.is_valid())
        # self.assertEqual(form.errors['latlng'], ["Geo coordinates are out of bounds."])

        data.update({
            'latlng_0': '-33.865854',
            'latlng_1': '151.210327',
            'latlng_2': '10',
        })
        form = form_class(user=self.user, data=data)
        self.assertEqual(form.is_valid(), True)

    def test_venue_form(self):
        self.place_form(VenueForm)

    def test_ground_form(self):
        self.place_form(GroundForm)

    # DivisionForm

    def test_division_form(self):
        season = Season.objects.get(pk=1)
        instance = Division(season=season)

        data = {
            'title': '',
            'short_title': '',
            'points_formula_0': '',
            'points_formula_1': '',
            'points_formula_2': '',
            'points_formula_3': '',
            'points_formula_4': '',
            'points_formula_5': '',
            'bonus_points_formula': '',
            'games_per_day': '',
            'forfeit_for_score': '',
            'forfeit_against_score': '',
            'include_forfeits_in_played': '0',
            'slug': '',
            'slug_locked': '0',
        }
        form = DivisionForm(user=self.user, data=data, instance=instance)
        self.failIf(form.is_valid())
        self.assertEqual(form.errors['title'], [u'This field is required.'])
        self.assertEqual(form.errors['forfeit_for_score'],
                         [u'This field is required.'])
        self.assertEqual(form.errors['forfeit_against_score'],
                         [u'This field is required.'])

        data.update({
            'title': 'Test Division',
            'forfeit_for_score': '5',
            'forfeit_against_score': '0',
        })
        form = DivisionForm(user=self.user, data=data, instance=instance)
        self.failIf(form.is_valid())
        self.assertEqual(form.errors['points_formula'],
                         [u'Syntax of this points formula is invalid.'])

        data.update({
            'points_formula_0': '3',
            'points_formula_1': '2',
            'points_formula_2': '1',
        })
        form = DivisionForm(user=self.user, data=data, instance=instance)
        self.assertEqual(form.is_valid(), True)

        data.update({
            'bonus_points_formula': '3*win + 2*draw + 1*loss',
        })
        form = DivisionForm(user=self.user, data=data, instance=instance)
        self.failIf(form.is_valid())
        self.assertEqual(form.errors['bonus_points_formula'],
                         [u'Syntax of this points formula is invalid.'])

        data.update({
            'bonus_points_formula': '[win=1,forfeit_for=0,score_against=0: 1] '
                                    '+ [loss=1,margin<=2: 1]',
        })
        form = DivisionForm(user=self.user, data=data, instance=instance)
        self.assertEqual(form.is_valid(), True)

    # StageForm

    def test_stage_form(self):
        division = Division.objects.get(pk=1)
        instance = Stage(division=division)

        data = {
            'title': '',
            'short_title': '',
            'keep_ladder': '1',
            'scale_group_points': '0',
            'carry_ladder': '0',
            'keep_mvp': '1',
            'slug': '',
            'slug_locked': '0',
        }
        form = StageForm(user=self.user, data=data, instance=instance)
        self.failIf(form.is_valid())
        self.assertEqual(form.errors['title'], [u'This field is required.'])

        data.update({
            'title': 'Test Division',
        })
        form = StageForm(user=self.user, data=data, instance=instance)
        self.assertEqual(form.is_valid(), True)

        instance.order = 3
        data.update({
            'follows': '404',
        })
        form = StageForm(user=self.user, data=data, instance=instance)
        self.failIf(form.is_valid())
        self.assertEqual(form.errors['follows'],
                         [u'Select a valid choice. That choice is not one of '
                          u'the available choices.'])

        data.update({
            'follows': '1',
        })
        form = StageForm(user=self.user, data=data, instance=instance)
        self.assertEqual(form.is_valid(), True)

    # StageGroupForm (Pool)

    @skip("StageGroupForm")
    def test_stagegroup_form(self):
        stage = Stage.objects.get(pk=1)
        instance = StageGroup(stage=stage)

        data = {
            'title': '',
            'short_title': '',
            'teams': [],
            'slug': '',
            'slug_locked': '0',
            'carry_ladder': '0',
        }
        form = StageGroupForm(user=self.user, data=data, instance=instance)
        self.failIf(form.is_valid())
        self.assertEqual(form.errors['title'], [u'This field is required.'])

        data.update({
            'title': 'Test Pool',
        })
        form = StageGroupForm(user=self.user, data=data, instance=instance)
        self.assertEqual(form.is_valid(), True)

        other = stage.pools.create(title='Other')
        other.teams = Team.objects.filter(pk__in=(1, 2, 3))
        data.update({
            'teams': ['1', '2', '3'],
        })
        form = StageGroupForm(user=self.user, data=data, instance=instance)
        self.failIf(form.is_valid())
        self.assertEqual(form.errors['teams'],
                         [u'Select a valid choice. 1 is not one of the '
                          u'available choices.'])

        data.update({
            'teams': ['4', '5'],
        })
        form = StageGroupForm(user=self.user, data=data, instance=instance)
        self.assertEqual(form.is_valid(), True)

    # CompetitionForm

    def test_competition_form(self):
        data = {
            'title': 'Test 1',
            'short_title': '',
            'enabled': '0',
            'description': '',
            'slug': '',
            'slug_locaked': '0',
            'clubs': [],
        }
        form = CompetitionForm(data=data)
        self.assertEqual(form.is_valid(), True)
