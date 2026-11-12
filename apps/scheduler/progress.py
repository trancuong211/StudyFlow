from django.utils import timezone

from apps.pomodoro.models import PomodoroSession


def focus_minutes(task):
    return sum(
        task.pomodoro_sessions.filter(
            completed=True, session_type=PomodoroSession.SessionType.WORK
        ).values_list("duration_minutes", flat=True)
    )


def remaining_minutes(task):
    return max(0, task.estimated_duration - focus_minutes(task))


def planned_minutes(task, now=None):
    now = now or timezone.now()
    from .availability import busy_intervals

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
        for b in task.schedule_blocks.filter(
            end_time__gt=now, end_time__lte=task.deadline
        )
        if not busy_intervals(task.user, b.start_time, b.end_time)
    )


def refresh_scheduled(task):
    from apps.tasks.models import Task

    value = task.status != Task.Status.COMPLETED and planned_minutes(
        task
    ) >= remaining_minutes(task)
    Task.objects.filter(pk=task.pk).update(is_scheduled=value)
    task.is_scheduled = value
    return value
