from datetime import timedelta, timezone as datetime_timezone

from django.utils import timezone

from apps.tasks.models import Task

from .models import ScheduleBlock


def escape_text(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
    )


def fold_line(line):
    folded = []
    current = []
    current_octets = 0
    limit = 75

    for character in line:
        octets = len(character.encode("utf-8"))
        if current_octets + octets > limit:
            folded.append("".join(current))
            current = []
            current_octets = 0
            folded.append("\r\n ")
            limit = 74
        current.append(character)
        current_octets += octets

    folded.append("".join(current))
    return "".join(folded)


def format_utc(value):
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    return value.astimezone(datetime_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_calendar(user, now=None):
    now = now or timezone.now()
    if timezone.is_naive(now):
        now = timezone.make_aware(now)
    start = now - timedelta(days=30)
    end = now + timedelta(days=180)
    stamp = format_utc(now)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//StudyFlow//Task2//VI",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:StudyFlow",
    ]

    blocks = (
        ScheduleBlock.objects.filter(
            user=user,
            start_time__gte=start,
            start_time__lte=end,
        )
        .select_related("task")
        .order_by("start_time", "pk")
    )
    for block in blocks:
        description = block.notes
        if block.task_id and block.task.user_id == user.pk:
            description = "\n".join(
                value for value in (description, f"Công việc: {block.task.title}") if value
            )
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:block-{block.pk}@studyflow",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{format_utc(block.start_time)}",
                f"DTEND:{format_utc(block.end_time)}",
                f"SUMMARY:{escape_text(block.title)}",
                f"DESCRIPTION:{escape_text(description)}",
                "END:VEVENT",
            ]
        )

    tasks = (
        Task.objects.filter(
            user=user,
            deadline__gte=start,
            deadline__lte=end,
        )
        .exclude(status=Task.Status.COMPLETED)
        .order_by("deadline", "pk")
    )
    for task in tasks:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:task-{task.pk}@studyflow",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{format_utc(task.deadline - timedelta(minutes=30))}",
                f"DTEND:{format_utc(task.deadline)}",
                f"SUMMARY:{escape_text('Hạn: ' + task.title)}",
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{escape_text('Hạn: ' + task.title)}",
                "TRIGGER:-PT60M",
                "END:VALARM",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    return "".join(f"{fold_line(line)}\r\n" for line in lines)
