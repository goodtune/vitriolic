from django.core.exceptions import ValidationError
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
from modelforms.forms import ModelForm

from touchtechnology.common.forms.mixins import BootstrapFormControlMixin


class ParentUniqueMixin:
    """
    Check a uniqueness constraint that involves the parent foreign key.

    The admin views set the parent on the instance and leave the field out of
    the form. A ModelForm skips the unique checks that involve excluded fields,
    and the ``modelforms`` one reports the clash against a single field with
    different wording, so without this the clash is not a plain form error.
    Subclasses name the fields of the constraint, in the order the model
    declares them, as ``unique_check``, and the parent among them as
    ``parent_field``.

    The check is made before the base ``clean()`` so that it is the error
    that is reported.
    """

    parent_field = None
    unique_check = ()

    def clean(self):
        model = self._meta.model
        lookup = {self.parent_field: getattr(self.instance, self.parent_field + "_id")}
        for name in self.unique_check:
            if name != self.parent_field:
                lookup[name] = self.cleaned_data.get(name)
        if all(value is not None for value in lookup.values()):
            duplicates = model._default_manager.filter(**lookup)
            if self.instance.pk is not None:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise self.instance.unique_error_message(model, self.unique_check)
        return super().clean()


class SchoolYearForm(BootstrapFormControlMixin, ModelForm):
    class Meta:
        model = SchoolYear
        fields = ("title", "start_date", "end_date")


class GradeForm(BootstrapFormControlMixin, ModelForm):
    class Meta:
        model = Grade
        fields = ("title", "ordinal")


class TeacherForm(BootstrapFormControlMixin, ModelForm):
    class Meta:
        model = Teacher
        fields = ("first_name", "last_name", "email")


class StudentForm(BootstrapFormControlMixin, ModelForm):
    class Meta:
        model = Student
        fields = (
            "first_name",
            "last_name",
            "date_of_birth",
            "guardian_name",
            "guardian_phone",
        )


class ClassGroupForm(ParentUniqueMixin, BootstrapFormControlMixin, ModelForm):
    parent_field = "year"
    unique_check = ("year", "title")

    class Meta:
        model = ClassGroup
        exclude = ("year",)


class EnrolmentForm(ParentUniqueMixin, BootstrapFormControlMixin, ModelForm):
    parent_field = "class_group"
    unique_check = ("student", "class_group")

    class Meta:
        model = Enrolment
        exclude = ("class_group",)

    def clean(self):
        super().clean()
        student = self.cleaned_data.get("student")
        if student is not None:
            elsewhere = student.enrolments.filter(
                class_group__year_id=self.instance.class_group.year_id
            ).exclude(class_group_id=self.instance.class_group_id)
            if self.instance.pk is not None:
                elsewhere = elsewhere.exclude(pk=self.instance.pk)
            existing = elsewhere.select_related("class_group__year").first()
            if existing is not None:
                raise ValidationError(
                    "%(student)s is already enrolled in %(class_group)s this year.",
                    params={"student": student, "class_group": existing.class_group},
                )


class AttendanceRecordForm(ParentUniqueMixin, BootstrapFormControlMixin, ModelForm):
    parent_field = "enrolment"
    unique_check = ("enrolment", "date")

    class Meta:
        model = AttendanceRecord
        exclude = ("enrolment",)


class ReportCardForm(ParentUniqueMixin, BootstrapFormControlMixin, ModelForm):
    parent_field = "enrolment"
    unique_check = ("enrolment", "term")

    class Meta:
        model = ReportCard
        exclude = ("enrolment",)


class AssessmentForm(BootstrapFormControlMixin, ModelForm):
    class Meta:
        model = Assessment
        exclude = ("class_group",)


class ScoreForm(BootstrapFormControlMixin, ModelForm):
    """
    A row of an assessment. The model's ``clean()`` rejects a mark above the
    assessment's maximum and a student from another class; the inline formset
    sets the assessment on the instance before the form is validated.

    The ``enrolments`` of the assessment's class are passed in by the view, so
    the choices are that class's students, labelled with their names.
    """

    class Meta:
        model = Score
        fields = ("enrolment", "mark")

    def __init__(self, *args, enrolments, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["enrolment"]
        field.queryset = enrolments
        field.label_from_instance = lambda enrolment: str(enrolment.student)
