import json
import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from apps.tasks.models import Task

from .models import AIConfiguration, AIInsight

logger = logging.getLogger(__name__)

import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta
import requests
from django.conf import settings
from django.utils import timezone
from apps.accounts.timezones import user_zone
from apps.tasks.models import Task
from apps.scheduler.models import ScheduleBlock
from apps.scheduler.engine.optimizer import ScheduleOptimizer
from apps.scheduler.progress import (
    focus_minutes_map,
    planned_minutes_map,
    remaining_minutes,
)
from apps.pomodoro.models import PomodoroSession
from ai_service.api.schemas import RiskAnalysisRequest, RiskAnalysisResponse, DailySummaryRequest, DailySummaryResponse
from ai_service.services.analyzer import AIAnalyzer
from .models import AIInsight

logger = logging.getLogger(__name__)


def habit_analysis(user):
    now = timezone.now()
    zone = user_zone(user)
    sessions = list(PomodoroSession.objects.filter(user=user, completed=True, session_type='WORK',
                     start_time__gte=now-timedelta(days=30)).order_by('start_time'))
    hours = defaultdict(int)
    days = defaultdict(int)
    for session in sessions:
        local = session.start_time.astimezone(zone)
        hours[local.hour] += session.duration_minutes
        days[local.date().isoformat()] += session.duration_minutes
    peak = max(hours, key=hours.get) if hours else None
    advice = (f'Bạn thường tập trung vào khoảng {peak:02d}:00. Có thể dành khung giờ này cho môn khó.'
              if len(sessions) >= 5 else 'Chưa đủ dữ liệu để nhận xét thói quen. Hãy ghi nhận ít nhất 5 phiên học.')
    today = now.astimezone(zone).date()
    goal = max(1, user.daily_study_goal_hours * 60)
    week = [{'date': (today-timedelta(days=i)).isoformat(), 'minutes': days[(today-timedelta(days=i)).isoformat()],
             'percent': min(100, round(days[(today-timedelta(days=i)).isoformat()] * 100 / goal)),
             'label': (today-timedelta(days=i)).strftime('%d/%m')}
            for i in range(6, -1, -1)]
    return {'sessions_count': len(sessions), 'focus_minutes': sum(hours.values()),
            'peak_hour': peak if len(sessions) >= 5 else None, 'advice': advice, 'week': week}


def planning_context(user):
    now = timezone.now()
    optimizer = ScheduleOptimizer(user, days_ahead=31)
    slots = optimizer.find_free_slots(optimizer.get_existing_busy_intervals())
    load = optimizer._daily_load()
    cap = user.daily_study_goal_hours*60
    cumulative = 0
    tasks = []
    task_list = list(
        Task.objects.filter(user=user)
        .exclude(status='COMPLETED')
        .order_by('deadline', '-priority')[:1000]
    )
    planned_by_task = planned_minutes_map(user, task_list, now)
    focus_by_task = focus_minutes_map(user, task_list)
    for task in task_list:
        remaining = remaining_minutes(task, focus_by_task.get(task.pk, 0))
        planned = planned_by_task.get(task.pk, 0)
        cumulative += max(0, remaining-planned)
        per_day = defaultdict(int)
        for a, b in slots:
            per_day[a.astimezone(optimizer.zone).date()] += max(0, int((min(b, task.deadline)-a).total_seconds()/60))
        capacity = sum(min(minutes, max(0, cap-load[day])) for day, minutes in per_day.items())
        tasks.append({'id': task.pk, 'title': task.title, 'deadline': task.deadline.isoformat(),
            'priority': task.get_priority_display(), 'estimated_duration': task.estimated_duration,
            'is_scheduled': planned >= remaining, 'remaining_minutes': remaining, 'planned_minutes': planned,
            'available_minutes': capacity if task.deadline <= optimizer.window_end else None,
            'cumulative_unscheduled_minutes': cumulative})
    habits = habit_analysis(user)
    habits['overloaded_days'] = [day.isoformat() for day, minutes in load.items() if minutes > cap]
    return {'user_id': user.pk, 'current_time': now.isoformat(), 'tasks': tasks, 'habits': habits}


class AIServiceBridge:
    @staticmethod
    def _cached(user, kind, payload):
        fingerprint_payload = dict(payload)
        fingerprint_payload['current_time'] = int(timezone.now().timestamp()//300)
        fingerprint = hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True).encode()).hexdigest()
        recent = AIInsight.objects.filter(user=user, insight_type=kind, is_dismissed=False,
                    created_at__gte=timezone.now()-timedelta(minutes=5)).first()
        if recent and recent.context_fingerprint == fingerprint:
            return recent, fingerprint
        return None, fingerprint

    @staticmethod
    def _request(endpoint, payload, schema, fallback):
        try:
            headers = {'X-Service-Token': settings.AI_SERVICE_TOKEN}
            response = requests.post(f'{settings.AI_SERVICE_URL}/api/v1/{endpoint}',
                                     json=payload, headers=headers, timeout=8)
            response.raise_for_status()
            return schema.model_validate(response.json())
        except Exception:
            logger.info('AI service unavailable; using local rules')
            return fallback

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
        payload = planning_context(user)
        kind = AIInsight.InsightType.DEADLINE_RISK
        cached, fingerprint = cls._cached(user, kind, payload)
        if cached:
            return cached
        parsed = RiskAnalysisRequest.model_validate(payload)
        baseline = AIAnalyzer.analyze_risks(parsed.tasks, parsed.current_time, parsed.habits, use_llm=False)
        result = cls._request('analyze-risks', payload, RiskAnalysisResponse, baseline)
        return AIInsight.objects.create(user=user, insight_type=kind, title=result.title[:200],
            content=result.summary, actionable_advice=result.advice, risk_level=baseline.risk_level,
            source=result.source, context_fingerprint=fingerprint, details={'habits': payload['habits']})

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
    def daily_summary(cls, user):
        context = planning_context(user)
        zone = user_zone(user)
        today = timezone.now().astimezone(zone).date()
        start = datetime.combine(today, time.min, zone)
        end = datetime.combine(today+timedelta(days=1), time.min, zone)
        blocks = list(ScheduleBlock.objects.filter(user=user, start_time__lt=end, end_time__gt=start))
        ids = {b.task_id for b in blocks}
        tasks = [t for t in context['tasks'] if t['id'] in ids or datetime.fromisoformat(t['deadline']) < end]
        payload = {'user_id': user.pk, 'date': today.isoformat(), 'tasks_due_today': tasks,
                   'scheduled_blocks_count': len(blocks),
                   'scheduled_minutes': sum(max(0, int((min(b.end_time, end)-max(b.start_time, start)).total_seconds()/60)) for b in blocks),
                   'daily_goal_minutes': user.daily_study_goal_hours*60, 'habits': context['habits']}
        kind = AIInsight.InsightType.DAILY_SUMMARY
        cached, fingerprint = cls._cached(user, kind, payload)
        if cached:
            return cached
        parsed = DailySummaryRequest.model_validate(payload)
        fallback = AIAnalyzer.daily_summary(parsed.tasks_due_today, parsed.scheduled_blocks_count,
                    parsed.scheduled_minutes, parsed.daily_goal_minutes, parsed.habits, use_llm=False)
        result = cls._request('daily-summary', payload, DailySummaryResponse, fallback)
        return AIInsight.objects.create(user=user, insight_type=kind, title=result.headline[:200],
            content=result.summary_text, actionable_advice=result.encouragement, source=result.source,
            context_fingerprint=fingerprint, details={'priorities': result.key_priorities, 'habits': context['habits']})
