from django.core.exceptions import ValidationError
from django.db import models

from touchtechnology.admin.mixins import AdminUrlMixin


class EnrolmentModel(AdminUrlMixin, models.Model):
    """Abstract base providing admin URL helpers for the enrolment models."""

    class Meta:
        abstract = True

    def _get_admin_namespace(self):
        return "admin:enrolment:%s" % self._meta.model_name

    def _get_url_args(self):
        return (self.pk,)


class SchoolYear(EnrolmentModel):
    title = models.CharField(max_length=4, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ("-start_date",)

    def __str__(self):
        return self.title


class Grade(EnrolmentModel):
    title = models.CharField(max_length=20, unique=True)
    ordinal = models.PositiveSmallIntegerField(unique=True)

    class Meta:
        ordering = ("ordinal",)

    def __str__(self):
        return self.title


class Teacher(EnrolmentModel):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(blank=True)

    class Meta:
        ordering = ("last_name", "first_name")

    def __str__(self):
        return "%s %s" % (self.first_name, self.last_name)


class ClassGroup(EnrolmentModel):
    year = models.ForeignKey(
        SchoolYear, on_delete=models.CASCADE, related_name="classes"
    )
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, related_name="classes")
    title = models.CharField(max_length=10)
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="classes",
    )

    class Meta:
        ordering = ("year", "grade", "title")
        constraints = [
            models.UniqueConstraint(
                fields=("year", "title"), name="unique_class_title_per_year"
            ),
        ]

    def __str__(self):
        return "%s (%s)" % (self.title, self.year)

    def _get_url_args(self):
        return (self.year_id, self.pk)


class Student(EnrolmentModel):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    date_of_birth = models.DateField()
    guardian_name = models.CharField(max_length=100)
    guardian_phone = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ("last_name", "first_name")

    def __str__(self):
        return "%s %s" % (self.first_name, self.last_name)


class Enrolment(EnrolmentModel):
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="enrolments"
    )
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="enrolments"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("student", "class_group"), name="unique_student_per_class"
            ),
        ]

    def __str__(self):
        return "%s in %s" % (self.student, self.class_group)

    def _get_url_args(self):
        return (self.class_group.year_id, self.class_group_id, self.pk)


class AttendanceRecord(EnrolmentModel):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    STATUS_CHOICES = [
        (PRESENT, "Present"),
        (ABSENT, "Absent"),
        (LATE, "Late"),
    ]

    enrolment = models.ForeignKey(
        Enrolment, on_delete=models.CASCADE, related_name="attendance"
    )
    date = models.DateField()
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default=PRESENT)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ("-date",)
        constraints = [
            models.UniqueConstraint(
                fields=("enrolment", "date"), name="unique_attendance_per_day"
            ),
        ]

    def __str__(self):
        return "%s: %s" % (self.date, self.status)

    def _get_url_args(self):
        return (
            self.enrolment.class_group.year_id,
            self.enrolment.class_group_id,
            self.enrolment_id,
            self.pk,
        )


class Assessment(EnrolmentModel):
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="assessments"
    )
    title = models.CharField(max_length=100)
    date = models.DateField()
    maximum_mark = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ("-date",)

    def __str__(self):
        return self.title

    def _get_url_args(self):
        return (self.class_group.year_id, self.class_group_id, self.pk)


class Score(models.Model):
    """
    A mark for one enrolled student on one assessment. Scores have no admin
    URLs of their own: they are edited as rows of the assessment.
    """

    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="scores"
    )
    enrolment = models.ForeignKey(
        Enrolment, on_delete=models.CASCADE, related_name="scores"
    )
    mark = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("assessment", "enrolment"), name="unique_score_per_assessment"
            ),
        ]

    def __str__(self):
        return "%s/%s" % (self.mark, self.assessment.maximum_mark)

    def clean(self):
        super().clean()
        if (
            self.assessment_id
            and self.mark is not None
            and self.mark > self.assessment.maximum_mark
        ):
            raise ValidationError(
                {
                    "mark": "The mark cannot be more than the maximum of %s."
                    % self.assessment.maximum_mark
                }
            )


class ReportCard(EnrolmentModel):
    TERM_CHOICES = [(term, "Term %d" % term) for term in range(1, 5)]
    BEGINNING = "beginning"
    DEVELOPING = "developing"
    SECURE = "secure"
    EXTENDING = "extending"
    RATING_CHOICES = [
        (BEGINNING, "Beginning"),
        (DEVELOPING, "Developing"),
        (SECURE, "Secure"),
        (EXTENDING, "Extending"),
    ]

    enrolment = models.ForeignKey(
        Enrolment, on_delete=models.CASCADE, related_name="report_cards"
    )
    term = models.PositiveSmallIntegerField(choices=TERM_CHOICES)
    literacy = models.CharField(
        max_length=10, choices=RATING_CHOICES, default=DEVELOPING
    )
    numeracy = models.CharField(
        max_length=10, choices=RATING_CHOICES, default=DEVELOPING
    )
    inquiry = models.CharField(
        max_length=10, choices=RATING_CHOICES, default=DEVELOPING
    )
    wellbeing = models.CharField(
        max_length=10, choices=RATING_CHOICES, default=DEVELOPING
    )
    general_comment = models.TextField(blank=True)

    class Meta:
        ordering = ("term",)
        constraints = [
            models.UniqueConstraint(
                fields=("enrolment", "term"), name="unique_report_card_per_term"
            ),
        ]

    def __str__(self):
        return "Term %s" % self.term

    def _get_url_args(self):
        return (
            self.enrolment.class_group.year_id,
            self.enrolment.class_group_id,
            self.enrolment_id,
            self.pk,
        )
