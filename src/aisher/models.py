from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ErrorLog(BaseModel):
    """Structured error log with comprehensive fields for LLM root cause analysis.

    Combines data from signoz_index_v3 and signoz_error_index_v2 for complete error context.
    """
    # 1. 기본 식별자 및 위치 정보
    trace_id: str = Field(..., description="Unique trace identifier")
    span_id: str = Field(..., description="Unique span identifier")
    timestamp: str = Field(..., description="Error timestamp")
    service_name: str = Field(..., description="Service name (e.g., api-gateway)")
    span_name: str = Field(..., description="Operation/span name (e.g., GET /api/checkout)")

    # 2. 에러의 핵심 내용 (LLM 분석의 핵심)
    error_type: str = Field(..., description="Exception type (e.g., NullPointerException)")
    error_message: str = Field(..., description="Exception message")
    stacktrace: str = Field("", description="Exception stacktrace (may be truncated)")

    # 3. HTTP 및 DB 문맥 정보
    http_status: Optional[int] = Field(None, description="HTTP response status code")
    http_method: Optional[str] = Field(None, description="HTTP method (GET, POST, etc.)")
    http_url: Optional[str] = Field(None, description="HTTP URL")
    db_system: Optional[str] = Field(None, description="Database system (mysql, postgresql, etc.)")
    db_operation: Optional[str] = Field(None, description="Database operation")

    # 4. 속성 및 리소스 정보 (LLM 환경 정보 제공)
    span_attributes: Optional[str] = Field(None, description="Span attributes as JSON string")
    resource_attributes: Optional[str] = Field(None, description="Resource attributes as JSON string")

    # 5. 에러 발생 시점의 이벤트 로그
    related_events: Optional[str] = Field(None, description="Related events before error (newline separated)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "trace_id": "abc123def456",
                "span_id": "span789",
                "timestamp": "2024-01-15T10:30:00Z",
                "service_name": "api-gateway",
                "span_name": "GET /users",
                "error_type": "NullPointerException",
                "error_message": "Cannot invoke method on null object",
                "stacktrace": "java.lang.NullPointerException...",
                "http_status": 500,
                "http_method": "GET",
                "http_url": "/api/users/123",
                "db_system": None,
                "db_operation": None,
                "span_attributes": '{"user_id": "u123"}',
                "resource_attributes": '{"k8s.pod.name": "api-pod-1"}',
                "related_events": "log: Processing request\nlog: Fetching user data"
            }
        }
    )
