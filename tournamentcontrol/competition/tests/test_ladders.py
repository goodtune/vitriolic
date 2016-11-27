from test_plus import TestCase

from tournamentcontrol.competition import models


class LadderTest(TestCase):

    fixtures = [
        'draw_format',
        'ladders',
    ]

    def setUp(self):
        super(LadderTest, self).setUp()
        # trigger the signal handlers to produce ladder entry and summary
        for match in models.Match.objects.all():
            match.save()

    def test_team_sequence(self):
        self.assertEqual(
            list(models.Team.objects.values_list('order', flat=True)),
            [1, 2, 3, 4, 5])

    def test_draw_format_count(self):
        self.assertEquals(1, models.DrawFormat.objects.count())

    def test_team_count(self):
        self.assertEqual(5, models.Team.objects.count())

    def test_ground_count(self):
        self.assertEqual(4, models.Ground.objects.count())

    def test_ladder_entry_count(self):
        self.assertEqual(4, models.LadderEntry.objects.count())

    def test_ladder_summary_count(self):
        self.assertEqual(4, models.LadderSummary.objects.count())

    def test_ladder_summary_points(self):
        "Control test - ensure that LadderSummary starts as we expect"
        summary = models.LadderSummary.objects.all()

        win = summary.get(win=1)
        loss = summary.get(loss=1)
        draw = summary.filter(draw=1)[0]

        self.assertEqual(3, win.points)
        self.assertEqual(1, loss.points)
        self.assertEqual(2, draw.points)

    def test_ladder_summary_points_adjusted(self):
        "Modify Division.points_formula and recalculate LadderSummary"
        summary = models.LadderSummary.objects.all()
        pks = sorted(summary.values_list('pk', flat=True))

        # update the points formula
        stage = models.Stage.objects.latest('pk')
        stage.division.points_formula = u"2*win + 1*draw"
        stage.division.save()

        win = summary.get(win=1)
        loss = summary.get(loss=1)
        draw = summary.filter(draw=1)[0]

        self.assertEqual(2, win.points)
        self.assertEqual(0, loss.points)
        self.assertEqual(1, draw.points)

        # check that the pk values have changed after the change
        self.assertNotEqual(pks, sorted(summary.values_list('pk', flat=True)))

    def test_ladder_summary_points_not_adjusted(self):
        "Modify another field on Division and don't update LadderSummary"
        summary = models.LadderSummary.objects.all()
        pks = sorted(summary.values_list('pk', flat=True))

        # update any fields other than the points formula
        stage = models.Stage.objects.latest('pk')
        stage.division.short_title = u"D%d" % stage.division.order
        stage.division.save()

        self.assertEqual(pks, sorted(summary.values_list('pk', flat=True)))
