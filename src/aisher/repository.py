import asyncio
from typing import List, Optional
import clickhouse_connect
from clickhouse_connect.driver.client import AsyncClient
from clickhouse_connect.driver.exceptions import DatabaseError

from .config import settings, logger
from .models import ErrorLog


class SigNozRepository:
    """Async repository for SigNoz/ClickHouse integration"""

    def __init__(self):
        self.host = settings.CLICKHOUSE_HOST
        self.port = settings.CLICKHOUSE_PORT
        self.user = settings.CLICKHOUSE_USER
        self.password = settings.CLICKHOUSE_PASSWORD.get_secret_value()
        self._validate_database_name(settings.CLICKHOUSE_DATABASE)
        self.database = settings.CLICKHOUSE_DATABASE
        self._client: Optional[AsyncClient] = None

    def _validate_database_name(self, name: str) -> None:
        """Validate database name contains only safe characters"""
        if not name.replace('_', '').isalnum():
            raise ValueError(f"Invalid database name: {name}")
        if name.lower() in ('system', 'information_schema'):
            raise ValueError(f"Restricted database: {name}")

    async def _get_client(self) -> AsyncClient:
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
        Fetch error logs with smart truncation, deduplication, and retry logic.

        Args:
            limit: Maximum number of error groups to return (1-1000)
            time_window_minutes: Time window for log aggregation (1-10080)

        Returns:
            List of ErrorLog objects with truncated stack traces

        Raises:
            ValueError: If parameters are out of valid range
        """
        # Validate input parameters
        if not (1 <= limit <= 1000):
            raise ValueError(f"limit must be between 1 and 1000, got {limit}")
        if not (1 <= time_window_minutes <= 10080):  # 1 week max
            raise ValueError(f"time_window_minutes must be between 1 and 10080, got {time_window_minutes}")

        # Retry logic with exponential backoff
        last_exception = None
        for attempt in range(settings.MAX_RETRIES):
            try:
                return await self._fetch_errors_internal(limit, time_window_minutes)
            except (DatabaseError, asyncio.TimeoutError) as e:
                last_exception = e
                if attempt < settings.MAX_RETRIES - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(
                        f"Query failed (attempt {attempt + 1}/{settings.MAX_RETRIES}), "
                        f"retrying in {wait_time}s...",
                        extra={"error_type": type(e).__name__, "attempt": attempt + 1}
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Query failed after {settings.MAX_RETRIES} attempts",
                        extra={"error_type": type(e).__name__},
                        exc_info=True
                    )
            except Exception as e:
                logger.error(f"❌ Unexpected Error: {e}", exc_info=True)
                return []

        # If all retries failed, return empty list
        return []

    async def _fetch_errors_internal(
        self,
        limit: int,
        time_window_minutes: int
    ) -> List[ErrorLog]:
        """Internal method to fetch errors from ClickHouse"""
        # Optimized query: Use exception.message for grouping (lower cardinality)
        query = f"""
        SELECT
            any(traceID) as id,
            any(serviceName) as svc,
            any(name) as op,
            stringTagMap['exception.message'] as msg,
            count(*) as cnt,
            any(stringTagMap['exception.stacktrace']) as raw_stack
        FROM {self.database}.signoz_index_v2
        WHERE statusCode = 2
          AND timestamp > now() - INTERVAL %(time_window)s MINUTE
          AND stringTagMap['exception.message'] != ''
        GROUP BY stringTagMap['exception.message']
        ORDER BY cnt DESC
        LIMIT %(limit_val)s
        """

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

        logs = []
        for row in result.result_rows:
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

    async def ping(self) -> bool:
        """
        Check if the ClickHouse connection is healthy.

        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            client = await self._get_client()
            result = await asyncio.wait_for(
                client.query("SELECT 1"),
                timeout=5
            )
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def close(self):
        """Close the ClickHouse connection"""
        if self._client:
            await self._client.close()
            logger.info("🔌 ClickHouse connection closed")

    async def __aenter__(self):
        """Async context manager entry"""
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
        return False
