# CLAUDE.md - AI Assistant Guide for Aisher

## Project Overview

**Aisher** is an AI-powered error log analyzer that:
1. Fetches OpenTelemetry logs from SigNoz/ClickHouse
2. Optimizes data using TOON (Token-Oriented Object Notation) format
3. Performs AI-powered root cause analysis via LLM

The key innovation is **TOON format** which reduces LLM token usage by 40-60% compared to JSON.

## Quick Commands

```bash
# Setup (one-time)
uv sync                              # Install dependencies and create virtual environment
uv sync --dev                        # Install with dev dependencies (testing, linting)

# Run application
uv run python -m aisher.main         # Execute main analysis pipeline

# Run tests
uv run pytest -v                     # All tests with verbose output
uv run pytest --cov=aisher --cov-report=term-missing  # With coverage

# Lint/Format
uv run black src/ tests/             # Format code
uv run ruff check src/ tests/        # Lint check

# Dependency management
uv add <package>                     # Add new dependency
uv add --dev <package>               # Add dev dependency
uv lock                              # Update lock file
```

## Project Architecture

```
Aisher/
├── src/aisher/            # Main application package
│   ├── __init__.py       # Package initialization
│   ├── config.py         # Settings and logging configuration
│   ├── models.py         # Data models (ErrorLog)
│   ├── toon_formatter.py # TOON format encoder
│   ├── repository.py     # SigNoz/ClickHouse repository
│   ├── analyzer.py       # LLM batch analyzer
│   └── main.py           # Main execution pipeline
├── tests/                 # Test suite
│   └── test_error_analyzer.py
├── pyproject.toml        # uv package configuration
├── uv.lock               # Locked dependencies (auto-generated)
├── requirements.txt      # Legacy pip requirements (kept for compatibility)
├── setup.sh              # Legacy setup script
├── .env.example          # Configuration template
├── README.md             # Full documentation
├── CODE_REVIEW.md        # Bug fixes & improvements history
└── QUICK_START.md        # Quick reference guide
```

### Core Components

| Module | Component | Description |
|--------|-----------|-------------|
| `config.py` | `Settings` | Pydantic v2 configuration with SecretStr for secrets |
| `config.py` | `logger` | Structured logging with colored console output |
| `models.py` | `ErrorLog` | Data model for error logs (TOON-optimized fields) |
| `toon_formatter.py` | `ToonFormatter` | TOON format encoder with smart escaping |
| `repository.py` | `SigNozRepository` | Async ClickHouse client with connection pooling |
| `analyzer.py` | `BatchAnalyzer` | LLM integration with retry logic |
| `main.py` | `main()` | Orchestrator with resource management |

## Code Conventions

### Python Style
- **Python version**: 3.10+
- **Package manager**: uv (fast, modern Python package installer)
- **Package structure**: `src/aisher/` layout (PEP 420)
- **Type hints**: Required on all public functions
- **Async/await**: Used for I/O operations (ClickHouse, LLM)
- **Formatter**: Black (line length 100)
- **Linter**: Ruff (line length 100)

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

## SigNoz ClickHouse Database Schema

This project queries the SigNoz ClickHouse backend. Understanding the schema is essential for writing custom queries.

### Database Overview

SigNoz uses three main databases:

| Database | Purpose | Primary Tables |
|----------|---------|----------------|
| `signoz_traces` | Distributed tracing data | `signoz_index_v2`, `signoz_spans`, `signoz_error_index_v2` |
| `signoz_logs` | Log aggregation | `logs_v2` |
| `signoz_metrics` | Metrics storage | `samples_v4`, `time_series_v4` |

> **Note**: For distributed deployments, use `distributed_` prefix (e.g., `distributed_signoz_index_v2`)

### signoz_traces.signoz_index_v2 (Used by this project)

This is the main traces table queried by `SigNozRepository.fetch_errors()`.

**Core Columns:**
| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | DateTime64(9) | Span timestamp (nanoseconds) |
| `traceID` | FixedString(32) | Unique trace identifier |
| `spanID` | String | Unique span identifier |
| `parentSpanID` | String | Parent span ID (empty for root) |
| `serviceName` | LowCardinality(String) | Service name (e.g., `api-gateway`) |
| `name` | LowCardinality(String) | Operation/span name |
| `kind` | Int8 | Span kind (0=Unspecified, 1=Internal, 2=Server, 3=Client, 4=Producer, 5=Consumer) |
| `durationNano` | UInt64 | Span duration in nanoseconds |
| `statusCode` | Int16 | Status (0=Unset, 1=Ok, **2=Error**) |
| `externalHttpMethod` | LowCardinality(String) | HTTP method |
| `externalHttpUrl` | LowCardinality(String) | HTTP URL |
| `dbSystem` | LowCardinality(String) | Database system (mysql, postgresql, etc.) |
| `dbName` | LowCardinality(String) | Database name |
| `rpcMethod` | LowCardinality(String) | RPC method (replaces deprecated `gRPCMethod`) |
| `responseStatusCode` | String | HTTP/gRPC response code |

**Tag Map Columns (for custom attributes):**
| Column | Type | Usage |
|--------|------|-------|
| `stringTagMap` | Map(String, String) | String attributes (e.g., `exception.message`) |
| `numberTagMap` | Map(String, Float64) | Numeric attributes |
| `boolTagMap` | Map(String, Bool) | Boolean attributes |

**Current Query Pattern (src/aisher/repository.py):**
```sql
SELECT
    any(traceID) as id,
    any(serviceName) as svc,
    any(name) as op,
    stringTagMap['exception.message'] as msg,
    count(*) as cnt,
    any(stringTagMap['exception.stacktrace']) as raw_stack
FROM signoz_traces.signoz_index_v2
WHERE statusCode = 2                              -- Error status
  AND timestamp > now() - INTERVAL ? MINUTE
  AND stringTagMap['exception.message'] != ''
GROUP BY stringTagMap['exception.message']
ORDER BY cnt DESC
LIMIT ?
```

**Common Exception Attributes in stringTagMap:**
- `exception.message` - Error message text
- `exception.stacktrace` - Full stack trace
- `exception.type` - Exception class name

### signoz_logs.logs_v2

**Core Columns:**
| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | UInt64 | Log timestamp (nanoseconds) |
| `observed_timestamp` | UInt64 | When log was observed |
| `id` | String | Unique log ID |
| `trace_id` | String | Associated trace ID |
| `span_id` | String | Associated span ID |
| `severity_text` | LowCardinality(String) | Log level (INFO, WARN, ERROR, etc.) |
| `severity_number` | UInt8 | Numeric severity (1-24) |
| `body` | String | Log message content |
| `attributes_string` | Map(String, String) | String log attributes |
| `attributes_number` | Map(String, Float64) | Numeric log attributes |
| `attributes_bool` | Map(String, Bool) | Boolean log attributes |
| `resources_string` | Map(String, String) | Resource attributes |
| `scope_name` | String | Instrumentation scope |

**Example Query:**
```sql
SELECT timestamp, severity_text, body, attributes_string
FROM signoz_logs.logs_v2
WHERE severity_text IN ('ERROR', 'FATAL')
  AND timestamp > now() - INTERVAL 1 HOUR
ORDER BY timestamp DESC
LIMIT 100
```

### signoz_metrics.samples_v4

**Columns:**
| Column | Type | Description |
|--------|------|-------------|
| `env` | LowCardinality(String) | Environment (default: 'default') |
| `temporality` | LowCardinality(String) | 'Unspecified' (gauge) or 'Cumulative' (counter) |
| `metric_name` | LowCardinality(String) | Metric name |
| `fingerprint` | UInt64 | Unique label set identifier |
| `unix_milli` | Int64 | Timestamp in milliseconds |
| `value` | Float64 | Metric value |

**Related Tables:**
- `time_series_v4` - Label sets (1 hour granularity)
- `time_series_v4_6hrs` - Label sets (6 hour granularity)
- `time_series_v4_1day` - Label sets (1 day granularity)

**Example Query (join pattern):**
```sql
SELECT ts.metric_name, samples.unix_milli, samples.value
FROM signoz_metrics.distributed_time_series_v4 ts
JOIN signoz_metrics.distributed_samples_v4 samples
  ON ts.fingerprint = samples.fingerprint
WHERE ts.metric_name = 'http_server_duration_bucket'
  AND samples.unix_milli > toUnixTimestamp(now() - INTERVAL 1 HOUR) * 1000
```

### Schema Version Notes

| Version | Changes |
|---------|---------|
| v2 → v3 | Added `ts_bucket_start` for faster timestamp filtering |
| tagMap split | `tagMap` → `stringTagMap`, `numberTagMap`, `boolTagMap` |
| HTTP/gRPC | `gRPCMethod` → `rpcMethod`, `httpCode`+`gRPCCode` → `responseStatusCode` |

### Query Performance Tips

1. **Use distributed tables** for multi-shard deployments: `distributed_signoz_index_v2`
2. **Filter early** with `WHERE` clauses on indexed columns (`timestamp`, `serviceName`, `statusCode`)
3. **Use `ts_bucket_start`** in v3 schema for timestamp range queries
4. **Avoid full table scans** on Map columns when possible
5. **Parameterize queries** to prevent SQL injection (see `SigNozRepository.fetch_errors()`)

### References

- [SigNoz Traces Query Guide](https://signoz.io/docs/userguide/writing-clickhouse-traces-query/)
- [SigNoz Logs Query Guide](https://signoz.io/docs/userguide/logs_clickhouse_queries/)
- [SigNoz Metrics Query Guide](https://signoz.io/docs/userguide/write-a-metrics-clickhouse-query/)
- [ClickHouse Schema Discussion](https://github.com/SigNoz/signoz/issues/3899)

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
uv run pytest tests/test_error_analyzer.py::TestToonFormatter -v

# Single test method
uv run pytest tests/test_error_analyzer.py::TestToonFormatter::test_format_tabular_basic -v

# Skip LLM tests (no API key)
uv run pytest -v -k "not analyze_batch"

# Run all tests with coverage
uv run pytest --cov=aisher --cov-report=html
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
1. Add field to `ErrorLog` model in `src/aisher/models.py` with `Field(...)` descriptor
2. Update SQL query in `src/aisher/repository.py` (`SigNozRepository.fetch_errors()`)
3. Update column unpacking in fetch result handler
4. Add test case in `tests/test_error_analyzer.py` (`TestToonFormatter`)
5. Run tests: `uv run pytest -v`

### Changing LLM Provider
1. Update `LLM_MODEL` in `.env` (litellm supports 100+ providers)
2. Set appropriate API key env var
3. Test with: `uv run pytest tests/test_error_analyzer.py::TestBatchAnalyzer -v`

### Modifying ClickHouse Query
1. Update query in `src/aisher/repository.py` (`SigNozRepository.fetch_errors()`)
2. Ensure parameterized queries (no f-string interpolation for user inputs)
3. Update column mapping in result handler
4. Test connection: `uv run python -c "from aisher.repository import SigNozRepository; import asyncio; asyncio.run(SigNozRepository().fetch_errors(limit=1))"`

### Adding a New Dependency
```bash
# Production dependency
uv add <package-name>

# Development dependency
uv add --dev <package-name>

# Update lock file after manual pyproject.toml edits
uv lock
```

## Security Considerations

- **Never** commit `.env` file (it's in `.gitignore`)
- **Always** use `SecretStr` for credentials
- **Always** use parameterized queries for ClickHouse
- **Never** log secret values (use `settings.API_KEY.get_secret_value()` only when needed)
- Stack traces may contain sensitive data - truncation helps limit exposure

## Dependencies

Dependencies are managed via `uv` and defined in `pyproject.toml`.

**Core dependencies** (production):
- `clickhouse-connect` - Async ClickHouse client
- `litellm` - Universal LLM API (supports OpenAI, Anthropic, Ollama, etc.)
- `pydantic` - Data validation
- `pydantic-settings` - Settings management
- `aiohttp` - Async HTTP client
- `httpx` - Modern HTTP client
- `prometheus-client` - Metrics collection

**Dev dependencies** (optional):
- `pytest` - Testing framework
- `pytest-asyncio` - Async test support
- `pytest-cov` - Code coverage
- `black` - Code formatter
- `ruff` - Linter

Install all dependencies:
```bash
uv sync --dev  # Install all dependencies including dev tools
uv sync        # Install production dependencies only
```

## Known Limitations

1. **Modular architecture**: Code is split into modules in `src/aisher/` - well-organized but still a small project
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
uv run python -c "
import asyncio
from aisher.repository import SigNozRepository
async def test():
    repo = SigNozRepository()
    errors = await repo.fetch_errors(limit=1)
    print(f'Found {len(errors)} errors')
    await repo.close()
asyncio.run(test())
"
```

### Inspect TOON Output
```bash
uv run python -c "
from aisher.toon_formatter import ToonFormatter
from aisher.models import ErrorLog
errors = [ErrorLog(id='1', svc='test', op='op', msg='error', cnt=1, stack='stack')]
print(ToonFormatter.format_tabular(errors, 'test'))
"
```

### Run the Application
```bash
# With uv (recommended)
uv run python -m aisher.main

# Or activate virtual environment first
source .venv/bin/activate  # Linux/Mac
python -m aisher.main
```

## Git Workflow

- Main development branch: feature branches off main
- Commit message format: `type: description` (e.g., `feat: add prometheus metrics`)
- Run tests before committing: `uv run pytest -v`
- Format code before committing: `uv run black src/ tests/ && uv run ruff check src/ tests/`

## uv Package Manager

This project uses [uv](https://github.com/astral-sh/uv) - an extremely fast Python package installer and resolver written in Rust.

### Key Benefits
- **Speed**: 10-100x faster than pip
- **Reliability**: Deterministic dependency resolution with `uv.lock`
- **Compatibility**: Drop-in replacement for pip and pip-tools
- **Modern**: Built-in virtual environment management

### Virtual Environment Location
uv creates virtual environments in `.venv/` by default (gitignored). The environment is automatically created on first `uv sync`.

### Common uv Commands
```bash
uv sync              # Install/sync dependencies from pyproject.toml
uv add <package>     # Add dependency to pyproject.toml and install
uv remove <package>  # Remove dependency
uv pip list          # List installed packages
uv pip show <pkg>    # Show package details
uv run <command>     # Run command in virtual environment
uv lock              # Update uv.lock file
```

### Migration from pip/venv
If you're used to traditional Python workflows:
- `python -m venv .venv` → automatic with `uv sync`
- `pip install -r requirements.txt` → `uv sync`
- `pip install <package>` → `uv add <package>`
- `source .venv/bin/activate && python` → `uv run python`

## External Resources

- [uv Documentation](https://github.com/astral-sh/uv)
- [TOON Format Spec](https://github.com/toon-format/spec)
- [SigNoz Documentation](https://signoz.io/docs/)
- [LiteLLM Providers](https://docs.litellm.ai/docs/providers)
- [ClickHouse Python Driver](https://clickhouse.com/docs/en/integrations/python)
