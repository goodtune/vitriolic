import collections
import datetime

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import get_resolver
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
from guardian.shortcuts import assign_perm
from test_plus import test as test_plus

from touchtechnology.admin.sites import site
from touchtechnology.common.tests.factories import UserFactory

ADD_CLASS_GROUP = "admin:enrolment:classgroup:add"


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
        cls.other_group = ClassGroup.objects.create(
            year=cls.year, grade=cls.grade, title="2E", teacher=cls.teacher
        )
        cls.student = Student.objects.create(
            first_name="Ines",
            last_name="Varga",
            date_of_birth=datetime.date(2018, 5, 3),
            guardian_name="Petra Varga",
        )
        cls.classmate = Student.objects.create(
            first_name="Priya",
            last_name="Nair",
            date_of_birth=datetime.date(2018, 9, 14),
            guardian_name="Asha Nair",
        )
        cls.outsider = Student.objects.create(
            first_name="Tomas",
            last_name="Lindqvist",
            date_of_birth=datetime.date(2018, 2, 21),
            guardian_name="Anna Lindqvist",
        )
        cls.enrolment = Enrolment.objects.create(
            student=cls.student, class_group=cls.group
        )
        cls.classmate_enrolment = Enrolment.objects.create(
            student=cls.classmate, class_group=cls.group
        )
        cls.outsider_enrolment = Enrolment.objects.create(
            student=cls.outsider, class_group=cls.other_group
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

    @property
    def assessment_kwargs(self):
        return {
            "year_id": self.year.pk,
            "class_group_id": self.group.pk,
            "pk": self.assessment.pk,
        }

    def assessment_data(self, *rows):
        "POST data for the assessment page, with one (enrolment, mark) per row."
        data = {
            "form-title": self.assessment.title,
            "form-date": "2026-03-03",
            "form-maximum_mark": "10",
            "formset-TOTAL_FORMS": str(len(rows)),
            "formset-INITIAL_FORMS": "0",
            "formset-MIN_NUM_FORMS": "0",
            "formset-MAX_NUM_FORMS": "1000",
        }
        for index, (enrolment, mark) in enumerate(rows):
            data["formset-%d-enrolment" % index] = enrolment.pk
            data["formset-%d-mark" % index] = mark
        return data


class GoodViewTests(EnrolmentDataMixin, test_plus.TestCase):
    def test_year_list(self):
        with self.login(self.superuser):
            self.get_check_200("admin:enrolment:schoolyear:list")
            self.assertResponseContains(
                f'<a href="{self.year.urls["edit"]}"><svg class="icon" aria-hidden="true" focusable="false"><use href="/static/touchtechnology/admin/img/icons.svg#schoolyear"></use></svg><span>2026</span></a>', html=True
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

    def test_student_list_search_filters_by_name(self):
        with self.login(self.superuser):
            self.get_check_200("admin:enrolment:student:list", data={"search": "Ines"})
            self.assertResponseContains(
                f'<a href="{self.student.urls["edit"]}"><svg class="icon" aria-hidden="true" focusable="false"><use href="/static/touchtechnology/admin/img/icons.svg#student"></use></svg><span>Ines Varga</span></a>', html=True
            )
            self.assertResponseNotContains(
                f'<a href="{self.outsider.urls["edit"]}"><svg class="icon" aria-hidden="true" focusable="false"><use href="/static/touchtechnology/admin/img/icons.svg#student"></use></svg><span>Tomas Lindqvist</span></a>',
                html=True,
            )

    def test_year_edit(self):
        with self.login(self.superuser):
            self.get_check_200("admin:enrolment:schoolyear:edit", pk=self.year.pk)

    def test_year_edit_links_to_add_a_class_group(self):
        with self.login(self.superuser):
            self.get_check_200("admin:enrolment:schoolyear:edit", pk=self.year.pk)
            self.assertResponseContains(
                '<a class="button primary compact" href="%s">'
                '<svg class="icon" aria-hidden="true" focusable="false">'
                '<use href="/static/touchtechnology/admin/img/icons.svg#plus"></use>'
                "</svg><span>Add class group</span></a>"
                % self.reverse(ADD_CLASS_GROUP, year_id=self.year.pk),
                html=True,
            )

    def test_grade_edit_has_no_link_to_add_a_class_group(self):
        with self.login(self.superuser):
            self.get_check_200("admin:enrolment:grade:edit", pk=self.grade.pk)
            self.assertResponseContains(
                f'<a href="{self.group.urls["edit"]}"><svg class="icon" aria-hidden="true" focusable="false"><use href="/static/touchtechnology/admin/img/icons.svg#classgroup"></use></svg><span>2C (2026)</span></a>', html=True
            )
            self.assertNotContains(self.last_response, "/class/add/")

    def test_teacher_edit_has_no_link_to_add_a_class_group(self):
        with self.login(self.superuser):
            self.get_check_200("admin:enrolment:teacher:edit", pk=self.teacher.pk)
            self.assertResponseContains(
                f'<a href="{self.group.urls["edit"]}"><svg class="icon" aria-hidden="true" focusable="false"><use href="/static/touchtechnology/admin/img/icons.svg#classgroup"></use></svg><span>2C (2026)</span></a>', html=True
            )
            self.assertNotContains(self.last_response, "/class/add/")

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
                "admin:enrolment:assessment:edit", **self.assessment_kwargs
            )

    def test_student_edit_shows_timeline_tab(self):
        with self.login(self.superuser):
            self.get_check_200("admin:enrolment:student:edit", pk=self.student.pk)
            self.assertResponseContains(
                '<a class="tab" role="tab" id="timeline-tab-link" href="#timeline-tab" '
                'aria-controls="timeline-tab" aria-selected="false" tabindex="-1">'
                '<svg class="icon" aria-hidden="true" focusable="false">'
                '<use href="/static/touchtechnology/admin/img/icons.svg#season"></use>'
                "</svg><span>Timeline</span></a>",
                html=True,
            )
            self.assertResponseContains(
                f'<li><a href="{self.enrolment.urls["edit"]}">2C (2026)</a></li>',
                html=True,
            )

    def test_student_add_has_no_timeline_tab(self):
        with self.login(self.superuser):
            self.get_check_200("admin:enrolment:student:add")
            self.assertNotContains(self.last_response, "timeline-tab")

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

    def test_student_in_another_class_of_the_year_is_a_form_error(self):
        with self.login(self.superuser):
            self.post(
                "admin:enrolment:enrolment:add",
                year_id=self.year.pk,
                class_group_id=self.other_group.pk,
                data={"student": self.student.pk},
            )
            self.response_200()
            self.assertFormError(
                self.last_response.context["form"],
                None,
                "Ines Varga is already enrolled in 2C (2026) this year.",
            )
            self.assertFalse(
                Enrolment.objects.filter(
                    student=self.student, class_group=self.other_group
                ).exists()
            )

    def test_student_may_move_up_to_a_class_in_the_next_year(self):
        next_year = SchoolYear.objects.create(
            title="2027",
            start_date=datetime.date(2027, 1, 27),
            end_date=datetime.date(2027, 12, 10),
        )
        next_group = ClassGroup.objects.create(
            year=next_year, grade=self.grade, title="3A"
        )
        with self.login(self.superuser):
            self.post(
                "admin:enrolment:enrolment:add",
                year_id=next_year.pk,
                class_group_id=next_group.pk,
                data={"student": self.student.pk},
            )
            self.response_302()
            self.assertTrue(
                Enrolment.objects.filter(
                    student=self.student, class_group=next_group
                ).exists()
            )

    def test_editing_an_enrolment_does_not_clash_with_itself(self):
        with self.login(self.superuser):
            self.post(
                "admin:enrolment:enrolment:edit",
                year_id=self.year.pk,
                class_group_id=self.group.pk,
                pk=self.enrolment.pk,
                data={"student": self.student.pk},
            )
            self.response_302()

    def test_score_above_maximum_is_a_form_error(self):
        with self.login(self.superuser):
            self.post(
                "admin:enrolment:assessment:edit",
                data=self.assessment_data((self.enrolment, "11")),
                **self.assessment_kwargs,
            )
            self.response_200()
            self.assertFormError(
                self.last_response.context["formset"].forms[0],
                "mark",
                "The mark cannot be more than the maximum of 10.",
            )
            self.assertFalse(self.assessment.scores.exists())

    def test_score_within_maximum_is_saved(self):
        with self.login(self.superuser):
            self.post(
                "admin:enrolment:assessment:edit",
                data=self.assessment_data((self.enrolment, "9")),
                **self.assessment_kwargs,
            )
            self.response_302()
            self.assertEqual(
                list(self.assessment.scores.values_list("enrolment", "mark")),
                [(self.enrolment.pk, 9)],
            )

    def test_score_for_a_student_of_another_class_is_a_form_error(self):
        with self.login(self.superuser):
            self.post(
                "admin:enrolment:assessment:edit",
                data=self.assessment_data((self.outsider_enrolment, "5")),
                **self.assessment_kwargs,
            )
            self.response_200()
            self.assertFormError(
                self.last_response.context["formset"].forms[0],
                "enrolment",
                "Select a valid choice. That choice is not one of the available "
                "choices.",
            )
            self.assertFalse(self.assessment.scores.exists())

    def test_assessment_offers_only_the_classs_students(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:enrolment:assessment:edit", **self.assessment_kwargs
            )
            self.assertResponseContains(
                f'<option value="{self.enrolment.pk}">Ines Varga</option>', html=True
            )
            self.assertResponseContains(
                f'<option value="{self.classmate_enrolment.pk}">Priya Nair</option>',
                html=True,
            )
            self.assertResponseNotContains(
                f'<option value="{self.outsider_enrolment.pk}">Tomas Lindqvist</option>',
                html=True,
            )

    def test_assessment_page_query_count_does_not_grow_with_the_class(self):
        group = ClassGroup.objects.create(
            year=self.year, grade=self.grade, title="2F", teacher=self.teacher
        )
        assessment = Assessment.objects.create(
            class_group=group,
            title="Number check",
            date=datetime.date(2026, 3, 10),
            maximum_mark=20,
        )
        for number in range(20):
            student = Student.objects.create(
                first_name="Pupil%02d" % number,
                last_name="Testcase",
                date_of_birth=datetime.date(2018, 1, 1),
                guardian_name="Guardian Testcase",
            )
            enrolment = Enrolment.objects.create(student=student, class_group=group)
            Score.objects.create(assessment=assessment, enrolment=enrolment, mark=12)

        with self.login(self.superuser):
            with CaptureQueriesContext(connection) as queries:
                self.get_check_200(
                    "admin:enrolment:assessment:edit",
                    year_id=self.year.pk,
                    class_group_id=group.pk,
                    pk=assessment.pk,
                )
        self.assertLess(len(queries), 60)

    def test_delete_class_group_cascades(self):
        Score.objects.create(
            assessment=self.assessment, enrolment=self.enrolment, mark=7
        )
        with self.login(self.superuser):
            self.post(
                "admin:enrolment:classgroup:delete",
                year_id=self.year.pk,
                pk=self.group.pk,
            )
            self.response_302()
            self.assertEqual(
                self.last_response["Location"],
                f'{self.year.urls["edit"]}#classes-tab',
            )
            self.assertFalse(Enrolment.objects.filter(class_group=self.group).exists())
            self.assertFalse(Assessment.objects.filter(class_group=self.group).exists())
            self.assertFalse(Score.objects.exists())


Row = collections.namedtuple("Row", "name kwargs target")


class PermissionDataMixin:
    """
    Two school years, each with a class group and an enrolment, and the
    attendance, assessment, scores and report card of the first.
    """

    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(is_staff=True, is_superuser=True)
        cls.staff = UserFactory.create(is_staff=True)
        cls.year = SchoolYear.objects.create(
            title="2026",
            start_date=datetime.date(2026, 1, 27),
            end_date=datetime.date(2026, 12, 11),
        )
        cls.other_year = SchoolYear.objects.create(
            title="2027",
            start_date=datetime.date(2027, 1, 27),
            end_date=datetime.date(2027, 12, 10),
        )
        cls.grade = Grade.objects.create(title="Year 3", ordinal=3)
        cls.teacher = Teacher.objects.create(first_name="Orla", last_name="Brannigan")
        cls.group = ClassGroup.objects.create(
            year=cls.year, grade=cls.grade, title="3A", teacher=cls.teacher
        )
        cls.other_group = ClassGroup.objects.create(
            year=cls.other_year, grade=cls.grade, title="3B", teacher=cls.teacher
        )
        cls.student = Student.objects.create(
            first_name="Wren",
            last_name="Halloran",
            date_of_birth=datetime.date(2017, 4, 8),
            guardian_name="Dara Halloran",
        )
        cls.other_student = Student.objects.create(
            first_name="Soren",
            last_name="Ingleby",
            date_of_birth=datetime.date(2017, 6, 30),
            guardian_name="Hana Ingleby",
        )
        cls.enrolment = Enrolment.objects.create(
            student=cls.student, class_group=cls.group
        )
        cls.other_enrolment = Enrolment.objects.create(
            student=cls.other_student, class_group=cls.other_group
        )
        cls.attendance = AttendanceRecord.objects.create(
            enrolment=cls.enrolment, date=datetime.date(2026, 2, 2)
        )
        cls.report_card = ReportCard.objects.create(enrolment=cls.enrolment, term=1)
        cls.assessment = Assessment.objects.create(
            class_group=cls.group,
            title="Reading check",
            date=datetime.date(2026, 3, 3),
            maximum_mark=10,
        )
        cls.score = Score.objects.create(
            assessment=cls.assessment, enrolment=cls.enrolment, mark=8
        )

    @property
    def year_kwargs(self):
        return {"year_id": self.year.pk}

    @property
    def class_kwargs(self):
        return {**self.year_kwargs, "class_group_id": self.group.pk}

    @property
    def enrolment_kwargs(self):
        return {**self.class_kwargs, "enrolment_id": self.enrolment.pk}

    @property
    def models(self):
        """
        Each model with pages: the URL namespace, an instance, the keyword
        arguments that name its parent in the URL, and whether it has a list
        page of its own.
        """
        return [
            ("schoolyear", self.year, {}, True),
            ("grade", self.grade, {}, True),
            ("teacher", self.teacher, {}, True),
            ("student", self.student, {}, True),
            ("classgroup", self.group, self.year_kwargs, False),
            ("enrolment", self.enrolment, self.class_kwargs, False),
            ("attendancerecord", self.attendance, self.enrolment_kwargs, False),
            ("reportcard", self.report_card, self.enrolment_kwargs, False),
            ("assessment", self.assessment, self.class_kwargs, False),
        ]

    @property
    def rows(self):
        "Every URL name of the component, with the arguments to reverse it."
        rows = []
        for namespace, instance, parent, listed in self.models:
            name = "admin:enrolment:%s:%%s" % namespace
            if listed:
                rows.append(Row(name % "list", {}, None))
            rows.extend(
                [
                    Row(name % "add", parent, None),
                    Row(name % "edit", {**parent, "pk": instance.pk}, None),
                    Row(name % "delete", {**parent, "pk": instance.pk}, instance),
                    Row(name % "perms", {**parent, "pk": instance.pk}, None),
                ]
            )
        return rows

    @staticmethod
    def method(row):
        "The delete views take POST only; the others are opened with GET."
        return "post" if row.target is not None else "get"

    def assertStillExists(self, row):
        if row.target is not None:
            self.assertTrue(
                type(row.target).objects.filter(pk=row.target.pk).exists(),
                "%s removed %r" % (row.name, row.target),
            )


class PermissionSweepTests(PermissionDataMixin, test_plus.TestCase):
    def test_table_has_every_url_name_of_the_component(self):
        component = (
            get_resolver().namespace_dict["admin"][1].namespace_dict["enrolment"][1]
        )
        registered = {
            "admin:enrolment:%s:%s" % (namespace, pattern.name)
            for namespace, (_, resolver) in component.namespace_dict.items()
            for pattern in resolver.url_patterns
        }
        self.assertEqual(registered, {row.name for row in self.rows})

    def test_anonymous_is_redirected_to_login(self):
        for row in self.rows:
            with self.subTest(row.name, **row.kwargs):
                self.assertLoginRequired(
                    row.name, method=self.method(row), **row.kwargs
                )
                self.assertStillExists(row)

    def test_staff_without_permission_is_forbidden(self):
        with self.login(self.staff):
            for row in self.rows:
                with self.subTest(row.name, **row.kwargs):
                    if row.target is None:
                        self.get(row.name, **row.kwargs)
                        self.response_403()
                    self.post(row.name, **row.kwargs)
                    self.response_403()
                    self.assertStillExists(row)

    def test_staff_with_model_permissions_can_list_and_edit(self):
        for namespace, instance, parent, listed in self.models:
            codename = instance._meta.model_name
            with self.subTest(namespace):
                user = UserFactory.create(is_staff=True)
                assign_perm("enrolment.view_%s" % codename, user)
                assign_perm("enrolment.change_%s" % codename, user)
                with self.login(user):
                    if listed:
                        self.get_check_200("admin:enrolment:%s:list" % namespace)
                    self.get_check_200(
                        "admin:enrolment:%s:edit" % namespace,
                        pk=instance.pk,
                        **parent,
                    )

    def test_change_permission_does_not_allow_assessment_delete(self):
        user = UserFactory.create(is_staff=True)
        assign_perm("enrolment.change_assessment", user)
        with self.login(user):
            self.post(
                "admin:enrolment:assessment:delete",
                pk=self.assessment.pk,
                **self.class_kwargs,
            )
            self.response_403()
        self.assertTrue(Assessment.objects.filter(pk=self.assessment.pk).exists())


class NestingTests(PermissionDataMixin, test_plus.TestCase):
    """
    A child asked for under a parent it does not belong to is not found, on
    each of the views that fetch it, and is left as it was.
    """

    def assertNotFoundUnder(self, namespace, instance, **parent):
        for view, method in (("edit", "get"), ("delete", "post"), ("perms", "get")):
            with self.subTest(namespace, view=view, **parent):
                name = "admin:enrolment:%s:%s" % (namespace, view)
                self.request(method, name, pk=instance.pk, **parent)
                self.response_404()
        self.assertTrue(type(instance).objects.filter(pk=instance.pk).exists())

    def test_class_group_under_the_other_year(self):
        with self.login(self.superuser):
            self.assertNotFoundUnder(
                "classgroup", self.group, year_id=self.other_year.pk
            )

    def test_enrolment_under_the_other_class(self):
        with self.login(self.superuser):
            self.assertNotFoundUnder(
                "enrolment",
                self.enrolment,
                year_id=self.other_year.pk,
                class_group_id=self.other_group.pk,
            )
            self.assertNotFoundUnder(
                "enrolment",
                self.enrolment,
                year_id=self.year.pk,
                class_group_id=self.other_group.pk,
            )

    def test_attendance_under_the_other_enrolment(self):
        with self.login(self.superuser):
            self.assertNotFoundUnder(
                "attendancerecord",
                self.attendance,
                year_id=self.other_year.pk,
                class_group_id=self.other_group.pk,
                enrolment_id=self.other_enrolment.pk,
            )

    def test_report_card_under_the_other_enrolment(self):
        with self.login(self.superuser):
            self.assertNotFoundUnder(
                "reportcard",
                self.report_card,
                year_id=self.other_year.pk,
                class_group_id=self.other_group.pk,
                enrolment_id=self.other_enrolment.pk,
            )

    def test_assessment_under_the_other_class(self):
        with self.login(self.superuser):
            self.assertNotFoundUnder(
                "assessment",
                self.assessment,
                year_id=self.other_year.pk,
                class_group_id=self.other_group.pk,
            )
        self.assertTrue(Score.objects.filter(pk=self.score.pk).exists())

    def test_add_under_a_class_of_the_other_year(self):
        with self.login(self.superuser):
            for namespace in ("enrolment", "assessment"):
                with self.subTest(namespace):
                    self.get(
                        "admin:enrolment:%s:add" % namespace,
                        year_id=self.year.pk,
                        class_group_id=self.other_group.pk,
                    )
                    self.response_404()


class YearSetupTests(EnrolmentDataMixin, test_plus.TestCase):
    def test_year_shows_class_without_teacher(self):
        bare = ClassGroup.objects.create(year=self.year, grade=self.grade, title="2W")
        with self.login(self.superuser):
            self.get("admin:enrolment:schoolyear:edit", pk=self.year.pk)
            self.response_200()
        self.assertResponseContains(
            '<p class="setup-detail"><span class="visually-hidden">Still to do:'
            "</span> %s has no teacher</p>" % bare
        )
        self.assertEqual(self.context["setup"].next_step.url, bare.urls["edit"])

    def test_class_shows_year_progress(self):
        with self.login(self.superuser):
            self.get(
                "admin:enrolment:classgroup:edit",
                year_id=self.year.pk,
                pk=self.group.pk,
            )
            self.response_200()
        setup = self.context["setup"]
        self.assertFalse(setup.here)
        self.assertResponseContains(
            '<a href="%s#setup-tab"><strong>School year set-up</strong> '
            "%d of %d done</a>" % (self.year.urls["edit"], setup.done, setup.total)
        )

    def test_report_card_shows_year_progress(self):
        with self.login(self.superuser):
            self.get_check_200(
                "admin:enrolment:reportcard:edit",
                pk=self.report_card.pk,
                **self.enrolment_kwargs,
            )
        setup = self.context["setup"]
        self.assertResponseContains(
            '<a href="%s#setup-tab"><strong>School year set-up</strong> '
            "%d of %d done</a>" % (self.year.urls["edit"], setup.done, setup.total)
        )
