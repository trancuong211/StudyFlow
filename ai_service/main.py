from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.endpoints import router as ai_router

app = FastAPI(
    title="StudyFlow AI Support Service",
    description="Microservice phân tích lịch bận, cảnh báo rủi ro deadline và tóm tắt tiến độ",
    version="1.0.0"
)

# Internal server-to-server API: no browser CORS access is required.

app.include_router(ai_router)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "studyflow-ai-service"}
