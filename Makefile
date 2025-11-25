.PHONY: help test test-unit test-integration test-all docker-up docker-down docker-logs clean

# Default target
help:
	@echo "Aisher Test Commands"
	@echo "===================="
	@echo ""
	@echo "Testing:"
	@echo "  make test              - Run unit tests only (default)"
	@echo "  make test-unit         - Run unit tests only"
	@echo "  make test-integration  - Run Docker-based integration tests"
	@echo "  make test-all          - Run all tests (unit + integration)"
	@echo "  make test-cov          - Run tests with coverage report"
	@echo ""
	@echo "Docker Management:"
	@echo "  make docker-up         - Start Docker test containers"
	@echo "  make docker-down       - Stop and remove Docker test containers"
	@echo "  make docker-logs       - Show Docker container logs"
	@echo "  make docker-shell      - Open ClickHouse shell"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean             - Remove test artifacts and Docker volumes"

# Run unit tests only
test: test-unit

test-unit:
	@echo "Running unit tests..."
	uv run pytest tests/test_error_analyzer.py -v

# Run integration tests with Docker
test-integration:
	@echo "Running integration tests with Docker..."
	@bash scripts/run_integration_tests.sh

# Run all tests
test-all:
	@echo "Running all tests..."
	uv run pytest tests/ -v

# Run tests with coverage
test-cov:
	@echo "Running tests with coverage..."
	uv run pytest tests/ -v --cov=aisher --cov-report=term-missing --cov-report=html

# Start Docker services
docker-up:
	@echo "Starting Docker test services..."
	docker-compose -f docker-compose.test.yml up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	@docker-compose -f docker-compose.test.yml ps

# Stop Docker services
docker-down:
	@echo "Stopping Docker test services..."
	docker-compose -f docker-compose.test.yml down -v

# Show Docker logs
docker-logs:
	docker-compose -f docker-compose.test.yml logs -f

# Open ClickHouse shell
docker-shell:
	@echo "Opening ClickHouse client shell..."
	@echo "Database: signoz_traces"
	@echo "Commands: SHOW TABLES; SELECT * FROM signoz_index_v2 LIMIT 5;"
	docker-compose -f docker-compose.test.yml exec clickhouse clickhouse-client --database signoz_traces

# Clean test artifacts
clean:
	@echo "Cleaning test artifacts..."
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf **/__pycache__
	rm -rf **/*.pyc
	@echo "Cleaning Docker volumes..."
	docker-compose -f docker-compose.test.yml down -v
	@echo "Clean complete!"
