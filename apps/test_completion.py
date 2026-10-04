"""Regression tests for scheduling, persistence, authorization and integrations."""

import json
import tempfile
from datetime import datetime, timedelta
from datetime import timezone as utc
from unittest.mock import Mock, patch

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ai_service.api.schemas import TaskInputSchema
from ai_service.services.analyzer import AIAnalyzer
from apps.accounts.forms import CustomUserChangeForm
from apps.accounts.models import User
from apps.accounts.timezones import user_zone
from apps.ai_assistant.models import AIInsight
from apps.ai_assistant.services import AIServiceBridge, habit_analysis
from apps.calendar_sync.models import (
    CalendarExport,
    GoogleCalendarEvent,
    GoogleCalendarToken,
)
from apps.calendar_sync.services import event_time, sync_calendar
from apps.courses.models import Course
from apps.notifications.models import Notification
from apps.notifications.tasks import send_due_reminders
from apps.pomodoro.models import PomodoroSession
from apps.resources.forms import ResourceForm
from apps.resources.models import StudyResource
from apps.scheduler.availability import recurring_intervals
from apps.scheduler.engine.optimizer import ScheduleOptimizer
from apps.scheduler.models import BusyPeriod, ScheduleBlock
from apps.scheduler.progress import refresh_scheduled, remaining_minutes
from apps.tasks.models import Task

NOW = datetime(2026, 1, 2, 0, tzinfo=utc.utc)  # 07:00 Vietnam


class CompletionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "reviewer", email="reviewer@example.test", password="StrongStudy123!"
        )
        self.other = User.objects.create_user("other", password="OtherStudy123!")
        self.client.force_login(self.user)
        self.clock = patch("django.utils.timezone.now", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def task(self, **kwargs):
        return Task.objects.create(
            user=self.user, title="Đồ án", deadline=NOW + timedelta(days=5), **kwargs
        )

    def block(self, task=None, start=1, minutes=60, **kwargs):
        return ScheduleBlock.objects.create(
            user=self.user,
            task=task,
            title="Học",
            start_time=NOW + timedelta(hours=start),
            end_time=NOW + timedelta(hours=start, minutes=minutes),
            **kwargs,
        )

    def post_json(self, url, data):
        return self.client.post(url, json.dumps(data), content_type="application/json")

    def test_new_pages_render(self):
        for url in [
            "/scheduler/busy/",
            "/scheduler/busy/new/",
            "/scheduler/block/new/",
            "/resources/",
            "/resources/new/",
            "/notifications/",
            "/calendar/",
            "/accounts/password/change/",
            "/accounts/password/reset/",
            "/health/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_daily_cap_and_report(self):
        self.user.daily_study_goal_hours = 1
        self.user.save()
        task = self.task(estimated_duration=240)
        scheduler = ScheduleOptimizer(self.user, days_ahead=1)
        blocks = scheduler.run()
        self.assertEqual(sum(b.duration_minutes for b in blocks), 60)
        self.assertEqual(scheduler.report[0]["missing_minutes"], 180)
        task.refresh_from_db()
        self.assertFalse(task.is_scheduled)

    def test_preserved_block_not_double_scheduled(self):
        task = self.task(estimated_duration=60)
        kept = self.block(task, is_locked=True)
        self.assertEqual(ScheduleOptimizer(self.user).run(), [])
        self.assertTrue(ScheduleBlock.objects.filter(pk=kept.pk).exists())
        task.refresh_from_db()
        self.assertTrue(task.is_scheduled)

    def test_manual_unlocked_block_preserved(self):
        task = self.task(estimated_duration=60)
        block = self.block(task)
        ScheduleOptimizer(self.user).run()
        self.assertTrue(ScheduleBlock.objects.filter(pk=block.pk).exists())
        self.assertEqual(task.schedule_blocks.count(), 1)

    def test_task_without_blocks_stale_flag_is_reset(self):
        task = self.task(estimated_duration=60, is_scheduled=True)
        BusyPeriod.objects.create(
            user=self.user,
            title="Bận",
            start_time=NOW - timedelta(days=1),
            end_time=NOW + timedelta(days=8),
        )
        self.assertEqual(ScheduleOptimizer(self.user).run(), [])
        task.refresh_from_db()
        self.assertFalse(task.is_scheduled)

    def test_crossing_boundary_busy_and_google_ignored_transparent(self):
        task = self.task(estimated_duration=60)
        BusyPeriod.objects.create(
            user=self.user,
            title="Ca làm",
            start_time=NOW - timedelta(hours=1),
            end_time=NOW + timedelta(hours=3),
        )
        GoogleCalendarEvent.objects.create(
            user=self.user,
            google_id="busy",
            title="Họp",
            start_time=NOW + timedelta(hours=3),
            end_time=NOW + timedelta(hours=4),
        )
        blocks = ScheduleOptimizer(self.user, days_ahead=1).run()
        self.assertTrue(blocks)
        self.assertGreaterEqual(blocks[0].start_time, NOW + timedelta(hours=4))

    def test_recurring_busy_keeps_local_hour(self):
        period = BusyPeriod.objects.create(
            user=self.user,
            title="Ca làm",
            start_time=NOW,
            end_time=NOW + timedelta(hours=2),
            repeats_weekly=True,
        )
        slots = recurring_intervals(
            period, NOW + timedelta(days=7), NOW + timedelta(days=8)
        )
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0][0], NOW + timedelta(days=7))

    def test_deadline_mid_slot_allocates_partial(self):
        task = self.task(estimated_duration=120)
        task.deadline = NOW + timedelta(hours=1, minutes=30)
        task.save()
        blocks = ScheduleOptimizer(self.user, days_ahead=1).run()
        self.assertEqual(sum(b.duration_minutes for b in blocks), 30)
        self.assertLessEqual(blocks[0].end_time, task.deadline)

    def test_repeated_scheduler_is_idempotent(self):
        self.task(estimated_duration=200)
        first = [(b.start_time, b.end_time) for b in ScheduleOptimizer(self.user).run()]
        second = [
            (b.start_time, b.end_time) for b in ScheduleOptimizer(self.user).run()
        ]
        self.assertEqual(first, second)

    def test_focus_credit_excludes_breaks(self):
        task = self.task(estimated_duration=60)
        for mode, duration in [("WORK", 25), ("SHORT_BREAK", 5)]:
            PomodoroSession.objects.create(
                user=self.user,
                task=task,
                start_time=NOW - timedelta(hours=1),
                end_time=NOW,
                session_type=mode,
                duration_minutes=duration,
                completed=True,
            )
        self.assertEqual(remaining_minutes(task), 35)
        blocks = ScheduleOptimizer(self.user).run()
        self.assertEqual(sum(b.duration_minutes for b in blocks), 35)

    def test_manual_study_counts_toward_daily_cap(self):
        self.user.daily_study_goal_hours = 1
        self.user.save()
        self.block(minutes=60)
        self.task(estimated_duration=60)
        self.assertEqual(ScheduleOptimizer(self.user, days_ahead=1).run(), [])

    def test_preserved_overload_is_warned(self):
        self.user.daily_study_goal_hours = 1
        self.user.save()
        self.block(minutes=120, is_locked=True)
        self.assertContains(self.client.get("/scheduler/"), "vượt mục tiêu")
        with patch("apps.ai_assistant.services.requests.post", side_effect=OSError()):
            insight = AIServiceBridge.analyze_schedule_and_deadlines(self.user)
        self.assertEqual(insight.risk_level, "HIGH")

    def test_same_deadline_prefers_high_priority(self):
        low = self.task(estimated_duration=60, priority=1)
        high = self.task(estimated_duration=60, priority=3)
        self.user.daily_study_goal_hours = 1
        self.user.save()
        blocks = ScheduleOptimizer(self.user, days_ahead=1).run()
        self.assertEqual(blocks[0].task_id, high.pk)

    def test_api_rejects_overlap_and_deadline(self):
        task = self.task()
        block = self.block(task)
        self.block(task, start=3)
        url = reverse("scheduler:api_update_block", args=[block.pk])
        for data in [
            {
                "start": (NOW + timedelta(hours=3)).isoformat(),
                "end": (NOW + timedelta(hours=4)).isoformat(),
            },
            {
                "start": task.deadline.isoformat(),
                "end": (task.deadline + timedelta(hours=1)).isoformat(),
            },
            {"start": None, "end": block.start_time.isoformat()},
            [],
        ]:
            with self.subTest(data=data):
                self.assertEqual(self.post_json(url, data).status_code, 400)
        block.refresh_from_db()
        self.assertEqual(block.start_time, NOW + timedelta(hours=1))

    def test_api_busy_and_other_user_block(self):
        block = self.block(self.task())
        BusyPeriod.objects.create(
            user=self.user,
            title="Ca làm",
            start_time=NOW + timedelta(hours=4),
            end_time=NOW + timedelta(hours=6),
        )
        url = reverse("scheduler:api_update_block", args=[block.pk])
        self.assertEqual(
            self.post_json(
                url,
                {
                    "start": (NOW + timedelta(hours=4)).isoformat(),
                    "end": (NOW + timedelta(hours=5)).isoformat(),
                },
            ).status_code,
            400,
        )
        self.client.force_login(self.other)
        self.assertEqual(self.post_json(url, {}).status_code, 404)

    def test_complete_task_removes_future_blocks(self):
        task = self.task()
        self.block(task, is_locked=True)
        task.mark_completed()
        self.assertFalse(task.schedule_blocks.exists())

    def test_mutating_gets_rejected(self):
        for url in [
            "/scheduler/auto-schedule/",
            "/pomodoro/api/start/",
            "/ai/analyze/",
            "/ai/summary/",
            "/calendar/sync/",
            "/calendar/disconnect/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)

    def test_csrf_required_for_start(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(
            client.post(
                "/pomodoro/api/start/", "{}", content_type="application/json"
            ).status_code,
            403,
        )

    def test_pomodoro_single_active_and_reloads(self):
        first = self.post_json("/pomodoro/api/start/", {"session_type": "WORK"}).json()[
            "session"
        ]
        second = self.post_json(
            "/pomodoro/api/start/", {"session_type": "SHORT_BREAK"}
        ).json()["session"]
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(
            self.client.get("/pomodoro/api/state/").json()["session"]["id"], first["id"]
        )
        self.assertEqual(PomodoroSession.objects.filter(is_active=True).count(), 1)

    def test_pomodoro_invalid_mode_and_fake_duration(self):
        self.assertEqual(
            self.post_json(
                "/pomodoro/api/start/", {"session_type": "FAKE"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post_json("/pomodoro/api/record/", {"duration": 999}).status_code, 400
        )

    def test_pomodoro_pause_finish_idempotent(self):
        session = self.post_json(
            "/pomodoro/api/start/", {"session_type": "WORK", "task_id": self.task().pk}
        ).json()["session"]
        pk = session["id"]
        url = f"/pomodoro/api/session/{pk}/"
        self.assertEqual(self.client.post(url + "finish/").status_code, 400)
        with patch(
            "django.utils.timezone.now", return_value=NOW + timedelta(minutes=10)
        ):
            paused = self.client.post(url + "pause/").json()["session"]
            self.assertEqual(paused["elapsed_seconds"], 600)
        with patch(
            "django.utils.timezone.now", return_value=NOW + timedelta(minutes=20)
        ):
            self.assertEqual(
                self.client.get("/pomodoro/api/state/").json()["session"][
                    "elapsed_seconds"
                ],
                600,
            )
            self.client.post(url + "resume/")
        with patch(
            "django.utils.timezone.now", return_value=NOW + timedelta(minutes=35)
        ):
            self.assertTrue(
                self.client.post(url + "finish/").json()["session"]["completed"]
            )
            self.client.post(url + "finish/")
        self.assertEqual(PomodoroSession.objects.filter(completed=True).count(), 1)
        self.assertEqual(PomodoroSession.objects.get(pk=pk).duration_minutes, 25)
        self.assertIsNone(self.client.get("/pomodoro/api/state/").json()["session"])

    def test_pomodoro_other_user_task_denied(self):
        task = Task.objects.create(
            user=self.other, title="Riêng", deadline=NOW + timedelta(days=1)
        )
        self.assertEqual(
            self.post_json("/pomodoro/api/start/", {"task_id": task.pk}).status_code,
            404,
        )

    def test_email_login(self):
        self.client.logout()
        response = self.client.post(
            "/accounts/login/",
            {"username": "REVIEWER@example.test", "password": "StrongStudy123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_sends_link(self):
        self.client.logout()
        response = self.client.post(
            "/accounts/password/reset/", {"email": self.user.email}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/password/reset/", mail.outbox[0].body)

    def test_invalid_timezone_and_hours(self):
        form = CustomUserChangeForm(
            data={
                "username": self.user.username,
                "email": self.user.email,
                "full_name": "Test",
                "timezone": "Invalid/Zone",
                "daily_study_goal_hours": 0,
                "study_start_hour": 22,
                "study_end_hour": 8,
            },
            instance=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("timezone", form.errors)
        self.assertIn("daily_study_goal_hours", form.errors)
        self.assertIn("__all__", form.errors)

    @override_settings(
        AUTH_RATE_LIMIT_ENABLED=True,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "test-rate-limit",
            }
        },
    )
    def test_login_is_rate_limited(self):
        from django.core.cache import cache

        cache.clear()
        self.client.logout()
        for _ in range(20):
            self.client.post(
                "/accounts/login/", {"username": "missing", "password": "wrong"}
            )
        self.assertEqual(
            self.client.post(
                "/accounts/login/", {"username": "missing", "password": "wrong"}
            ).status_code,
            429,
        )
        cache.clear()

    def test_course_and_task_forms_render_all_required_controls(self):
        self.assertContains(self.client.get("/tasks/create/"), 'name="difficulty"')
        self.assertContains(self.client.get("/courses/create/"), 'name="is_active"')

    def test_resource_relations_and_file_validation(self):
        course = Course.objects.create(user=self.other, name="Riêng")
        for upload in [
            SimpleUploadedFile("unsafe.html", b"<script>"),
            SimpleUploadedFile("big.pdf", b"x" * (10 * 1024 * 1024 + 1)),
        ]:
            form = ResourceForm(
                data={"title": "Tệp"}, files={"file": upload}, user=self.user
            )
            self.assertFalse(form.is_valid())
        form = ResourceForm(
            data={"title": "Link", "course": course.pk, "url": "https://example.org/"},
            user=self.user,
        )
        self.assertFalse(form.is_valid())

    def test_resource_download_is_private(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            override_settings(MEDIA_ROOT=folder),
        ):
            item = StudyResource.objects.create(
                user=self.user,
                title="Notes",
                file=SimpleUploadedFile("notes.pdf", b"%PDF notes"),
            )
            url = reverse("resources:download", args=[item.pk])
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            response.close()
            self.client.force_login(self.other)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(
                self.client.get("/media/" + item.file.name).status_code, 404
            )

    def test_resource_upload_form_success(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            override_settings(MEDIA_ROOT=folder),
        ):
            response = self.client.post(
                "/resources/new/",
                {
                    "title": "Ghi chú",
                    "file": SimpleUploadedFile("notes.txt", b"Synthetic test notes"),
                },
            )
            self.assertEqual(response.status_code, 302)
            item = StudyResource.objects.get(user=self.user)
            self.assertTrue(item.file.storage.exists(item.file.name))
            with self.captureOnCommitCallbacks(execute=True):
                item.delete()
            self.assertFalse(item.file.storage.exists(item.file.name))

    def test_user_deletion_cleans_resource_file(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            override_settings(MEDIA_ROOT=folder),
        ):
            item = StudyResource.objects.create(
                user=self.user,
                title="Notes",
                file=SimpleUploadedFile("notes.txt", b"Synthetic test notes"),
            )
            name, storage = item.file.name, item.file.storage
            with self.captureOnCommitCallbacks(execute=True):
                self.user.delete()
            self.assertFalse(storage.exists(name))

    def test_busy_form_accepts_weekly_period(self):
        response = self.client.post(
            "/scheduler/busy/new/",
            {
                "title": "Ca làm",
                "start_time": "2026-01-02T17:00",
                "end_time": "2026-01-02T20:00",
                "repeats_weekly": "on",
                "repeat_until": "2026-02-28",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(BusyPeriod.objects.get(user=self.user).repeats_weekly)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_reminders_are_deduplicated(self):
        task = self.task()
        task.deadline = NOW + timedelta(minutes=45)
        task.save()
        send_due_reminders()
        send_due_reminders()
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIsNotNone(Notification.objects.get().emailed_at)

    def test_failed_email_is_retryable(self):
        task = self.task()
        task.deadline = NOW + timedelta(hours=2)
        task.save()
        with patch(
            "apps.notifications.tasks.send_mail",
            side_effect=OSError("SMTP unavailable"),
        ):
            send_due_reminders()
        self.assertIsNone(Notification.objects.get().emailed_at)
        with patch("apps.notifications.tasks.send_mail", return_value=1):
            send_due_reminders()
        self.assertIsNotNone(Notification.objects.get().emailed_at)
        self.assertEqual(Notification.objects.count(), 1)

    def test_get_ai_does_not_create_data(self):
        self.task()
        self.client.get("/ai/")
        self.client.get("/")
        self.assertEqual(AIInsight.objects.count(), 0)

    def test_ai_fallback_cached_and_summary(self):
        self.task()
        with patch("apps.ai_assistant.services.requests.post", side_effect=OSError()):
            first = AIServiceBridge.analyze_schedule_and_deadlines(self.user)
            second = AIServiceBridge.analyze_schedule_and_deadlines(self.user)
            summary = AIServiceBridge.daily_summary(self.user)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.source, "rules")
        self.assertEqual(summary.insight_type, "DAILY_SUMMARY")

    def test_ai_overdue_and_capacity_risk(self):
        for deadline, capacity, expected in [
            (NOW - timedelta(hours=1), 0, "CRITICAL"),
            (NOW + timedelta(days=1), 10, "HIGH"),
        ]:
            task = TaskInputSchema(
                id=1,
                title="Đồ án",
                deadline=deadline,
                priority="HIGH",
                is_scheduled=False,
                estimated_duration=120,
                remaining_minutes=120,
                planned_minutes=0,
                available_minutes=capacity,
                cumulative_unscheduled_minutes=120,
            )
            result = AIAnalyzer.analyze_risks([task], NOW, use_llm=False)
            self.assertEqual(result.risk_level, expected)

    def test_real_habits_no_placeholder(self):
        PomodoroSession.objects.create(
            user=self.user,
            start_time=NOW,
            end_time=NOW + timedelta(minutes=25),
            duration_minutes=25,
            completed=True,
        )
        habits = habit_analysis(self.user)
        self.assertEqual(habits["week"][-1]["minutes"], 25)
        self.assertIsNone(habits["peak_hour"])
        self.assertContains(self.client.get("/"), "25p")

    def test_google_tokens_encrypted_at_rest(self):
        token = GoogleCalendarToken.objects.create(
            user=self.user,
            access_token="fake-access-secret",
            refresh_token="fake-refresh-secret",
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT access_token FROM calendar_sync_googlecalendartoken WHERE id = %s",
                [token.pk],
            )
            stored = cursor.fetchone()[0]
        self.assertNotIn("fake-access-secret", stored)
        token.refresh_from_db()
        self.assertEqual(token.access_token, "fake-access-secret")

    def test_google_all_day_uses_owner_zone(self):
        self.assertEqual(
            event_time({"date": "2026-01-02"}, user_zone(self.user)).hour, 0
        )

    def test_google_import_and_export_mapping(self):
        GoogleCalendarToken.objects.create(user=self.user, access_token="fake")
        block = self.block(self.task())
        events = Mock()
        events.list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "external",
                    "summary": "Ca làm",
                    "start": {"dateTime": (NOW + timedelta(hours=4)).isoformat()},
                    "end": {"dateTime": (NOW + timedelta(hours=5)).isoformat()},
                },
                {
                    "id": "own",
                    "extendedProperties": {
                        "private": {"studyflow_owner": str(self.user.pk)}
                    },
                    "start": {"dateTime": NOW.isoformat()},
                    "end": {"dateTime": (NOW + timedelta(hours=1)).isoformat()},
                },
            ]
        }
        events.insert.return_value.execute.return_value = {"id": "export-id"}
        events.get.return_value.execute.return_value = {
            "id": "export-id",
            "extendedProperties": {"private": {"studyflow_owner": str(self.user.pk)}},
        }
        service = Mock()
        service.events.return_value = events
        with patch("apps.calendar_sync.services.calendar_client", return_value=service):
            result = sync_calendar(self.user)
            self.assertEqual(result["imported"], 1)
            self.assertEqual(GoogleCalendarEvent.objects.get().google_id, "external")
            self.assertEqual(CalendarExport.objects.get().block_id, block.pk)
            sync_calendar(self.user)
            self.assertEqual(events.insert.call_count, 1)
            block.delete()
            sync_calendar(self.user)
            self.assertEqual(events.delete.call_count, 1)
        self.assertFalse(CalendarExport.objects.exists())
