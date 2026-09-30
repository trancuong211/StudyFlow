import requests
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from .models import AIInsight
from apps.tasks.models import Task
from apps.scheduler.models import ScheduleBlock

class AIServiceBridge:
    """
    Bridge kết nối Django với FastAPI AI Microservice (hoặc fallback phân tích thông minh).
    """

    @classmethod
    def analyze_schedule_and_deadlines(cls, user):
        """
        Gửi dữ liệu các task và schedule blocks tới FastAPI AI Service để phân tích rủi ro deadline.
        """
        now = timezone.now()
        upcoming_tasks = Task.objects.filter(
            user=user,
            status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS]
        ).order_by('deadline')

        task_payload = [
            {
                'id': t.id,
                'title': t.title,
                'deadline': t.deadline.isoformat(),
                'priority': t.get_priority_display(),
                'estimated_duration': t.estimated_duration,
                'is_scheduled': t.is_scheduled
            }
            for t in upcoming_tasks[:15]
        ]

        payload = {
            'user_id': user.id,
            'current_time': now.isoformat(),
            'tasks': task_payload,
        }

        try:
            url = f"{settings.AI_SERVICE_URL}/api/v1/analyze-risks"
            response = requests.post(url, json=payload, timeout=8)
            if response.status_code == 200:
                result = response.json()
                insight = AIInsight.objects.create(
                    user=user,
                    insight_type=AIInsight.InsightType.DEADLINE_RISK,
                    title=result.get('title', 'Phân tích rủi ro deadline'),
                    content=result.get('summary', ''),
                    actionable_advice=result.get('advice', '')
                )
                return insight
        except Exception:
            pass

        # Mọi nhánh lỗi (non-200, exception, JSON sai) đều rơi về phân tích heuristic
        return cls._heuristic_risk_analysis(user, upcoming_tasks)

    @classmethod
    def _heuristic_risk_analysis(cls, user, tasks):
        """Phân tích quy tắc dự phòng khi AI service chưa khả dụng."""
        now = timezone.now()
        urgent_tasks = [t for t in tasks if t.deadline < now + timedelta(days=2)]
        
        if urgent_tasks:
            title = f"Cảnh báo: Có {len(urgent_tasks)} công việc sắp đến hạn trong 48 giờ tới!"
            content = f"Bạn đang có các deadline gần: {', '.join([t.title for t in urgent_tasks])}."
            advice = "Hãy tận dụng các khung giờ trống hôm nay và chạy tính năng Tự Động Lập Lịch để phân bổ thời gian ôn tập!"
        else:
            title = "Lịch học tập đang trong tầm kiểm soát"
            content = "Không có deadline nào nguy cấp trong 48 giờ tới."
            advice = "Duy trì tiến độ học tập đều đặn với các phiên Pomodoro 25 phút."

        return AIInsight.objects.create(
            user=user,
            insight_type=AIInsight.InsightType.DEADLINE_RISK,
            title=title,
            content=content,
            actionable_advice=advice
        )
