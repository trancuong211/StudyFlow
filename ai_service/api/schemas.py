from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class TaskInputSchema(BaseModel):
    id: int
    title: str = Field(max_length=200)
    deadline: datetime
    priority: str
    estimated_duration: int = Field(ge=1)
    is_scheduled: bool
    remaining_minutes: int | None = Field(default=None, ge=0)
    planned_minutes: int = Field(default=0, ge=0)
    available_minutes: int | None = Field(default=None, ge=0)
    cumulative_unscheduled_minutes: int = Field(default=0, ge=0)

    @field_validator('deadline')
    @classmethod
    def aware_deadline(cls, value):
        if value.tzinfo is None:
            raise ValueError('Deadline must include timezone')
        return value


class RiskAnalysisRequest(BaseModel):
    user_id: int
    current_time: datetime
    tasks: list[TaskInputSchema] = Field(max_length=1000)
    habits: dict = Field(default_factory=dict)

    @field_validator('current_time')
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None:
            raise ValueError('Current time must include timezone')
        return value


class RiskAnalysisResponse(BaseModel):
    title: str
    summary: str
    risk_level: Literal['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']
    advice: str
    source: str = 'rules'


class DailySummaryRequest(BaseModel):
    user_id: int
    date: str
    tasks_due_today: list[TaskInputSchema] = Field(max_length=1000)
    scheduled_blocks_count: int = Field(ge=0)
    scheduled_minutes: int = Field(default=0, ge=0)
    daily_goal_minutes: int = Field(default=240, ge=1)
    habits: dict = Field(default_factory=dict)


class DailySummaryResponse(BaseModel):
    headline: str
    summary_text: str
    key_priorities: list[str]
    encouragement: str
    source: str = 'rules'
