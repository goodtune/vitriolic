# -*- coding: utf-8 -*-

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from django.conf import settings

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

logger = logging.getLogger(__name__)


@dataclass
class PoolStructure:
    """Represents a pool within a stage."""

    name: str
    teams: List[str]
    description: str = ""


@dataclass
class StageStructure:
    """Represents a stage within a division."""

    name: str
    stage_type: str  # 'round_robin', 'knockout', 'swiss', etc.
    pools: List[PoolStructure]
    description: str = ""
    matches_per_day_min: int = 2
    matches_per_day_max: int = 3


@dataclass
class DivisionStructure:
    """Represents a division within a season."""

    name: str
    team_count: int
    teams: List[str]
    stages: List[StageStructure]
    description: str = ""


@dataclass
class CompetitionPlan:
    """Complete plan for competition structure."""

    description: str
    total_teams: int
    total_days: int
    divisions: List[DivisionStructure]
    summary: str = ""
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class AICompetitionService:
    """Service for generating competition structures using AI."""

    def __init__(self):
        self.client = None
        if OpenAI and hasattr(settings, "OPENAI_API_KEY"):
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def is_available(self) -> bool:
        """Check if AI service is available."""
        return self.client is not None

    def generate_plan(
        self, prompt: str, season_context: Optional[Dict] = None
    ) -> CompetitionPlan:
        """
        Generate a competition structure plan from a natural language prompt.

        Args:
            prompt: Natural language description of competition requirements
            season_context: Optional context about the season (existing teams, venues, etc.)

        Returns:
            CompetitionPlan object with detailed structure
        """
        if not self.is_available():
            return self._generate_mock_plan(prompt)

        try:
            system_prompt = self._get_system_prompt()
            user_prompt = self._format_user_prompt(prompt, season_context)

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=2000,
            )

            plan_json = response.choices[0].message.content
            return self._parse_plan_json(plan_json)

        except Exception as e:
            logger.error(f"Error generating AI plan: {e}")
            # Fallback to mock plan
            return self._generate_mock_plan(prompt)

    def _get_system_prompt(self) -> str:
        """Get the system prompt for the AI model."""
        return """You are an expert sports tournament organizer. Your task is to create detailed competition structures based on natural language requirements.

You must respond with valid JSON that matches this exact schema:

{
  "description": "Brief description of the plan",
  "total_teams": 19,
  "total_days": 5,
  "summary": "High-level summary of the approach",
  "warnings": ["Any warnings or limitations"],
  "divisions": [
    {
      "name": "Mixed Open",
      "team_count": 19,
      "teams": ["Team 1", "Team 2", ...],
      "description": "Description of this division",
      "stages": [
        {
          "name": "Pool Play",
          "stage_type": "round_robin",
          "description": "Round robin pool play",
          "matches_per_day_min": 2,
          "matches_per_day_max": 3,
          "pools": [
            {
              "name": "Pool A",
              "teams": ["Team 1", "Team 2", ...],
              "description": "First pool"
            }
          ]
        },
        {
          "name": "Finals",
          "stage_type": "knockout",
          "description": "Playoff finals",
          "matches_per_day_min": 1,
          "matches_per_day_max": 2,
          "pools": [
            {
              "name": "Championship Bracket",
              "teams": ["Pool A Winner", "Pool B Winner"],
              "description": "Top teams playoff"
            }
          ]
        }
      ]
    }
  ]
}

Key principles:
- Consider constraints like matches per day, total days available
- Create realistic pool sizes (typically 8-12 teams max for round robin)
- Plan appropriate progression between stages
- Include all teams in the final ranking structure
- Provide clear descriptions and rationale"""

    def _format_user_prompt(self, prompt: str, context: Optional[Dict] = None) -> str:
        """Format the user prompt with context."""
        formatted = f"Create a competition structure for: {prompt}"

        if context:
            formatted += f"\n\nAdditional context: {json.dumps(context, indent=2)}"

        formatted += (
            "\n\nProvide your response as valid JSON matching the required schema."
        )
        return formatted

    def _parse_plan_json(self, json_str: str) -> CompetitionPlan:
        """Parse JSON response into CompetitionPlan object."""
        try:
            # Extract JSON from response if it's wrapped in markdown
            if "```json" in json_str:
                start = json_str.find("```json") + 7
                end = json_str.find("```", start)
                json_str = json_str[start:end].strip()
            elif "```" in json_str:
                start = json_str.find("```") + 3
                end = json_str.find("```", start)
                json_str = json_str[start:end].strip()

            data = json.loads(json_str)

            # Convert dict to dataclass structure
            divisions = []
            for div_data in data.get("divisions", []):
                stages = []
                for stage_data in div_data.get("stages", []):
                    pools = []
                    for pool_data in stage_data.get("pools", []):
                        pools.append(PoolStructure(**pool_data))

                    stage_data_copy = stage_data.copy()
                    stage_data_copy["pools"] = pools
                    stages.append(StageStructure(**stage_data_copy))

                div_data_copy = div_data.copy()
                div_data_copy["stages"] = stages
                divisions.append(DivisionStructure(**div_data_copy))

            plan_data = data.copy()
            plan_data["divisions"] = divisions

            return CompetitionPlan(**plan_data)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"Error parsing AI response: {e}")
            logger.error(f"Response was: {json_str}")
            # Return a basic fallback plan
            return self._generate_fallback_plan()

    def _generate_mock_plan(self, prompt: str) -> CompetitionPlan:
        """Generate a mock plan for testing when AI is not available."""
        # Extract basic info from prompt
        team_count = 19  # default
        days = 5  # default

        # Simple parsing for team count and days
        import re

        team_match = re.search(r"(\d+)\s+(?:teams?|Mixed|Open)", prompt, re.IGNORECASE)
        if team_match:
            team_count = int(team_match.group(1))

        day_match = re.search(r"(\d+)\s+days?", prompt, re.IGNORECASE)
        if day_match:
            days = int(day_match.group(1))

        # Generate team names
        teams = [f"Team {i+1}" for i in range(team_count)]

        # Split into two pools for round robin
        pool_a_size = team_count // 2
        pool_b_size = team_count - pool_a_size

        pool_a = PoolStructure(
            name="Pool A",
            teams=teams[:pool_a_size],
            description=f"Pool A with {pool_a_size} teams",
        )

        pool_b = PoolStructure(
            name="Pool B",
            teams=teams[pool_a_size:],
            description=f"Pool B with {pool_b_size} teams",
        )

        # Round robin stage
        round_robin = StageStructure(
            name="Pool Play",
            stage_type="round_robin",
            pools=[pool_a, pool_b],
            description="Round robin within pools",
            matches_per_day_min=2,
            matches_per_day_max=3,
        )

        # Finals stage
        finals = StageStructure(
            name="Finals",
            stage_type="knockout",
            pools=[
                PoolStructure(
                    name="Championship Bracket",
                    teams=[
                        "Pool A Winner",
                        "Pool B Winner",
                        "Pool A Runner-up",
                        "Pool B Runner-up",
                    ],
                    description="Top 4 playoff for medals",
                )
            ],
            description="Medal playoffs and final rankings",
            matches_per_day_min=1,
            matches_per_day_max=2,
        )

        division = DivisionStructure(
            name="Mixed Open",
            team_count=team_count,
            teams=teams,
            stages=[round_robin, finals],
            description=f"Main division with {team_count} teams",
        )

        return CompetitionPlan(
            description=f"Competition structure for {team_count} teams over {days} days",
            total_teams=team_count,
            total_days=days,
            divisions=[division],
            summary=f"Two pools of {pool_a_size} and {pool_b_size} teams, round robin followed by knockout finals",
            warnings=["This is a mock plan generated without AI integration"],
        )

    def _generate_fallback_plan(self) -> CompetitionPlan:
        """Generate a basic fallback plan when parsing fails."""
        teams = [f"Team {i+1}" for i in range(8)]

        pool = PoolStructure(
            name="Main Pool", teams=teams, description="Single pool with all teams"
        )

        stage = StageStructure(
            name="Round Robin",
            stage_type="round_robin",
            pools=[pool],
            description="Single round robin",
            matches_per_day_min=2,
            matches_per_day_max=3,
        )

        division = DivisionStructure(
            name="Main Division",
            team_count=8,
            teams=teams,
            stages=[stage],
            description="Main division",
        )

        return CompetitionPlan(
            description="Fallback competition plan",
            total_teams=8,
            total_days=3,
            divisions=[division],
            summary="Basic single pool round robin",
            warnings=["This is a fallback plan due to parsing error"],
        )
