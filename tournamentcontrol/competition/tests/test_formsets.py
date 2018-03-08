from test_plus import TestCase
from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.models import Match
from tournamentcontrol.competition.tests import factories


class DrawGenerationMatchFormSetTest(TestCase):

    def setUp(self):
        super(TestCase, self).setUp()
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        self.draw_format = factories.DrawFormatFactory.create(teams=4)

    def test_draw_format_name(self):
        self.assertEqual(self.draw_format.name, "Round Robin (3/4 teams)")

    def test_draw_format_text(self):
        self.assertEqual(
            self.draw_format.text,
            "ROUND\n"
            "1: 1 vs 4\n"
            "2: 2 vs 3\n"
            "ROUND\n"
            "3: 1 vs 3\n"
            "4: 4 vs 2\n"
            "ROUND\n"
            "5: 1 vs 2\n"
            "6: 3 vs 4"
        )

    def test_draw_generation_match_form_set_save(self):
        stage = factories.StageFactory.create()
        factories.TeamFactory.create_batch(4, division=stage.division)

        self.assertEqual(Match.objects.count(), 0)

        data0 = {
            'draw_generation_wizard-current_step': '0',

            '0-TOTAL_FORMS': '1',
            '0-INITIAL_FORMS': '1',
            '0-MIN_NUM_FORMS': '0',
            '0-MAX_NUM_FORMS': '1000',

            '0-0-start_date_0': '8',
            '0-0-start_date_1': '8',
            '0-0-start_date_2': '2018',
            '0-0-format': str(self.draw_format.pk),
            '0-0-rounds': '',
            '0-0-offset': '',
        }

        with self.login(self.superuser):
            self.post(
                'admin:fixja:competition:season:division:stage:draw:build',
                stage.division.season.competition.pk,
                stage.division.season.pk,
                stage.division.pk,
                stage.pk,
                data=data0)
            self.response_200()

            wizard = self.get_context('wizard')
            forms = wizard['form']
            total_forms = initial_forms = len(forms)

            data1 = {
                'draw_generation_wizard-current_step': '1',

                '1-TOTAL_FORMS': str(total_forms),
                '1-INITIAL_FORMS': str(initial_forms),
                '1-MIN_NUM_FORMS': '0',
                '1-MAX_NUM_FORMS': '1000',
            }

            for i, form in enumerate(forms):
                data1.update({
                    '1-%d-round' % i: str(form['round'].initial),
                    '1-%d-home_team' % i: str(form['home_team'].initial or ''),
                    '1-%d-away_team' % i: str(form['away_team'].initial or ''),
                    '1-%d-date' % i: form['date'].initial.strftime("%Y-%m-%d"),
                })

            self.post(
                'admin:fixja:competition:season:division:stage:draw:build',
                stage.division.season.competition.pk,
                stage.division.season.pk,
                stage.division.pk,
                stage.pk,
                data=data1)
            self.response_302()

        self.assertEqual(Match.objects.count(), 6)
        self.assertQuerysetEqual(
            Match.objects.all(),
            [
                '<Match: 1: Team 1 vs Team 4>',
                '<Match: 1: Team 2 vs Team 3>',
                '<Match: 2: Team 1 vs Team 3>',
                '<Match: 2: Team 4 vs Team 2>',
                '<Match: 3: Team 1 vs Team 2>',
                '<Match: 3: Team 3 vs Team 4>',
            ],
        )
