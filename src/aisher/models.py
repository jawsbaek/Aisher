from pydantic import BaseModel, Field


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
