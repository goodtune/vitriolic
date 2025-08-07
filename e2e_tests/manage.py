#!/usr/bin/env python
"""Django's command-line utility for E2E tests."""
import os
import sys

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'e2e_tests.settings')
    
    # Add the parent directory to the path so we can import the main project
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)