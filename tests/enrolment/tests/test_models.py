import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
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
from test_plus import TestCase


class ModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.year = SchoolYear.objects.create(
            title="2026",
            start_date=datetime.date(2026, 1, 27),
            end_date=datetime.date(2026, 12, 11),
        )
        cls.grade = Grade.objects.create(title="Year 1", ordinal=1)
        cls.teacher = Teacher.objects.create(first_name="Maeve", last_name="Okafor")
        cls.group = ClassGroup.objects.create(
            year=cls.year, grade=cls.grade, title="1B", teacher=cls.teacher
        )
        cls.student = Student.objects.create(
            first_name="Ines",
            last_name="Varga",
            date_of_birth=datetime.date(2019, 5, 3),
            guardian_name="Petra Varga",
        )
        cls.assessment = Assessment.objects.create(
            class_group=cls.group,
            title="Spelling check",
            date=datetime.date(2026, 3, 4),
            maximum_mark=10,
        )

    def setUp(self):
        self.enrolment = Enrolment.objects.create(
            student=self.student, class_group=self.group
        )

    def test_class_group_str_names_year(self):
        group = ClassGroup.objects.create(year=self.year, grade=self.grade, title="1C")
        self.assertEqual(str(group), "1C (2026)")

    def test_str_forms(self):
        self.assertEqual(str(self.year), "2026")
        self.assertEqual(str(self.student), "Ines Varga")
        self.assertEqual(str(self.teacher), "Maeve Okafor")
        self.assertEqual(str(self.enrolment), "Ines Varga in 1B (2026)")
        self.assertEqual(str(self.assessment), "Spelling check")
        record = AttendanceRecord.objects.create(
            enrolment=self.enrolment,
            date=datetime.date(2026, 2, 2),
            status=AttendanceRecord.ABSENT,
        )
        self.assertEqual(str(record), "2026-02-02: absent")
        score = Score.objects.create(
            assessment=self.assessment, enrolment=self.enrolment, mark=7
        )
        self.assertEqual(str(score), "7/10")
        report = ReportCard.objects.create(enrolment=self.enrolment, term=1)
        self.assertEqual(str(report), "Term 1")

    def test_url_args_follow_the_hierarchy(self):
        record = AttendanceRecord.objects.create(
            enrolment=self.enrolment, date=datetime.date(2026, 2, 2)
        )
        self.assertEqual(
            record._get_url_args(),
            (self.year.pk, self.group.pk, self.enrolment.pk, record.pk),
        )
        self.assertEqual(
            self.enrolment._get_admin_namespace(), "admin:enrolment:enrolment"
        )

    def test_enrolment_urls_nest_under_year_and_class(self):
        enrolment = Enrolment.objects.create(
            student=Student.objects.create(
                first_name="Tomas",
                last_name="Lindqvist",
                date_of_birth=datetime.date(2019, 8, 9),
                guardian_name="Anna Lindqvist",
            ),
            class_group=self.group,
        )
        self.assertEqual(
            str(enrolment.urls["edit"]),
            f"/admin/enrolment/year/{self.year.pk}/class/{self.group.pk}/enrolment/{enrolment.pk}/",
        )

    def test_score_above_maximum_is_invalid(self):
        score = Score(assessment=self.assessment, enrolment=self.enrolment, mark=11)
        with self.assertRaises(ValidationError) as cm:
            score.full_clean()
        self.assertIn("mark", cm.exception.message_dict)

    def test_score_at_maximum_is_valid(self):
        score = Score(assessment=self.assessment, enrolment=self.enrolment, mark=10)
        score.full_clean()
        score.save()
        self.assertEqual(self.assessment.scores.count(), 1)

    def test_duplicate_enrolment_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Enrolment.objects.create(student=self.student, class_group=self.group)

    def test_duplicate_class_title_in_year_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClassGroup.objects.create(
                year=self.year, grade=self.grade, title=self.group.title
            )

    def test_one_report_card_per_term(self):
        ReportCard.objects.create(enrolment=self.enrolment, term=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReportCard.objects.create(enrolment=self.enrolment, term=2)
