from django.test import TestCase
from django.contrib.auth import get_user_model

from tournamentcontrol.competition.models import Season, Division, Competition
from tournamentcontrol.competition.forms import DivisionBulkCreateFormSet
from tournamentcontrol.competition.tests.factories import SeasonFactory, CompetitionFactory

User = get_user_model()


class DivisionBulkCreateTest(TestCase):
    """Test bulk Division creation functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', 
            email='test@example.com', 
            password='testpass123'
        )
        self.competition = CompetitionFactory()
        self.season = SeasonFactory(competition=self.competition)

    def test_division_bulk_create_formset(self):
        """Test that the DivisionBulkCreateFormSet can create multiple divisions."""
        # Test data for creating 3 divisions
        data = {
            'form-TOTAL_FORMS': '3',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-title': 'Men\'s Division',
            'form-0-short_title': 'Men',
            'form-0-copy': 'Men\'s competition division',
            'form-0-draft': False,
            'form-1-title': 'Women\'s Division',
            'form-1-short_title': 'Women',
            'form-1-copy': 'Women\'s competition division',
            'form-1-draft': False,
            'form-2-title': 'Mixed Division',
            'form-2-short_title': 'Mixed',
            'form-2-copy': 'Mixed competition division',
            'form-2-draft': True,
        }

        formset = DivisionBulkCreateFormSet(
            data=data, 
            instance=self.season, 
            user=self.user
        )
        
        self.assertTrue(formset.is_valid(), f"Formset errors: {formset.errors}")
        
        # Save the formset
        divisions = formset.save()
        
        # Verify divisions were created
        self.assertEqual(len(divisions), 3)
        self.assertEqual(Division.objects.filter(season=self.season).count(), 3)
        
        # Check the first division
        men_division = Division.objects.get(title='Men\'s Division')
        self.assertEqual(men_division.season, self.season)
        self.assertEqual(men_division.short_title, 'Men')
        self.assertEqual(men_division.copy, 'Men\'s competition division')
        self.assertFalse(men_division.draft)
        # Check defaults are applied
        self.assertEqual(men_division.points_formula, '3*win + 1*draw')
        self.assertEqual(men_division.forfeit_for_score, 5)
        self.assertEqual(men_division.forfeit_against_score, 0)

        # Check the draft division
        mixed_division = Division.objects.get(title='Mixed Division')
        self.assertTrue(mixed_division.draft)

    def test_division_bulk_create_formset_empty_forms(self):
        """Test that empty forms are ignored in the formset."""
        data = {
            'form-TOTAL_FORMS': '3',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-title': 'Valid Division',
            'form-0-short_title': '',
            'form-0-copy': '',
            'form-0-draft': False,
            'form-1-title': '',  # Empty title - should be ignored
            'form-1-short_title': '',
            'form-1-copy': '',
            'form-1-draft': False,
            'form-2-title': '',  # Empty title - should be ignored
            'form-2-short_title': '',
            'form-2-copy': '',
            'form-2-draft': False,
        }

        formset = DivisionBulkCreateFormSet(
            data=data, 
            instance=self.season, 
            user=self.user
        )
        
        self.assertTrue(formset.is_valid(), f"Formset errors: {formset.errors}")
        
        # Save the formset
        divisions = formset.save()
        
        # Verify only one division was created (empty forms ignored)
        self.assertEqual(len(divisions), 1)
        self.assertEqual(Division.objects.filter(season=self.season).count(), 1)
        
        # Check the valid division
        division = Division.objects.get(title='Valid Division')
        self.assertEqual(division.season, self.season)

    def test_division_bulk_create_form_defaults(self):
        """Test that the DivisionBulkCreateForm applies correct defaults."""
        from tournamentcontrol.competition.forms import DivisionBulkCreateForm
        
        form_data = {
            'title': 'Test Division',
            'short_title': 'Test',
            'copy': 'Test division',
            'draft': False,
        }
        
        form = DivisionBulkCreateForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        # Create an instance but don't save yet
        division = form.save(commit=False)
        division.season = self.season
        
        # Apply the form's save method
        division = form.save(commit=True)
        
        # Check defaults are applied
        self.assertEqual(division.points_formula, '3*win + 1*draw')
        self.assertEqual(division.forfeit_for_score, 5)
        self.assertEqual(division.forfeit_against_score, 0)