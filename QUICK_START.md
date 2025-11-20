# 🎯 Quick Reference Guide

## 📁 Project Structure

```
error-analyzer/
├── error_analyzer.py      # Main application
├── test_error_analyzer.py # Test suite
├── requirements.txt       # Dependencies
├── .env.example          # Config template
├── setup.sh              # Quick setup script
├── README.md             # Full documentation
└── CODE_REVIEW.md        # Bug fixes & improvements
```

## ⚡ Quick Start

```bash
# 1. Setup (one-time)
./setup.sh

# 2. Configure
nano .env  # Add your credentials

# 3. Run
python error_analyzer.py
```

## 🔧 Common Use Cases

### 1️⃣ Analyze Last Hour's Errors
```python
import asyncio
from error_analyzer import SigNozRepository, BatchAnalyzer

async def main():
    repo = SigNozRepository()
    analyzer = BatchAnalyzer()
    
    errors = await repo.fetch_errors(limit=10, time_window_minutes=60)
    if errors:
        result = await analyzer.analyze_batch(errors)
        print(result['root_cause'])
    
    await repo.close()

asyncio.run(main())
```

### 2️⃣ Custom Time Window
```python
# Last 24 hours
errors = await repo.fetch_errors(
    limit=20, 
    time_window_minutes=1440
)
```

### 3️⃣ Export to TOON Format Only
```python
from error_analyzer import ToonFormatter, ErrorLog

errors = [ErrorLog(...)]
toon_output = ToonFormatter.format_tabular(errors, "errors")

# Save to file
with open("errors.toon", "w") as f:
    f.write(toon_output)
```

### 4️⃣ Batch Processing Multiple Windows
```python
async def hourly_analysis():
    repo = SigNozRepository()
    analyzer = BatchAnalyzer()
    
    # Analyze each hour in the last 24 hours
    for hour in range(24):
        start_min = hour * 60
        end_min = (hour + 1) * 60
        
        errors = await repo.fetch_errors(
            limit=10,
            time_window_minutes=60  # Query window
        )
        
        if errors:
            result = await analyzer.analyze_batch(errors)
            print(f"Hour {hour}: {result['severity']}")
    
    await repo.close()
```

### 5️⃣ Use Different LLM Models
```python
# In .env:
# Option 1: GPT-4o (faster, cheaper)
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-your-key

# Option 2: Claude Sonnet
LLM_MODEL=claude-sonnet-4-5-20250929
ANTHROPIC_API_KEY=sk-ant-your-key

# Option 3: Local Ollama
LLM_MODEL=ollama/llama3
# No API key needed
```

### 6️⃣ Custom Error Query
```python
class CustomRepository(SigNozRepository):
    async def fetch_critical_errors(self):
        query = """
        SELECT ...
        FROM signoz_traces.signoz_index_v2
        WHERE statusCode = 2
          AND stringMap['severity'] = 'CRITICAL'
          AND serviceName IN ('payment', 'checkout')
        """
        # ... rest of implementation
```

## 🧪 Testing Commands

```bash
# Run all tests
pytest test_error_analyzer.py -v

# Run specific test
pytest test_error_analyzer.py::TestToonFormatter::test_format_tabular_basic -v

# With coverage
pytest test_error_analyzer.py --cov=error_analyzer --cov-report=term-missing

# Performance test only
pytest test_error_analyzer.py::TestPerformance -v
```

## 🐛 Debugging

### Enable Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Test ClickHouse Connection
```python
import asyncio
from error_analyzer import SigNozRepository

async def test_connection():
    repo = SigNozRepository()
    try:
        errors = await repo.fetch_errors(limit=1)
        print(f"✅ Connection OK. Found {len(errors)} errors")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
    finally:
        await repo.close()

asyncio.run(test_connection())
```

### Test LLM Integration
```python
from error_analyzer import BatchAnalyzer, ErrorLog

async def test_llm():
    analyzer = BatchAnalyzer()
    test_errors = [
        ErrorLog(
            id="test-1",
            svc="test-svc",
            op="test-op",
            msg="Test error",
            cnt=1,
            stack="Test stack"
        )
    ]
    
    result = await analyzer.analyze_batch(test_errors)
    print(result)

import asyncio
asyncio.run(test_llm())
```

## 📊 Performance Tips

### Optimize Token Usage
```python
# 1. Reduce error limit
errors = await repo.fetch_errors(limit=5)  # Instead of 10

# 2. Truncate longer stacks
# In .env:
STACK_MAX_LENGTH=400  # Default: 600
```

### Reduce LLM Costs
```python
# Use cheaper model
LLM_MODEL=gpt-4o-mini  # ~70% cheaper than gpt-4-turbo

# Or local model (free)
LLM_MODEL=ollama/llama3
```

### Parallel Processing
```python
async def parallel_analysis():
    repo = SigNozRepository()
    analyzer = BatchAnalyzer()
    
    # Fetch multiple time windows
    tasks = [
        repo.fetch_errors(limit=10, time_window_minutes=60),
        repo.fetch_errors(limit=10, time_window_minutes=120),
    ]
    
    results = await asyncio.gather(*tasks)
    
    # Analyze each batch
    for errors in results:
        if errors:
            await analyzer.analyze_batch(errors)
```

## 🔍 TOON Format Examples

### Simple Table
```
users[3]{id,name,age}:
1,Alice,30
2,Bob,25
3,Carol,35
```

### With Special Characters
```
errors[2|]{id,msg}:
err-1|Error with, commas
err-2|"Quoted value"
```

### Complex Data
```
logs[2]{id,svc,stack}:
abc,"api-gateway","Line1\nLine2\nLine3"
def,payment,"Error at PaymentService.java:123"
```

## 📈 Monitoring Integration

### Prometheus Metrics (Future)
```python
from prometheus_client import Counter, Histogram

error_count = Counter('errors_analyzed', 'Total errors analyzed')
analysis_time = Histogram('analysis_duration_seconds', 'LLM analysis time')

# In analyzer
with analysis_time.time():
    result = await analyzer.analyze_batch(errors)
error_count.inc(len(errors))
```

### Alert on Critical Errors
```python
async def check_and_alert():
    errors = await repo.fetch_errors()
    result = await analyzer.analyze_batch(errors)
    
    if result.get('severity') == 'critical':
        # Send to Slack/PagerDuty
        await send_alert(result)
```

## 🔗 Integration Examples

### With Slack
```python
import httpx

async def send_to_slack(analysis_result):
    webhook_url = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
    
    message = {
        "text": f"🚨 Critical Error Detected",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Root Cause:* {analysis_result['root_cause']}"
                }
            }
        ]
    }
    
    async with httpx.AsyncClient() as client:
        await client.post(webhook_url, json=message)
```

### With Grafana Annotations
```python
import httpx

async def create_annotation(analysis):
    grafana_url = "http://grafana:3000/api/annotations"
    headers = {"Authorization": "Bearer YOUR_API_KEY"}
    
    annotation = {
        "time": int(datetime.now().timestamp() * 1000),
        "tags": ["error-analysis", analysis['severity']],
        "text": analysis['root_cause']
    }
    
    async with httpx.AsyncClient() as client:
        await client.post(grafana_url, json=annotation, headers=headers)
```

## 💡 Pro Tips

1. **Start with smaller time windows** (15-30 min) to validate queries
2. **Use gpt-4o for production** (good balance of speed/cost)
3. **Cache similar errors** to reduce LLM calls
4. **Monitor token usage** in LLM provider dashboard
5. **Set up alerts** for critical severity errors
6. **Review TOON output** periodically to optimize format

## 🆘 Common Errors & Solutions

| Error | Solution |
|-------|----------|
| `ClickHouse connection timeout` | Check SigNoz is running: `docker ps` |
| `Empty result set` | Increase time window: `time_window_minutes=1440` |
| `LLM timeout` | Use faster model: `LLM_MODEL=gpt-4o` |
| `Invalid JSON response` | Check LLM model supports `response_format` |
| `Token limit exceeded` | Reduce `limit` param or `STACK_MAX_LENGTH` |

---

**Need Help?** Check full documentation in `README.md`
