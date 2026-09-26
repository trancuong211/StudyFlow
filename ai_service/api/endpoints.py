from fastapi import APIRouter
from .schemas import RiskAnalysisRequest, RiskAnalysisResponse, DailySummaryRequest, DailySummaryResponse
from ..services.analyzer import AIAnalyzer

router = APIRouter(prefix="/api/v1", tags=["AI Support Services"])

@router.post("/analyze-risks", response_model=RiskAnalysisResponse)
def analyze_risks(request: RiskAnalysisRequest):
    return AIAnalyzer.analyze_risks(request.tasks)

@router.post("/daily-summary", response_model=DailySummaryResponse)
def daily_summary(request: DailySummaryRequest):
    return AIAnalyzer.daily_summary(request.tasks_due_today, request.scheduled_blocks_count)
