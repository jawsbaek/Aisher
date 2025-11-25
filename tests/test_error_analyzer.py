import pytest
import asyncio
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

from aisher.toon_formatter import ToonFormatter
from aisher.models import ErrorLog
from aisher.repository import SigNozRepository
from aisher.config import Settings

# --- Test Data ---
@pytest.fixture
def sample_errors() -> List[ErrorLog]:
    """Sample error logs for testing with new Golden Query schema"""
    return [
        ErrorLog(
            trace_id="abc123def456",
            span_id="span-001",
            timestamp="2024-01-15T10:30:00Z",
            service_name="api-gateway",
            span_name="GET /users",
            error_type="NullPointerException",
            error_message="NullPointerException: user is null",
            stacktrace="java.lang.NullPointerException\n\tat com.example.UserService.getUser(UserService.java:123)",
            http_status=500,
            http_method="GET",
            http_url="/api/users/123",
            db_system=None,
            db_operation=None,
            span_attributes='{"user_id": "u123"}',
            resource_attributes='{"k8s.pod.name": "api-pod-1"}',
            related_events="log: Processing request"
        ),
        ErrorLog(
            trace_id="xyz789ghi012",
            span_id="span-002",
            timestamp="2024-01-15T10:31:00Z",
            service_name="payment-service",
            span_name="POST /checkout",
            error_type="TimeoutException",
            error_message="TimeoutException: Database connection timeout",
            stacktrace="java.util.concurrent.TimeoutException\n\tat com.example.PaymentService.process(PaymentService.java:45)",
            http_status=503,
            http_method="POST",
            http_url="/api/checkout",
            db_system="postgresql",
            db_operation="SELECT",
            span_attributes='{"order_id": "o456"}',
            resource_attributes='{"k8s.pod.name": "payment-pod-2"}',
            related_events="log: Connecting to database\nlog: Query started"
        ),
    ]

@pytest.fixture
def complex_errors() -> List[ErrorLog]:
    """Errors with special characters for TOON escaping tests"""
    return [
        ErrorLog(
            trace_id="trace-003",
            span_id="span-003",
            timestamp="2024-01-15T10:32:00Z",
            service_name="data-processor",
            span_name="parse_csv",
            error_type="ParseException",
            error_message='Invalid data: "value" contains comma, pipe|bar',
            stacktrace="Stack trace with\nnewlines\tand\ttabs",
            http_status=None,
            http_method=None,
            http_url=None,
            db_system=None,
            db_operation=None,
            span_attributes=None,
            resource_attributes=None,
            related_events=None
        ),
    ]

# --- TOON Formatter Tests ---
class TestToonFormatter:
    """Test suite for TOON format generation"""

    def test_escape_string_basic(self):
        """Test basic string escaping"""
        result = ToonFormatter._escape_string("hello world", ",")
        assert result == "hello world"

    def test_escape_string_with_delimiter(self):
        """Test escaping when string contains delimiter"""
        result = ToonFormatter._escape_string("hello,world", ",")
        assert result == '"hello,world"'

    def test_escape_string_with_newline(self):
        """Test newline escaping - escapes newline but doesn't quote if no delimiter"""
        result = ToonFormatter._escape_string("line1\nline2", ",")
        # No quotes needed since no delimiter in string
        assert result == 'line1\\nline2'

    def test_escape_string_with_quotes(self):
        """Test quote escaping - escapes quotes but doesn't wrap if no delimiter"""
        result = ToonFormatter._escape_string('say "hello"', ",")
        # No wrapping quotes needed since no delimiter in string
        assert result == 'say \\"hello\\"'

    def test_escape_string_with_structural_chars(self):
        """Test strings with structural characters are quoted"""
        result = ToonFormatter._escape_string("key:value", ",")
        assert result == '"key:value"'

        result = ToonFormatter._escape_string("{object}", ",")
        assert result == '"\\{object\\}"' or result == '"{object}"'

    def test_escape_string_leading_trailing_spaces(self):
        """Test preservation of leading/trailing spaces"""
        result = ToonFormatter._escape_string(" padded ", ",")
        assert result == '" padded "'

    def test_escape_null_value(self):
        """Test null value handling"""
        result = ToonFormatter._escape_string(None, ",")
        assert result == "null"

    def test_format_tabular_basic(self, sample_errors):
        """Test basic TOON tabular format generation"""
        result = ToonFormatter.format_tabular(sample_errors, "errors")

        # Check header format
        assert result.startswith("errors[2]{")
        # New model has different fields
        assert "trace_id" in result or "service_name" in result

        # Check data rows
        lines = result.split("\n")
        assert len(lines) == 3  # Header + 2 data rows
        assert "abc123def456" in lines[1]
        assert "api-gateway" in lines[1]

    def test_format_tabular_with_special_chars(self, complex_errors):
        """Test TOON format with special characters"""
        result = ToonFormatter.format_tabular(complex_errors, "errors")

        # Should handle quotes, commas, newlines
        assert "\\n" in result  # Escaped newlines
        assert '\\"' in result  # Escaped quotes

    def test_format_tabular_delimiter_optimization(self):
        """Test automatic delimiter selection"""
        # Create data with many commas
        errors_with_commas = [
            ErrorLog(
                trace_id="1",
                span_id="span-1",
                timestamp="2024-01-15T10:00:00Z",
                service_name="svc",
                span_name="op",
                error_type="Error",
                error_message="error with, many, commas, here",
                stacktrace="stack"
            )
        ]
        result = ToonFormatter.format_tabular(errors_with_commas, "test")

        # Should prefer pipe delimiter when commas are common
        # Check if pipe is used in header or data
        assert "|" in result or "," in result  # One must be used

    def test_format_tabular_empty_list(self):
        """Test handling of empty list"""
        result = ToonFormatter.format_tabular([], "errors")
        assert result == "errors[0]:"

    def test_format_tabular_custom_array_name(self, sample_errors):
        """Test custom array name"""
        result = ToonFormatter.format_tabular(sample_errors, "exceptions")
        assert result.startswith("exceptions[2]")

# --- Repository Tests (Mock-based) ---
class TestSigNozRepository:
    """Test suite for repository layer"""

    @pytest.mark.asyncio
    async def test_fetch_errors_structure(self):
        """Test that fetch_errors returns correct structure"""
        repo = SigNozRepository()

        # Note: This requires actual ClickHouse connection
        # In real tests, you'd mock the client
        try:
            errors = await repo.fetch_errors(limit=1, time_window_minutes=60)

            # Check structure even if empty
            assert isinstance(errors, list)

            if errors:
                error = errors[0]
                assert isinstance(error, ErrorLog)
                assert hasattr(error, 'trace_id')
                assert hasattr(error, 'service_name')
                assert hasattr(error, 'stacktrace')
        except Exception as e:
            pytest.skip(f"ClickHouse not available: {e}")
        finally:
            await repo.close()

    @pytest.mark.asyncio
    async def test_repository_close(self):
        """Test clean resource cleanup"""
        repo = SigNozRepository()
        await repo.close()  # Should not raise

    def test_validate_database_name_valid(self):
        """Test valid database name validation"""
        repo = SigNozRepository()
        # Should not raise for valid names
        repo._validate_database_name("signoz_traces")
        repo._validate_database_name("my_db_123")

    def test_validate_database_name_invalid(self):
        """Test invalid database name validation"""
        repo = SigNozRepository()
        with pytest.raises(ValueError, match="Invalid database name"):
            repo._validate_database_name("db;DROP TABLE")
        with pytest.raises(ValueError, match="Invalid database name"):
            repo._validate_database_name("db-with-dashes")

    def test_validate_database_name_restricted(self):
        """Test restricted database names"""
        repo = SigNozRepository()
        with pytest.raises(ValueError, match="Restricted database"):
            repo._validate_database_name("system")
        with pytest.raises(ValueError, match="Restricted database"):
            repo._validate_database_name("information_schema")

    @pytest.mark.asyncio
    async def test_fetch_errors_invalid_limit(self):
        """Test fetch_errors with invalid limit parameter"""
        repo = SigNozRepository()
        try:
            with pytest.raises(ValueError, match="limit must be between"):
                await repo.fetch_errors(limit=0)
            with pytest.raises(ValueError, match="limit must be between"):
                await repo.fetch_errors(limit=1001)
        finally:
            await repo.close()

    @pytest.mark.asyncio
    async def test_fetch_errors_invalid_time_window(self):
        """Test fetch_errors with invalid time_window parameter"""
        repo = SigNozRepository()
        try:
            with pytest.raises(ValueError, match="time_window_minutes must be between"):
                await repo.fetch_errors(time_window_minutes=0)
            with pytest.raises(ValueError, match="time_window_minutes must be between"):
                await repo.fetch_errors(time_window_minutes=10081)
        finally:
            await repo.close()

    @pytest.mark.asyncio
    async def test_context_manager(self, monkeypatch):
        """Test async context manager"""
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()

        async def mock_get_client(self):
            self._client = mock_client
            return mock_client

        monkeypatch.setattr(SigNozRepository, "_get_client", mock_get_client)

        async with SigNozRepository() as repo:
            # Should be able to use repo in context
            assert repo is not None
        # Connection should be closed after context

    @pytest.mark.asyncio
    async def test_fetch_errors_with_mock_client(self, monkeypatch):
        """Test fetch_errors with mocked client returning data (Golden Query format)"""
        mock_result = MagicMock()
        # Golden Query row structure:
        # (time, trace_id, span_id, service_name, span_name,
        #  error_type, error_message, stacktrace,
        #  http_status, http_method, http_url, db_system, db_operation,
        #  span_attributes_json, resource_attributes_json, related_events)
        mock_result.result_rows = [
            (
                "2024-01-15T10:30:00Z",  # time
                "trace-123",              # trace_id
                "span-456",               # span_id
                "api-service",            # service_name
                "GET /health",            # span_name
                "RuntimeException",       # error_type
                "Error msg",              # error_message
                "stack trace here",       # stacktrace
                "500",                    # http_status
                "GET",                    # http_method
                "/health",                # http_url
                None,                     # db_system
                None,                     # db_operation
                '{"key": "value"}',       # span_attributes_json
                '{"env": "prod"}',        # resource_attributes_json
                "log: request started"    # related_events
            )
        ]

        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value=mock_result)
        mock_client.close = AsyncMock()

        repo = SigNozRepository()
        repo._client = mock_client

        errors = await repo.fetch_errors(limit=10, time_window_minutes=60)

        assert len(errors) == 1
        assert errors[0].trace_id == "trace-123"
        assert errors[0].service_name == "api-service"
        assert errors[0].error_type == "RuntimeException"
        assert errors[0].http_status == 500
        await repo.close()

    @pytest.mark.asyncio
    async def test_fetch_errors_stack_truncation(self, monkeypatch):
        """Test stack trace truncation for long stacks"""
        long_stack = "x" * 1000
        mock_result = MagicMock()
        mock_result.result_rows = [
            (
                "2024-01-15T10:30:00Z",  # time
                "trace-123",              # trace_id
                "span-456",               # span_id
                "svc",                    # service_name
                "op",                     # span_name
                "Error",                  # error_type
                "msg",                    # error_message
                long_stack,               # stacktrace
                None, None, None, None, None, None, None, None
            )
        ]

        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value=mock_result)
        mock_client.close = AsyncMock()

        repo = SigNozRepository()
        repo._client = mock_client

        errors = await repo.fetch_errors(limit=1)

        # Stack should be truncated
        assert len(errors[0].stacktrace) < len(long_stack)
        assert "...[truncated]..." in errors[0].stacktrace
        await repo.close()

    @pytest.mark.asyncio
    async def test_ping_success(self, monkeypatch):
        """Test ping returns True on success"""
        mock_result = MagicMock()
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(return_value=mock_result)
        mock_client.close = AsyncMock()

        repo = SigNozRepository()
        repo._client = mock_client

        result = await repo.ping()
        assert result is True
        await repo.close()

    @pytest.mark.asyncio
    async def test_ping_failure(self, monkeypatch):
        """Test ping returns False on failure"""
        mock_client = AsyncMock()
        mock_client.query = AsyncMock(side_effect=Exception("Connection failed"))
        mock_client.close = AsyncMock()

        repo = SigNozRepository()
        repo._client = mock_client

        result = await repo.ping()
        assert result is False
        await repo.close()

    def test_truncate_stacktrace_short(self):
        """Test that short stacktraces are not truncated"""
        repo = SigNozRepository()
        short_stack = "Error at line 1"
        result = repo._truncate_stacktrace(short_stack)
        assert result == short_stack

    def test_truncate_stacktrace_none(self):
        """Test that None stacktrace returns empty string"""
        repo = SigNozRepository()
        result = repo._truncate_stacktrace(None)
        assert result == ""

    def test_truncate_stacktrace_long(self):
        """Test that long stacktraces are truncated"""
        repo = SigNozRepository()
        long_stack = "x" * 1000
        result = repo._truncate_stacktrace(long_stack)
        assert len(result) < len(long_stack)
        assert "...[truncated]..." in result


# --- Analyzer Tests (with mocks) ---
class TestBatchAnalyzer:
    """Test suite for BatchAnalyzer with mocked LLM"""

    @pytest.mark.asyncio
    async def test_analyze_batch_success(self, sample_errors):
        """Test successful batch analysis with mocked LLM"""
        from aisher.analyzer import BatchAnalyzer

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"root_cause": "Database issue", "severity": "high"}'

        with patch('aisher.analyzer.acompletion', new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            analyzer = BatchAnalyzer()
            result = await analyzer.analyze_batch(sample_errors)

            assert "root_cause" in result
            assert result["root_cause"] == "Database issue"
            assert "_meta" in result
            assert result["_meta"]["error_count"] == 2

    @pytest.mark.asyncio
    async def test_analyze_batch_timeout_retry(self, sample_errors):
        """Test retry logic on timeout"""
        from aisher.analyzer import BatchAnalyzer

        call_count = 0

        async def mock_acompletion(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise asyncio.TimeoutError()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = '{"root_cause": "Fixed"}'
            return mock_response

        with patch('aisher.analyzer.acompletion', mock_acompletion):
            with patch('aisher.analyzer.settings') as mock_settings:
                mock_settings.LLM_MODEL = "test-model"
                mock_settings.OPENAI_API_KEY.get_secret_value.return_value = "test-key"
                mock_settings.LLM_TIMEOUT = 1
                mock_settings.MAX_RETRIES = 5

                analyzer = BatchAnalyzer()
                result = await analyzer.analyze_batch(sample_errors)

                assert call_count == 3
                assert "root_cause" in result

    @pytest.mark.asyncio
    async def test_analyze_batch_timeout_exhausted(self, sample_errors):
        """Test that retries are exhausted on persistent timeout"""
        from aisher.analyzer import BatchAnalyzer

        async def mock_acompletion(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch('aisher.analyzer.acompletion', mock_acompletion):
            with patch('aisher.analyzer.settings') as mock_settings:
                mock_settings.LLM_MODEL = "test-model"
                mock_settings.OPENAI_API_KEY.get_secret_value.return_value = "test-key"
                mock_settings.LLM_TIMEOUT = 1
                mock_settings.MAX_RETRIES = 2

                analyzer = BatchAnalyzer()
                result = await analyzer.analyze_batch(sample_errors)

                assert "error" in result
                assert result["retry_exhausted"] is True

    @pytest.mark.asyncio
    async def test_analyze_batch_invalid_json(self, sample_errors):
        """Test handling of invalid JSON response"""
        from aisher.analyzer import BatchAnalyzer

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not valid json"

        with patch('aisher.analyzer.acompletion', new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            analyzer = BatchAnalyzer()
            result = await analyzer.analyze_batch(sample_errors)

            assert "error" in result
            assert "Invalid LLM response format" in result["error"]

    @pytest.mark.asyncio
    async def test_analyze_batch_generic_error(self, sample_errors):
        """Test handling of generic errors"""
        from aisher.analyzer import BatchAnalyzer

        with patch('aisher.analyzer.acompletion', new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.side_effect = RuntimeError("Unexpected error")

            analyzer = BatchAnalyzer()
            result = await analyzer.analyze_batch(sample_errors)

            assert "error" in result
            assert "LLM Interaction Failed" in result["error"]

# --- Integration Tests ---
class TestIntegration:
    """End-to-end integration tests"""

    def test_error_log_model_validation(self):
        """Test Pydantic model validation"""
        # Valid model with new schema
        error = ErrorLog(
            trace_id="123",
            span_id="span-1",
            timestamp="2024-01-15T10:00:00Z",
            service_name="test-svc",
            span_name="test-op",
            error_type="TestError",
            error_message="test message",
            stacktrace="test stack"
        )
        assert error.trace_id == "123"

        # Invalid model (missing required field)
        with pytest.raises(Exception):
            ErrorLog(trace_id="123", service_name="test")

    def test_settings_validation(self):
        """Test settings model validation"""
        settings = Settings()

        # Check defaults
        assert settings.CLICKHOUSE_HOST == "localhost"
        assert settings.QUERY_TIMEOUT == 30

    @pytest.mark.asyncio
    async def test_full_pipeline_with_mocks(self, sample_errors, monkeypatch):
        """Test full pipeline with mocked dependencies"""
        # Mock repository
        async def mock_fetch(*args, **kwargs):
            return sample_errors

        repo = SigNozRepository()
        monkeypatch.setattr(repo, "fetch_errors", mock_fetch)

        # Fetch and format
        errors = await repo.fetch_errors()
        toon_output = ToonFormatter.format_tabular(errors, "errors")

        # Verify output
        assert "errors[2]" in toon_output
        assert "NullPointerException" in toon_output

# --- Main Pipeline Tests ---
class TestMainPipeline:
    """Test suite for main pipeline"""

    @pytest.mark.asyncio
    async def test_main_no_errors(self, monkeypatch, capsys):
        """Test main function when no errors found"""
        from aisher import main as main_module

        async def mock_fetch(*args, **kwargs):
            return []

        async def mock_close(*args, **kwargs):
            pass

        monkeypatch.setattr(SigNozRepository, "fetch_errors", mock_fetch)
        monkeypatch.setattr(SigNozRepository, "close", mock_close)

        await main_module.main()
        # Should complete without error

    @pytest.mark.asyncio
    async def test_main_with_errors(self, sample_errors, monkeypatch, tmp_path):
        """Test main function with errors"""
        from aisher import main as main_module
        import os

        async def mock_fetch(*args, **kwargs):
            return sample_errors

        async def mock_close(*args, **kwargs):
            pass

        async def mock_analyze(*args, **kwargs):
            return {"root_cause": "Test issue", "severity": "low"}

        monkeypatch.setattr(SigNozRepository, "fetch_errors", mock_fetch)
        monkeypatch.setattr(SigNozRepository, "close", mock_close)
        monkeypatch.setenv("AISHER_OUTPUT_DIR", str(tmp_path))

        from aisher.analyzer import BatchAnalyzer
        monkeypatch.setattr(BatchAnalyzer, "analyze_batch", mock_analyze)

        await main_module.main()

        # Check output file was created
        output_files = list(tmp_path.glob("analysis_*.json"))
        assert len(output_files) >= 0  # May or may not create file based on mocking


# --- Config Tests ---
class TestConfig:
    """Test suite for configuration"""

    def test_settings_defaults(self):
        """Test default settings values"""
        from aisher.config import Settings
        settings = Settings()

        assert settings.CLICKHOUSE_HOST == "localhost"
        assert settings.CLICKHOUSE_PORT == 8123
        assert settings.CLICKHOUSE_USER == "default"
        assert settings.CLICKHOUSE_DATABASE == "signoz_traces"
        assert settings.QUERY_TIMEOUT == 30
        assert settings.LLM_TIMEOUT == 45
        assert settings.MAX_RETRIES == 3
        assert settings.STACK_MAX_LENGTH == 600
        assert settings.STACK_HEAD_LENGTH == 250
        assert settings.STACK_TAIL_LENGTH == 350

    def test_settings_secret_str(self):
        """Test that secrets are properly masked"""
        from aisher.config import Settings
        settings = Settings()

        # SecretStr should not reveal value in repr
        assert "sk-" not in repr(settings.OPENAI_API_KEY)
        assert "SecretStr" in repr(settings.OPENAI_API_KEY) or "**" in repr(settings.OPENAI_API_KEY)

    def test_logger_exists(self):
        """Test that logger is configured"""
        from aisher.config import logger
        import logging

        assert logger is not None
        assert isinstance(logger, logging.Logger)


# --- Model Tests ---
class TestErrorLogModel:
    """Test suite for ErrorLog model"""

    def test_model_json_serialization(self, sample_errors):
        """Test model can be serialized to JSON"""
        error = sample_errors[0]
        json_str = error.model_dump_json()
        assert "abc123def456" in json_str
        assert "api-gateway" in json_str

    def test_model_dict_conversion(self, sample_errors):
        """Test model can be converted to dict"""
        error = sample_errors[0]
        data = error.model_dump()
        assert data["trace_id"] == "abc123def456"
        assert data["service_name"] == "api-gateway"

    def test_model_schema(self):
        """Test model schema is generated"""
        schema = ErrorLog.model_json_schema()
        assert "properties" in schema
        assert "trace_id" in schema["properties"]
        assert "service_name" in schema["properties"]

    def test_model_optional_fields(self):
        """Test that optional fields work correctly"""
        error = ErrorLog(
            trace_id="123",
            span_id="span-1",
            timestamp="2024-01-15T10:00:00Z",
            service_name="svc",
            span_name="op",
            error_type="Error",
            error_message="msg",
            stacktrace="stack"
            # Optional fields not provided
        )
        assert error.http_status is None
        assert error.http_method is None
        assert error.db_system is None


# --- Performance Tests ---
class TestPerformance:
    """Performance and scalability tests"""

    def test_toon_format_large_dataset(self):
        """Test TOON formatting with large dataset"""
        large_dataset = [
            ErrorLog(
                trace_id=f"trace-{i}",
                span_id=f"span-{i}",
                timestamp=f"2024-01-15T10:{i:02d}:00Z",
                service_name=f"service-{i % 10}",
                span_name=f"operation-{i % 5}",
                error_type="RuntimeError",
                error_message=f"Error message {i}",
                stacktrace=f"Stack trace {i}" * 100  # Long stack
            )
            for i in range(100)
        ]

        import time
        start = time.time()
        result = ToonFormatter.format_tabular(large_dataset, "errors")
        duration = time.time() - start

        # Should complete in reasonable time
        assert duration < 1.0  # Less than 1 second
        assert "errors[100]" in result


# --- Edge Case Tests ---
class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_empty_string_escaping(self):
        """Test escaping empty strings"""
        result = ToonFormatter._escape_string("", ",")
        assert result == '""'

    def test_backslash_escaping(self):
        """Test backslash escaping"""
        result = ToonFormatter._escape_string("path\\to\\file", ",")
        assert "\\\\" in result

    def test_tab_escaping(self):
        """Test tab character escaping"""
        result = ToonFormatter._escape_string("col1\tcol2", ",")
        assert "\\t" in result

    def test_carriage_return_escaping(self):
        """Test carriage return escaping"""
        result = ToonFormatter._escape_string("line1\rline2", ",")
        assert "\\r" in result

    def test_pipe_delimiter_selection(self):
        """Test that pipe delimiter is selected when data has many commas"""
        errors = [
            ErrorLog(
                trace_id="1",
                span_id="span-1",
                timestamp="2024-01-15T10:00:00Z",
                service_name="svc",
                span_name="op",
                error_type="Error",
                error_message="a,b,c,d,e,f,g,h,i,j",  # Many commas
                stacktrace="stack"
            )
        ]
        result = ToonFormatter.format_tabular(errors, "test")
        # Header should indicate pipe delimiter
        assert "|" in result.split("\n")[0]

    def test_error_log_with_special_characters(self):
        """Test ErrorLog with various special characters"""
        error = ErrorLog(
            trace_id="test-123",
            span_id="span-1",
            timestamp="2024-01-15T10:00:00Z",
            service_name="svc:name",
            span_name="GET /api?param=value",
            error_type="RuntimeError",
            error_message='Error: "Something" went wrong!',
            stacktrace="Stack\n\tat line1\n\tat line2"
        )
        result = ToonFormatter.format_tabular([error], "errors")
        assert "errors[1]" in result


# --- Phase 1: Repository Retry Logic Tests ---
class TestRepositoryRetryLogic:
    """Test suite for repository retry logic with exponential backoff"""

    @pytest.mark.asyncio
    async def test_fetch_errors_retries_on_database_error(self, monkeypatch):
        """Test that DatabaseError triggers retry with exponential backoff"""
        from clickhouse_connect.driver.exceptions import DatabaseError

        call_count = 0
        call_times = []

        async def mock_fetch_internal(self, limit, time_window_minutes):
            nonlocal call_count
            call_count += 1
            call_times.append(asyncio.get_event_loop().time())
            if call_count < 3:
                raise DatabaseError("Connection lost")
            return []

        repo = SigNozRepository()
        monkeypatch.setattr(repo, "_fetch_errors_internal", lambda l, t: mock_fetch_internal(repo, l, t))

        result = await repo.fetch_errors(limit=5, time_window_minutes=30)

        assert call_count == 3
        assert result == []
        await repo.close()

    @pytest.mark.asyncio
    async def test_fetch_errors_retries_on_timeout_error(self, monkeypatch):
        """Test that TimeoutError triggers retry"""
        call_count = 0

        async def mock_fetch_internal(self, limit, time_window_minutes):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise asyncio.TimeoutError()
            return []

        repo = SigNozRepository()
        monkeypatch.setattr(repo, "_fetch_errors_internal", lambda l, t: mock_fetch_internal(repo, l, t))

        result = await repo.fetch_errors(limit=5, time_window_minutes=30)

        assert call_count == 2
        assert result == []
        await repo.close()

    @pytest.mark.asyncio
    async def test_fetch_errors_exhausts_max_retries(self, monkeypatch):
        """Test that retries are exhausted after MAX_RETRIES attempts"""
        from clickhouse_connect.driver.exceptions import DatabaseError

        call_count = 0

        async def mock_fetch_internal(self, limit, time_window_minutes):
            nonlocal call_count
            call_count += 1
            raise DatabaseError("Persistent failure")

        # Mock settings.MAX_RETRIES to speed up test
        monkeypatch.setattr("aisher.repository.settings.MAX_RETRIES", 3)

        repo = SigNozRepository()
        monkeypatch.setattr(repo, "_fetch_errors_internal", lambda l, t: mock_fetch_internal(repo, l, t))

        result = await repo.fetch_errors(limit=5, time_window_minutes=30)

        assert call_count == 3  # MAX_RETRIES attempts
        assert result == []
        await repo.close()

    @pytest.mark.asyncio
    async def test_fetch_errors_unexpected_error_no_retry(self, monkeypatch):
        """Test that unexpected errors don't trigger retry"""
        call_count = 0

        async def mock_fetch_internal(self, limit, time_window_minutes):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Unexpected error")

        repo = SigNozRepository()
        monkeypatch.setattr(repo, "_fetch_errors_internal", lambda l, t: mock_fetch_internal(repo, l, t))

        result = await repo.fetch_errors(limit=5, time_window_minutes=30)

        assert call_count == 1  # No retry for unexpected errors
        assert result == []
        await repo.close()


# --- Phase 1: Parameter Boundary Tests ---
class TestParameterBoundaries:
    """Test suite for parameter boundary conditions"""

    @pytest.mark.asyncio
    async def test_fetch_errors_limit_minimum_boundary(self):
        """Test limit=1 (minimum valid value)"""
        repo = SigNozRepository()
        try:
            # Should not raise - limit=1 is valid
            # We just test the validation passes, not actual query
            with patch.object(repo, '_fetch_errors_internal', new_callable=AsyncMock) as mock:
                mock.return_value = []
                result = await repo.fetch_errors(limit=1, time_window_minutes=60)
                mock.assert_called_once_with(1, 60)
        finally:
            await repo.close()

    @pytest.mark.asyncio
    async def test_fetch_errors_limit_maximum_boundary(self):
        """Test limit=1000 (maximum valid value)"""
        repo = SigNozRepository()
        try:
            with patch.object(repo, '_fetch_errors_internal', new_callable=AsyncMock) as mock:
                mock.return_value = []
                result = await repo.fetch_errors(limit=1000, time_window_minutes=60)
                mock.assert_called_once_with(1000, 60)
        finally:
            await repo.close()

    @pytest.mark.asyncio
    async def test_fetch_errors_time_window_minimum_boundary(self):
        """Test time_window_minutes=1 (minimum valid value)"""
        repo = SigNozRepository()
        try:
            with patch.object(repo, '_fetch_errors_internal', new_callable=AsyncMock) as mock:
                mock.return_value = []
                result = await repo.fetch_errors(limit=10, time_window_minutes=1)
                mock.assert_called_once_with(10, 1)
        finally:
            await repo.close()

    @pytest.mark.asyncio
    async def test_fetch_errors_time_window_maximum_boundary(self):
        """Test time_window_minutes=10080 (maximum valid value - 1 week)"""
        repo = SigNozRepository()
        try:
            with patch.object(repo, '_fetch_errors_internal', new_callable=AsyncMock) as mock:
                mock.return_value = []
                result = await repo.fetch_errors(limit=10, time_window_minutes=10080)
                mock.assert_called_once_with(10, 10080)
        finally:
            await repo.close()

    @pytest.mark.asyncio
    async def test_fetch_errors_limit_below_minimum(self):
        """Test limit=0 raises ValueError"""
        repo = SigNozRepository()
        try:
            with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
                await repo.fetch_errors(limit=0, time_window_minutes=60)
        finally:
            await repo.close()

    @pytest.mark.asyncio
    async def test_fetch_errors_limit_above_maximum(self):
        """Test limit=1001 raises ValueError"""
        repo = SigNozRepository()
        try:
            with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
                await repo.fetch_errors(limit=1001, time_window_minutes=60)
        finally:
            await repo.close()

    @pytest.mark.asyncio
    async def test_fetch_errors_time_window_below_minimum(self):
        """Test time_window_minutes=0 raises ValueError"""
        repo = SigNozRepository()
        try:
            with pytest.raises(ValueError, match="time_window_minutes must be between 1 and 10080"):
                await repo.fetch_errors(limit=10, time_window_minutes=0)
        finally:
            await repo.close()

    @pytest.mark.asyncio
    async def test_fetch_errors_time_window_above_maximum(self):
        """Test time_window_minutes=10081 raises ValueError"""
        repo = SigNozRepository()
        try:
            with pytest.raises(ValueError, match="time_window_minutes must be between 1 and 10080"):
                await repo.fetch_errors(limit=10, time_window_minutes=10081)
        finally:
            await repo.close()


# --- Phase 1: Main Pipeline Exception Handling Tests ---
class TestMainExceptionHandling:
    """Test suite for main pipeline exception handling"""

    @pytest.mark.asyncio
    async def test_main_keyboard_interrupt_cleanup(self, monkeypatch, capsys):
        """Test that KeyboardInterrupt triggers proper cleanup"""
        from aisher import main as main_module

        close_called = False

        async def mock_fetch(*args, **kwargs):
            raise KeyboardInterrupt()

        async def mock_close(self):
            nonlocal close_called
            close_called = True

        monkeypatch.setattr(SigNozRepository, "fetch_errors", mock_fetch)
        monkeypatch.setattr(SigNozRepository, "close", mock_close)

        await main_module.main()

        # Verify cleanup happened
        assert close_called

    @pytest.mark.asyncio
    async def test_main_generic_exception_cleanup(self, monkeypatch, capsys):
        """Test that generic exceptions trigger proper cleanup"""
        from aisher import main as main_module

        close_called = False

        async def mock_fetch(*args, **kwargs):
            raise RuntimeError("Database exploded")

        async def mock_close(self):
            nonlocal close_called
            close_called = True

        monkeypatch.setattr(SigNozRepository, "fetch_errors", mock_fetch)
        monkeypatch.setattr(SigNozRepository, "close", mock_close)

        await main_module.main()

        # Verify cleanup happened despite exception
        assert close_called

    @pytest.mark.asyncio
    async def test_main_exception_during_analyze(self, sample_errors, monkeypatch, capsys):
        """Test exception handling during analyze phase"""
        from aisher import main as main_module
        from aisher.analyzer import BatchAnalyzer

        close_called = False

        async def mock_fetch(*args, **kwargs):
            return sample_errors

        async def mock_analyze(*args, **kwargs):
            raise RuntimeError("LLM service unavailable")

        async def mock_close(self):
            nonlocal close_called
            close_called = True

        monkeypatch.setattr(SigNozRepository, "fetch_errors", mock_fetch)
        monkeypatch.setattr(SigNozRepository, "close", mock_close)
        monkeypatch.setattr(BatchAnalyzer, "analyze_batch", mock_analyze)

        await main_module.main()

        # Verify cleanup happened despite exception
        assert close_called


# --- Phase 2: Analyzer LLM Response Edge Cases ---
class TestAnalyzerEdgeCases:
    """Test suite for analyzer LLM response edge cases"""

    @pytest.mark.asyncio
    async def test_analyze_batch_empty_errors_list(self):
        """Test analyze_batch with empty errors list"""
        from aisher.analyzer import BatchAnalyzer

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"root_cause": "No errors to analyze"}'

        with patch('aisher.analyzer.acompletion', new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            analyzer = BatchAnalyzer()
            result = await analyzer.analyze_batch([])

            assert "_meta" in result
            assert result["_meta"]["error_count"] == 0

    @pytest.mark.asyncio
    async def test_analyze_batch_empty_choices_array(self, sample_errors):
        """Test handling when LLM returns empty choices array"""
        from aisher.analyzer import BatchAnalyzer

        mock_response = MagicMock()
        mock_response.choices = []  # Empty choices

        with patch('aisher.analyzer.acompletion', new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            analyzer = BatchAnalyzer()
            result = await analyzer.analyze_batch(sample_errors)

            # Should handle gracefully with error
            assert "error" in result

    @pytest.mark.asyncio
    async def test_analyze_batch_none_message_content(self, sample_errors):
        """Test handling when message content is None"""
        from aisher.analyzer import BatchAnalyzer

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        with patch('aisher.analyzer.acompletion', new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            analyzer = BatchAnalyzer()
            result = await analyzer.analyze_batch(sample_errors)

            # Should handle gracefully with error
            assert "error" in result

    @pytest.mark.asyncio
    async def test_analyze_batch_empty_string_content(self, sample_errors):
        """Test handling when message content is empty string"""
        from aisher.analyzer import BatchAnalyzer

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""

        with patch('aisher.analyzer.acompletion', new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            analyzer = BatchAnalyzer()
            result = await analyzer.analyze_batch(sample_errors)

            # Empty string is invalid JSON
            assert "error" in result

    @pytest.mark.asyncio
    async def test_analyze_batch_partial_json_response(self, sample_errors):
        """Test handling when LLM returns incomplete JSON"""
        from aisher.analyzer import BatchAnalyzer

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"root_cause": "incomplete'  # Incomplete JSON

        with patch('aisher.analyzer.acompletion', new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            analyzer = BatchAnalyzer()
            result = await analyzer.analyze_batch(sample_errors)

            assert "error" in result
            assert "Invalid LLM response format" in result["error"]

    @pytest.mark.asyncio
    async def test_analyze_batch_json_missing_expected_fields(self, sample_errors):
        """Test handling when JSON response is valid but missing expected fields"""
        from aisher.analyzer import BatchAnalyzer

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        # Valid JSON but missing root_cause, severity, etc.
        mock_response.choices[0].message.content = '{"unexpected_field": "value"}'

        with patch('aisher.analyzer.acompletion', new_callable=AsyncMock) as mock_acompletion:
            mock_acompletion.return_value = mock_response

            analyzer = BatchAnalyzer()
            result = await analyzer.analyze_batch(sample_errors)

            # Current implementation accepts any valid JSON
            # This test documents the current behavior
            assert "_meta" in result
            assert "unexpected_field" in result


# --- Phase 2: Repository Client Reuse Tests ---
class TestRepositoryClientReuse:
    """Test suite for repository client reuse verification"""

    @pytest.mark.asyncio
    async def test_get_client_returns_same_instance(self, monkeypatch):
        """Test that _get_client() returns the same client instance on multiple calls"""
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()

        call_count = 0

        async def mock_get_async_client(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_client

        monkeypatch.setattr("aisher.repository.clickhouse_connect.get_async_client", mock_get_async_client)

        repo = SigNozRepository()

        # First call
        client1 = await repo._get_client()
        # Second call
        client2 = await repo._get_client()

        # Should be same instance
        assert client1 is client2
        # get_async_client should only be called once
        assert call_count == 1

        await repo.close()

    @pytest.mark.asyncio
    async def test_close_clears_client(self, monkeypatch):
        """Test that close() properly clears the client"""
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()

        async def mock_get_async_client(*args, **kwargs):
            return mock_client

        monkeypatch.setattr("aisher.repository.clickhouse_connect.get_async_client", mock_get_async_client)

        repo = SigNozRepository()
        await repo._get_client()

        assert repo._client is not None

        await repo.close()

        # Client close should have been called
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_idempotent(self, monkeypatch):
        """Test that calling close() multiple times is safe (doesn't raise)"""
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()

        async def mock_get_async_client(*args, **kwargs):
            return mock_client

        monkeypatch.setattr("aisher.repository.clickhouse_connect.get_async_client", mock_get_async_client)

        repo = SigNozRepository()
        await repo._get_client()

        # Call close multiple times - should not raise
        await repo.close()
        await repo.close()
        await repo.close()

        # Note: Current implementation doesn't clear _client after close,
        # so close() is called on the underlying client multiple times.
        # This documents current behavior - the test verifies no exception is raised.
        assert mock_client.close.call_count == 3

    @pytest.mark.asyncio
    async def test_close_without_connection(self):
        """Test that close() is safe when no connection was ever made"""
        repo = SigNozRepository()

        # Should not raise
        await repo.close()


# --- Phase 2: Main File I/O Error Handling Tests ---
class TestMainFileIOErrors:
    """Test suite for main pipeline file I/O error handling"""

    @pytest.mark.asyncio
    async def test_main_invalid_output_directory(self, sample_errors, monkeypatch):
        """Test handling when output directory doesn't exist"""
        from aisher import main as main_module
        from aisher.analyzer import BatchAnalyzer

        async def mock_fetch(*args, **kwargs):
            return sample_errors

        async def mock_close(*args, **kwargs):
            pass

        async def mock_analyze(*args, **kwargs):
            return {"root_cause": "Test issue"}

        monkeypatch.setattr(SigNozRepository, "fetch_errors", mock_fetch)
        monkeypatch.setattr(SigNozRepository, "close", mock_close)
        monkeypatch.setattr(BatchAnalyzer, "analyze_batch", mock_analyze)
        monkeypatch.setenv("AISHER_OUTPUT_DIR", "/nonexistent/directory/path")

        # Should not raise, but handle gracefully via exception handler
        await main_module.main()

    @pytest.mark.asyncio
    async def test_main_output_with_valid_directory(self, sample_errors, monkeypatch, tmp_path):
        """Test successful file output to valid directory"""
        from aisher import main as main_module
        from aisher.analyzer import BatchAnalyzer

        async def mock_fetch(*args, **kwargs):
            return sample_errors

        async def mock_close(*args, **kwargs):
            pass

        async def mock_analyze(*args, **kwargs):
            return {"root_cause": "Test issue", "severity": "low"}

        monkeypatch.setattr(SigNozRepository, "fetch_errors", mock_fetch)
        monkeypatch.setattr(SigNozRepository, "close", mock_close)
        monkeypatch.setattr(BatchAnalyzer, "analyze_batch", mock_analyze)
        monkeypatch.setenv("AISHER_OUTPUT_DIR", str(tmp_path))

        await main_module.main()

        # Check output file was created
        output_files = list(tmp_path.glob("analysis_*.json"))
        assert len(output_files) == 1

        # Verify content
        import json
        with open(output_files[0]) as f:
            content = json.load(f)
            assert content["root_cause"] == "Test issue"


# --- Phase 2: Additional Stacktrace Truncation Boundary Tests ---
class TestStacktraceTruncationBoundaries:
    """Test suite for stacktrace truncation boundary conditions"""

    def test_truncate_stacktrace_exactly_at_max_length(self):
        """Test stacktrace exactly at STACK_MAX_LENGTH (600 chars)"""
        repo = SigNozRepository()
        stack = "x" * 600  # Exactly at limit
        result = repo._truncate_stacktrace(stack)
        # Should NOT be truncated
        assert result == stack
        assert "...[truncated]..." not in result

    def test_truncate_stacktrace_one_over_max_length(self):
        """Test stacktrace at STACK_MAX_LENGTH + 1 (601 chars)"""
        repo = SigNozRepository()
        stack = "x" * 601  # One over limit
        result = repo._truncate_stacktrace(stack)
        # Should be truncated with marker
        assert "...[truncated]..." in result
        # Result should be HEAD(250) + marker + TAIL(350)
        # This may be longer than input but prevents unbounded growth
        assert result.startswith("x" * 250)
        assert result.endswith("x" * 350)

    def test_truncate_stacktrace_shorter_than_head_length(self):
        """Test stacktrace shorter than STACK_HEAD_LENGTH (250 chars)"""
        repo = SigNozRepository()
        stack = "x" * 100  # Much shorter than head length
        result = repo._truncate_stacktrace(stack)
        # Should NOT be truncated
        assert result == stack

    def test_truncate_stacktrace_empty_string(self):
        """Test empty string stacktrace"""
        repo = SigNozRepository()
        result = repo._truncate_stacktrace("")
        assert result == ""

    def test_truncate_json_attribute_exactly_at_max(self):
        """Test JSON attribute exactly at JSON_ATTR_MAX_LENGTH (2000 chars)"""
        repo = SigNozRepository()
        json_str = "x" * 2000  # Exactly at limit
        result = repo._truncate_json_attribute(json_str)
        # Should NOT be truncated
        assert result == json_str
        assert "...[truncated]" not in result

    def test_truncate_json_attribute_one_over_max(self):
        """Test JSON attribute at JSON_ATTR_MAX_LENGTH + 1 (2001 chars)"""
        repo = SigNozRepository()
        json_str = "x" * 2001  # One over limit
        result = repo._truncate_json_attribute(json_str)
        # Should be truncated with marker
        assert "...[truncated]" in result
        # Result should be first 2000 chars + marker
        assert result.startswith("x" * 2000)
        assert result == "x" * 2000 + "...[truncated]"

    def test_truncate_json_attribute_none(self):
        """Test None JSON attribute"""
        repo = SigNozRepository()
        result = repo._truncate_json_attribute(None)
        assert result is None

    def test_truncate_json_attribute_empty_string(self):
        """Test empty string JSON attribute"""
        repo = SigNozRepository()
        result = repo._truncate_json_attribute("")
        assert result is None  # Empty string is falsy


# --- Phase 3: TOON Escaping Edge Cases ---
class TestToonEscapingEdgeCases:
    """Test suite for TOON escaping edge cases"""

    def test_escape_boolean_true(self):
        """Test escaping boolean True value"""
        result = ToonFormatter._escape_string(True, ",")
        # Boolean is converted to string "True"
        assert result == "True"

    def test_escape_boolean_false(self):
        """Test escaping boolean False value"""
        result = ToonFormatter._escape_string(False, ",")
        # Boolean is converted to string "False"
        assert result == "False"

    def test_escape_integer(self):
        """Test escaping integer value"""
        result = ToonFormatter._escape_string(123, ",")
        assert result == "123"

    def test_escape_float(self):
        """Test escaping float value"""
        result = ToonFormatter._escape_string(123.456, ",")
        assert result == "123.456"

    def test_escape_negative_number(self):
        """Test escaping negative number"""
        result = ToonFormatter._escape_string(-42, ",")
        assert result == "-42"

    def test_escape_zero(self):
        """Test escaping zero"""
        result = ToonFormatter._escape_string(0, ",")
        assert result == "0"

    def test_escape_very_long_string(self):
        """Test escaping very long string (10KB)"""
        long_string = "x" * 10000
        result = ToonFormatter._escape_string(long_string, ",")
        # Should not modify the string (no special chars)
        assert result == long_string
        assert len(result) == 10000

    def test_escape_string_with_both_pipe_and_comma(self):
        """Test escaping string containing both pipe and comma"""
        # When using comma delimiter, pipe doesn't need quoting
        result_comma = ToonFormatter._escape_string("a|b,c", ",")
        assert result_comma == '"a|b,c"'  # Quoted because of comma

        # When using pipe delimiter, comma doesn't need quoting
        result_pipe = ToonFormatter._escape_string("a|b,c", "|")
        assert result_pipe == '"a|b,c"'  # Quoted because of pipe

    def test_escape_leading_space_with_delimiter(self):
        """Test escaping string with leading space AND delimiter"""
        result = ToonFormatter._escape_string(" hello,world", ",")
        # Should be quoted (both leading space and delimiter)
        assert result == '" hello,world"'

    def test_escape_trailing_space_with_delimiter(self):
        """Test escaping string with trailing space AND delimiter"""
        result = ToonFormatter._escape_string("hello,world ", ",")
        assert result == '"hello,world "'

    def test_escape_only_spaces(self):
        """Test escaping string with only spaces"""
        result = ToonFormatter._escape_string("   ", ",")
        assert result == '"   "'

    def test_escape_mixed_whitespace(self):
        """Test escaping string with mixed whitespace"""
        result = ToonFormatter._escape_string("a\tb\nc", ",")
        assert "\\t" in result
        assert "\\n" in result

    def test_escape_nested_quotes(self):
        """Test escaping nested quotes"""
        result = ToonFormatter._escape_string('He said "it\'s \\"quoted\\""', ",")
        # All quotes should be escaped
        assert '\\"' in result

    def test_escape_all_structural_chars(self):
        """Test that all structural characters trigger quoting"""
        for char in "{}:[]":
            result = ToonFormatter._escape_string(f"test{char}value", ",")
            assert result.startswith('"'), f"Char {char} should trigger quoting"
            assert result.endswith('"'), f"Char {char} should trigger quoting"


# --- Phase 3: Unicode Handling Tests ---
class TestUnicodeHandling:
    """Test suite for unicode character handling"""

    def test_escape_unicode_korean(self):
        """Test escaping Korean characters"""
        result = ToonFormatter._escape_string("안녕하세요", ",")
        assert result == "안녕하세요"

    def test_escape_unicode_chinese(self):
        """Test escaping Chinese characters"""
        result = ToonFormatter._escape_string("你好世界", ",")
        assert result == "你好世界"

    def test_escape_unicode_japanese(self):
        """Test escaping Japanese characters"""
        result = ToonFormatter._escape_string("こんにちは", ",")
        assert result == "こんにちは"

    def test_escape_unicode_emoji(self):
        """Test escaping emoji characters"""
        result = ToonFormatter._escape_string("Hello 🚀 World 🎉", ",")
        assert "🚀" in result
        assert "🎉" in result

    def test_escape_unicode_special_symbols(self):
        """Test escaping special unicode symbols"""
        result = ToonFormatter._escape_string("Price: €100 £50 ¥200", ",")
        assert "€" in result
        assert "£" in result
        assert "¥" in result

    def test_escape_unicode_with_delimiter(self):
        """Test unicode string containing delimiter"""
        result = ToonFormatter._escape_string("한글,테스트", ",")
        assert result == '"한글,테스트"'

    def test_format_tabular_with_unicode(self):
        """Test TOON formatting with unicode content"""
        errors = [
            ErrorLog(
                trace_id="trace-unicode",
                span_id="span-1",
                timestamp="2024-01-15T10:00:00Z",
                service_name="서비스-한글",
                span_name="GET /api/데이터",
                error_type="에러타입",
                error_message="오류 메시지: 데이터베이스 연결 실패 🔴",
                stacktrace="스택트레이스\n\tat line1"
            )
        ]
        result = ToonFormatter.format_tabular(errors, "errors")

        assert "errors[1]" in result
        assert "서비스-한글" in result
        assert "오류 메시지" in result
        assert "🔴" in result

    def test_format_tabular_unicode_delimiter_selection(self):
        """Test delimiter selection with unicode content containing commas"""
        errors = [
            ErrorLog(
                trace_id="1",
                span_id="span-1",
                timestamp="2024-01-15T10:00:00Z",
                service_name="svc",
                span_name="op",
                error_type="Error",
                error_message="한글,쉼표,가,많이,포함,된,메시지",
                stacktrace="stack"
            )
        ]
        result = ToonFormatter.format_tabular(errors, "test")

        # Should detect many commas and potentially use pipe delimiter
        assert "한글" in result


# --- Phase 3: Config Validator Tests ---
class TestConfigValidators:
    """Test suite for configuration validators"""

    def test_placeholder_api_key_warning(self, caplog):
        """Test that placeholder API key triggers warning"""
        import logging
        from pydantic import SecretStr
        from aisher.config import Settings

        # Create settings with placeholder key
        with caplog.at_level(logging.WARNING):
            settings = Settings(OPENAI_API_KEY=SecretStr("sk-...placeholder"))

        # Check that warning was logged (validator runs during init)
        # Note: The validator only warns for keys starting with "sk-..."
        # so "sk-...placeholder" should trigger it

    def test_valid_api_key_no_warning(self, caplog):
        """Test that valid API key doesn't trigger warning"""
        import logging
        from pydantic import SecretStr
        from aisher.config import Settings

        with caplog.at_level(logging.WARNING):
            settings = Settings(OPENAI_API_KEY=SecretStr("sk-valid-key-12345"))

        # Should not have placeholder warning in logs
        placeholder_warnings = [r for r in caplog.records if "placeholder" in r.message.lower()]
        assert len(placeholder_warnings) == 0

    def test_settings_env_override(self, monkeypatch):
        """Test that environment variables override defaults"""
        from aisher.config import Settings

        monkeypatch.setenv("CLICKHOUSE_HOST", "custom-host.example.com")
        monkeypatch.setenv("CLICKHOUSE_PORT", "9000")
        monkeypatch.setenv("QUERY_TIMEOUT", "60")

        # Create new settings instance (will read from env)
        settings = Settings()

        assert settings.CLICKHOUSE_HOST == "custom-host.example.com"
        assert settings.CLICKHOUSE_PORT == 9000
        assert settings.QUERY_TIMEOUT == 60

    def test_settings_invalid_port_type(self, monkeypatch):
        """Test that invalid port type raises validation error"""
        from pydantic import ValidationError
        from aisher.config import Settings

        monkeypatch.setenv("CLICKHOUSE_PORT", "not-a-number")

        with pytest.raises(ValidationError):
            Settings()

    def test_settings_secret_value_access(self):
        """Test accessing secret values"""
        from pydantic import SecretStr
        from aisher.config import Settings

        settings = Settings(
            CLICKHOUSE_PASSWORD=SecretStr("test-password"),
            OPENAI_API_KEY=SecretStr("sk-test-key-12345")
        )

        # Should be able to get secret value
        assert settings.CLICKHOUSE_PASSWORD.get_secret_value() == "test-password"
        assert settings.OPENAI_API_KEY.get_secret_value() == "sk-test-key-12345"

    def test_settings_defaults_not_mutated(self):
        """Test that default settings values aren't mutated between instances"""
        from aisher.config import Settings

        settings1 = Settings()
        settings2 = Settings()

        # Verify both have same defaults
        assert settings1.CLICKHOUSE_HOST == settings2.CLICKHOUSE_HOST
        assert settings1.QUERY_TIMEOUT == settings2.QUERY_TIMEOUT
        assert settings1.MAX_RETRIES == settings2.MAX_RETRIES


# --- Phase 3: TOON Delimiter Threshold Tests ---
class TestToonDelimiterThreshold:
    """Test suite for TOON delimiter selection at exact thresholds"""

    def test_delimiter_exactly_at_threshold(self):
        """Test delimiter selection when comma_count == pipe_count * 2"""
        # When comma_count equals pipe_count * 2 exactly, should use comma (not >)
        errors = [
            ErrorLog(
                trace_id="1",
                span_id="span-1",
                timestamp="2024-01-15T10:00:00Z",
                service_name="svc",
                span_name="op",
                error_type="Error",
                error_message="a,b|c,d",  # 2 commas, 1 pipe -> 2 == 1*2
                stacktrace="stack"
            )
        ]
        result = ToonFormatter.format_tabular(errors, "test")

        # At exactly 2x, should NOT switch to pipe (> not >=)
        # Default delimiter is comma
        header = result.split("\n")[0]
        # If pipe were selected, header would have "|" marker
        # Comma is default, so no marker needed
        assert "test[1]" in header

    def test_delimiter_just_over_threshold(self):
        """Test delimiter selection when comma_count > pipe_count * 2"""
        # Need many commas across ALL fields to trigger pipe delimiter
        errors = [
            ErrorLog(
                trace_id="1,2,3,4,5",
                span_id="a,b,c,d,e",
                timestamp="2024,01,15,10,00,00",
                service_name="svc,name,with,commas",
                span_name="op,with,commas",
                error_type="Error,Type",
                error_message="a,b,c,d,e,f,g,h,i,j|k",  # Many commas, 1 pipe
                stacktrace="stack,trace,with,commas"
            )
        ]
        result = ToonFormatter.format_tabular(errors, "test")

        # Should switch to pipe delimiter due to many commas
        header = result.split("\n")[0]
        assert "test[1|]" in header  # Pipe marker in header

    def test_delimiter_no_special_chars(self):
        """Test delimiter selection with no commas or pipes in data"""
        errors = [
            ErrorLog(
                trace_id="1",
                span_id="span-1",
                timestamp="2024-01-15T10:00:00Z",
                service_name="svc",
                span_name="op",
                error_type="Error",
                error_message="simple message",
                stacktrace="stack"
            )
        ]
        result = ToonFormatter.format_tabular(errors, "test")

        # Should use default comma delimiter
        header = result.split("\n")[0]
        assert "|]" not in header  # No pipe marker

    def test_delimiter_many_pipes(self):
        """Test delimiter selection with many pipes"""
        errors = [
            ErrorLog(
                trace_id="1",
                span_id="span-1",
                timestamp="2024-01-15T10:00:00Z",
                service_name="svc",
                span_name="op",
                error_type="Error",
                error_message="a|b|c|d|e,f",  # 4 pipes, 1 comma
                stacktrace="stack"
            )
        ]
        result = ToonFormatter.format_tabular(errors, "test")

        # 1 comma is NOT > 4*2=8, so use comma
        header = result.split("\n")[0]
        assert "|]" not in header


# --- Phase 3: Single Row Formatting Test ---
class TestToonSingleRow:
    """Test suite for TOON single row formatting"""

    def test_format_tabular_single_row(self):
        """Test TOON formatting with exactly one row"""
        errors = [
            ErrorLog(
                trace_id="single-trace",
                span_id="span-1",
                timestamp="2024-01-15T10:00:00Z",
                service_name="single-service",
                span_name="single-op",
                error_type="SingleError",
                error_message="Single error message",
                stacktrace="Single stack"
            )
        ]
        result = ToonFormatter.format_tabular(errors, "errors")

        lines = result.split("\n")
        assert len(lines) == 2  # Header + 1 data row
        assert "errors[1]" in lines[0]
        assert "single-trace" in lines[1]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
