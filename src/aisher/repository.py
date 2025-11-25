import asyncio
from typing import List, Optional, Any
import clickhouse_connect
from clickhouse_connect.driver.exceptions import DatabaseError

from config import settings, logger
from models import ErrorLog


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
