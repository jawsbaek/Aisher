# CLAUDE.md - AI Assistant Guide for Aisher

## Project Overview

**Aisher** is an AI-powered error log analyzer that:
1. Fetches OpenTelemetry logs from SigNoz/ClickHouse
2. Optimizes data using TOON (Token-Oriented Object Notation) format
3. Performs AI-powered root cause analysis via LLM

The key innovation is **TOON format** which reduces LLM token usage by 40-60% compared to JSON.

## Quick Commands

```bash
# Setup
./setup.sh                           # One-time setup with virtual environment

# Run application
python error_analyzer.py             # Execute main analysis pipeline

# Run tests
pytest test_error_analyzer.py -v     # All tests with verbose output
pytest test_error_analyzer.py --cov=error_analyzer --cov-report=term-missing  # With coverage

# Lint/Format
black error_analyzer.py              # Format code
ruff check error_analyzer.py         # Lint check
```

## Project Architecture

```
Aisher/
├── error_analyzer.py      # Main application (all core logic)
├── test_error_analyzer.py # Pytest test suite
├── requirements.txt       # Python dependencies
├── setup.sh              # Quick setup script
├── .env.example          # Configuration template
├── README.md             # Full documentation
├── CODE_REVIEW.md        # Bug fixes & improvements history
└── QUICK_START.md        # Quick reference guide
```

### Core Components (in error_analyzer.py)

| Component | Lines | Description |
|-----------|-------|-------------|
| `Settings` | 23-56 | Pydantic v2 configuration with SecretStr for secrets |
| `ErrorLog` | 59-78 | Data model for error logs (TOON-optimized fields) |
| `ToonFormatter` | 81-155 | TOON format encoder with smart escaping |
| `SigNozRepository` | 158-276 | Async ClickHouse client with connection pooling |
| `BatchAnalyzer` | 278-374 | LLM integration with retry logic |
| `main()` | 377-418 | Orchestrator with resource management |

## Code Conventions

### Python Style
- **Python version**: 3.10+
- **Type hints**: Required on all public functions
- **Async/await**: Used for I/O operations (ClickHouse, LLM)
- **Formatter**: Black (line length 88)
- **Linter**: Ruff

### Pydantic Conventions
- Use Pydantic v2 (`BaseModel`, `BaseSettings`)
- Use `SecretStr` for sensitive data (API keys, passwords)
- Use `Field(...)` with descriptions for documentation
- Settings loaded from `.env` file

### Async Patterns
```python
# Always use context manager pattern for resources
async def main():
    repo = SigNozRepository()
    try:
        # ... operations
    finally:
        await repo.close()

# Use asyncio.wait_for for timeouts
result = await asyncio.wait_for(
    operation(),
    timeout=settings.TIMEOUT
)
```

### Error Handling
- Return empty list `[]` on query failures (not exceptions)
- Use structured logging (`logger.error()`, not `print()`)
- Include `exc_info=True` for unexpected errors
- Retry with exponential backoff for transient failures

### TOON Format Rules
When modifying TOON formatter:
1. Escape order matters: `\` first, then `"`, then `\n`, `\r`, `\t`
2. Quote strings containing: delimiter, leading/trailing spaces, structural chars `{}:[]`
3. Delimiter selection: Use `|` if commas appear 2x more than pipes in data
4. Header format: `array_name[count|delimiter]{col1,col2,...}:`

## Environment Configuration

Required environment variables (in `.env`):
```bash
# ClickHouse (required)
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=your_password
CLICKHOUSE_DATABASE=signoz_traces

# LLM (required)
LLM_MODEL=gpt-4-turbo          # or gpt-4o, claude-sonnet-4-5-20250929, ollama/llama3
OPENAI_API_KEY=sk-your-key     # or ANTHROPIC_API_KEY for Claude

# Performance (optional)
QUERY_TIMEOUT=30
LLM_TIMEOUT=45
MAX_RETRIES=3
STACK_MAX_LENGTH=600
```

## Testing Guidelines

### Test Structure
- `TestToonFormatter`: Unit tests for TOON format generation
- `TestSigNozRepository`: Repository layer tests (requires ClickHouse or mocks)
- `TestBatchAnalyzer`: LLM integration tests (skipped by default)
- `TestIntegration`: End-to-end tests with mocks
- `TestPerformance`: Performance benchmarks

### Running Specific Tests
```bash
# Single test class
pytest test_error_analyzer.py::TestToonFormatter -v

# Single test method
pytest test_error_analyzer.py::TestToonFormatter::test_format_tabular_basic -v

# Skip LLM tests (no API key)
pytest test_error_analyzer.py -v -k "not analyze_batch"
```

### Mock Patterns
```python
@pytest.mark.asyncio
async def test_with_mock(monkeypatch):
    async def mock_fetch(*args, **kwargs):
        return [ErrorLog(...)]

    repo = SigNozRepository()
    monkeypatch.setattr(repo, "fetch_errors", mock_fetch)
```

## Common Tasks

### Adding a New Field to ErrorLog
1. Add field to `ErrorLog` model with `Field(...)` descriptor
2. Update SQL query in `SigNozRepository.fetch_errors()`
3. Update column unpacking in fetch result handler
4. Add test case in `TestToonFormatter`

### Changing LLM Provider
1. Update `LLM_MODEL` in `.env` (litellm supports 100+ providers)
2. Set appropriate API key env var
3. Test with: `pytest test_error_analyzer.py::TestBatchAnalyzer -v`

### Modifying ClickHouse Query
1. Update query in `SigNozRepository.fetch_errors()`
2. Ensure parameterized queries (no f-string interpolation for user inputs)
3. Update column mapping in result handler
4. Test connection: `python -c "from error_analyzer import ..."`

## Security Considerations

- **Never** commit `.env` file (it's in `.gitignore`)
- **Always** use `SecretStr` for credentials
- **Always** use parameterized queries for ClickHouse
- **Never** log secret values (use `settings.API_KEY.get_secret_value()` only when needed)
- Stack traces may contain sensitive data - truncation helps limit exposure

## Dependencies

Core:
- `clickhouse-connect==0.7.0` - Async ClickHouse client
- `litellm==1.30.0` - Universal LLM API (supports OpenAI, Anthropic, Ollama, etc.)
- `pydantic==2.6.0` - Data validation
- `pydantic-settings==2.1.0` - Settings management

Dev:
- `pytest==7.4.0` - Testing framework
- `pytest-asyncio==0.21.0` - Async test support
- `black==23.12.0` - Code formatter
- `ruff==0.1.0` - Linter

## Known Limitations

1. **Single-file architecture**: All code in `error_analyzer.py` - may need refactoring for larger features
2. **No connection pooling**: Single client per repository instance
3. **No caching**: Each analysis makes fresh LLM call
4. **SigNoz-specific**: Query assumes SigNoz schema (`signoz_index_v2` table)

## Debugging Tips

### Enable Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Test ClickHouse Connection
```bash
python -c "
import asyncio
from error_analyzer import SigNozRepository
async def test():
    repo = SigNozRepository()
    errors = await repo.fetch_errors(limit=1)
    print(f'Found {len(errors)} errors')
    await repo.close()
asyncio.run(test())
"
```

### Inspect TOON Output
```python
from error_analyzer import ToonFormatter, ErrorLog
errors = [ErrorLog(id='1', svc='test', op='op', msg='error', cnt=1, stack='stack')]
print(ToonFormatter.format_tabular(errors, 'test'))
```

## Git Workflow

- Main development branch: feature branches off main
- Commit message format: `type: description` (e.g., `feat: add prometheus metrics`)
- Run tests before committing: `pytest test_error_analyzer.py -v`

## External Resources

- [TOON Format Spec](https://github.com/toon-format/spec)
- [SigNoz Documentation](https://signoz.io/docs/)
- [LiteLLM Providers](https://docs.litellm.ai/docs/providers)
- [ClickHouse Python Driver](https://clickhouse.com/docs/en/integrations/python)
