# -*- coding: utf-8 -*-

"""
Django management command to test Ollama tournament generation.

Usage: python manage.py test_ollama
"""

from django.core.management.base import BaseCommand, CommandError

from tournamentcontrol.competition.ai.executor import build
from tournamentcontrol.competition.ai.ollama import OllamaProvider
from tournamentcontrol.competition.models import Season


class Command(BaseCommand):
    help = "Test Ollama tournament generation with the original GitHub issue prompt"

    def add_arguments(self, parser):
        parser.add_argument(
            "season_pk",
            type=int,
            help="Primary key of the Season to add the tournament to",
        )
        parser.add_argument(
            "--model",
            type=str,
            default="llama3.2",
            help="Ollama model to use (default: llama3.2)",
        )
        parser.add_argument(
            "--url",
            type=str,
            default="http://localhost:11434",
            help="Ollama API URL (default: http://localhost:11434)",
        )
        parser.add_argument(
            "--prompt",
            type=str,
            help="Custom prompt (default: use GitHub issue prompt)",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=60,
            help="Request timeout in seconds (default: 60)",
        )

    def handle(self, **options):
        # Use original GitHub issue prompt by default
        default_prompt = (
            "Build a competition for 19 Mixed Open teams. Must be completed in 5 days, "
            "max 3 matches per team per day, minimum 2 matches until elimination. "
            "Gold, Silver, Bronze medals for top teams, full 1-19 ranking for all teams."
        )

        prompt = options.get("prompt") or default_prompt
        model = options["model"]
        url = options["url"]
        timeout = options["timeout"]
        season_pk = options["season_pk"]

        # Get the season
        try:
            season = Season.objects.get(pk=season_pk)
        except Season.DoesNotExist:
            raise CommandError(f"Season with pk={season_pk} does not exist")

        self.stdout.write(self.style.SUCCESS("🤖 Testing Ollama Tournament Generation"))
        self.stdout.write(f"🏆 Season: {season.title} (pk={season.pk})")
        self.stdout.write(f"📝 Prompt: {prompt}")
        self.stdout.write("")

        # Initialize Ollama provider
        provider = OllamaProvider(base_url=url, model=model, timeout=timeout)

        # Check if Ollama is available
        if not provider.is_available():
            self.stdout.write(self.style.ERROR(f"❌ Ollama is not available at {url}"))
            self.stdout.write("   Make sure Ollama is running: `ollama serve`")
            self.stdout.write(f"   And you have model installed: `ollama pull {model}`")
            return

        self.stdout.write(self.style.SUCCESS("✅ Ollama is available"))
        self.stdout.write(f"🧠 Using model: {model}")
        self.stdout.write(f"⏱️  Timeout: {timeout}s")
        self.stdout.write("")

        # Show system prompt if verbosity >= 2
        if options["verbosity"] >= 2:
            self.stdout.write(self.style.WARNING("📋 System Prompt:"))
            self.stdout.write("")
            system_prompt = provider.get_system_prompt()

            # Add some color to the system prompt for readability
            colored_prompt = self._colorize_system_prompt(system_prompt)
            self.stdout.write(colored_prompt)
            self.stdout.write("")
            self.stdout.write("─" * 80)
            self.stdout.write("")

        # Generate tournament structure
        self.stdout.write("⏳ Generating tournament structure...")
        division_structure = provider.generate_tournament(prompt)

        if not division_structure:
            self.stdout.write(
                self.style.ERROR("❌ Failed to generate tournament structure")
            )
            return

        self.stdout.write(self.style.SUCCESS("✅ Tournament structure generated!"))
        self.stdout.write("")
        self.stdout.write("📋 Generated Structure:")
        self.stdout.write(f"Title: {division_structure.title}")
        self.stdout.write(f"Teams: {len(division_structure.teams)} teams")
        self.stdout.write(f"Stages: {len(division_structure.stages)} stages")
        self.stdout.write("")

        for i, stage in enumerate(division_structure.stages, 1):
            self.stdout.write(f"Stage {i}: {stage.title}")
            if stage.pools:
                self.stdout.write(f"  Pools: {len(stage.pools)}")
                for pool in stage.pools:
                    team_count = len(pool.teams) if pool.teams else "variable"
                    self.stdout.write(f"    - {pool.title}: {team_count} teams")
            else:
                self.stdout.write("  Direct knockout stage")
        self.stdout.write("")

        # Show generated JSON
        self.stdout.write("📄 Generated JSON:")
        self.stdout.write(division_structure.model_dump_json(indent=2))
        self.stdout.write("")

        # Test building actual tournament
        self.stdout.write("⏳ Building tournament in database...")
        try:
            division = build(season, division_structure)
            self.stdout.write(self.style.SUCCESS("✅ Tournament built successfully!"))
            self.stdout.write(
                f"📊 Created: {division.teams.count()} teams, {division.stages.count()} stages"
            )

            match_count = 0
            for stage in division.stages.all():
                stage_matches = stage.matches.count()
                match_count += stage_matches
                self.stdout.write(f"  {stage.title}: {stage_matches} matches")

            self.stdout.write(f"🏆 Total matches: {match_count}")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to build tournament: {e}"))
            return

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("🎉 Success! The full pipeline works:"))
        self.stdout.write(
            "   Natural Language → Ollama → JSON → DivisionStructure → Database"
        )

    def _colorize_system_prompt(self, prompt: str) -> str:
        """Add colors to system prompt for better readability."""
        lines = prompt.split("\n")
        colored_lines = []

        for line in lines:
            # Headers (lines starting with # or ###)
            if line.strip().startswith("###"):
                colored_lines.append(self.style.SUCCESS(line))
            elif line.strip().startswith("##"):
                colored_lines.append(self.style.WARNING(line))
            elif line.strip().startswith("#"):
                colored_lines.append(
                    self.style.ERROR(line)
                )  # Bright color for main headers

            # JSON code blocks
            elif '{"title":' in line or line.strip().startswith('{"'):
                colored_lines.append(self.style.MIGRATE_LABEL(line))  # Cyan for JSON

            # Draw format examples
            elif "ROUND\\n" in line or line.strip().startswith('"ROUND'):
                colored_lines.append(self.style.SUCCESS(line))  # Green for draw formats

            # Important keywords
            elif any(
                keyword in line.upper()
                for keyword in ["CRITICAL:", "IMPORTANT:", "WARNING:", "ERROR:"]
            ):
                colored_lines.append(self.style.ERROR(line))

            # Bullet points and lists
            elif line.strip().startswith("- ") or line.strip().startswith("* "):
                colored_lines.append(self.style.HTTP_INFO(line))  # Blue for lists

            # Code examples and technical terms
            elif any(
                term in line
                for term in ["G1P1", "W1", "L1", "match_id:", "teams:", "vs"]
            ):
                colored_lines.append(
                    self.style.MIGRATE_HEADING(line)
                )  # Yellow for technical terms

            else:
                colored_lines.append(line)

        return "\n".join(colored_lines)
