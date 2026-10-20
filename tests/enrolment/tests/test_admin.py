import datetime

from django.conf import settings
from enrolment.models import (
    Assessment,
    AttendanceRecord,
    ClassGroup,
    Enrolment,
    Grade,
    ReportCard,
    SchoolYear,
    Student,
    Teacher,
)
from test_plus import test as test_plus

from touchtechnology.admin.sites import site
from touchtechnology.common.tests.factories import UserFactory


class RegistrationTests(test_plus.TestCase):
    def setUp(self):
        self.superuser = UserFactory.create(is_staff=True, is_superuser=True)

    def test_component_is_registered(self):
        names = [c.app_name for c in site._components.values()]
        self.assertIn("enrolment", names)

    def test_index_redirects_to_years(self):
        with self.login(self.superuser):
            self.get("admin:enrolment:index")
            self.response_302()
            self.assertEqual(
                self.last_response["Location"],
                self.reverse("admin:enrolment:schoolyear:list"),
            )


class EnrolmentDataMixin:
    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        cls.staff = UserFactory.create(is_staff=True)
        cls.year = SchoolYear.objects.create(
            title="2026",
            start_date=datetime.date(2026, 1, 27),
            end_date=datetime.date(2026, 12, 11),
        )
        cls.grade = Grade.objects.create(title="Year 2", ordinal=2)
        cls.teacher = Teacher.objects.create(first_name="Maeve", last_name="Okafor")
        cls.group = ClassGroup.objects.create(
            year=cls.year, grade=cls.grade, title="2C", teacher=cls.teacher
        )
        cls.student = Student.objects.create(
            first_name="Ines",
            last_name="Varga",
            date_of_birth=datetime.date(2018, 5, 3),
            guardian_name="Petra Varga",
        )
        cls.enrolment = Enrolment.objects.create(
            student=cls.student, class_group=cls.group
        )
        cls.attendance = AttendanceRecord.objects.create(
            enrolment=cls.enrolment, date=datetime.date(2026, 2, 2)
        )
        cls.report_card = ReportCard.objects.create(enrolment=cls.enrolment, term=1)
        cls.assessment = Assessment.objects.create(
            class_group=cls.group,
            title="Spelling check",
            date=datetime.date(2026, 3, 3),
            maximum_mark=10,
        )

    @property
    def enrolment_kwargs(self):
        return {
            "year_id": self.year.pk,
            "class_group_id": self.group.pk,
            "enrolment_id": self.enrolment.pk,
        }


class GoodViewTests(EnrolmentDataMixin, test_plus.TestCase):
    def test_year_list(self):
        with self.login(self.superuser):
            self.get_check_200("admin:enrolment:schoolyear:list")
            self.assertResponseContains(
                f'<a href="{self.year.urls["edit"]}">2026</a>', html=True
            )

    def test_grade_list(self):
        with self.login(self.superuser):
            self.get_check_200("admin:enrolment:grade:list")

    def test_teacher_list(self):
        with self.login(self.superuser):
            self.get_check_200("admin:enrolment:teacher:list")

    def test_student_list(self):
        with self.login(self.superuser):
            self.get_check_200("admin:enrolment:student:list")

    def test_year_edit(self):
        with self.login(self.superuser):
            self.get_check_200("admin:enrolment:schoolyear:edit", pk=self.year.pk)

    def test_class_group_edit(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:enrolment:classgroup:edit",
                year_id=self.year.pk,
                pk=self.group.pk,
            )

    def test_enrolment_edit(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:enrolment:enrolment:edit",
                year_id=self.year.pk,
                class_group_id=self.group.pk,
                pk=self.enrolment.pk,
            )

    def test_attendance_edit(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:enrolment:attendancerecord:edit",
                pk=self.attendance.pk,
                **self.enrolment_kwargs,
            )

    def test_report_card_edit(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:enrolment:reportcard:edit",
                pk=self.report_card.pk,
                **self.enrolment_kwargs,
            )

    def test_assessment_edit(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:enrolment:assessment:edit",
                year_id=self.year.pk,
                class_group_id=self.group.pk,
                pk=self.assessment.pk,
            )

    def test_student_edit_shows_timeline_tab(self):
        with self.login(self.superuser):
            self.get_check_200("admin:enrolment:student:edit", pk=self.student.pk)
            self.assertResponseContains(
                '<a href="#timeline-tab" data-toggle="tab">Timeline</a>', html=True
            )
            self.assertResponseContains(
                f'<li><a href="{self.enrolment.urls["edit"]}">2C (2026)</a></li>',
                html=True,
            )

    def test_create_class_group_returns_to_year_tab(self):
        with self.login(self.superuser):
            self.post(
                "admin:enrolment:classgroup:add",
                year_id=self.year.pk,
                data={
                    "grade": self.grade.pk,
                    "title": "2D",
                    "teacher": self.teacher.pk,
                },
            )
            self.response_302()
            self.assertEqual(
                self.last_response["Location"],
                f'{self.year.urls["edit"]}#classes-tab',
            )
            self.assertTrue(
                ClassGroup.objects.filter(year=self.year, title="2D").exists()
            )

    def test_duplicate_enrolment_is_a_form_error(self):
        with self.login(self.superuser):
            self.post(
                "admin:enrolment:enrolment:add",
                year_id=self.year.pk,
                class_group_id=self.group.pk,
                data={"student": self.student.pk},
            )
            self.response_200()
            self.assertFormError(
                self.last_response.context["form"],
                None,
                "Enrolment with this Student and Class group already exists.",
            )

    def test_score_above_maximum_is_a_form_error(self):
        with self.login(self.superuser):
            self.post(
                "admin:enrolment:assessment:edit",
                year_id=self.year.pk,
                class_group_id=self.group.pk,
                pk=self.assessment.pk,
                data={
                    "form-title": self.assessment.title,
                    "form-date": "2026-03-03",
                    "form-maximum_mark": "10",
                    "formset-TOTAL_FORMS": "1",
                    "formset-INITIAL_FORMS": "0",
                    "formset-MIN_NUM_FORMS": "0",
                    "formset-MAX_NUM_FORMS": "1000",
                    "formset-0-enrolment": self.enrolment.pk,
                    "formset-0-mark": "11",
                },
            )
            self.response_200()
            self.assertIn("mark", self.last_response.context["formset"].errors[0])
            self.assertFalse(self.assessment.scores.exists())

    def test_delete_class_group_cascades(self):
        with self.login(self.superuser):
            self.post(
                "admin:enrolment:classgroup:delete",
                year_id=self.year.pk,
                pk=self.group.pk,
            )
            self.response_302()
            self.assertFalse(Enrolment.objects.filter(class_group=self.group).exists())


class BadViewTests(EnrolmentDataMixin, test_plus.TestCase):
    def test_anonymous_is_redirected_to_login(self):
        self.get("admin:enrolment:schoolyear:list")
        self.response_302()
        self.assertIn(str(settings.LOGIN_URL), self.last_response["Location"])

    def test_staff_without_permission_is_forbidden(self):
        with self.login(self.staff):
            self.get("admin:enrolment:schoolyear:list")
            self.response_403()
