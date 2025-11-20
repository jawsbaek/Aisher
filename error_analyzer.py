import asyncio
import json
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

# Libraries
import clickhouse_connect
from clickhouse_connect.driver.exceptions import DatabaseError, Error as ClickHouseError
from litellm import acompletion
from pydantic import BaseModel, Field, SecretStr, validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- 1. Settings (Pydantic V2 & Security) ---
class Settings(BaseSettings):
    """Application configuration with security best practices"""
    CLICKHOUSE_HOST: str = "localhost"
    CLICKHOUSE_PORT: int = 8123
    CLICKHOUSE_USER: str = "default"
    CLICKHOUSE_PASSWORD: SecretStr = SecretStr("")
    CLICKHOUSE_DATABASE: str = "signoz_traces"
    
    LLM_MODEL: str = "gpt-4-turbo"
    OPENAI_API_KEY: SecretStr = SecretStr("sk-...")
    
    # Performance tuning
    QUERY_TIMEOUT: int = 30
    LLM_TIMEOUT: int = 45
    MAX_RETRIES: int = 3
    
    # Smart truncation
    STACK_MAX_LENGTH: int = 600
    STACK_HEAD_LENGTH: int = 250
    STACK_TAIL_LENGTH: int = 350

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        extra='ignore'
    )
    
    @validator('OPENAI_API_KEY')
    def validate_api_key(cls, v):
        if v.get_secret_value().startswith('sk-...'):
            logger.warning("⚠️  Using placeholder API key. Set OPENAI_API_KEY in .env")
        return v

settings = Settings()

# --- 2. Data Models ---
class ErrorLog(BaseModel):
    """Structured error log with optimized fields for LLM analysis"""
    id: str = Field(..., description="Trace ID")
    svc: str = Field(..., description="Service name")
    op: str = Field(..., description="Operation/Span name")
    msg: str = Field(..., description="Error message")
    cnt: int = Field(..., description="Occurrence count")
    stack: str = Field(..., description="Stack trace (truncated)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "abc123",
                "svc": "api-gateway",
                "op": "GET /users",
                "msg": "NullPointerException",
                "cnt": 42,
                "stack": "java.lang.NullPointerException..."
            }
        }

# --- 3. TOON Formatter (Core Engine) ---
class ToonFormatter:
    """
    TOON (Token-Oriented Object Notation) Implementation.
    Optimizes tabular data for LLM token efficiency.
    Ref: https://github.com/toon-format/spec
    """
    
    @staticmethod
    def _escape_string(value: Any, delimiter: str) -> str:
        """
        TOON string escaping rules:
        1. Newlines → \\n (preserve table structure)
        2. Quotes → \\"
        3. Quote if contains delimiter or leading/trailing spaces
        """
        if value is None:
            return "null"
            
        val_str = str(value)
        
        # Escape special characters
        val_str = (val_str
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
        )
        
        # Quote if necessary
        needs_quotes = (
            delimiter in val_str or 
            val_str.startswith(" ") or 
            val_str.endswith(" ") or 
            val_str == "" or
            any(c in val_str for c in "{}:[]")  # Structural characters
        )
        
        return f'"{val_str}"' if needs_quotes else val_str

    @classmethod
    def format_tabular(cls, data: List[BaseModel], array_name: str = "errors") -> str:
        """
        Convert Pydantic model list to TOON Tabular Array format.
        Example: errors[5]{id,svc,msg}:\nabc,api,Error\n...
        """
        if not data:
            return f"{array_name}[0]:"

        # 1. Extract dictionaries
        dicts = [item.model_dump() for item in data]
        if not dicts:
            return f"{array_name}[0]:"
            
        headers = list(dicts[0].keys())  # FIX: Use first dict's keys
        
        # 2. Cost-based delimiter optimization
        sample_text = " ".join([str(v) for row in dicts for v in row.values()])
        comma_count = sample_text.count(',')
        pipe_count = sample_text.count('|')
        
        delimiter = '|' if comma_count > pipe_count * 2 else ','
        
        # 3. Build header: array_name[count|]{col1,col2}:
        count = len(data)
        delim_marker = '|' if delimiter == '|' else ''  # Comma is default
        header_line = f"{array_name}[{count}{delim_marker}]{{{','.join(headers)}}}:"
        
        # 4. Build rows
        lines = [header_line]
        for row in dicts:
            values = [cls._escape_string(row[k], delimiter) for k in headers]
            lines.append(delimiter.join(values))
            
        return "\n".join(lines)

# --- 4. Repository (Async ClickHouse with Resource Management) ---
class SigNozRepository:
    """Async repository for SigNoz/ClickHouse integration"""
    
    def __init__(self):
        self.host = settings.CLICKHOUSE_HOST
        self.port = settings.CLICKHOUSE_PORT
        self.user = settings.CLICKHOUSE_USER
        self.password = settings.CLICKHOUSE_PASSWORD.get_secret_value()
        self.database = settings.CLICKHOUSE_DATABASE
        self._client: Optional[Any] = None

    async def _get_client(self):
        """Get or create async ClickHouse client"""
        if self._client is None:
            try:
                self._client = await clickhouse_connect.get_async_client(
                    host=self.host,
                    port=self.port,
                    username=self.user,
                    password=self.password,
                    connect_timeout=settings.QUERY_TIMEOUT
                )
                logger.info(f"✅ Connected to ClickHouse at {self.host}:{self.port}")
            except Exception as e:
                logger.error(f"❌ Failed to connect to ClickHouse: {e}")
                raise
        return self._client

    async def fetch_errors(
        self, 
        limit: int = 10, 
        time_window_minutes: int = 60
    ) -> List[ErrorLog]:
        """
        Fetch error logs with smart truncation and deduplication.
        
        Args:
            limit: Maximum number of error groups to return
            time_window_minutes: Time window for log aggregation
            
        Returns:
            List of ErrorLog objects with truncated stack traces
        """
        # Optimized query: Use exception.message for grouping (lower cardinality)
        query = f"""
        SELECT
            any(traceID) as id,
            any(serviceName) as svc,
            any(name) as op,
            stringMap['exception.message'] as msg,
            count(*) as cnt,
            any(stringMap['exception.stacktrace']) as raw_stack
        FROM {self.database}.signoz_index_v2
        WHERE statusCode = 2 
          AND timestamp > now() - INTERVAL %(time_window)s MINUTE
          AND stringMap['exception.message'] != ''
        GROUP BY stringMap['exception.message']
        ORDER BY cnt DESC
        LIMIT %(limit_val)s
        """
        
        try:
            client = await self._get_client()
            
            result = await asyncio.wait_for(
                client.query(
                    query, 
                    parameters={
                        'limit_val': limit,
                        'time_window': time_window_minutes
                    }
                ),
                timeout=settings.QUERY_TIMEOUT
            )
            
            logs = []  # FIX: Initialize list
            for row in result.result_rows:
                # FIX: Correct column mapping
                # row structure: (id, svc, op, msg, cnt, raw_stack)
                trace_id, service, operation, message, count, full_stack = row
                
                # Smart Truncation: Preserve error context
                if full_stack and len(full_stack) > settings.STACK_MAX_LENGTH:
                    stack_display = (
                        full_stack[:settings.STACK_HEAD_LENGTH] + 
                        "\n...[truncated]...\n" + 
                        full_stack[-settings.STACK_TAIL_LENGTH:]
                    )
                else:
                    stack_display = full_stack or ""

                logs.append(ErrorLog(
                    id=trace_id,
                    svc=service,
                    op=operation,
                    msg=message,
                    cnt=count,
                    stack=stack_display
                ))
            
            logger.info(f"📊 Fetched {len(logs)} error groups")
            return logs

        except asyncio.TimeoutError:
            logger.error(f"⏱️  Query timeout after {settings.QUERY_TIMEOUT}s")
            return []
        except DatabaseError as e:
            logger.error(f"❌ ClickHouse Error: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected Error: {e}", exc_info=True)
            return []
    
    async def close(self):
        """Close the ClickHouse connection"""
        if self._client:
            await self._client.close()
            logger.info("🔌 ClickHouse connection closed")

# --- 5. AI Service (TOON Optimized with Retry Logic) ---
class BatchAnalyzer:
    """AI-powered batch analysis with TOON format optimization"""
    
    async def analyze_batch(
        self, 
        errors: List[ErrorLog],
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Analyze error batch using LLM with TOON format.
        
        Args:
            errors: List of error logs to analyze
            retry_count: Current retry attempt
            
        Returns:
            Analysis result as JSON dict
        """
        # Convert to TOON format
        toon_payload = ToonFormatter.format_tabular(errors, array_name="exception_logs")
        
        # Token estimation (rough)
        token_estimate = len(toon_payload) // 4
        logger.info(f"📋 TOON Payload: {len(toon_payload)} chars (~{token_estimate} tokens)")
        
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"\n{'-'*60}\n{toon_payload}\n{'-'*60}")

        system_prompt = """You are a Principal SRE analyzing production errors.

Input format: TOON (Token-Oriented Object Notation)
- Format: array_name[count]{columns}:
- Each line after header is a data row

Task:
1. Identify the PRIMARY root cause (not symptoms)
2. Assess severity and business impact
3. Provide actionable remediation steps
4. Suggest monitoring improvements

Output as JSON:
{
  "root_cause": "string",
  "severity": "critical|high|medium|low",
  "affected_services": ["service1", "service2"],
  "remediation": {
    "immediate": ["action1", "action2"],
    "long_term": ["improvement1"]
  },
  "monitoring_gaps": ["metric1", "alert2"]
}"""
        
        try:
            response = await asyncio.wait_for(
                acompletion(
                    model=settings.LLM_MODEL,
                    api_key=settings.OPENAI_API_KEY.get_secret_value(),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Analyze these errors:\n\n{toon_payload}"}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=2000
                ),
                timeout=settings.LLM_TIMEOUT
            )
            
            content = response.choices[0].message.content
            result = json.loads(content)
            
            # Add metadata
            result["_meta"] = {
                "model": settings.LLM_MODEL,
                "analyzed_at": datetime.utcnow().isoformat(),
                "error_count": len(errors),
                "total_occurrences": sum(e.cnt for e in errors)
            }
            
            logger.info("✅ Analysis completed successfully")
            return result
            
        except asyncio.TimeoutError:
            logger.error(f"⏱️  LLM timeout after {settings.LLM_TIMEOUT}s")
            if retry_count < settings.MAX_RETRIES:
                logger.info(f"🔄 Retrying... ({retry_count + 1}/{settings.MAX_RETRIES})")
                await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                return await self.analyze_batch(errors, retry_count + 1)
            return {"error": "LLM Analysis Timed Out", "retry_exhausted": True}
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON response: {e}")
            return {"error": "Invalid LLM response format", "details": str(e)}
            
        except Exception as e:
            logger.error(f"❌ LLM Error: {e}", exc_info=True)
            return {"error": f"LLM Interaction Failed: {str(e)}"}

# --- 6. Main Orchestrator ---
async def main():
    """Main execution flow with proper resource management"""
    repo = SigNozRepository()
    analyzer = BatchAnalyzer()

    try:
        logger.info("🚀 Starting Error Analysis Pipeline...")
        
        # Step 1: Fetch errors
        errors = await repo.fetch_errors(limit=10, time_window_minutes=60)
        
        if not errors:
            logger.info("✅ No significant errors found in the last hour")
            return

        # Step 2: Analyze with AI
        logger.info(f"🤖 Analyzing {len(errors)} error groups...")
        result = await analyzer.analyze_batch(errors)
        
        # Step 3: Output results
        print("\n" + "="*60)
        print("🎯 ERROR ANALYSIS REPORT")
        print("="*60)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("="*60 + "\n")
        
        # Optional: Save to file
        output_file = f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(f"/home/claude/{output_file}", "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Report saved to {output_file}")
        
    except KeyboardInterrupt:
        logger.info("⚠️  Process interrupted by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        await repo.close()
        logger.info("👋 Shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
