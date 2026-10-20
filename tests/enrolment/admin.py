from django.forms.models import inlineformset_factory
from django.shortcuts import get_object_or_404
from django.urls import include, path
from django.utils.translation import gettext_lazy as _
from enrolment.forms import (
    AssessmentForm,
    AttendanceRecordForm,
    ClassGroupForm,
    EnrolmentForm,
    GradeForm,
    ReportCardForm,
    SchoolYearForm,
    ScoreForm,
    StudentForm,
    TeacherForm,
)
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
from guardian.utils import get_40x_or_None

from touchtechnology.admin.base import AdminComponent
from touchtechnology.common.decorators import staff_login_required_m
from touchtechnology.common.utils import get_perms_for_model

YEAR = "year/<int:year_id>/"
CLASS = YEAR + "class/"
CLASS_ITEM = CLASS + "<int:class_group_id>/"
ENROLMENT = CLASS_ITEM + "enrolment/"
ENROLMENT_ITEM = ENROLMENT + "<int:enrolment_id>/"


class EnrolmentAdminComponent(AdminComponent):
    """
    School year, grade, class, student and enrolment records, with the
    attendance, assessments and report cards that hang off them.
    """

    verbose_name = _("Enrolment")
    unprotected = False

    def __init__(self, app, name="enrolment", app_name="enrolment"):
        super().__init__(app, name, app_name)

    def _include(self, name, edit, delete, perms, list_=None):
        """
        The list, add, edit, delete and perms views of one model, under a
        namespace of the model's name. Each model is also its own app_name:
        sharing one with the component would make a reversal made while on
        one model's page resolve the component's own namespace to that model.
        """
        patterns = []
        if list_ is not None:
            patterns.append(path("", list_, name="list"))
        patterns.extend(
            [
                path("add/", edit, name="add"),
                path("<int:pk>/", edit, name="edit"),
                path("<int:pk>/delete/", delete, name="delete"),
                path("<int:pk>/perms/", perms, name="perms"),
            ]
        )
        return include((patterns, name), namespace=name)

    def get_urls(self):
        return [
            path("", self.index, name="index"),
            path(
                "year/",
                self._include(
                    "schoolyear",
                    self.edit_schoolyear,
                    self.delete_schoolyear,
                    self.perms_schoolyear,
                    self.list_schoolyears,
                ),
            ),
            path(
                "grade/",
                self._include(
                    "grade",
                    self.edit_grade,
                    self.delete_grade,
                    self.perms_grade,
                    self.list_grades,
                ),
            ),
            path(
                "teacher/",
                self._include(
                    "teacher",
                    self.edit_teacher,
                    self.delete_teacher,
                    self.perms_teacher,
                    self.list_teachers,
                ),
            ),
            path(
                "student/",
                self._include(
                    "student",
                    self.edit_student,
                    self.delete_student,
                    self.perms_student,
                    self.list_students,
                ),
            ),
            path(
                CLASS,
                self._include(
                    "classgroup",
                    self.edit_classgroup,
                    self.delete_classgroup,
                    self.perms_classgroup,
                ),
            ),
            path(
                ENROLMENT,
                self._include(
                    "enrolment",
                    self.edit_enrolment,
                    self.delete_enrolment,
                    self.perms_enrolment,
                ),
            ),
            path(
                ENROLMENT_ITEM + "attendance/",
                self._include(
                    "attendancerecord",
                    self.edit_attendancerecord,
                    self.delete_attendancerecord,
                    self.perms_attendancerecord,
                ),
            ),
            path(
                ENROLMENT_ITEM + "report/",
                self._include(
                    "reportcard",
                    self.edit_reportcard,
                    self.delete_reportcard,
                    self.perms_reportcard,
                ),
            ),
            path(
                CLASS_ITEM + "assessment/",
                self._include(
                    "assessment",
                    self.edit_assessment,
                    self.delete_assessment,
                    self.perms_assessment,
                ),
            ),
        ]

    def dropdowns(self):
        return (
            (_("Years"), self.reverse("schoolyear:list"), "calendar"),
            (_("Grades"), self.reverse("grade:list"), "sort-numeric-asc"),
            (_("Students"), self.reverse("student:list"), "graduation-cap"),
            (_("Teachers"), self.reverse("teacher:list"), "user"),
        )

    @staticmethod
    def _tab(url, tab):
        "The URL of a parent's edit page, opened on one of its related tabs."
        return "%s#%s-tab" % (url, tab)

    def _class_group(self, year_id, class_group_id):
        return get_object_or_404(ClassGroup, year_id=year_id, pk=class_group_id)

    def _enrolment(self, year_id, class_group_id, enrolment_id):
        return get_object_or_404(
            Enrolment,
            class_group__year_id=year_id,
            class_group_id=class_group_id,
            pk=enrolment_id,
        )

    @staff_login_required_m
    def index(self, request, **kwargs):
        return self.redirect(self.reverse("schoolyear:list"))

    # School years

    @staff_login_required_m
    def list_schoolyears(self, request, **kwargs):
        return self.generic_list(
            request,
            SchoolYear,
            paginate_by=25,
            permission_required=True,
            extra_context=kwargs,
        )

    @staff_login_required_m
    def edit_schoolyear(self, request, pk=None, **kwargs):
        # The class groups tab adds a class to the school year on the page, so
        # it is told which year that is; the add page has no year yet.
        year = None if pk is None else get_object_or_404(SchoolYear, pk=pk)
        return self.generic_edit(
            request,
            SchoolYear,
            instance=year,
            form_class=SchoolYearForm,
            permission_required=True,
            post_save_redirect=self.redirect(self.reverse("schoolyear:list")),
            related=("classes",),
            extra_context={"year": year, **kwargs},
        )

    @staff_login_required_m
    def delete_schoolyear(self, request, pk, **kwargs):
        return self.generic_delete(
            request,
            SchoolYear,
            pk=pk,
            permission_required=True,
            post_delete_redirect=self.redirect(self.reverse("schoolyear:list")),
        )

    @staff_login_required_m
    def perms_schoolyear(self, request, pk, **kwargs):
        return self.generic_permissions(
            request,
            SchoolYear,
            pk=pk,
            post_save_redirect=self.redirect(
                self.reverse("schoolyear:edit", kwargs={"pk": pk})
            ),
            **kwargs,
        )

    # Grades

    @staff_login_required_m
    def list_grades(self, request, **kwargs):
        return self.generic_list(
            request,
            Grade,
            paginate_by=25,
            permission_required=True,
            extra_context=kwargs,
        )

    @staff_login_required_m
    def edit_grade(self, request, pk=None, **kwargs):
        return self.generic_edit(
            request,
            Grade,
            pk=pk,
            form_class=GradeForm,
            permission_required=True,
            post_save_redirect=self.redirect(self.reverse("grade:list")),
            extra_context=kwargs,
        )

    @staff_login_required_m
    def delete_grade(self, request, pk, **kwargs):
        return self.generic_delete(
            request,
            Grade,
            pk=pk,
            permission_required=True,
            post_delete_redirect=self.redirect(self.reverse("grade:list")),
        )

    @staff_login_required_m
    def perms_grade(self, request, pk, **kwargs):
        return self.generic_permissions(
            request,
            Grade,
            pk=pk,
            post_save_redirect=self.redirect(
                self.reverse("grade:edit", kwargs={"pk": pk})
            ),
            **kwargs,
        )

    # Teachers

    @staff_login_required_m
    def list_teachers(self, request, **kwargs):
        return self.generic_list(
            request,
            Teacher,
            paginate_by=25,
            permission_required=True,
            extra_context=kwargs,
        )

    @staff_login_required_m
    def edit_teacher(self, request, pk=None, **kwargs):
        return self.generic_edit(
            request,
            Teacher,
            pk=pk,
            form_class=TeacherForm,
            permission_required=True,
            post_save_redirect=self.redirect(self.reverse("teacher:list")),
            extra_context=kwargs,
        )

    @staff_login_required_m
    def delete_teacher(self, request, pk, **kwargs):
        return self.generic_delete(
            request,
            Teacher,
            pk=pk,
            permission_required=True,
            post_delete_redirect=self.redirect(self.reverse("teacher:list")),
        )

    @staff_login_required_m
    def perms_teacher(self, request, pk, **kwargs):
        return self.generic_permissions(
            request,
            Teacher,
            pk=pk,
            post_save_redirect=self.redirect(
                self.reverse("teacher:edit", kwargs={"pk": pk})
            ),
            **kwargs,
        )

    # Students

    @staff_login_required_m
    def list_students(self, request, **kwargs):
        return self.generic_list(
            request,
            Student,
            paginate_by=25,
            permission_required=True,
            search=("first_name", "last_name"),
            extra_context=kwargs,
        )

    @staff_login_required_m
    def edit_student(self, request, pk=None, **kwargs):
        return self.generic_edit(
            request,
            Student,
            pk=pk,
            form_class=StudentForm,
            permission_required=True,
            post_save_redirect=self.redirect(self.reverse("student:list")),
            related=("enrolments",),
            extra_context=kwargs,
        )

    @staff_login_required_m
    def delete_student(self, request, pk, **kwargs):
        return self.generic_delete(
            request,
            Student,
            pk=pk,
            permission_required=True,
            post_delete_redirect=self.redirect(self.reverse("student:list")),
        )

    @staff_login_required_m
    def perms_student(self, request, pk, **kwargs):
        return self.generic_permissions(
            request,
            Student,
            pk=pk,
            post_save_redirect=self.redirect(
                self.reverse("student:edit", kwargs={"pk": pk})
            ),
            **kwargs,
        )

    # Classes, within a school year

    @staff_login_required_m
    def edit_classgroup(self, request, year_id, pk=None, **kwargs):
        year = get_object_or_404(SchoolYear, pk=year_id)
        if pk is None:
            instance = ClassGroup(year=year)
        else:
            instance = get_object_or_404(year.classes, pk=pk)
        return self.generic_edit(
            request,
            ClassGroup,
            instance=instance,
            form_class=ClassGroupForm,
            permission_required=True,
            post_save_redirect=self.redirect(self._tab(year.urls["edit"], "classes")),
            related=("enrolments", "assessments"),
            extra_context={"year": year, **kwargs},
        )

    @staff_login_required_m
    def delete_classgroup(self, request, year_id, pk, **kwargs):
        year = get_object_or_404(SchoolYear, pk=year_id)
        return self.generic_delete(
            request,
            year.classes,
            pk=pk,
            permission_required=True,
            post_delete_redirect=self.redirect(self._tab(year.urls["edit"], "classes")),
        )

    @staff_login_required_m
    def perms_classgroup(self, request, year_id, pk, **kwargs):
        year = get_object_or_404(SchoolYear, pk=year_id)
        instance = get_object_or_404(year.classes, pk=pk)
        return self.generic_permissions(
            request,
            ClassGroup,
            instance=instance,
            post_save_redirect=self.redirect(instance.urls["edit"]),
            **kwargs,
        )

    # Enrolments, within a class

    @staff_login_required_m
    def edit_enrolment(self, request, year_id, class_group_id, pk=None, **kwargs):
        class_group = self._class_group(year_id, class_group_id)
        if pk is None:
            instance = Enrolment(class_group=class_group)
        else:
            instance = get_object_or_404(class_group.enrolments, pk=pk)
        return self.generic_edit(
            request,
            Enrolment,
            instance=instance,
            form_class=EnrolmentForm,
            permission_required=True,
            post_save_redirect=self.redirect(
                self._tab(class_group.urls["edit"], "enrolments")
            ),
            related=("attendance", "report_cards"),
            extra_context={
                "year": class_group.year,
                "class_group": class_group,
                **kwargs,
            },
        )

    @staff_login_required_m
    def delete_enrolment(self, request, year_id, class_group_id, pk, **kwargs):
        class_group = self._class_group(year_id, class_group_id)
        return self.generic_delete(
            request,
            class_group.enrolments,
            pk=pk,
            permission_required=True,
            post_delete_redirect=self.redirect(
                self._tab(class_group.urls["edit"], "enrolments")
            ),
        )

    @staff_login_required_m
    def perms_enrolment(self, request, year_id, class_group_id, pk, **kwargs):
        class_group = self._class_group(year_id, class_group_id)
        instance = get_object_or_404(class_group.enrolments, pk=pk)
        return self.generic_permissions(
            request,
            Enrolment,
            instance=instance,
            post_save_redirect=self.redirect(instance.urls["edit"]),
            **kwargs,
        )

    # Attendance, within an enrolment

    @staff_login_required_m
    def edit_attendancerecord(
        self, request, year_id, class_group_id, enrolment_id, pk=None, **kwargs
    ):
        enrolment = self._enrolment(year_id, class_group_id, enrolment_id)
        if pk is None:
            instance = AttendanceRecord(enrolment=enrolment)
        else:
            instance = get_object_or_404(enrolment.attendance, pk=pk)
        return self.generic_edit(
            request,
            AttendanceRecord,
            instance=instance,
            form_class=AttendanceRecordForm,
            permission_required=True,
            post_save_redirect=self.redirect(
                self._tab(enrolment.urls["edit"], "attendance")
            ),
            extra_context={"enrolment": enrolment, **kwargs},
        )

    @staff_login_required_m
    def delete_attendancerecord(
        self, request, year_id, class_group_id, enrolment_id, pk, **kwargs
    ):
        enrolment = self._enrolment(year_id, class_group_id, enrolment_id)
        return self.generic_delete(
            request,
            enrolment.attendance,
            pk=pk,
            permission_required=True,
            post_delete_redirect=self.redirect(
                self._tab(enrolment.urls["edit"], "attendance")
            ),
        )

    @staff_login_required_m
    def perms_attendancerecord(
        self, request, year_id, class_group_id, enrolment_id, pk, **kwargs
    ):
        enrolment = self._enrolment(year_id, class_group_id, enrolment_id)
        instance = get_object_or_404(enrolment.attendance, pk=pk)
        return self.generic_permissions(
            request,
            AttendanceRecord,
            instance=instance,
            post_save_redirect=self.redirect(instance.urls["edit"]),
            **kwargs,
        )

    # Report cards, within an enrolment

    @staff_login_required_m
    def edit_reportcard(
        self, request, year_id, class_group_id, enrolment_id, pk=None, **kwargs
    ):
        enrolment = self._enrolment(year_id, class_group_id, enrolment_id)
        if pk is None:
            instance = ReportCard(enrolment=enrolment)
        else:
            instance = get_object_or_404(enrolment.report_cards, pk=pk)
        return self.generic_edit(
            request,
            ReportCard,
            instance=instance,
            form_class=ReportCardForm,
            permission_required=True,
            post_save_redirect=self.redirect(
                self._tab(enrolment.urls["edit"], "report_cards")
            ),
            extra_context={"enrolment": enrolment, **kwargs},
        )

    @staff_login_required_m
    def delete_reportcard(
        self, request, year_id, class_group_id, enrolment_id, pk, **kwargs
    ):
        enrolment = self._enrolment(year_id, class_group_id, enrolment_id)
        return self.generic_delete(
            request,
            enrolment.report_cards,
            pk=pk,
            permission_required=True,
            post_delete_redirect=self.redirect(
                self._tab(enrolment.urls["edit"], "report_cards")
            ),
        )

    @staff_login_required_m
    def perms_reportcard(
        self, request, year_id, class_group_id, enrolment_id, pk, **kwargs
    ):
        enrolment = self._enrolment(year_id, class_group_id, enrolment_id)
        instance = get_object_or_404(enrolment.report_cards, pk=pk)
        return self.generic_permissions(
            request,
            ReportCard,
            instance=instance,
            post_save_redirect=self.redirect(instance.urls["edit"]),
            **kwargs,
        )

    # Assessments, within a class; the scores are rows of the assessment

    @staff_login_required_m
    def edit_assessment(self, request, year_id, class_group_id, pk=None, **kwargs):
        class_group = self._class_group(year_id, class_group_id)
        post_save_redirect = self.redirect(
            self._tab(class_group.urls["edit"], "assessments")
        )
        extra_context = {
            "year": class_group.year,
            "class_group": class_group,
            **kwargs,
        }

        if pk is None:
            return self.generic_edit(
                request,
                Assessment,
                instance=Assessment(class_group=class_group),
                form_class=AssessmentForm,
                permission_required=True,
                post_save_redirect=post_save_redirect,
                extra_context=extra_context,
            )

        instance = get_object_or_404(class_group.assessments, pk=pk)

        # generic_edit_related has no permission_required, so apply the same
        # object permission check generic_edit makes.
        has_permission = get_40x_or_None(
            request,
            get_perms_for_model(Assessment, change=True),
            obj=instance,
            return_403=not request.user.is_anonymous,
            accept_global_perms=True,
        )
        if has_permission is not None:
            return has_permission

        return self.generic_edit_related(
            request,
            Assessment,
            Score,
            instance=instance,
            form_class=AssessmentForm,
            formset_class=inlineformset_factory(
                Assessment, Score, form=ScoreForm, extra=1
            ),
            formset_kwargs={
                "form_kwargs": {
                    "enrolments": class_group.enrolments.select_related("student")
                }
            },
            post_save_redirect=post_save_redirect,
            extra_context=extra_context,
        )

    @staff_login_required_m
    def delete_assessment(self, request, year_id, class_group_id, pk, **kwargs):
        class_group = self._class_group(year_id, class_group_id)
        return self.generic_delete(
            request,
            class_group.assessments,
            pk=pk,
            permission_required=True,
            post_delete_redirect=self.redirect(
                self._tab(class_group.urls["edit"], "assessments")
            ),
        )

    @staff_login_required_m
    def perms_assessment(self, request, year_id, class_group_id, pk, **kwargs):
        class_group = self._class_group(year_id, class_group_id)
        instance = get_object_or_404(class_group.assessments, pk=pk)
        return self.generic_permissions(
            request,
            Assessment,
            instance=instance,
            post_save_redirect=self.redirect(instance.urls["edit"]),
            **kwargs,
        )
