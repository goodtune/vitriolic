from django.core.management.base import BaseCommand
from enrolment.seeding import seed


class Command(BaseCommand):
    help = "Seed the enrolment demonstration app with invented data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--students",
            type=int,
            default=300,
            help="The number of students to create (default: 300).",
        )

    def handle(self, *args, **options):
        counts = seed(students=options["students"])
        for name, count in counts.items():
            self.stdout.write("%s: %d" % (name, count))
