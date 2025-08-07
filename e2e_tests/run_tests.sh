#!/bin/bash
# Script to run E2E tests with proper environment setup

set -e

echo "Starting E2E test environment..."

# Install dependencies
echo "Installing E2E dependencies..."
uv sync --group e2e

# Install Playwright browsers
echo "Installing Playwright browsers..."
uv run playwright install chromium

# Start Docker services
echo "Starting Docker services..."
docker compose -f e2e_tests/docker-compose.yml up -d

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 15

# Check if services are healthy
echo "Checking service health..."
docker compose -f e2e_tests/docker-compose.yml ps

# Setup database
echo "Setting up test database..."
cd e2e_tests
uv run python manage.py migrate --run-syncdb
cd ..

# Start Celery worker in background
echo "Starting Celery worker..."
cd tests
uv run celery -A vitriolic.celery worker --loglevel=info --detach
cd ..

echo "Running E2E tests..."
# Run the tests
uv run pytest e2e_tests/ -v --tb=short

# Cleanup
echo "Cleaning up..."
cd tests
pkill -f "celery.*worker" || true
cd ..

docker compose -f e2e_tests/docker-compose.yml down

echo "E2E tests completed!"