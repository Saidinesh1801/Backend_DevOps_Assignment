from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TransactionOut(BaseModel):
    id: int
    txn_id: Optional[str] = None
    date: Optional[str] = None
    merchant: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    account_id: Optional[str] = None
    notes: Optional[str] = None
    is_anomaly: bool = False
    anomaly_reason: Optional[str] = None
    llm_category: Optional[str] = None
    llm_failed: bool = False

    class Config:
        from_attributes = True


class JobSummaryOut(BaseModel):
    total_spend_inr: float = 0.0
    total_spend_usd: float = 0.0
    top_merchants: list = []
    anomaly_count: int = 0
    narrative: Optional[str] = None
    risk_level: str = "low"

    class Config:
        from_attributes = True


class JobStatusOut(BaseModel):
    job_id: str = Field(validation_alias="id")
    filename: str
    status: str
    row_count_raw: int = 0
    row_count_clean: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class JobResultsOut(BaseModel):
    job_id: str
    filename: str
    status: str
    row_count_raw: int = 0
    row_count_clean: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    transactions: list[TransactionOut] = []
    summary: Optional[JobSummaryOut] = None

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    job_id: str
    filename: str
    status: str = "pending"
    message: str = "CSV uploaded and queued for processing"
