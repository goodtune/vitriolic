#!/usr/bin/env python
"""Validation script to check E2E test setup."""
import os
import sys
import subprocess
import time
import requests
import redis
from pathlib import Path

def check_docker():
    """Check if Docker is available."""
    try:
        docker_result = subprocess.run(["docker", "--version"], check=True, capture_output=True, text=True)
        compose_result = subprocess.run(["docker", "compose", "--version"], check=True, capture_output=True, text=True)
        print("✓ Docker and Docker Compose are available")
        print(f"  Docker: {docker_result.stdout.strip()}")
        print(f"  Compose: {compose_result.stdout.strip()}")
        return True
    except FileNotFoundError as e:
        print(f"✗ Docker command not found: {e}")
        print("  Please install Docker Desktop or Docker Engine")
        return False
    except subprocess.CalledProcessError as e:
        print(f"✗ Docker command failed: {e}")
        if e.stderr:
            print(f"  Error output: {e.stderr.decode().strip()}")
        return False

def check_uv():
    """Check if uv is available."""
    try:
        result = subprocess.run(["uv", "--version"], check=True, capture_output=True, text=True)
        print("✓ uv package manager is available")
        print(f"  Version: {result.stdout.strip()}")
        return True
    except FileNotFoundError as e:
        print(f"✗ uv command not found: {e}")
        print("  Please install uv: https://docs.astral.sh/uv/getting-started/installation/")
        return False
    except subprocess.CalledProcessError as e:
        print(f"✗ uv command failed: {e}")
        if e.stderr:
            print(f"  Error output: {e.stderr.decode().strip()}")
        return False

def check_dependencies():
    """Check if E2E dependencies are installed."""
    try:
        # Check Playwright specifically
        result = subprocess.run(["uv", "run", "python", "-c", "import playwright; print(playwright.__version__)"], 
                              check=True, capture_output=True, text=True)
        print("✓ Playwright is installed")
        print(f"  Version: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Playwright not installed: {e}")
        if e.stderr:
            error_msg = e.stderr.strip()
            print(f"  Error details: {error_msg}")
            if "ModuleNotFoundError" in error_msg:
                print("  Solution: Run 'uv sync --group e2e' to install dependencies")
            elif "No such file or directory" in error_msg:
                print("  Solution: Make sure you're in the project root and uv is installed")
        else:
            print("  Solution: Run 'uv sync --group e2e' to install dependencies")
        return False

def check_services():
    """Check if services are available (either via Docker Compose or CI services)."""
    # In CI, services are already running via GitHub Actions services
    if os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS'):
        print("✓ Services are provided by CI environment")
        print(f"  Environment: CI={os.environ.get('CI', 'false')}, GITHUB_ACTIONS={os.environ.get('GITHUB_ACTIONS', 'false')}")
        return True
    
    # For local development, start Docker Compose services
    print("  Starting Docker Compose services...")
    try:
        # Start services
        start_result = subprocess.run([
            "docker", "compose", "-f", "e2e_tests/docker-compose.yml", "up", "-d"
        ], check=True, capture_output=True, text=True)
        
        print("✓ Docker services started")
        if start_result.stdout:
            print(f"  Start output: {start_result.stdout.strip()}")
        
        # Wait for services
        print("  Waiting 10 seconds for services to initialize...")
        time.sleep(10)
        
        # Check service health
        ps_result = subprocess.run([
            "docker", "compose", "-f", "e2e_tests/docker-compose.yml", "ps", "--format", "json"
        ], capture_output=True, text=True)
        
        if ps_result.returncode == 0:
            print("✓ Services are running")
            # Parse and display service status
            try:
                import json
                services = json.loads(ps_result.stdout) if ps_result.stdout.strip() else []
                for service in services:
                    name = service.get('Name', 'unknown')
                    state = service.get('State', 'unknown')
                    status = service.get('Status', 'unknown')
                    print(f"    {name}: {state} ({status})")
            except json.JSONDecodeError:
                print(f"    Raw status: {ps_result.stdout}")
            return True
        else:
            print(f"✗ Services status check failed (exit code {ps_result.returncode})")
            if ps_result.stderr:
                print(f"  Error: {ps_result.stderr}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to start services: {e}")
        if e.stderr:
            error_msg = e.stderr.decode().strip()
            print(f"  Error details: {error_msg}")
            if "port is already allocated" in error_msg.lower():
                print("  Cause: Ports may be in use by other services")
                print("  Solution: Run 'docker compose -f e2e_tests/docker-compose.yml down' first")
            elif "no such file" in error_msg.lower():
                print("  Cause: docker-compose.yml file not found")
                print("  Solution: Make sure you're in the project root directory")
        return False

def test_database_connection():
    """Test database connection."""
    original_dir = os.getcwd()
    try:
        os.chdir("e2e_tests")
        print("  Testing Django database connection...")
        
        result = subprocess.run([
            "uv", "run", "python", "manage.py", "check", "--database", "default"
        ], check=True, capture_output=True, text=True, env={
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "e2e_tests.settings"
        })
        
        print("✓ Database connection works")
        if result.stdout and result.stdout.strip():
            print(f"  Django check output: {result.stdout.strip()}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"✗ Database connection failed (exit code {e.returncode})")
        if e.stderr:
            error_msg = e.stderr.decode().strip()
            print(f"  Error details: {error_msg}")
            
            # Provide specific troubleshooting based on common errors
            if "could not connect to server" in error_msg.lower():
                print("  Cause: PostgreSQL server is not accessible")
                if os.environ.get('CI'):
                    print("  Solution: Check that PostgreSQL service is running in CI")
                else:
                    print("  Solution: Ensure Docker PostgreSQL container is running")
            elif "authentication failed" in error_msg.lower():
                print("  Cause: Database authentication failed")
                print("  Solution: Check database credentials in e2e_tests/settings.py")
            elif "database" in error_msg.lower() and "does not exist" in error_msg.lower():
                print("  Cause: Database does not exist")
                print("  Solution: Run migrations or check database setup")
            elif "connection refused" in error_msg.lower():
                print("  Cause: Connection refused")
                print("  Solution: Check if database service is running on correct port")
        
        if e.stdout and e.stdout.strip():
            print(f"  Command output: {e.stdout.decode().strip()}")
        return False
        
    except Exception as e:
        print(f"✗ Database connection test failed: {e}")
        return False
        
    finally:
        os.chdir(original_dir)

def test_redis_connection():
    """Test Redis connection using Python redis client."""
    try:
        print("  Testing Redis connection...")
        
        # Connect to Redis (works both in CI and locally)
        redis_client = redis.Redis(host='localhost', port=6379, db=0, socket_timeout=5)
        
        # Test connection with a ping
        response = redis_client.ping()
        
        print("✓ Redis connection works")
        print(f"  Ping response: {response}")
        
        # Get some basic Redis info for diagnostics
        try:
            info = redis_client.info('server')
            if 'redis_version' in info:
                print(f"  Redis version: {info['redis_version']}")
        except:
            # Info command might fail in some environments, but connection works
            pass
        
        return True
        
    except redis.ConnectionError as e:
        print(f"✗ Redis connection failed: {e}")
        print("  Cause: Cannot connect to Redis server")
        if os.environ.get('CI'):
            print("  Solution: Check that Redis service is running in CI workflow")
            print("  Environment: Verify REDIS_URL or default port 6379 is accessible")
        else:
            print("  Solution: Ensure Docker Redis container is running")
            print("  Check: docker compose -f e2e_tests/docker-compose.yml ps")
        return False
        
    except redis.TimeoutError as e:
        print(f"✗ Redis connection timed out: {e}")
        print("  Cause: Redis server is not responding within 5 seconds")
        print("  Solution: Check if Redis is overloaded or network connectivity issues")
        return False
        
    except redis.AuthenticationError as e:
        print(f"✗ Redis authentication failed: {e}")
        print("  Cause: Redis server requires authentication")
        print("  Solution: Check Redis configuration and authentication settings")
        return False
        
    except redis.RedisError as e:
        print(f"✗ Redis error: {e}")
        print(f"  Redis error type: {type(e).__name__}")
        return False
        
    except (ConnectionError, OSError) as e:
        print(f"✗ Network/system error connecting to Redis: {e}")
        print(f"  Error type: {type(e).__name__}")
        print("  Cause: System-level connection issue")
        if "Connection refused" in str(e):
            print("  Solution: Redis service is not running or not accessible on port 6379")
        elif "Name or service not known" in str(e):
            print("  Solution: DNS resolution issue - check hostname 'localhost'")
        return False
        
    except Exception as e:
        print(f"✗ Unexpected error testing Redis: {e}")
        print(f"  Error type: {type(e).__name__}")
        return False

def cleanup():
    """Cleanup services."""
    # Only cleanup if we started services locally (not in CI)
    if not (os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS')):
        print("  Cleaning up Docker services...")
        try:
            result = subprocess.run([
                "docker", "compose", "-f", "e2e_tests/docker-compose.yml", "down"
            ], check=True, capture_output=True, text=True)
            print("✓ Services cleaned up")
            if result.stdout and result.stdout.strip():
                print(f"  Cleanup output: {result.stdout.strip()}")
        except subprocess.CalledProcessError as e:
            print(f"✗ Cleanup failed: {e}")
            if e.stderr:
                print(f"  Error details: {e.stderr.decode().strip()}")
            print("  Note: Manual cleanup may be required")
        except Exception as e:
            print(f"✗ Unexpected cleanup error: {e}")
    else:
        print("✓ Services managed by CI environment")

def main():
    """Run validation checks."""
    print("Validating E2E test setup...")
    print("=" * 50)
    
    checks = [
        ("Docker & Docker Compose", check_docker),
        ("uv Package Manager", check_uv), 
        ("E2E Dependencies", check_dependencies),
        ("Docker Services", check_services),
        ("Database Connection", test_database_connection),
        ("Redis Connection", test_redis_connection),
    ]
    
    passed = 0
    failed_checks = []
    total = len(checks)
    
    for name, check_func in checks:
        print(f"\n[{passed + len(failed_checks) + 1}/{total}] {name}")
        if check_func():
            passed += 1
        else:
            failed_checks.append(name)
    
    print("\n" + "=" * 50)
    cleanup()
    print()
    
    print(f"Validation Results: {passed}/{total} checks passed")
    
    if failed_checks:
        print(f"\n❌ Failed checks:")
        for i, check in enumerate(failed_checks, 1):
            print(f"  {i}. {check}")
    
    if passed == total:
        print("\n🎉 E2E test setup is ready!")
        print("\nTo run tests:")
        print("  ./e2e_tests/run_tests.sh")
        return 0
    else:
        print("\n❌ Setup needs attention")
        print("\nPlease address the failed checks above.")
        print("For detailed troubleshooting, check the error messages and solutions provided.")
        return 1

if __name__ == "__main__":
    sys.exit(main())