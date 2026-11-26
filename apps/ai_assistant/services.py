import json
import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from apps.tasks.models import Task

from .models import AIConfiguration, AIInsight

logger = logging.getLogger(__name__)


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
        upcoming_tasks = list(Task.objects.filter(
            user=user,
            status__in=[Task.Status.TODO, Task.Status.IN_PROGRESS]
        ).order_by('deadline')[:15])

        task_payload = [
            {
                'id': t.id,
                'title': t.title,
                'deadline': t.deadline.isoformat(),
                'priority': t.get_priority_display(),
                'estimated_duration': t.estimated_duration,
                'is_scheduled': t.is_scheduled
            }
            for t in upcoming_tasks
        ]

        payload = {
            'user_id': user.id,
            'current_time': now.isoformat(),
            'tasks': task_payload,
        }

        # Ưu tiên cấu hình AI riêng của người dùng (provider + API key của họ).
        config = cls._get_user_config(user)
        if config and config.is_active and config.has_api_key:
            insight = cls._call_user_ai(user, config, task_payload, now)
            if insight is not None:
                return insight
            # Người dùng đã tự cấu hình key: không âm thầm dùng key server.
            return cls._heuristic_risk_analysis(user, upcoming_tasks)

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
                    actionable_advice=result.get('advice', ''),
                    risk_level=cls._normalize_risk_level(result.get('risk_level'), 'MEDIUM'),
                    source='ai_service',
                )
                return insight
        except Exception:
            logger.warning('AI service không khả dụng, dùng phân tích dự phòng.', exc_info=True)

        # Mọi nhánh lỗi (non-200, exception, JSON sai) đều rơi về phân tích heuristic
        return cls._heuristic_risk_analysis(user, upcoming_tasks)

    @staticmethod
    def _get_user_config(user):
        try:
            return user.ai_config
        except AIConfiguration.DoesNotExist:
            return None

    @classmethod
    def _call_user_ai(cls, user, config, tasks, now):
        """Gọi trực tiếp nhà cung cấp AI bằng API key của người dùng."""
        api_key = config.get_api_key()
        if not api_key:
            return None

        prompt = cls._build_prompt(tasks, now)
        try:
            if config.provider == AIConfiguration.Provider.ANTHROPIC:
                content = cls._call_anthropic(api_key, config, prompt)
            else:
                content = cls._call_openai(api_key, config, prompt)
        except Exception:
            logger.warning(
                'Gọi AI bằng key của user_id=%s thất bại, dùng phân tích dự phòng.',
                user.pk,
                exc_info=True,
            )
            return None

        data = cls._parse_ai_content(content)
        return AIInsight.objects.create(
            user=user,
            insight_type=AIInsight.InsightType.DEADLINE_RISK,
            title=data['title'],
            content=data['summary'],
            actionable_advice=data['advice'],
            risk_level=cls._normalize_risk_level(data.get('risk_level'), 'MEDIUM'),
            source=config.provider,
            details={'provider': config.provider, 'model': config.get_model_name()},
        )

    @staticmethod
    def _normalize_risk_level(value, default='MEDIUM'):
        valid = {'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'}
        value = (value or '').strip().upper()
        return value if value in valid else default

    @staticmethod
    def _build_prompt(tasks, now):
        tasks_text = '\n'.join([
            f"- {t['title']} (Hạn: {t['deadline']}, Ưu tiên: {t['priority']}, "
            f"Thời lượng: {t['estimated_duration']}m, Đã xếp lịch: {t['is_scheduled']})"
            for t in tasks
        ]) or '(không có deadline nào đang mở)'

        return (
            'Bạn là trợ lý AI chuyên về năng suất học tập và quản lý thời gian. '
            'Hãy phân tích danh sách deadline dưới đây và đưa ra cảnh báo rủi ro ngắn gọn. '
            'Trả về DUY NHẤT một đối tượng JSON (không kèm markdown) với các khóa: '
            '"title" (tiêu đề ngắn), "summary" (2-4 câu), '
            '"advice" (1-2 câu lời khuyên hành động), '
            '"risk_level" (một trong LOW, MEDIUM, HIGH, CRITICAL).\n\n'
            f'Thời điểm hiện tại: {now.isoformat()}\n'
            f'Danh sách deadline:\n{tasks_text}'
        )

    @staticmethod
    def _call_openai(api_key, config, prompt):
        from openai import OpenAI

        kwargs = {'api_key': api_key}
        if config.base_url:
            kwargs['base_url'] = config.base_url
        client = OpenAI(**kwargs)
        response = client.chat.completions.create(
            model=config.get_model_name() or 'gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=400,
            temperature=0.3,
        )
        return response.choices[0].message.content or ''

    @staticmethod
    def _call_anthropic(api_key, config, prompt):
        from anthropic import Anthropic

        kwargs = {'api_key': api_key}
        if config.base_url:
            kwargs['base_url'] = config.base_url
        client = Anthropic(**kwargs)
        response = client.messages.create(
            model=config.get_model_name() or 'claude-3-5-sonnet-latest',
            max_tokens=400,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return '\n'.join(
            block.text for block in response.content if getattr(block, 'text', None)
        )

    @staticmethod
    def _parse_ai_content(content):
        text = (content or '').strip()
        data = {}

        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
            except (ValueError, TypeError):
                data = {}

        if not isinstance(data, dict):
            data = {}

        title = (data.get('title') or 'Phân tích rủi ro deadline từ AI').strip()
        summary = (data.get('summary') or text or 'AI chưa trả về nội dung.').strip()
        advice = (data.get('advice') or '').strip()

        return {
            'title': title[:200],
            'summary': summary,
            'advice': advice,
            'risk_level': data.get('risk_level'),
        }

    @classmethod
    def _heuristic_risk_analysis(cls, user, tasks):
        """Phân tích quy tắc dự phòng khi AI service chưa khả dụng."""
        now = timezone.now()
        threshold = now + timedelta(days=2)
        urgent_tasks = []
        for task in tasks:
            deadline = task.deadline
            if deadline is None:
                continue
            if timezone.is_naive(deadline):
                deadline = timezone.make_aware(deadline)
            if deadline < threshold:
                urgent_tasks.append(task)

        if urgent_tasks:
            title = f"Cảnh báo: Có {len(urgent_tasks)} công việc sắp đến hạn trong 48 giờ tới!"
            content = f"Bạn đang có các deadline gần: {', '.join([t.title for t in urgent_tasks])}."
            advice = "Hãy tận dụng các khung giờ trống hôm nay và chạy tính năng Tự Động Lập Lịch để phân bổ thời gian ôn tập!"
            risk_level = 'HIGH'
        else:
            title = "Lịch học tập đang trong tầm kiểm soát"
            content = "Không có deadline nào nguy cấp trong 48 giờ tới."
            advice = "Duy trì tiến độ học tập đều đặn với các phiên Pomodoro 25 phút."
            risk_level = 'LOW'

        return AIInsight.objects.create(
            user=user,
            insight_type=AIInsight.InsightType.DEADLINE_RISK,
            title=title,
            content=content,
            actionable_advice=advice,
            risk_level=risk_level,
            source='rules',
        )
