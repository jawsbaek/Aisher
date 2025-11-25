"""
SigNoz/ClickHouse Repository Module

This module implements the "Golden Query" strategy for fetching comprehensive
error context by joining signoz_index_v3 with signoz_error_index_v2.

The query provides:
1. Context info (index_v3): service, API endpoint, duration
2. Detailed error info (error_index_v2): exception message and stacktrace
3. Event timeline (events): event logs before error occurrence
"""

import asyncio
from typing import List, Optional
import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient
from clickhouse_connect.driver.exceptions import DatabaseError

from .config import settings, logger
from .models import ErrorLog


# SQL Query Template: The Golden Query
# Joins index_v3 and error_index_v2 for complete error context
GOLDEN_QUERY = """
SELECT
    -- 1. 기본 식별자 및 위치 정보
    toString(t.timestamp) AS time,
    t.trace_id,
    t.span_id,
    t.service_name,
    t.name AS span_name,

    -- 2. 에러의 핵심 내용 (LLM 분석의 핵심)
    e.exceptionType AS error_type,
    e.exceptionMessage AS error_message,
    e.exceptionStacktrace AS stacktrace,

    -- 3. HTTP 및 DB 문맥 정보
    t.response_status_code AS http_status,
    t.http_method,
    t.http_url,
    t.db_system,
    t.db_operation,

    -- 4. 전체 속성 및 리소스 정보 (LLM에게 환경 정보 제공)
    toJSONString(t.attributes_string) AS span_attributes_json,
    toJSONString(t.resource_string) AS resource_attributes_json,

    -- 5. 에러 발생 시점의 이벤트 로그
    arrayStringConcat(t.events, '\n') AS related_events

FROM {database}.distributed_signoz_index_v3 AS t
LEFT JOIN {database}.distributed_signoz_error_index_v2 AS e
    ON t.trace_id = e.traceID
    AND t.span_id = e.spanID

WHERE
    -- 성능 최적화를 위한 파티션 키 활용
    t.ts_bucket_start >= (toUnixTimestamp(now()) - %(time_window_seconds)s)
    AND t.timestamp >= (now() - toIntervalSecond(%(time_window_seconds)s))
    AND t.has_error = true

ORDER BY t.timestamp DESC
LIMIT %(limit_val)s
"""


class SigNozRepository:
    """Async repository for SigNoz/ClickHouse integration.

    Uses the Golden Query strategy to fetch comprehensive error context
    by joining signoz_index_v3 with signoz_error_index_v2.
    """

    def __init__(self):
        self.host = settings.CLICKHOUSE_HOST
        self.port = settings.CLICKHOUSE_PORT
        self.user = settings.CLICKHOUSE_USER
        self.password = settings.CLICKHOUSE_PASSWORD.get_secret_value()
        self._validate_database_name(settings.CLICKHOUSE_DATABASE)
        self.database = settings.CLICKHOUSE_DATABASE
        self._client: Optional[AsyncClient] = None

    def _validate_database_name(self, name: str) -> None:
        """Validate database name contains only safe characters."""
        if not name.replace('_', '').isalnum():
            raise ValueError(f"Invalid database name: {name}")
        if name.lower() in ('system', 'information_schema'):
            raise ValueError(f"Restricted database: {name}")

    async def _get_client(self) -> AsyncClient:
        """Get or create async ClickHouse client."""
        if self._client is None:
            try:
                self._client = await clickhouse_connect.get_async_client(
                    host=self.host,
                    port=self.port,
                    username=self.user,
                    password=self.password,
                    connect_timeout=settings.QUERY_TIMEOUT
                )
                logger.info(f"Connected to ClickHouse at {self.host}:{self.port}")
            except Exception as e:
                logger.error(f"Failed to connect to ClickHouse: {e}")
                raise
        return self._client

    async def fetch_errors(
        self,
        limit: int = 10,
        time_window_minutes: int = 60
    ) -> List[ErrorLog]:
        """
        Fetch error logs using the Golden Query strategy.

        Joins signoz_index_v3 with signoz_error_index_v2 to provide:
        - Context info: service, API endpoint, duration
        - Error details: exception message and stacktrace
        - Event timeline: events before error occurrence

        Args:
            limit: Maximum number of errors to return (1-1000)
            time_window_minutes: Time window for log query (1-10080)

        Returns:
            List of ErrorLog objects with comprehensive error context

        Raises:
            ValueError: If parameters are out of valid range
        """
        # Validate input parameters
        if not (1 <= limit <= 1000):
            raise ValueError(f"limit must be between 1 and 1000, got {limit}")
        if not (1 <= time_window_minutes <= 10080):  # 1 week max
            raise ValueError(f"time_window_minutes must be between 1 and 10080, got {time_window_minutes}")

        # Retry logic with exponential backoff
        for attempt in range(settings.MAX_RETRIES):
            try:
                return await self._fetch_errors_internal(limit, time_window_minutes)
            except (DatabaseError, asyncio.TimeoutError) as e:
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
                        f"All retries exhausted. Query failed after {settings.MAX_RETRIES} attempts: {e}",
                        extra={"error_type": type(e).__name__},
                        exc_info=True
                    )
            except Exception as e:
                logger.error(f"Unexpected Error: {e}", exc_info=True)
                return []

        # If all retries failed, return empty list
        return []

    async def _fetch_errors_internal(
        self,
        limit: int,
        time_window_minutes: int
    ) -> List[ErrorLog]:
        """Internal method to fetch errors using Golden Query."""
        # Format query with database name (safe - already validated)
        query = GOLDEN_QUERY.format(database=self.database)

        client = await self._get_client()

        # Calculate time window in seconds for ts_bucket_start optimization
        time_window_seconds = time_window_minutes * 60

        result = await asyncio.wait_for(
            client.query(
                query,
                parameters={
                    'limit_val': limit,
                    'time_window_seconds': time_window_seconds
                }
            ),
            timeout=settings.QUERY_TIMEOUT
        )

        logs = []
        for row in result.result_rows:
            # Row structure from Golden Query:
            # (time, trace_id, span_id, service_name, span_name,
            #  error_type, error_message, stacktrace,
            #  http_status, http_method, http_url, db_system, db_operation,
            #  span_attributes_json, resource_attributes_json, related_events)
            (
                timestamp, trace_id, span_id, service_name, span_name,
                error_type, error_message, stacktrace,
                http_status, http_method, http_url, db_system, db_operation,
                span_attributes, resource_attributes, related_events
            ) = row

            # Smart Truncation: Preserve error context in stacktrace and limit JSON sizes
            truncated_stack = self._truncate_stacktrace(stacktrace)
            truncated_span_attrs = self._truncate_json_attribute(span_attributes)
            truncated_resource_attrs = self._truncate_json_attribute(resource_attributes)

            logs.append(ErrorLog(
                trace_id=trace_id,
                span_id=span_id,
                timestamp=timestamp,
                service_name=service_name,
                span_name=span_name,
                error_type=error_type if error_type is not None else "Unknown",
                error_message=error_message if error_message is not None else "No message",
                stacktrace=truncated_stack,
                http_status=int(http_status) if http_status else None,
                http_method=http_method or None,
                http_url=http_url or None,
                db_system=db_system or None,
                db_operation=db_operation or None,
                span_attributes=truncated_span_attrs,
                resource_attributes=truncated_resource_attrs,
                related_events=related_events or None
            ))

        logger.info(f"Fetched {len(logs)} error logs from SigNoz")
        return logs

    def _truncate_stacktrace(self, stacktrace: Optional[str]) -> str:
        """
        Smart truncation of stacktrace to preserve error context.

        Keeps the beginning (where the error is defined) and the end
        (where the root cause usually is) of the stacktrace.
        """
        if not stacktrace:
            return ""

        if len(stacktrace) <= settings.STACK_MAX_LENGTH:
            return stacktrace

        return (
            stacktrace[:settings.STACK_HEAD_LENGTH] +
            "\n...[truncated]...\n" +
            stacktrace[-settings.STACK_TAIL_LENGTH:]
        )

    def _truncate_json_attribute(self, json_str: Optional[str]) -> Optional[str]:
        """
        Truncate JSON attribute strings to prevent token overflow.

        Args:
            json_str: JSON string to truncate

        Returns:
            Truncated JSON string or None
        """
        if not json_str:
            return None

        if len(json_str) <= settings.JSON_ATTR_MAX_LENGTH:
            return json_str

        return json_str[:settings.JSON_ATTR_MAX_LENGTH] + "...[truncated]"

    async def ping(self) -> bool:
        """
        Check if the ClickHouse connection is healthy.

        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            client = await self._get_client()
            await asyncio.wait_for(
                client.query("SELECT 1"),
                timeout=5
            )
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def close(self):
        """Close the ClickHouse connection."""
        if self._client:
            await self._client.close()
            logger.info("ClickHouse connection closed")

    async def __aenter__(self):
        """Async context manager entry."""
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False
