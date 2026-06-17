import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ProcessingRunCreate(BaseModel):
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID | None = None
    priority: int = Field(0, ge=0, le=10)
    max_retries: int = Field(3, ge=0, le=10)


class ProcessingRunEnqueue(BaseModel):
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID | None = None
    webhook_event_id: uuid.UUID | None = None
    priority: int = Field(0, ge=0, le=10)
    max_retries: int = Field(3, ge=0, le=10)


class EnqueueResultOut(BaseModel):
    run_id: uuid.UUID
    transcript_id: uuid.UUID
    status: str
    priority: int
    queued_at: datetime | None = None
    webhook_event_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class BatchEnqueueRequest(BaseModel):
    transcript_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=100)
    priority: int = Field(0, ge=0, le=10)
    max_retries: int = Field(3, ge=0, le=10)


class BatchEnqueueResponse(BaseModel):
    enqueued: list[EnqueueResultOut]
    skipped: list[dict]
    errors: list[str]


class ProcessingFailureOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    step: str
    error_type: str | None = None
    error_message: str
    stack_trace: str | None = None
    retry_eligible: bool = True
    retry_number: int = 0
    occurred_at: datetime

    model_config = {"from_attributes": True}


class ProcessingRunListItem(BaseModel):
    id: uuid.UUID
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID | None = None
    webhook_event_id: uuid.UUID | None = None
    status: str
    current_step: str | None = None
    steps_completed: int
    total_steps: int
    questions_generated: int
    model_used: str | None = None
    error_message: str | None = None
    warnings: list[str] = []
    priority: int = 0
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_duration_seconds: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def extract_warnings(cls, data: dict) -> dict:
        if isinstance(data, dict):
            if "warnings" not in data or not data.get("warnings"):
                step_results = data.get("step_results") or []
                all_warnings: list[str] = []
                for sr in step_results:
                    if isinstance(sr, dict):
                        for w in sr.get("warnings", []):
                            if isinstance(w, str):
                                all_warnings.append(w)
                data["warnings"] = all_warnings
        return data


class ProcessingRunDetailOut(ProcessingRunListItem):
    step_results: list[dict] = Field(default_factory=list)
    failures: list[ProcessingFailureOut] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def extract_warnings_detail(cls, data: dict) -> dict:
        if isinstance(data, dict):
            if "warnings" not in data or not data.get("warnings"):
                step_results = data.get("step_results") or []
                all_warnings: list[str] = []
                for sr in step_results:
                    if isinstance(sr, dict):
                        for w in sr.get("warnings", []):
                            if isinstance(w, str):
                                all_warnings.append(w)
                data["warnings"] = all_warnings
        return data


class ProcessingRunListOut(BaseModel):
    items: list[ProcessingRunListItem]
    total: int
    offset: int
    limit: int


class ProcessingRunResultOut(BaseModel):
    id: uuid.UUID
    transcript_id: uuid.UUID
    meeting_id: uuid.UUID | None = None
    webhook_event_id: uuid.UUID | None = None
    status: str
    current_step: str | None = None
    steps_completed: int
    total_steps: int
    step_results: list[dict] = Field(default_factory=list)
    questions_generated: int
    model_used: str | None = None
    error_message: str | None = None
    warnings: list[str] = []
    priority: int = 0
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_duration_seconds: float | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def extract_warnings_result(cls, data: dict) -> dict:
        if isinstance(data, dict):
            if "warnings" not in data or not data.get("warnings"):
                step_results = data.get("step_results") or []
                all_warnings: list[str] = []
                for sr in step_results:
                    if isinstance(sr, dict):
                        for w in sr.get("warnings", []):
                            if isinstance(w, str):
                                all_warnings.append(w)
                data["warnings"] = all_warnings
        return data


class ProcessingRunStatusOut(BaseModel):
    id: uuid.UUID
    status: str
    current_step: str | None = None
    steps_completed: int
    total_steps: int
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: datetime | None = None
    error_message: str | None = None
    warnings: list[str] = []
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def extract_warnings_status(cls, data: dict) -> dict:
        if isinstance(data, dict):
            if "warnings" not in data or not data.get("warnings"):
                step_results = data.get("step_results") or []
                all_warnings: list[str] = []
                for sr in step_results:
                    if isinstance(sr, dict):
                        for w in sr.get("warnings", []):
                            if isinstance(w, str):
                                all_warnings.append(w)
                data["warnings"] = all_warnings
        return data


class ProcessingFailureListOut(BaseModel):
    items: list[ProcessingFailureOut]
    total: int


class QueueMetricsOut(BaseModel):
    status_counts: dict[str, int]
    queue_depth: int
    active_workers: int
    avg_processing_duration_seconds: float | None = None
    avg_failed_duration_seconds: float | None = None
    avg_queue_wait_seconds: float | None = None
    failure_rate: float = 0.0
    throughput_per_hour: float = 0.0
    failure_breakdown_by_step: dict[str, int] = {}
    total_runs_created_last_n_hours: int = 0
    hours_window: int = 24
