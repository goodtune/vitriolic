"""
Seed the enrolment demonstration app with two school years of invented data.

Every name, phrase and phone number below is made up. The seed is
deterministic (the same arguments always produce the same rows) and idempotent
(running it again changes nothing), so it is safe to call repeatedly.
"""

import datetime
import itertools
import random

from django.db import transaction
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

FIRST_NAMES = [
    "Alba", "Bram", "Calla", "Dara", "Elio", "Farah", "Gideon", "Hana",
    "Idris", "Jonty", "Kasia", "Lior", "Maeve", "Nico", "Orla", "Pelle",
    "Quinn", "Rosalind", "Soren", "Talia", "Ulrich", "Vera", "Wren", "Xanthe",
    "Yusuf", "Zora", "Ansel", "Briony", "Cormac", "Delphine",
]  # fmt: skip

LAST_NAMES = [
    "Ashdown", "Brannigan", "Castellan", "Dunmore", "Eastwick", "Fairweather",
    "Garrity", "Halloran", "Ingleby", "Jessamy", "Kettering", "Lindqvist",
    "Marchetti", "Northcott", "Okafor", "Pemberton", "Quillfeather", "Rasmussen",
    "Sandoval", "Tregarthen", "Underhill", "Varga", "Whitlock", "Yarrow",
    "Zielinski", "Abernethy", "Blackthorn", "Carraway", "Devereux", "Ellerby",
]  # fmt: skip

TEACHER_COUNT = 16
GRADES = [("Kindergarten", 0)] + [("Year %d" % n, n) for n in range(1, 7)]
YEARS = [
    ("2026", datetime.date(2026, 1, 27), datetime.date(2026, 12, 11)),
    ("2027", datetime.date(2027, 1, 27), datetime.date(2027, 12, 10)),
]
ASSESSMENTS = [
    ("Term 1 Reading", datetime.date(2026, 3, 10), 20),
    ("Term 1 Number", datetime.date(2026, 3, 24), 30),
]
ATTENDANCE_START = datetime.date(2026, 2, 2)
ATTENDANCE_DAYS = 28
ABSENCE_NOTES = [
    "Sick at home.",
    "Medical appointment.",
    "Family trip.",
    "Away with a cold.",
    "Dentist visit.",
]
LITERACY = [
    "reads aloud with growing confidence",
    "is building a wider vocabulary every week",
    "writes clear sentences with careful punctuation",
    "enjoys sharing stories with the group",
    "needs a little more practice with spelling patterns",
    "chooses challenging books to read independently",
]
NUMERACY = [
    "is secure with number facts to twenty",
    "explains how they solved a problem",
    "is learning to read the time to the quarter hour",
    "works well with measurement tasks",
    "needs more practice with place value",
    "enjoys number games and patterns",
]
INQUIRY = [
    "asks thoughtful questions during science lessons",
    "carried out the garden project with care",
    "works well with a partner on research tasks",
    "shows curiosity about how things work",
    "presents findings in an organised way",
    "is learning to record observations accurately",
]
WELLBEING = [
    "is a kind and helpful member of the class",
    "joins in playground games cheerfully",
    "is learning to manage frustration calmly",
    "greets everyone warmly each morning",
    "shows good sportsmanship in team games",
    "is becoming more confident in speaking up",
]
GENERAL = [
    "Has made a strong start to the year.",
    "Is a pleasure to have in the class.",
    "Should be proud of the effort shown this term.",
    "Settled quickly into the routines of the term.",
    "Shows steady progress and a positive attitude.",
    "Keep up the good work next term.",
]


def _comment(rng, first_name, phrases):
    """Compose a two-sentence comment from two distinct phrases."""
    first, second = rng.sample(phrases, 2)
    return "%s %s. %s also %s." % (first_name, first, first_name, second)


def _weekdays():
    for offset in range(ATTENDANCE_DAYS):
        day = ATTENDANCE_START + datetime.timedelta(days=offset)
        if day.weekday() < 5:
            yield day


def _class_title(grade, number):
    """K1, K2 for kindergarten, then 1A, 1B ... 6B for the school years."""
    if grade.ordinal == 0:
        return "K%d" % (number + 1)
    return "%d%s" % (grade.ordinal, "AB"[number])


def _seed_structure():
    years = {}
    for title, start, end in YEARS:
        years[title], _ = SchoolYear.objects.update_or_create(
            title=title, defaults={"start_date": start, "end_date": end}
        )

    grades = {}
    for title, ordinal in GRADES:
        grades[ordinal], _ = Grade.objects.update_or_create(
            ordinal=ordinal, defaults={"title": title}
        )

    teachers = []
    for index in range(TEACHER_COUNT):
        first = FIRST_NAMES[(index * 7) % len(FIRST_NAMES)]
        last = LAST_NAMES[(index * 11 + 3) % len(LAST_NAMES)]
        teacher, _ = Teacher.objects.update_or_create(
            first_name=first,
            last_name=last,
            defaults={"email": "%s.%s@school.example" % (first.lower(), last.lower())},
        )
        teachers.append(teacher)

    groups = {2026: {}, 2027: {}}
    teacher_cycle = itertools.cycle(teachers)
    for year_title, per_grade in (("2026", 2), ("2027", 1)):
        for _, ordinal in GRADES:
            grade = grades[ordinal]
            for number in range(per_grade):
                group, _ = ClassGroup.objects.update_or_create(
                    year=years[year_title],
                    title=_class_title(grade, number),
                    defaults={"grade": grade, "teacher": next(teacher_cycle)},
                )
                groups[int(year_title)].setdefault(ordinal, []).append(group)
    return grades, groups


def _seed_students(rng, students):
    combinations = list(itertools.product(FIRST_NAMES, LAST_NAMES))
    if students > len(combinations):
        raise ValueError("At most %d students can be seeded." % len(combinations))
    rng.shuffle(combinations)

    rows = []
    for index, (first, last) in enumerate(combinations[:students]):
        ordinal = index % len(GRADES)
        date_of_birth = datetime.date(
            2026 - 5 - ordinal, rng.randint(1, 12), rng.randint(1, 28)
        )
        student, _ = Student.objects.update_or_create(
            first_name=first,
            last_name=last,
            date_of_birth=date_of_birth,
            defaults={
                "guardian_name": "%s %s" % (rng.choice(FIRST_NAMES), last),
                "guardian_phone": "0491 570 1%02d" % rng.randint(0, 99),
            },
        )
        rows.append((student, ordinal, index // len(GRADES)))
    return rows


def _seed_enrolments(student_rows, groups):
    """Return the 2026 enrolments, adding the move up to 2027 on the way."""
    enrolments = []
    for student, ordinal, position in student_rows:
        current = groups[2026][ordinal]
        enrolment, _ = Enrolment.objects.get_or_create(
            student=student, class_group=current[position % len(current)]
        )
        enrolments.append(enrolment)
        if ordinal + 1 in groups[2027]:
            Enrolment.objects.get_or_create(
                student=student, class_group=groups[2027][ordinal + 1][0]
            )
    return enrolments


def _seed_attendance(rng, enrolments):
    records = []
    for enrolment in enrolments:
        for day in _weekdays():
            roll = rng.random()
            status, note = AttendanceRecord.PRESENT, ""
            if roll >= 0.97:
                status = AttendanceRecord.LATE
            elif roll >= 0.92:
                status = AttendanceRecord.ABSENT
                if rng.random() < 1 / 3:
                    note = rng.choice(ABSENCE_NOTES)
            records.append(
                AttendanceRecord(
                    enrolment=enrolment, date=day, status=status, note=note
                )
            )
    AttendanceRecord.objects.bulk_create(
        records, ignore_conflicts=True, batch_size=2000
    )


def _seed_assessments(rng, groups, enrolments):
    by_group = {}
    for enrolment in enrolments:
        by_group.setdefault(enrolment.class_group_id, []).append(enrolment)

    scores = []
    for grade_groups in groups[2026].values():
        for group in grade_groups:
            for title, date, maximum in ASSESSMENTS:
                assessment, _ = Assessment.objects.update_or_create(
                    class_group=group,
                    title=title,
                    defaults={"date": date, "maximum_mark": maximum},
                )
                for enrolment in by_group.get(group.pk, []):
                    mark = round(rng.gauss(0.7, 0.12) * maximum)
                    scores.append(
                        Score(
                            assessment=assessment,
                            enrolment=enrolment,
                            mark=max(0, min(maximum, mark)),
                        )
                    )
    Score.objects.bulk_create(scores, ignore_conflicts=True, batch_size=2000)


def _seed_report_cards(rng, enrolments):
    for enrolment in enrolments:
        name = enrolment.student.first_name
        ReportCard.objects.update_or_create(
            enrolment=enrolment,
            term=1,
            defaults={
                "literacy": _comment(rng, name, LITERACY),
                "numeracy": _comment(rng, name, NUMERACY),
                "inquiry": _comment(rng, name, INQUIRY),
                "wellbeing": _comment(rng, name, WELLBEING),
                "general_comment": rng.choice(GENERAL),
            },
        )


@transaction.atomic
def seed(students: int = 300, seed: int = 20261) -> dict[str, int]:
    """
    Create (or bring up to date) the demonstration data and return the number
    of rows in each seeded table, keyed by model name.
    """
    rng = random.Random(seed)

    _, groups = _seed_structure()
    student_rows = _seed_students(rng, students)
    enrolments = _seed_enrolments(student_rows, groups)
    _seed_attendance(rng, enrolments)
    _seed_assessments(rng, groups, enrolments)
    _seed_report_cards(rng, enrolments)

    return {
        model.__name__: model.objects.count()
        for model in (
            SchoolYear, Grade, Teacher, ClassGroup, Student, Enrolment,
            AttendanceRecord, Assessment, Score, ReportCard,
        )
    }  # fmt: skip
