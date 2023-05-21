from __future__ import unicode_literals

from test_plus import TestCase
from touchtechnology.common.tests.factories import UserFactory
from tournamentcontrol.competition.models import Match
from tournamentcontrol.competition.tests import factories


class DrawGenerationMatchFormSetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(is_staff=True, is_superuser=True)

        factories.DrawFormatFactory.reset_sequence()
        cls.draw_format = factories.DrawFormatFactory.create(teams=4)

        factories.StageFactory.reset_sequence()
        cls.stage = factories.StageFactory.create()

        factories.TeamFactory.reset_sequence()
        cls.teams = factories.TeamFactory.create_batch(4, division=cls.stage.division)

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
            "6: 3 vs 4",
        )

    def test_draw_generation_match_form_set_save(self):
        self.assertEqual(Match.objects.count(), 0)

        data0 = {
            "draw_generation_wizard-current_step": "0",
            "0-TOTAL_FORMS": "1",
            "0-INITIAL_FORMS": "1",
            "0-MIN_NUM_FORMS": "0",
            "0-MAX_NUM_FORMS": "1000",
            "0-0-start_date_0": "8",
            "0-0-start_date_1": "8",
            "0-0-start_date_2": "2018",
            "0-0-format": str(self.draw_format.pk),
            "0-0-rounds": "",
            "0-0-offset": "",
        }

        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:division:stage:draw:build",
                self.stage.division.season.competition.pk,
                self.stage.division.season.pk,
                self.stage.division.pk,
                self.stage.pk,
                data=data0,
            )
            self.response_200()

            wizard = self.get_context("wizard")
            forms = wizard["form"]
            total_forms = initial_forms = len(forms)

            data1 = {
                "draw_generation_wizard-current_step": "1",
                "1-TOTAL_FORMS": str(total_forms),
                "1-INITIAL_FORMS": str(initial_forms),
                "1-MIN_NUM_FORMS": "0",
                "1-MAX_NUM_FORMS": "1000",
            }

            for i, form in enumerate(forms):
                data1.update(
                    {
                        "1-%d-round" % i: str(form["round"].initial),
                        "1-%d-home_team" % i: str(form["home_team"].initial or ""),
                        "1-%d-away_team" % i: str(form["away_team"].initial or ""),
                        "1-%d-date" % i: form["date"].initial.strftime("%Y-%m-%d"),
                    }
                )

            self.post(
                "admin:fixja:competition:season:division:stage:draw:build",
                self.stage.division.season.competition.pk,
                self.stage.division.season.pk,
                self.stage.division.pk,
                self.stage.pk,
                data=data1,
            )
            self.response_302()

        self.assertEqual(Match.objects.count(), 6)

        team1, team2, team3, team4 = self.teams
        self.assertQuerysetEqual(
            Match.objects.all(),
            [
                "<Match: 1: %s vs %s>" % (team1, team4),
                "<Match: 1: %s vs %s>" % (team2, team3),
                "<Match: 2: %s vs %s>" % (team1, team3),
                "<Match: 2: %s vs %s>" % (team4, team2),
                "<Match: 3: %s vs %s>" % (team1, team2),
                "<Match: 3: %s vs %s>" % (team3, team4),
            ],
            transform=repr,
        )

    def test_draw_generation_match_form_set_progression_save(self):
        stage = factories.StageFactory.create(
            division=self.stage.division,
            follows=self.stage,
        )

        draw_format = factories.DrawFormatFactory.create(
            teams=4,
            name="Single Elimination",
            text=(
                "ROUND\n"
                "1: P1 vs P4 Semi Final 1\n"
                "2: P2 vs P3 Semi Final 2\n"
                "ROUND\n"
                "3: L1 vs L2 Bronze Medal\n"
                "4: W1 vs W2 Gold Medal\n"
            ),
        )

        self.assertEqual(Match.objects.count(), 0)

        data0 = {
            "draw_generation_wizard-current_step": "0",
            "0-TOTAL_FORMS": "1",
            "0-INITIAL_FORMS": "1",
            "0-MIN_NUM_FORMS": "0",
            "0-MAX_NUM_FORMS": "1000",
            "0-0-start_date_0": "8",
            "0-0-start_date_1": "8",
            "0-0-start_date_2": "2018",
            "0-0-format": str(draw_format.pk),
            "0-0-rounds": "",
            "0-0-offset": "",
        }

        with self.login(self.superuser):
            self.post(
                "admin:fixja:competition:season:division:stage:draw:build",
                stage.division.season.competition.pk,
                stage.division.season.pk,
                stage.division.pk,
                stage.pk,
                data=data0,
            )
            self.response_200()

            wizard = self.get_context("wizard")
            forms = wizard["form"]
            total_forms = initial_forms = len(forms)

            data1 = {
                "draw_generation_wizard-current_step": "1",
                "1-TOTAL_FORMS": str(total_forms),
                "1-INITIAL_FORMS": str(initial_forms),
                "1-MIN_NUM_FORMS": "0",
                "1-MAX_NUM_FORMS": "1000",
            }

            for i, form in enumerate(forms):
                data1.update(
                    {
                        "1-%d-round" % i: str(form["round"].initial),
                        "1-%d-home_team" % i: str(form["home_team"].initial or ""),
                        "1-%d-away_team" % i: str(form["away_team"].initial or ""),
                        "1-%d-date" % i: form["date"].initial.strftime("%Y-%m-%d"),
                    }
                )

            self.post(
                "admin:fixja:competition:season:division:stage:draw:build",
                stage.division.season.competition.pk,
                stage.division.season.pk,
                stage.division.pk,
                stage.pk,
                data=data1,
            )
            self.response_302()

        self.assertCountEqual(
            [(m.get_home_team(), m.get_away_team()) for m in Match.objects.all()],
            [
                ({"title": "1st"}, {"title": "4th"}),
                ({"title": "2nd"}, {"title": "3rd"}),
                ({"title": "Loser Semi Final 1"}, {"title": "Loser Semi Final 2"}),
                ({"title": "Winner Semi Final 1"}, {"title": "Winner Semi Final 2"}),
            ],
        )
