"""
Tests for admin ranking column removal from templates.

This test module verifies that ranking columns are properly removed from
admin list templates while maintaining proper functionality.
"""

import os

from test_plus import TestCase


class AdminRankingTemplateTests(TestCase):
    """Test that ranking columns are removed from admin templates."""

    def test_division_list_template_content(self):
        """Test that division list template content has no ranking references."""
        template_path = "/home/runner/work/vitriolic/vitriolic/tournamentcontrol/competition/templates/tournamentcontrol/competition/admin/division/list.inc.html"
        with open(template_path, "r") as f:
            content = f.read()

        # Verify ranking columns are NOT present
        self.assertNotIn('{% trans "Rank" %}', content)
        self.assertNotIn('{% trans "Importance" %}', content)
        self.assertNotIn("get_rank_division", content)
        self.assertNotIn("get_rank_importance", content)

        # Verify the template is still properly structured
        self.assertIn('{% extends "mvp/list.split.inc.html" %}', content)
        self.assertIn('{% trans "Short title" %}', content)

    def test_team_list_template_content(self):
        """Test that team list template content has no ranking references."""
        template_path = "/home/runner/work/vitriolic/vitriolic/tournamentcontrol/competition/templates/tournamentcontrol/competition/admin/team/list.inc.html"
        with open(template_path, "r") as f:
            content = f.read()

        # Verify ranking columns are NOT present
        self.assertNotIn('{% trans "Rank" %}', content)
        self.assertNotIn("get_rank_division", content)

        # Verify the template is still properly structured
        self.assertIn('{% extends "mvp/list.split.inc.html" %}', content)
        self.assertIn('{% trans "Slug" %}', content)

    def test_stagegroup_list_template_content(self):
        """Test that stagegroup list template content has no ranking references."""
        template_path = "/home/runner/work/vitriolic/vitriolic/tournamentcontrol/competition/templates/tournamentcontrol/competition/admin/stagegroup/list.inc.html"
        with open(template_path, "r") as f:
            content = f.read()

        # Verify ranking columns are NOT present
        self.assertNotIn('{% trans "Importance" %}', content)
        self.assertNotIn("get_rank_importance", content)

        # Verify the template is still properly structured
        self.assertIn('{% extends "mvp/list.inc.html" %}', content)
        self.assertIn('{% trans "Short title" %}', content)

    def test_competition_list_template_content(self):
        """Test that competition list template content has no ranking references."""
        template_path = "/home/runner/work/vitriolic/vitriolic/tournamentcontrol/competition/templates/tournamentcontrol/competition/admin/competition/list.inc.html"
        with open(template_path, "r") as f:
            content = f.read()

        # Verify ranking columns are NOT present
        self.assertNotIn('{% trans "Importance" %}', content)
        self.assertNotIn("get_rank_importance", content)

        # Verify the template is still properly structured
        self.assertIn('{% extends "mvp/list.inc.html" %}', content)
        self.assertIn('{% trans "Competition name" %}', content)

    def test_stage_list_template_content(self):
        """Test that stage list template content has no ranking references."""
        template_path = "/home/runner/work/vitriolic/vitriolic/tournamentcontrol/competition/templates/tournamentcontrol/competition/admin/stage/list.inc.html"
        with open(template_path, "r") as f:
            content = f.read()

        # Verify ranking columns are NOT present
        self.assertNotIn('{% trans "Importance" %}', content)
        self.assertNotIn("get_rank_importance", content)

        # Verify the template is still properly structured
        self.assertIn('{% extends "mvp/list.split.inc.html" %}', content)
        self.assertIn('{% trans "Short title" %}', content)
