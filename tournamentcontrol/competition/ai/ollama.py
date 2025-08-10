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
        import os

        from .schemas import DivisionStructure

        schema = DivisionStructure.get_json_schema()

        # Read the system prompt from markdown file
        prompt_file = os.path.join(os.path.dirname(__file__), "SYSTEM_PROMPT.md")
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                system_prompt = f.read()
        except FileNotFoundError:
            # Fallback to a basic prompt if file not found
            system_prompt = "You are an expert tournament organizer. Generate tournament structures that meet user requirements."

        # Replace the schema placeholder with actual schema
        system_prompt = system_prompt.replace(
            "- JSON Schema will be inserted here dynamically by the calling code",
            f"JSON SCHEMA:\n{json.dumps(schema, indent=2)}",
        )

        return system_prompt

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
