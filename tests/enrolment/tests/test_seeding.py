from io import StringIO

from django.core.management import call_command
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
)
from enrolment.seeding import seed
from test_plus import TestCase


class SeedingTests(TestCase):
    def test_seed_is_idempotent(self):
        first = seed(students=40)
        second = seed(students=40)
        self.assertEqual(first, second)
        self.assertEqual(SchoolYear.objects.count(), 2)
        self.assertEqual(Grade.objects.count(), 7)
        self.assertEqual(ClassGroup.objects.count(), 21)
        self.assertEqual(Student.objects.count(), 40)
        self.assertEqual(Assessment.objects.count(), 28)
        self.assertEqual(
            ReportCard.objects.count(),
            Enrolment.objects.filter(class_group__year__title="2026").count(),
        )

    def test_seed_is_deterministic(self):
        seed(students=20)
        fields = ("first_name", "last_name", "date_of_birth")
        names = list(Student.objects.values_list(*fields))
        Student.objects.all().delete()
        seed(students=20)
        self.assertEqual(names, list(Student.objects.values_list(*fields)))

    def test_seeded_rows_follow_the_rules(self):
        counts = seed(students=40)
        self.assertEqual(counts["Student"], 40)
        self.assertEqual(counts["Teacher"], 16)
        enrolments_2026 = Enrolment.objects.filter(class_group__year__title="2026")
        self.assertEqual(enrolments_2026.count(), 40)
        self.assertEqual(AttendanceRecord.objects.count(), 40 * 20)
        self.assertEqual(Score.objects.count(), 40 * 2)
        for enrolment in enrolments_2026.select_related(
            "student", "class_group__grade"
        ):
            age = 2026 - enrolment.student.date_of_birth.year
            self.assertEqual(age, 5 + enrolment.class_group.grade.ordinal)
        # Year 6 students leave, the rest move up one grade.
        leavers = Enrolment.objects.filter(
            class_group__year__title="2026", class_group__grade__ordinal=6
        ).count()
        self.assertEqual(
            Enrolment.objects.filter(class_group__year__title="2027").count(),
            40 - leavers,
        )
        self.assertFalse(
            ClassGroup.objects.filter(year__title="2026", teacher__isnull=True).exists()
        )

    def test_command_prints_counts(self):
        out = StringIO()
        call_command("seed_enrolment", students=10, stdout=out)
        self.assertIn("Student: 10", out.getvalue())
