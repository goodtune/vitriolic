#!/usr/bin/env python
"""Validation script to check E2E test setup."""
import os
import sys
import subprocess
import time
import requests
from pathlib import Path

def check_docker():
    """Check if Docker is available."""
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True)
        subprocess.run(["docker", "compose", "--version"], check=True, capture_output=True)
        print("✓ Docker and Docker Compose are available")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ Docker or Docker Compose not found")
        return False

def check_uv():
    """Check if uv is available."""
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
        print("✓ uv package manager is available")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ uv package manager not found")
        return False

def check_dependencies():
    """Check if E2E dependencies are installed."""
    try:
        subprocess.run(["uv", "run", "python", "-c", "import playwright"], 
                      check=True, capture_output=True)
        print("✓ Playwright is installed")
        return True
    except subprocess.CalledProcessError:
        print("✗ Playwright not installed - run 'uv sync --group e2e'")
        return False

def start_services():
    """Start Docker services."""
    try:
        # Start services
        subprocess.run([
            "docker", "compose", "-f", "e2e_tests/docker-compose.yml", "up", "-d"
        ], check=True, capture_output=True)
        
        print("✓ Docker services started")
        
        # Wait for services
        time.sleep(10)
        
        # Check service health
        result = subprocess.run([
            "docker", "compose", "-f", "e2e_tests/docker-compose.yml", "ps", "--format", "json"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✓ Services are running")
            return True
        else:
            print("✗ Services failed to start properly")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to start services: {e}")
        return False

def test_database_connection():
    """Test database connection."""
    try:
        os.chdir("e2e_tests")
        result = subprocess.run([
            "uv", "run", "python", "manage.py", "check", "--database", "default"
        ], check=True, capture_output=True, env={
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "e2e_tests.settings"
        })
        print("✓ Database connection works")
        os.chdir("..")
        return True
    except subprocess.CalledProcessError:
        print("✗ Database connection failed")
        os.chdir("..")
        return False

def test_redis_connection():
    """Test Redis connection."""
    try:
        subprocess.run([
            "docker", "exec", "-i", "e2e_tests-redis-1", 
            "redis-cli", "ping"
        ], check=True, capture_output=True)
        print("✓ Redis connection works")
        return True
    except subprocess.CalledProcessError:
        print("✗ Redis connection failed")
        return False

def cleanup():
    """Cleanup services."""
    try:
        subprocess.run([
            "docker", "compose", "-f", "e2e_tests/docker-compose.yml", "down"
        ], check=True, capture_output=True)
        print("✓ Services cleaned up")
    except subprocess.CalledProcessError:
        print("✗ Cleanup failed")

def main():
    """Run validation checks."""
    print("Validating E2E test setup...")
    print("=" * 50)
    
    checks = [
        check_docker,
        check_uv, 
        check_dependencies,
        start_services,
        test_database_connection,
        test_redis_connection,
    ]
    
    passed = 0
    total = len(checks)
    
    for check in checks:
        if check():
            passed += 1
        print()
    
    cleanup()
    print()
    
    print(f"Validation Results: {passed}/{total} checks passed")
    
    if passed == total:
        print("🎉 E2E test setup is ready!")
        print("\nTo run tests:")
        print("  ./e2e_tests/run_tests.sh")
        return 0
    else:
        print("❌ Setup needs attention")
        print("\nPlease address the failed checks above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())