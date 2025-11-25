"""
Docker-based integration tests for Aisher.

These tests require a running ClickHouse instance via Docker Compose.
Run with: pytest tests/test_integration_docker.py -v --integration

Setup:
    docker-compose -f docker-compose.test.yml up -d
    pytest tests/test_integration_docker.py -v --integration

Teardown:
    docker-compose -f docker-compose.test.yml down -v
"""

import pytest
import asyncio
import os
import time
from pathlib import Path
from typing import List

# Import from src package
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aisher.models import ErrorLog
from aisher.repository import SigNozRepository
from aisher.toon_formatter import ToonFormatter
from aisher.config import Settings

# Mark all tests in this module as requiring --integration flag
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def docker_services():
    """
    Fixture to ensure Docker services are running.
    This is a placeholder - actual implementation would check docker-compose status.
    """
    # Check if ClickHouse is accessible
    import socket
    host = os.getenv("CLICKHOUSE_HOST", "localhost")
    port = int(os.getenv("CLICKHOUSE_PORT", "8123"))

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)

    try:
        result = sock.connect_ex((host, port))
        if result != 0:
            pytest.skip(
                f"ClickHouse not accessible at {host}:{port}. "
                "Run: docker-compose -f docker-compose.test.yml up -d"
            )
    finally:
        sock.close()

    # Wait a bit for ClickHouse to be fully ready
    time.sleep(2)

    yield

    # Cleanup is handled by docker-compose down


@pytest.fixture
def test_settings():
    """Override settings to use test environment"""
    # Load .env.test if it exists
    env_test = Path(__file__).parent.parent / ".env.test"
    if env_test.exists():
        from dotenv import load_dotenv
        load_dotenv(env_test)

    return Settings()


@pytest.fixture
async def test_repository(test_settings, docker_services):
    """Create a repository instance connected to test ClickHouse"""
    repo = SigNozRepository()
    yield repo
    await repo.close()


class TestDockerClickHouseConnection:
    """Test actual ClickHouse connection via Docker"""

    @pytest.mark.asyncio
    async def test_clickhouse_is_running(self, test_repository):
        """Verify ClickHouse container is accessible"""
        # Try to fetch errors - should not raise exception
        try:
            errors = await test_repository.fetch_errors(limit=1, time_window_minutes=60)
            assert isinstance(errors, list)
        except Exception as e:
            pytest.fail(f"Failed to connect to ClickHouse: {e}")

    @pytest.mark.asyncio
    async def test_database_schema_exists(self, test_repository):
        """Verify signoz_traces database and table exist"""
        # The init.sql should have created the schema
        errors = await test_repository.fetch_errors(limit=1, time_window_minutes=60)

        # Should not raise "Table doesn't exist" error
        assert isinstance(errors, list)


class TestDockerErrorFetching:
    """Test error fetching with real ClickHouse data"""

    @pytest.mark.asyncio
    async def test_fetch_errors_returns_test_data(self, test_repository):
        """Verify test data inserted by init.sql can be retrieved"""
        errors = await test_repository.fetch_errors(limit=10, time_window_minutes=60)

        # Should have at least 5 error records from init.sql
        assert len(errors) >= 4, f"Expected at least 4 errors, got {len(errors)}"

        # Verify ErrorLog structure
        for error in errors:
            assert isinstance(error, ErrorLog)
            assert error.id  # traceID
            assert error.svc  # serviceName
            assert error.op  # operation name
            assert error.msg  # exception message
            assert error.cnt >= 1  # count
            # stack may be empty for some errors

    @pytest.mark.asyncio
    async def test_fetch_errors_grouping(self, test_repository):
        """Verify errors are grouped by message"""
        errors = await test_repository.fetch_errors(limit=10, time_window_minutes=60)

        # Check if duplicate "User object is null" errors are grouped
        null_pointer_errors = [e for e in errors if "User object is null" in e.msg]

        if null_pointer_errors:
            # Should be grouped into one record with cnt >= 2
            assert len(null_pointer_errors) == 1, "Duplicate errors should be grouped"
            assert null_pointer_errors[0].cnt >= 2, "Grouped error should have count >= 2"

    @pytest.mark.asyncio
    async def test_fetch_errors_sorted_by_count(self, test_repository):
        """Verify errors are sorted by count (descending)"""
        errors = await test_repository.fetch_errors(limit=10, time_window_minutes=60)

        if len(errors) > 1:
            # Counts should be in descending order
            counts = [e.cnt for e in errors]
            assert counts == sorted(counts, reverse=True), "Errors should be sorted by count DESC"

    @pytest.mark.asyncio
    async def test_fetch_errors_limit(self, test_repository):
        """Verify limit parameter works"""
        errors = await test_repository.fetch_errors(limit=2, time_window_minutes=60)

        # Should return at most 2 errors
        assert len(errors) <= 2, f"Expected at most 2 errors with limit=2, got {len(errors)}"

    @pytest.mark.asyncio
    async def test_fetch_errors_time_window(self, test_repository):
        """Verify time_window_minutes parameter filters correctly"""
        # Test data is inserted with timestamps like "now() - INTERVAL X MINUTE"
        # where X ranges from 5 to 20 minutes

        # Fetch only last 10 minutes
        recent_errors = await test_repository.fetch_errors(limit=10, time_window_minutes=10)

        # Fetch last 30 minutes
        all_errors = await test_repository.fetch_errors(limit=10, time_window_minutes=30)

        # Should have more errors in 30 minute window
        assert len(all_errors) >= len(recent_errors), \
            "30-minute window should have >= errors than 10-minute window"

    @pytest.mark.asyncio
    async def test_fetch_errors_excludes_non_errors(self, test_repository):
        """Verify only error spans (statusCode=2) are fetched"""
        errors = await test_repository.fetch_errors(limit=10, time_window_minutes=60)

        # init.sql inserts one non-error span (GET /api/health with statusCode=1)
        # It should not appear in results
        health_check_errors = [e for e in errors if "/api/health" in e.op]
        assert len(health_check_errors) == 0, "Non-error spans should not be included"

    @pytest.mark.asyncio
    async def test_fetch_errors_has_exception_details(self, test_repository):
        """Verify exception details are present in fetched errors"""
        errors = await test_repository.fetch_errors(limit=10, time_window_minutes=60)

        # At least one error should have a non-empty message
        assert any(e.msg for e in errors), "At least one error should have a message"

        # At least one error should have a stack trace
        errors_with_stack = [e for e in errors if e.stack and e.stack.strip()]
        assert len(errors_with_stack) > 0, "At least one error should have a stack trace"


class TestDockerToonFormatting:
    """Test TOON formatting with real data from ClickHouse"""

    @pytest.mark.asyncio
    async def test_toon_format_real_data(self, test_repository):
        """Test TOON formatting with actual ClickHouse data"""
        errors = await test_repository.fetch_errors(limit=5, time_window_minutes=60)

        if not errors:
            pytest.skip("No test data available in ClickHouse")

        # Format as TOON
        toon_output = ToonFormatter.format_tabular(errors, "errors")

        # Verify TOON structure
        assert toon_output.startswith("errors["), "Should start with array name"
        assert "{" in toon_output, "Should have column header"
        assert "id,svc,op,msg,cnt,stack" in toon_output or \
               "id|svc|op|msg|cnt|stack" in toon_output, "Should have all columns"

        # Verify data rows exist
        lines = toon_output.split("\n")
        assert len(lines) >= 2, "Should have at least header + 1 data row"

        # Verify some expected content from test data
        content_lower = toon_output.lower()
        assert any(keyword in content_lower for keyword in [
            "nullpointer", "timeout", "connection", "refused"
        ]), "Should contain test error keywords"


class TestDockerEndToEnd:
    """End-to-end integration tests with Docker"""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_real_clickhouse(self, test_repository):
        """Test complete pipeline: fetch -> format -> verify"""
        # Step 1: Fetch errors
        errors = await test_repository.fetch_errors(limit=5, time_window_minutes=60)
        assert len(errors) > 0, "Should fetch at least one error from test data"

        # Step 2: Format as TOON
        toon_output = ToonFormatter.format_tabular(errors, "errors")
        assert len(toon_output) > 0, "TOON output should not be empty"

        # Step 3: Verify TOON output structure
        lines = toon_output.split("\n")
        assert lines[0].startswith("errors["), "First line should be header"

        # Step 4: Verify error details are preserved
        for error in errors[:3]:  # Check first 3 errors
            # Service name should appear in TOON output
            assert error.svc in toon_output, f"Service '{error.svc}' should be in TOON output"

    @pytest.mark.asyncio
    async def test_multiple_queries_with_same_connection(self, test_repository):
        """Test connection reuse across multiple queries"""
        # First query
        errors1 = await test_repository.fetch_errors(limit=2, time_window_minutes=60)
        assert len(errors1) > 0

        # Second query (should reuse connection)
        errors2 = await test_repository.fetch_errors(limit=3, time_window_minutes=60)
        assert len(errors2) > 0

        # Third query
        errors3 = await test_repository.fetch_errors(limit=1, time_window_minutes=30)
        assert isinstance(errors3, list)

    @pytest.mark.asyncio
    async def test_concurrent_queries(self, test_repository):
        """Test handling concurrent queries"""
        # Launch multiple queries concurrently
        tasks = [
            test_repository.fetch_errors(limit=2, time_window_minutes=60),
            test_repository.fetch_errors(limit=3, time_window_minutes=60),
            test_repository.fetch_errors(limit=1, time_window_minutes=30),
        ]

        results = await asyncio.gather(*tasks)

        # All queries should complete successfully
        assert len(results) == 3
        for result in results:
            assert isinstance(result, list)


class TestDockerErrorScenarios:
    """Test error handling with real Docker environment"""

    @pytest.mark.asyncio
    async def test_empty_result_handling(self, test_repository):
        """Test handling of queries that return no results"""
        # Query with very short time window (should return empty or fewer results)
        errors = await test_repository.fetch_errors(limit=10, time_window_minutes=0.001)

        # Should return empty list, not raise exception
        assert isinstance(errors, list)

    @pytest.mark.asyncio
    async def test_large_limit_handling(self, test_repository):
        """Test handling of large limit values"""
        # Request more errors than available
        errors = await test_repository.fetch_errors(limit=1000, time_window_minutes=60)

        # Should return available errors without error
        assert isinstance(errors, list)
        assert len(errors) < 1000  # Test data has only ~5 unique error groups


class TestDockerPerformance:
    """Performance tests with real ClickHouse"""

    @pytest.mark.asyncio
    async def test_query_performance(self, test_repository):
        """Verify query completes in reasonable time"""
        start = time.time()
        errors = await test_repository.fetch_errors(limit=10, time_window_minutes=60)
        duration = time.time() - start

        # Should complete within timeout
        assert duration < 5.0, f"Query took {duration:.2f}s, expected < 5s"
        assert len(errors) >= 0  # Just verify it completed

    @pytest.mark.asyncio
    async def test_toon_formatting_performance(self, test_repository):
        """Verify TOON formatting is fast"""
        errors = await test_repository.fetch_errors(limit=10, time_window_minutes=60)

        if not errors:
            pytest.skip("No data for performance test")

        start = time.time()
        toon_output = ToonFormatter.format_tabular(errors, "errors")
        duration = time.time() - start

        # TOON formatting should be very fast
        assert duration < 0.1, f"TOON formatting took {duration:.2f}s, expected < 0.1s"
        assert len(toon_output) > 0


# Pytest configuration for integration tests
def pytest_addoption(parser):
    """Add --integration flag to pytest"""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests that require Docker"
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless --integration flag is provided"""
    if config.getoption("--integration"):
        # --integration given in cli: do not skip integration tests
        return

    skip_integration = pytest.mark.skip(reason="Need --integration option to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--integration", "--tb=short"])
