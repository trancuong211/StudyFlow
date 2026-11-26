import os
import secrets
from fastapi import APIRouter, Depends, Header, HTTPException
from .schemas import RiskAnalysisRequest, RiskAnalysisResponse, DailySummaryRequest, DailySummaryResponse
from ..services.analyzer import AIAnalyzer


def service_auth(x_service_token: str = Header(default='')):
    expected = os.getenv('AI_SERVICE_TOKEN', '')
    if expected and not secrets.compare_digest(expected, x_service_token):
        raise HTTPException(status_code=401, detail='Invalid service credentials')


router = APIRouter(prefix='/api/v1', tags=['AI Support Services'], dependencies=[Depends(service_auth)])


@router.post('/analyze-risks', response_model=RiskAnalysisResponse)
def analyze_risks(request: RiskAnalysisRequest):
    return AIAnalyzer.analyze_risks(request.tasks, request.current_time, request.habits)


@router.post('/daily-summary', response_model=DailySummaryResponse)
def daily_summary(request: DailySummaryRequest):
    return AIAnalyzer.daily_summary(request.tasks_due_today, request.scheduled_blocks_count,
                                   request.scheduled_minutes, request.daily_goal_minutes, request.habits)
