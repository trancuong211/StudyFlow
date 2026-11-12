"""Read-only schedule proposals and an explicit, signed apply operation."""

import hashlib
import json
from datetime import datetime, timedelta
from math import ceil

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ai_service.api.schemas import RiskAnalysisRequest
from ai_service.services.risk import score_task
from apps.calendar_sync.models import GoogleCalendarEvent
from apps.pomodoro.models import PomodoroSession
from apps.scheduler.availability import busy_intervals
from apps.scheduler.engine.optimizer import ScheduleOptimizer
from apps.scheduler.models import BusyPeriod, ScheduleBlock
from apps.scheduler.progress import planned_minutes, refresh_scheduled, remaining_minutes
from apps.tasks.models import Task

from .services import planning_context

SALT = 'studyflow.schedule-proposal.v1'
MAX_AGE = 15 * 60
RISK_LABELS = {'LOW': 'Thấp', 'MEDIUM': 'Trung bình', 'HIGH': 'Cao', 'CRITICAL': 'Nghiêm trọng'}


def calendar_signature(user):
    """Bind proposals to the exact progress, settings, and calendar they used."""
    state = {
        'profile': [user.timezone, user.daily_study_goal_hours, user.study_start_hour, user.study_end_hour],
        'tasks': list(Task.objects.filter(user=user).order_by('pk').values(
            'id', 'deadline', 'status', 'estimated_duration', 'priority', 'difficulty')),
        'blocks': list(ScheduleBlock.objects.filter(user=user).order_by('pk').values(
            'id', 'task_id', 'start_time', 'end_time', 'is_locked', 'is_auto_generated')),
        'busy': list(BusyPeriod.objects.filter(user=user).order_by('pk').values()),
        'google': list(GoogleCalendarEvent.objects.filter(user=user).order_by('pk').values(
            'id', 'start_time', 'end_time', 'is_busy')),
        'focus': list(PomodoroSession.objects.filter(user=user).order_by('pk').values(
            'id', 'task_id', 'start_time', 'duration_minutes', 'completed', 'session_type', 'is_active')),
    }
    return hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()


def current_task_risks(user):
    context = RiskAnalysisRequest.model_validate(planning_context(user))
    risks = [score_task(task, context.current_time).model_dump() for task in context.tasks]
    for risk in risks:
        risk['label'] = RISK_LABELS[risk['risk_level']]
    return sorted(risks, key=lambda item: (-item['score'], item['task_id']))


class ProposalPlanner:
    def __init__(self, user):
        self.user = user
        self.now = timezone.now()
        self.optimizer = ScheduleOptimizer(user, days_ahead=31)
        self.busy = busy_intervals(user, self.optimizer.window_start, self.optimizer.window_end)
        self.blocks = list(ScheduleBlock.objects.filter(user=user,
            start_time__lt=self.optimizer.window_end, end_time__gt=self.now).order_by('start_time'))
        self.load = self.optimizer._daily_load()
        self.cap = user.daily_study_goal_hours * 60
        self.signature = calendar_signature(user)

    def propose(self, task):
        remaining = remaining_minutes(task)
        if task.deadline <= self.now or remaining <= 0 or task.status == Task.Status.COMPLETED:
            return None
        missing = max(0, remaining - planned_minutes(task, self.now))
        movable = next((block for block in self.blocks if block.task_id == task.pk
            and block.is_auto_generated and not block.is_locked and block.start_time > self.now
            and (block.end_time > task.deadline
                 or self.load[block.start_time.astimezone(self.optimizer.zone).date()] > self.cap
                 or any(a < block.end_time and b > block.start_time for a, b in self.busy))), None)
        if not missing and not movable:
            return None
        intervals = self.busy + [(block.start_time-timedelta(minutes=15), block.end_time+timedelta(minutes=15))
                                 for block in self.blocks if not movable or block.pk != movable.pk]
        load = self.load.copy()
        if movable:
            for day in load:
                start = datetime.combine(day, datetime.min.time(), self.optimizer.zone)
                end = start + timedelta(days=1)
                released = max(0, int((min(end, movable.end_time)-max(start, movable.start_time)).total_seconds()/60))
                load[day] = max(0, load[day]-released)
        for start, end in self.optimizer.find_free_slots(intervals):
            # Round upwards to a readable minute; never offer a slot in the past.
            start = datetime.fromtimestamp(ceil(start.timestamp()/300)*300, tz=self.optimizer.zone)
            end = min(end, task.deadline)
            if start >= end:
                continue
            day = start.astimezone(self.optimizer.zone).date()
            capacity = min(int((end-start).total_seconds()/60), max(0, self.cap-load[day]), 120)
            minutes = movable.duration_minutes if movable else min(missing, capacity)
            if minutes <= 0 or minutes > capacity or (not movable and minutes < min(15, missing)):
                continue
            finish = start+timedelta(minutes=minutes)
            if movable and start == movable.start_time:
                continue
            data = {'user_id': self.user.pk, 'task_id': task.pk,
                'block_id': movable.pk if movable else None, 'start': start.isoformat(),
                'end': finish.isoformat(), 'signature': self.signature}
            return {'token': signing.dumps(data, salt=SALT, compress=True),
                'start': start, 'end': finish, 'minutes': minutes,
                'kind': 'move' if movable else 'add',
                'original_start': movable.start_time if movable else None,
                'original_end': movable.end_time if movable else None,
                'partial': not movable and minutes < missing,
                'reason': 'Dời khung tự động bị trùng, vượt hạn hoặc nằm trong ngày quá tải.' if movable
                    else f'Bổ sung {minutes} phút còn thiếu trước deadline.'}
        return None


def risk_cards(user, limit=20, task_id=None):
    risks = current_task_risks(user)
    if task_id is not None:
        risks = [risk for risk in risks if risk['task_id'] == task_id]
    cards = risks[:limit]
    if cards:
        planner = ProposalPlanner(user)
        tasks = {task.pk: task for task in Task.objects.filter(user=user, pk__in=[r['task_id'] for r in cards])}
        for card in cards:
            card['proposal'] = planner.propose(tasks[card['task_id']])
    return cards, max(0, len(risks)-len(cards))


@transaction.atomic
def apply_proposal(user, token):
    user = get_user_model().objects.select_for_update().get(pk=user.pk)
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature as exc:
        raise ValidationError('Gợi ý không hợp lệ hoặc đã hết hạn. Hãy tải lại để lấy gợi ý mới.') from exc
    if data['user_id'] != user.pk:
        raise ValidationError('Gợi ý không thuộc tài khoản của bạn.')
    if data['signature'] != calendar_signature(user):
        raise ValidationError('Lịch hoặc tiến độ đã thay đổi. Hãy xem gợi ý mới trước khi áp dụng.')
    task = Task.objects.filter(user=user, pk=data['task_id']).first()
    if not task or task.status == Task.Status.COMPLETED:
        raise ValidationError('Công việc không còn khả dụng.')
    start, end = datetime.fromisoformat(data['start']), datetime.fromisoformat(data['end'])
    if start <= timezone.now():
        raise ValidationError('Giờ đề xuất đã qua. Hãy lấy gợi ý mới.')
    if data['block_id']:
        block = ScheduleBlock.objects.filter(user=user, task=task, pk=data['block_id'],
            is_auto_generated=True, is_locked=False, start_time__gt=timezone.now()).first()
        if not block:
            raise ValidationError('Khung học đã đổi hoặc đã khóa. Hãy lấy gợi ý mới.')
    else:
        block = ScheduleBlock(user=user, task=task, title=f'[Học] {task.title}'[:200])
        if int((end-start).total_seconds()/60) > max(0, remaining_minutes(task)-planned_minutes(task)):
            raise ValidationError('Công việc đã được xếp đủ lịch. Hãy lấy gợi ý mới.')
    block.start_time, block.end_time = start, end
    # Explicitly accepted changes are preserved by subsequent auto-scheduling.
    block.is_auto_generated = True
    block.is_locked = True
    block.full_clean()
    block.save()
    refresh_scheduled(task)
    return block
