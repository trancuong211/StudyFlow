import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.timezones import user_zone
from apps.scheduler.models import ScheduleBlock
from apps.tasks.models import Task

from .models import Notification

logger = logging.getLogger(__name__)


def deliver(notification):
    with transaction.atomic():
        item = (
            Notification.objects.select_for_update()
            .select_related("user")
            .get(pk=notification.pk)
        )
        if item.emailed_at or not item.user.email_reminders or not item.user.email:
            return
        try:
            sent = send_mail(
                item.title,
                item.content + "\n\n" + settings.SITE_URL + "/notifications/",
                settings.DEFAULT_FROM_EMAIL,
                [item.user.email],
                fail_silently=False,
            )
        except Exception:
            logger.warning(
                "Reminder email failed; pending notification will be retried",
                exc_info=False,
            )
            return
        if sent:
            item.emailed_at = timezone.now()
            item.save(update_fields=["emailed_at"])


@shared_task
def send_due_reminders():
    now = timezone.now()
    created_count = 0
    for task in (
        Task.objects.filter(user__is_active=True)
        .exclude(status="COMPLETED")
        .filter(
            deadline__gte=now - timedelta(days=7),
            deadline__lte=now + timedelta(hours=24),
        )
        .select_related("user")
    ):
        seconds = (task.deadline - now).total_seconds()
        kind = "overdue" if seconds <= 0 else "1h" if seconds <= 3600 else "24h"
        local = timezone.localtime(task.deadline, user_zone(task.user)).strftime(
            "%H:%M %d/%m/%Y"
        )
        title = ("Đã quá hạn: " if kind == "overdue" else "Sắp đến hạn: ") + task.title
        item, created = Notification.objects.get_or_create(
            dedup_key=f"deadline:{task.pk}:{task.deadline.isoformat()}:{kind}",
            defaults={
                "user": task.user,
                "task": task,
                "title": title[:200],
                "content": f"{task.title}\nDeadline: {local}. Hãy kiểm tra tiến độ và kế hoạch học.",
            },
        )
        created_count += int(created)
        deliver(item)
    for block in (
        ScheduleBlock.objects.filter(
            user__is_active=True,
            start_time__gt=now,
            start_time__lte=now + timedelta(minutes=30),
        )
        .exclude(task__status="COMPLETED")
        .select_related("user")
    ):
        item, created = Notification.objects.get_or_create(
            dedup_key=f"block:{block.pk}:{block.start_time.isoformat()}",
            defaults={
                "user": block.user,
                "task_id": block.task_id,
                "title": ("Sắp học: " + block.title)[:200],
                "content": f"Khung học bắt đầu lúc {timezone.localtime(block.start_time, user_zone(block.user)):%H:%M %d/%m}. Chuẩn bị tài liệu và bật Pomodoro.",
            },
        )
        created_count += int(created)
        deliver(item)
    return created_count


@shared_task
def daily_briefings():
    from apps.ai_assistant.services import AIServiceBridge

    count = 0
    for user in User.objects.filter(is_active=True):
        with timezone.override(user_zone(user)):
            local = timezone.localtime()
            key = f"daily:{user.pk}:{local.date().isoformat()}"
            if local.hour != 7:
                continue
            existing = Notification.objects.filter(dedup_key=key).first()
            if existing:
                deliver(existing)
                continue
            insight = AIServiceBridge.daily_summary(user)
            item, created = Notification.objects.get_or_create(
                dedup_key=key,
                defaults={
                    "user": user,
                    "title": insight.title,
                    "content": insight.content + "\n" + insight.actionable_advice,
                },
            )
            count += int(created)
            deliver(item)
    return count
