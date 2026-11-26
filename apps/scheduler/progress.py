from collections import defaultdict

from django.db.models import Sum
from django.utils import timezone

from apps.pomodoro.models import PomodoroSession

from .models import ScheduleBlock


def focus_minutes(task):
    return sum(
        task.pomodoro_sessions.filter(
            completed=True, session_type=PomodoroSession.SessionType.WORK
        ).values_list("duration_minutes", flat=True)
    )


def focus_minutes_map(user, tasks):
    """Tổng phút tập trung của nhiều task chỉ với một truy vấn."""
    tasks = list(tasks)
    if not tasks:
        return {}
    rows = (
        PomodoroSession.objects.filter(
            user=user,
            task__in=tasks,
            completed=True,
            session_type=PomodoroSession.SessionType.WORK,
        )
        .values("task_id")
        .annotate(total=Sum("duration_minutes"))
    )
    return {row["task_id"]: row["total"] for row in rows}


def remaining_minutes(task, focus=None):
    if focus is None:
        focus = focus_minutes(task)
    return max(0, task.estimated_duration - focus)


def overlaps_busy(busy, start, end):
    return any(a < end and b > start for a, b in busy)


def _relevant_blocks(task, now, blocks=None):
    if blocks is None:
        return list(
            task.schedule_blocks.filter(end_time__gt=now, end_time__lte=task.deadline)
        )
    return [b for b in blocks if b.end_time > now and b.end_time <= task.deadline]


def planned_minutes(task, now=None, busy=None, blocks=None):
    now = now or timezone.now()
    blocks = _relevant_blocks(task, now, blocks)
    if not blocks:
        return 0
    if busy is None:
        from .availability import busy_intervals

        busy = busy_intervals(
            task.user,
            min(b.start_time for b in blocks),
            max(b.end_time for b in blocks),
        )
    return sum(
        max(
            0,
            int(
                (
                    min(b.end_time, task.deadline) - max(b.start_time, now)
                ).total_seconds()
                / 60
            ),
        )
        for b in blocks
        if not overlaps_busy(busy, b.start_time, b.end_time)
    )


def planned_minutes_map(user, tasks, now=None, busy=None):
    """Tính planned_minutes cho nhiều task chỉ với một lần truy vấn lịch bận."""
    now = now or timezone.now()
    tasks = list(tasks)
    if not tasks:
        return {}
    blocks = list(
        ScheduleBlock.objects.filter(
            user=user, task__in=tasks, end_time__gt=now
        ).select_related("task")
    )
    if busy is None and blocks:
        from .availability import busy_intervals

        busy = busy_intervals(
            user,
            min(b.start_time for b in blocks),
            max(b.end_time for b in blocks),
        )
    grouped = defaultdict(list)
    for block in blocks:
        grouped[block.task_id].append(block)
    return {
        task.pk: planned_minutes(task, now, busy=busy, blocks=grouped.get(task.pk, []))
        for task in tasks
    }


def refresh_scheduled(task, now=None, busy=None, focus=None):
    from apps.tasks.models import Task

    value = task.status != Task.Status.COMPLETED and planned_minutes(
        task, now, busy=busy
    ) >= remaining_minutes(task, focus)
    Task.objects.filter(pk=task.pk).update(is_scheduled=value)
    task.is_scheduled = value
    return value
