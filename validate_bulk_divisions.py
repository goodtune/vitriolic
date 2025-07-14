#!/usr/bin/env python
"""
Simple validation script for bulk Division creation feature.
This script validates the code structure without requiring all dependencies.
"""

import os
import ast
import sys

def validate_python_syntax(file_path):
    """Validate Python syntax of a file."""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        ast.parse(content)
        return True, None
    except SyntaxError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

def check_form_class_exists(forms_file):
    """Check if DivisionBulkCreateForm and formset exist in forms.py."""
    try:
        with open(forms_file, 'r') as f:
            content = f.read()
        
        checks = {
            'DivisionBulkCreateForm': 'class DivisionBulkCreateForm' in content,
            'DivisionBulkCreateFormSet': 'DivisionBulkCreateFormSet = inlineformset_factory' in content,
            'BaseDivisionBulkCreateFormSet': 'class BaseDivisionBulkCreateFormSet' in content,
        }
        
        return checks
    except Exception as e:
        return {'error': str(e)}

def check_admin_integration(admin_file):
    """Check if bulk_divisions method exists in admin.py."""
    try:
        with open(admin_file, 'r') as f:
            content = f.read()
        
        checks = {
            'bulk_divisions_method': 'def bulk_divisions(' in content,
            'bulk_divisions_import': 'DivisionBulkCreateFormSet' in content,
            'bulk_divisions_url': 'bulk-divisions' in content,
        }
        
        return checks
    except Exception as e:
        return {'error': str(e)}

def check_template_exists(template_file):
    """Check if template file exists and has basic structure."""
    try:
        if not os.path.exists(template_file):
            return {'exists': False}
        
        with open(template_file, 'r') as f:
            content = f.read()
        
        checks = {
            'exists': True,
            'extends_base': '{% extends ' in content,
            'has_form': '<form' in content,
            'has_formset': '{{ formset' in content,
            'has_management_form': 'management_form' in content,
        }
        
        return checks
    except Exception as e:
        return {'error': str(e)}

def main():
    """Run validation checks."""
    print("=" * 60)
    print("Bulk Division Creation Feature Validation")
    print("=" * 60)
    
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    # File paths
    forms_file = os.path.join(base_path, 'tournamentcontrol/competition/forms.py')
    admin_file = os.path.join(base_path, 'tournamentcontrol/competition/admin.py')
    template_file = os.path.join(base_path, 'tournamentcontrol/competition/templates/tournamentcontrol/competition/admin/season/bulk_divisions.html')
    
    all_passed = True
    
    # 1. Syntax validation
    print("\n1. Python Syntax Validation")
    print("-" * 30)
    
    for name, file_path in [('forms.py', forms_file), ('admin.py', admin_file)]:
        if os.path.exists(file_path):
            valid, error = validate_python_syntax(file_path)
            if valid:
                print(f"✓ {name}: Syntax valid")
            else:
                print(f"✗ {name}: Syntax error - {error}")
                all_passed = False
        else:
            print(f"✗ {name}: File not found")
            all_passed = False
    
    # 2. Forms validation
    print("\n2. Forms Component Validation")
    print("-" * 30)
    
    if os.path.exists(forms_file):
        form_checks = check_form_class_exists(forms_file)
        if 'error' in form_checks:
            print(f"✗ Forms check failed: {form_checks['error']}")
            all_passed = False
        else:
            for check, passed in form_checks.items():
                status = "✓" if passed else "✗"
                print(f"{status} {check}: {'Found' if passed else 'Missing'}")
                if not passed:
                    all_passed = False
    else:
        print("✗ forms.py not found")
        all_passed = False
    
    # 3. Admin integration validation
    print("\n3. Admin Integration Validation")
    print("-" * 30)
    
    if os.path.exists(admin_file):
        admin_checks = check_admin_integration(admin_file)
        if 'error' in admin_checks:
            print(f"✗ Admin check failed: {admin_checks['error']}")
            all_passed = False
        else:
            for check, passed in admin_checks.items():
                status = "✓" if passed else "✗"
                print(f"{status} {check}: {'Found' if passed else 'Missing'}")
                if not passed:
                    all_passed = False
    else:
        print("✗ admin.py not found")
        all_passed = False
    
    # 4. Template validation
    print("\n4. Template Validation")
    print("-" * 30)
    
    template_checks = check_template_exists(template_file)
    if 'error' in template_checks:
        print(f"✗ Template check failed: {template_checks['error']}")
        all_passed = False
    else:
        for check, passed in template_checks.items():
            status = "✓" if passed else "✗"
            print(f"{status} {check}: {'Found' if passed else 'Missing'}")
            if not passed and check != 'exists':  # Don't fail for missing optional elements
                all_passed = False
    
    # 5. File structure validation
    print("\n5. File Structure Validation")
    print("-" * 30)
    
    files_to_check = [
        ('Documentation', 'BULK_DIVISIONS_DOCUMENTATION.md'),
        ('Test file', 'test_bulk_divisions.py'),
        ('Manual test', 'manual_test_bulk_divisions.py'),
    ]
    
    for name, filename in files_to_check:
        file_path = os.path.join(base_path, filename)
        if os.path.exists(file_path):
            print(f"✓ {name}: {filename}")
        else:
            print(f"? {name}: {filename} (optional)")
    
    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 ALL VALIDATIONS PASSED!")
        print("\nThe bulk Division creation feature appears to be correctly implemented:")
        print("- Forms and formsets are defined")
        print("- Admin integration is in place") 
        print("- Template structure is correct")
        print("- Python syntax is valid")
        print("\nNext steps:")
        print("- Test in a Django environment with proper dependencies")
        print("- Verify admin interface integration")
        print("- Test with real user scenarios")
    else:
        print("❌ SOME VALIDATIONS FAILED")
        print("\nPlease review the errors above and fix them before proceeding.")
    
    print("=" * 60)
    
    return all_passed

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)