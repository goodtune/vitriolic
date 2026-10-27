from django.core.management.base import BaseCommand, CommandError
from enrolment.seeding import MAX_STUDENTS, seed


class Command(BaseCommand):
    help = "Seed the enrolment demonstration app with invented data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--students",
            type=int,
            default=300,
            help=(
                f"The number of students to create, from 1 to {MAX_STUDENTS} "
                "(default: 300)."
            ),
        )

    def handle(self, *args, **options):
        students = options["students"]
        if not 1 <= students <= MAX_STUDENTS:
            raise CommandError(
                f"--students must be from 1 to {MAX_STUDENTS}, not {students}."
            )
        counts = seed(students=students)
        for name, count in counts.items():
            self.stdout.write(f"{name}: {count}")
