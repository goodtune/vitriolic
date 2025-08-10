# -*- coding: utf-8 -*-

"""
Ollama provider for AI-generated tournament structures.

This module provides integration with Ollama for generating tournament
structures from natural language prompts.
"""

import json
import logging
from typing import Optional

import requests

from .schemas import DivisionStructure

logger = logging.getLogger(__name__)


class OllamaProvider:
    """Simple Ollama provider for tournament generation."""

    def __init__(
        self, base_url: str = "http://localhost:11434", model: str = "llama3.2"
    ):
        """
        Initialize Ollama provider.

        Args:
            base_url: Ollama API base URL
            model: Model name to use (e.g., 'llama3.2', 'codellama')
        """
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate_tournament(self, prompt: str) -> Optional[DivisionStructure]:
        """
        Generate a tournament structure from a natural language prompt.

        Args:
            prompt: User's natural language description of tournament requirements

        Returns:
            DivisionStructure instance or None if generation fails
        """
        try:
            # Build the system prompt with schema information and examples
            system_prompt = self._build_system_prompt()

            # Make the API call to Ollama
            response = self._call_ollama_api(system_prompt, prompt)

            if not response:
                logger.error("No response from Ollama API")
                return None

            # Parse the JSON response
            try:
                # Extract JSON from response - sometimes models wrap it in markdown
                json_text = self._extract_json(response)
                data = json.loads(json_text)
                return DivisionStructure.model_validate(data)
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse Ollama response as JSON: {e}")
                logger.error(f"Response was: {response}")
                return None

        except Exception as e:
            logger.error(f"Error generating tournament with Ollama: {e}")
            return None

    def _build_system_prompt(self) -> str:
        """Build the system prompt with tournament generation instructions."""
        from .schemas import DivisionStructure

        schema = DivisionStructure.get_json_schema()

        return f"""You are an expert tournament organizer with deep knowledge of sports competition formats. Generate tournament structures that meet user requirements.

OUTPUT FORMAT:
- ONLY output valid JSON matching the schema below
- NO markdown, explanations, or extra text
- Ensure proper JSON syntax with correct quotes and brackets

TOURNAMENT STRUCTURE RULES:

1. TEAM ASSIGNMENTS:
   - For pools with specific teams: use 0-based indices [0, 1, 2, 3] referring to positions in main teams array
   - For pools referencing other stage results: set teams: null

2. STAGE TYPES:
   - Pool stages: have "pools" array, "draw_format": null
   - Knockout stages: have "draw_format" string, "pools": null
   - Never have both pools AND draw_format

3. DRAW FORMAT SYNTAX (critical - follow exactly):

   BASIC STRUCTURE:
   ROUND [optional_label]
   match_id: team1 vs team2 [optional_match_label]

   TEAM REFERENCES:
   - Direct indices: 1, 2, 3, 4 (position in division teams, 1-based)
   - Winners: W1, W2 (winner of match 1, 2)
   - Losers: L1, L2 (loser of match 1, 2) 
   - Pool positions: G1P1, G2P3 (Group 1 Position 1, Group 2 Position 3)
   - Stage positions: S1G1P2 (Stage 1 Group 1 Position 2)

4. COMMON PATTERNS:

   Round Robin (4 teams in pool):
   "ROUND\\n1: 1 vs 2\\n2: 3 vs 4\\nROUND\\n3: 1 vs 3\\n4: 2 vs 4\\nROUND\\n5: 1 vs 4\\n6: 2 vs 3"

   Simple Knockout (4 teams):
   "ROUND\\n1: 1 vs 2 Semi 1\\n2: 3 vs 4 Semi 2\\nROUND\\n3: L1 vs L2 Bronze\\nROUND\\n4: W1 vs W2 Final"

   Cross-Pool Finals:
   "ROUND\\n1: G1P1 vs G2P2 Final\\n2: G1P2 vs G2P1 3rd Place"

5. TOURNAMENT DESIGN PRINCIPLES:
   - Keep pools to 3-8 teams (optimal: 4-6)
   - Ensure all teams get minimum required matches
   - Plan realistic progression between stages
   - Consider venue/time constraints
   - Create clear ranking structure (1st-Nth place)

6. DRAW FORMAT TECHNICAL DETAILS:
   - Each ROUND section groups matches played simultaneously
   - Match IDs must be unique (typically sequential: 1, 2, 3...)
   - Team references are resolved by the DrawGenerator class
   - Pool positions (G1P1) refer to final standings after pool completion
   - Winner/Loser refs (W1, L1) create bracket-style progression
   - Direct indices (1, 2, 3) map to teams array positions (1-based)

JSON SCHEMA:
{json.dumps(schema, indent=2)}

COMPLETE EXAMPLES:

8-Team Pool + Finals:
{{"title": "Mixed Competition", "teams": ["Red", "Blue", "Green", "Yellow", "Orange", "Purple", "Pink", "Cyan"], "stages": [{{"title": "Pool Play", "draw_format": null, "pools": [{{"title": "Pool A", "draw_format": "ROUND\\n1: 1 vs 2\\n2: 3 vs 4\\nROUND\\n3: 1 vs 3\\n4: 2 vs 4\\nROUND\\n5: 1 vs 4\\n6: 2 vs 3", "teams": [0, 1, 2, 3]}}, {{"title": "Pool B", "draw_format": "ROUND\\n1: 1 vs 2\\n2: 3 vs 4\\nROUND\\n3: 1 vs 3\\n4: 2 vs 4\\nROUND\\n5: 1 vs 4\\n6: 2 vs 3", "teams": [4, 5, 6, 7]}}]}}, {{"title": "Finals", "draw_format": "ROUND\\n1: G1P1 vs G2P2 Semi 1\\n2: G1P2 vs G2P1 Semi 2\\nROUND\\n3: L1 vs L2 Bronze\\nROUND\\n4: W1 vs W2 Final", "pools": null}}]}}

Large Tournament (19 teams):
{{"title": "19-Team Championship", "teams": ["Team 1", "Team 2", "Team 3", "Team 4", "Team 5", "Team 6", "Team 7", "Team 8", "Team 9", "Team 10", "Team 11", "Team 12", "Team 13", "Team 14", "Team 15", "Team 16", "Team 17", "Team 18", "Team 19"], "stages": [{{"title": "Pool Stage", "draw_format": null, "pools": [{{"title": "Pool A", "draw_format": "ROUND\\n1: 1 vs 2\\n2: 3 vs 4\\n3: 5 vs 6\\nROUND\\n4: 1 vs 3\\n5: 2 vs 5\\n6: 4 vs 6\\nROUND\\n7: 1 vs 4\\n8: 3 vs 5\\n9: 2 vs 6\\nROUND\\n10: 1 vs 5\\n11: 4 vs 3\\n12: 6 vs 2\\nROUND\\n13: 1 vs 6\\n14: 5 vs 4\\n15: 2 vs 3", "teams": [0, 1, 2, 3, 4, 5]}}, {{"title": "Pool B", "draw_format": "ROUND\\n1: 1 vs 2\\n2: 3 vs 4\\n3: 5 vs 6\\nROUND\\n4: 1 vs 3\\n5: 2 vs 5\\n6: 4 vs 6\\nROUND\\n7: 1 vs 4\\n8: 3 vs 5\\n9: 2 vs 6\\nROUND\\n10: 1 vs 5\\n11: 4 vs 3\\n12: 6 vs 2\\nROUND\\n13: 1 vs 6\\n14: 5 vs 4\\n15: 2 vs 3", "teams": [6, 7, 8, 9, 10, 11]}}, {{"title": "Pool C", "draw_format": "ROUND\\n1: 1 vs 2\\n2: 3 vs 4\\n3: 5 vs 6\\n4: 7 vs 1\\nROUND\\n5: 2 vs 3\\n6: 4 vs 5\\n7: 6 vs 7\\n8: 1 vs 4\\nROUND\\n9: 3 vs 6\\n10: 5 vs 2\\n11: 7 vs 4\\n12: 1 vs 3\\nROUND\\n13: 6 vs 2\\n14: 4 vs 3\\n15: 7 vs 5\\n16: 1 vs 6\\nROUND\\n17: 2 vs 7\\n18: 3 vs 5\\n19: 4 vs 6\\n20: 1 vs 5\\nROUND\\n21: 7 vs 3\\n22: 5 vs 1\\n23: 2 vs 4\\n24: 6 vs 1", "teams": [12, 13, 14, 15, 16, 17, 18]}}]}}, {{"title": "Championship", "draw_format": "ROUND\\n1: G1P1 vs G2P2 QF1\\n2: G1P2 vs G3P2 QF2\\n3: G2P1 vs G3P1 QF3\\n4: G1P3 vs G2P3 QF4\\nROUND\\n5: W1 vs W2 SF1\\n6: W3 vs W4 SF2\\nROUND\\n7: L5 vs L6 Bronze\\nROUND\\n8: W5 vs W6 Final", "pools": null}}]}}

Generate tournament structure for the user's requirements:"""

    def _call_ollama_api(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """Make API call to Ollama."""
        try:
            url = f"{self.base_url}/api/generate"
            payload = {
                "model": self.model,
                "prompt": f"{system_prompt}\n\nUser Request: {user_prompt}\n\nJSON Output:",
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                },
            }

            logger.debug(f"Calling Ollama API at {url}")
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()

            data = response.json()
            return data.get("response", "").strip()

        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API request failed: {e}")
            return None
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse Ollama API response: {e}")
            return None

    def _extract_json(self, response: str) -> str:
        """Extract JSON from response, handling markdown code blocks."""
        response = response.strip()

        # Remove markdown code block markers if present
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]

        if response.endswith("```"):
            response = response[:-3]

        return response.strip()

    def is_available(self) -> bool:
        """Check if Ollama API is available."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
