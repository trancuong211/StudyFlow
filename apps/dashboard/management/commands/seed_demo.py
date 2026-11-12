from datetime import timedelta
from getpass import getpass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.courses.models import Course
from apps.pomodoro.models import PomodoroSession
from apps.resources.models import StudyResource
from apps.scheduler.engine.optimizer import ScheduleOptimizer
from apps.scheduler.models import BusyPeriod
from apps.tasks.models import Task


class Command(BaseCommand):
    help = (
        "Create an isolated synthetic demo account; never modifies an existing account."
    )

    def add_arguments(self, parser):
        parser.add_argument("--username", default="studyflow-demo")
        parser.add_argument(
            "--password",
            help="Optional for automated local QA; interactive input is safer.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        name = options["username"]
        if User.objects.filter(username=name).exists():
            raise CommandError(
                "Username already exists. Choose another --username; no existing data was changed."
            )
        password = options["password"] or getpass("Demo password: ")
        if len(password) < 10:
            raise CommandError("Use at least 10 characters.")
        user = User.objects.create_user(
            name,
            email=name + "@example.test",
            password=password,
            full_name="Sinh viên Demo",
            email_reminders=False,
        )
        now = timezone.now()
        course = Course.objects.create(
            user=user, name="Lập trình Python", color="#3B82F6"
        )
        second = Course.objects.create(user=user, name="Cơ sở dữ liệu", color="#8B5CF6")
        for i, (title, minutes, days) in enumerate(
            [
                ("Hoàn thành đồ án StudyFlow", 240, 3),
                ("Ôn thi cơ sở dữ liệu", 180, 5),
                ("Đọc tài liệu thuật toán", 60, 7),
            ]
        ):
            Task.objects.create(
                user=user,
                course=course if i != 1 else second,
                title=title,
                estimated_duration=minutes,
                deadline=now + timedelta(days=days),
                priority=3 if i == 0 else 2,
            )
        local = timezone.localtime(now)
        start = local.replace(hour=17, minute=0, second=0, microsecond=0)
        if start < now:
            start += timedelta(days=1)
        BusyPeriod.objects.create(
            user=user,
            title="Ca làm thêm",
            start_time=start,
            end_time=start + timedelta(hours=3),
            repeats_weekly=True,
        )
        for i in range(7):
            beginning = now - timedelta(days=i, hours=1)
            PomodoroSession.objects.create(
                user=user,
                start_time=beginning,
                end_time=beginning + timedelta(minutes=25),
                duration_minutes=25,
                completed=True,
                session_type="WORK",
            )
        StudyResource.objects.create(
            user=user,
            course=course,
            title="Tài liệu Django chính thức",
            url="https://docs.djangoproject.com/en/5.2/",
        )
        ScheduleOptimizer(user).run()
        self.stdout.write(
            self.style.SUCCESS(
                f"Created demo account {name}. No admin permission granted."
            )
        )
