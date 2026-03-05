from typing import Any, Literal
from pydantic import BaseModel, Field


class FileImportRequest(BaseModel):
    filename: str


class ManualEventCreate(BaseModel):
    source: str = "manual"
    event_type: Literal["BUY", "SELL", "DIVIDEND", "DEPOSIT", "WITHDRAW", "FEE", "NOTE"]
    ticker: str | None = None
    quantity: float | None = None
    price: float | None = None
    amount: float | None = None
    currency: str = "USD"
    event_ts: str
    description: str | None = None
    recommendation_id: int | None = None


class ResolveReminderRequest(BaseModel):
    status: Literal["done", "ignored"]
    acted_event: ManualEventCreate | None = None


class RecommendationResponse(BaseModel):
    id: int
    ticker: str
    action: str
    confidence: float
    reasons: list[str]
    created_at: str
    follow_up_at: str | None
    status: str


class DailyReportRow(BaseModel):
    ticker: str
    close: float | None
    change_1d_pct: float | None
    change_1w_pct: float | None
    rsi_14: float | None
    drawdown_6mo_pct: float | None
    risk_flags: list[str] = Field(default_factory=list)
    data_delayed: bool = False


class DailyReportResponse(BaseModel):
    as_of: str
    rows: list[DailyReportRow]
    warnings: list[str] = Field(default_factory=list)


class GenericResponse(BaseModel):
    detail: str
    data: dict[str, Any] | None = None
