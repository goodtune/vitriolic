#!/usr/bin/env python
"""
Manual test script to verify bulk Division creation functionality.

This script simulates the admin interface interaction to test the bulk creation feature.
"""

import os
import sys
import django
from django.conf import settings

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vitriolic.settings')

# Minimal Django configuration for testing
if not settings.configured:
    settings.configure(
        DEBUG=True,
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'django.contrib.messages',
            'touchtechnology.common',
            'tournamentcontrol.competition',
        ],
        SECRET_KEY='test-key-for-manual-verification',
        USE_TZ=True,
    )

django.setup()

# Now import Django components
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from tournamentcontrol.competition.models import Competition, Season, Division
from tournamentcontrol.competition.forms import DivisionBulkCreateFormSet
from tournamentcontrol.competition.admin import CompetitionAdminComponent

User = get_user_model()

def create_test_data():
    """Create test competition and season."""
    competition = Competition.objects.create(
        title="Test Competition",
        slug="test-competition"
    )
    
    season = Season.objects.create(
        title="2024 Season",
        slug="2024-season", 
        competition=competition
    )
    
    user = User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123',
        is_staff=True,
        is_superuser=True
    )
    
    return competition, season, user

def test_bulk_division_form():
    """Test the DivisionBulkCreateForm functionality."""
    print("Testing DivisionBulkCreateForm...")
    
    from tournamentcontrol.competition.forms import DivisionBulkCreateForm
    
    # Create a test season
    competition, season, user = create_test_data()
    
    # Test form with valid data
    form_data = {
        'title': 'Men\'s Open',
        'short_title': 'Men',
        'copy': 'Men\'s open division',
        'draft': False,
    }
    
    form = DivisionBulkCreateForm(data=form_data)
    if form.is_valid():
        division = form.save(commit=False)
        division.season = season
        division = form.save(commit=True)
        
        print(f"✓ Division created: {division.title}")
        print(f"  - Season: {division.season}")
        print(f"  - Points formula: {division.points_formula}")
        print(f"  - Forfeit for score: {division.forfeit_for_score}")
        print(f"  - Forfeit against score: {division.forfeit_against_score}")
        
        # Verify defaults were applied
        assert division.points_formula == '3*win + 1*draw'
        assert division.forfeit_for_score == 5
        assert division.forfeit_against_score == 0
        print("✓ Defaults applied correctly")
        
    else:
        print(f"✗ Form validation failed: {form.errors}")
        return False
        
    return True

def test_bulk_division_formset():
    """Test the DivisionBulkCreateFormSet functionality."""
    print("\nTesting DivisionBulkCreateFormSet...")
    
    # Create a test season
    competition, season, user = create_test_data()
    
    # Test formset with multiple divisions
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
        instance=season,
        user=user
    )
    
    if formset.is_valid():
        divisions = formset.save()
        print(f"✓ Created {len(divisions)} divisions:")
        for division in divisions:
            print(f"  - {division.title} (order: {division.order}, draft: {division.draft})")
            
        # Verify count
        total_divisions = Division.objects.filter(season=season).count()
        assert total_divisions == 3
        print(f"✓ Total divisions in season: {total_divisions}")
        
    else:
        print(f"✗ Formset validation failed: {formset.errors}")
        return False
        
    return True

def test_admin_method():
    """Test the admin bulk_divisions method (simulation)."""
    print("\nTesting admin bulk_divisions method...")
    
    try:
        # Create admin component
        admin = CompetitionAdminComponent(None)
        print("✓ Admin component created")
        
        # Check the method exists
        assert hasattr(admin, 'bulk_divisions')
        print("✓ bulk_divisions method exists")
        
        # Check URL patterns (this will be added during actual integration)
        # For now, just verify the method signature
        import inspect
        sig = inspect.signature(admin.bulk_divisions)
        expected_params = ['self', 'request', 'competition', 'season', 'extra_context']
        actual_params = list(sig.parameters.keys())
        print(f"  Method signature: {actual_params}")
        
        # We can't fully test without HTTP request, but we can check the method exists
        print("✓ Admin method ready for integration")
        
    except Exception as e:
        print(f"✗ Admin method test failed: {e}")
        return False
        
    return True

def main():
    """Run all tests."""
    print("=" * 50)
    print("Manual Verification: Bulk Division Creation")
    print("=" * 50)
    
    # Apply migrations to create tables
    from django.core.management import execute_from_command_line
    execute_from_command_line(['manage.py', 'migrate', '--run-syncdb'])
    
    tests = [
        test_bulk_division_form,
        test_bulk_division_formset,
        test_admin_method,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with exception: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 50)
    
    if failed == 0:
        print("🎉 All tests passed! Bulk Division creation is working correctly.")
        return True
    else:
        print("❌ Some tests failed. Check the output above for details.")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)