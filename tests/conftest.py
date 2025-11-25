"""
Pytest configuration and shared fixtures for Aisher tests.
"""

import pytest


def pytest_addoption(parser):
    """Add custom command line options"""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests that require Docker services"
    )


def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests requiring Docker (deselect with '-m \"not integration\"')"
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless --integration flag is provided"""
    if config.getoption("--integration"):
        # --integration given in CLI: run all tests including integration
        return

    # Skip integration tests by default
    skip_integration = pytest.mark.skip(reason="Need --integration option to run (or run: docker-compose -f docker-compose.test.yml up -d)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
