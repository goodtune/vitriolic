from harness.flow import STEPS

EXPECTED = [
    "step_1_sign_in",
    "step_2_competition",
    "step_3_season",
    "step_4_clubs_and_people",
    "step_5_divisions_and_teams",
    "step_6_draw",
    "step_7_schedule",
    "step_8_results",
    "step_9_undo_draw",
    "step_10_content",
    "step_11_enrolment",
    "step_12_delete_attendance",
    "step_13_sign_out",
]


def test_the_flow_has_the_thirteen_steps_in_order():
    assert [step.__name__ for step in STEPS] == EXPECTED


def test_every_step_can_be_called():
    assert all(callable(step) for step in STEPS)
