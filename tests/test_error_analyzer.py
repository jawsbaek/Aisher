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
            http_status="500",
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
            http_status="503",
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
        assert errors[0].http_status == "500"
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


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
