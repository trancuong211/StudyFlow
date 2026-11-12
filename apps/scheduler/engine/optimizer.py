from collections import defaultdict
from datetime import datetime, time, timedelta
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from apps.accounts.timezones import user_zone
from apps.tasks.models import Task
from apps.scheduler.models import ScheduleBlock
from apps.scheduler.availability import busy_intervals
from apps.scheduler.progress import remaining_minutes, planned_minutes, refresh_scheduled


class ScheduleOptimizer:
    """EDF greedy scheduler with weekly availability, daily caps and preserved edits."""
    def __init__(self, user, start_date=None, days_ahead=7, study_hours=None):
        self.user = user
        self.zone = user_zone(user)
        self.start_date = start_date or timezone.localdate(timezone=user_zone(user))
        self.days_ahead = min(max(int(days_ahead), 1), 31)
        self.study_start_hour, self.study_end_hour = study_hours or (user.study_start_hour, user.study_end_hour)
        self.window_start = datetime.combine(self.start_date, time.min, self.zone)
        self.window_end = datetime.combine(self.start_date + timedelta(days=self.days_ahead), time.min, self.zone)
        self.report = []

    def get_existing_busy_intervals(self):
        blocks = ScheduleBlock.objects.filter(user=self.user, start_time__lt=self.window_end,
                                               end_time__gt=self.window_start)
        intervals = [(b.start_time - timedelta(minutes=15), b.end_time + timedelta(minutes=15)) for b in blocks]
        return intervals + busy_intervals(self.user, self.window_start, self.window_end)

    def find_free_slots(self, intervals):
        slots = []
        earliest = timezone.now() + timedelta(minutes=15)
        for offset in range(self.days_ahead):
            day = self.start_date + timedelta(days=offset)
            start = max(datetime.combine(day, time(self.study_start_hour), self.zone), earliest)
            end = datetime.combine(day, time(self.study_end_hour), self.zone)
            if start >= end:
                continue
            cursor = start
            for a, b in sorted((max(start, a), min(end, b)) for a, b in intervals if a < end and b > start):
                if a > cursor:
                    slots.append((cursor, a))
                cursor = max(cursor, b)
            if cursor < end:
                slots.append((cursor, end))
        return slots

    def _daily_load(self):
        from apps.pomodoro.models import PomodoroSession
        load = defaultdict(int)
        for offset in range(self.days_ahead):
            day = self.start_date + timedelta(days=offset)
            start = datetime.combine(day, time.min, self.zone)
            end = datetime.combine(day + timedelta(days=1), time.min, self.zone)
            for b in ScheduleBlock.objects.filter(user=self.user,
                                                   start_time__lt=end, end_time__gt=max(start, timezone.now())):
                load[day] += max(0, int((min(b.end_time, end) - max(b.start_time, start, timezone.now())).total_seconds()/60))
            load[day] += sum(PomodoroSession.objects.filter(user=self.user, completed=True, session_type='WORK',
                            start_time__gte=start, start_time__lt=end).values_list('duration_minutes', flat=True))
        return load

    @transaction.atomic
    def run(self):
        get_user_model().objects.select_for_update().get(pk=self.user.pk)
        now = timezone.now()
        ScheduleBlock.objects.filter(user=self.user, is_auto_generated=True, is_locked=False,
                                      start_time__gte=max(now, self.window_start), start_time__lt=self.window_end).delete()
        tasks = list(Task.objects.filter(user=self.user, status__in=['TODO', 'IN_PROGRESS'])
                     .order_by('deadline', '-priority', '-difficulty'))
        slots = self.find_free_slots(self.get_existing_busy_intervals())
        load = self._daily_load()
        cap = self.user.daily_study_goal_hours * 60
        created = []
        self.report = []
        for task in tasks:
            needed = max(0, remaining_minutes(task) - planned_minutes(task, now))
            for i, (start, end) in enumerate(slots):
                if needed <= 0:
                    break
                if start >= end or start >= task.deadline:
                    continue
                day = start.astimezone(self.zone).date()
                while needed > 0:
                    available = int((min(end, task.deadline) - start).total_seconds()/60)
                    allocation = min(needed, available, 120, max(0, cap-load[day]))
                    if allocation <= 0 or (allocation < 15 and allocation < needed):
                        break
                    finish = start + timedelta(minutes=allocation)
                    b = ScheduleBlock.objects.create(user=self.user, task=task, title=f'[Học] {task.title}',
                            start_time=start, end_time=finish, is_auto_generated=True)
                    created.append(b)
                    needed -= allocation
                    load[day] += allocation
                    start = finish + timedelta(minutes=15)
                    slots[i] = (start, end)
            refresh_scheduled(task)
            if needed:
                self.report.append({'task_id': task.pk, 'title': task.title, 'missing_minutes': needed,
                    'reason': 'Đã quá deadline' if task.deadline <= now else
                              'Không đủ thời gian trước deadline trong khung giờ học và giới hạn mỗi ngày'})
        return created
