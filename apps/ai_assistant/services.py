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
from apps.scheduler.progress import remaining_minutes, planned_minutes
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
    for task in Task.objects.filter(user=user).exclude(status='COMPLETED').order_by('deadline', '-priority')[:1000]:
        remaining, planned = remaining_minutes(task), planned_minutes(task, now)
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

    @classmethod
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
