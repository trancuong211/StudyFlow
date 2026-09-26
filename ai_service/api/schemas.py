from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class TaskInputSchema(BaseModel):
    id: int
    title: str
    deadline: str
    priority: str
    estimated_duration: int
    is_scheduled: bool

class RiskAnalysisRequest(BaseModel):
    user_id: int
    current_time: str
    tasks: List[TaskInputSchema]

class RiskAnalysisResponse(BaseModel):
    title: str
    summary: str
    risk_level: str = Field(description="LOW, MEDIUM, HIGH, CRITICAL")
    advice: str

class DailySummaryRequest(BaseModel):
    user_id: int
    date: str
    tasks_due_today: List[TaskInputSchema]
    scheduled_blocks_count: int

class DailySummaryResponse(BaseModel):
    headline: str
    summary_text: str
    key_priorities: List[str]
    encouragement: str
