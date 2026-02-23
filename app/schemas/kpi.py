from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.entities import SharePermission, ShareScope


class KPITemplateMetricInput(BaseModel):
    title: str
    description: str
    weight_percent: float = Field(gt=0, le=100)
    plan_value: float
    allow_overtime: bool = False
    formula: str


class KPITemplateCreate(BaseModel):
    title: str
    max_total_amount: float = Field(gt=0)
    formula_config: dict = Field(default_factory=dict)
    metrics: list[KPITemplateMetricInput] = Field(min_length=1)


class KPIInstanceMetricInput(BaseModel):
    template_metric_id: int
    fact_value: float
    overtime_result: float = 0


class KPIInstanceCreate(BaseModel):
    employee_id: int
    template_id: int
    month: str
    period_start: date
    period_end: date
    base_salary: float = 0
    salary_share_percent: float = Field(default=0, ge=0, le=100)
    overtime_hours_x1: float = Field(default=0, ge=0)
    overtime_hours_x2: float = Field(default=0, ge=0)
    overtime_amount: float = 0
    metrics: list[KPIInstanceMetricInput] = Field(default_factory=list)


class KPIShareLinkCreate(BaseModel):
    scope: ShareScope
    permission: SharePermission
    kpi_instance_id: int | None = None
    employee_id: int | None = None
    month: str | None = None
    expires_at: datetime | None = None


class KPIExportQuery(BaseModel):
    format: str = "pdf"


class DisputeCreate(BaseModel):
    instance_id: int
    metric_id: int | None = None
    comment: str


class KPIResponse(BaseModel):
    id: int
    month: str
    total_amount: float
    status: str


class ShareResponse(BaseModel):
    uuid: UUID
    scope: str
    permission: str
