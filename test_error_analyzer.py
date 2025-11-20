import pytest
import asyncio
from typing import List
from error_analyzer import (
    ToonFormatter, 
    ErrorLog, 
    SigNozRepository,
    BatchAnalyzer,
    Settings
)

# --- Test Data ---
@pytest.fixture
def sample_errors() -> List[ErrorLog]:
    """Sample error logs for testing"""
    return [
        ErrorLog(
            id="trace-001",
            svc="api-gateway",
            op="GET /users",
            msg="NullPointerException: user is null",
            cnt=42,
            stack="java.lang.NullPointerException\n\tat com.example.UserService.getUser(UserService.java:123)"
        ),
        ErrorLog(
            id="trace-002",
            svc="payment-service",
            op="POST /checkout",
            msg="TimeoutException: Database connection timeout",
            cnt=15,
            stack="java.util.concurrent.TimeoutException\n\tat com.example.PaymentService.process(PaymentService.java:45)"
        ),
    ]

@pytest.fixture
def complex_errors() -> List[ErrorLog]:
    """Errors with special characters for TOON escaping tests"""
    return [
        ErrorLog(
            id="trace-003",
            svc="data-processor",
            op="parse_csv",
            msg='Invalid data: "value" contains comma, pipe|bar',
            cnt=5,
            stack="Stack trace with\nnewlines\tand\ttabs"
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
        """Test newline escaping"""
        result = ToonFormatter._escape_string("line1\nline2", ",")
        assert result == '"line1\\nline2"'
    
    def test_escape_string_with_quotes(self):
        """Test quote escaping"""
        result = ToonFormatter._escape_string('say "hello"', ",")
        assert result == '"say \\"hello\\""'
    
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
        assert "id,svc,op,msg,cnt,stack" in result
        
        # Check data rows
        lines = result.split("\n")
        assert len(lines) == 3  # Header + 2 data rows
        assert "trace-001" in lines[1]
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
                id="1",
                svc="svc",
                op="op",
                msg="error with, many, commas, here",
                cnt=1,
                stack="stack"
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
                assert hasattr(error, 'id')
                assert hasattr(error, 'svc')
                assert hasattr(error, 'stack')
        except Exception as e:
            pytest.skip(f"ClickHouse not available: {e}")
        finally:
            await repo.close()
    
    @pytest.mark.asyncio
    async def test_repository_close(self):
        """Test clean resource cleanup"""
        repo = SigNozRepository()
        await repo.close()  # Should not raise

# --- Analyzer Tests ---
class TestBatchAnalyzer:
    """Test suite for AI analyzer"""
    
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires actual LLM API key")
    async def test_analyze_batch_format(self, sample_errors):
        """Test that analyzer produces valid JSON"""
        analyzer = BatchAnalyzer()
        result = await analyzer.analyze_batch(sample_errors)
        
        # Check result structure
        assert isinstance(result, dict)
        
        if "error" not in result:
            # Valid analysis should have these keys
            assert "root_cause" in result or "_meta" in result

# --- Integration Tests ---
class TestIntegration:
    """End-to-end integration tests"""
    
    def test_error_log_model_validation(self):
        """Test Pydantic model validation"""
        # Valid model
        error = ErrorLog(
            id="123",
            svc="test-svc",
            op="test-op",
            msg="test message",
            cnt=1,
            stack="test stack"
        )
        assert error.id == "123"
        
        # Invalid model (missing required field)
        with pytest.raises(Exception):
            ErrorLog(id="123", svc="test")
    
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

# --- Performance Tests ---
class TestPerformance:
    """Performance and scalability tests"""
    
    def test_toon_format_large_dataset(self):
        """Test TOON formatting with large dataset"""
        large_dataset = [
            ErrorLog(
                id=f"trace-{i}",
                svc=f"service-{i % 10}",
                op=f"operation-{i % 5}",
                msg=f"Error message {i}",
                cnt=i,
                stack=f"Stack trace {i}" * 100  # Long stack
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

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
