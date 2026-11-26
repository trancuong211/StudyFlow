"""Regression and workflow checks from the October 2026 functional review."""

from datetime import datetime, timedelta, timezone as utc
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.ai_assistant.models import AIInsight
from apps.ai_assistant.services import AIServiceBridge
from apps.courses.models import Course
from apps.notifications.models import Notification
from apps.notifications.tasks import daily_briefings
from apps.resources.models import StudyResource
from apps.scheduler.models import BusyPeriod, ScheduleBlock
from apps.tasks.models import Task

NOW = datetime(2026, 10, 4, 0, tzinfo=utc.utc)


class FunctionalReviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "functional-review", email="review@example.test", password="ReviewStudy2026!"
        )
        self.other = get_user_model().objects.create_user(
            "review-other", email="other@example.test", password="OtherStudy2026!"
        )
        self.client.force_login(self.user)
        self.clock = patch("django.utils.timezone.now", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def task(self, **kwargs):
        return Task.objects.create(
            user=self.user, title="Ôn tập", deadline=NOW + timedelta(days=3), **kwargs
        )

    def task_data(self, task, **overrides):
        data = {
            "title": task.title,
            "course_name": "",
            "priority": task.priority,
            "estimated_duration": task.estimated_duration,
            "deadline": task.deadline.isoformat(),
            "status": task.status,
            "difficulty": task.difficulty,
            "description": "",
        }
        return {**data, **overrides}

    def test_moving_deadline_before_manual_unlocked_block_is_rejected(self):
        task = self.task()
        ScheduleBlock.objects.create(
            user=self.user, task=task, title="Khung thủ công",
            start_time=NOW + timedelta(days=2),
            end_time=NOW + timedelta(days=2, hours=1),
            is_locked=False, is_auto_generated=False,
        )
        original = task.deadline
        response = self.client.post(
            reverse("tasks:edit", args=[task.pk]),
            self.task_data(task, deadline=(NOW + timedelta(days=1)).isoformat()),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())
        task.refresh_from_db()
        self.assertEqual(task.deadline, original)

    def test_deadline_edit_removes_only_unlocked_generated_blocks(self):
        task = self.task()
        block = ScheduleBlock.objects.create(
            user=self.user, task=task, title="Khung tự động",
            start_time=NOW + timedelta(days=2),
            end_time=NOW + timedelta(days=2, hours=1),
            is_locked=False, is_auto_generated=True,
        )
        response = self.client.post(
            reverse("tasks:edit", args=[task.pk]),
            self.task_data(task, deadline=(NOW + timedelta(days=1)).isoformat()),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ScheduleBlock.objects.filter(pk=block.pk).exists())

    def test_risk_cache_is_invalidated_after_task_changes(self):
        task = self.task()
        with patch("apps.ai_assistant.services.requests.post", side_effect=OSError):
            before = AIServiceBridge.analyze_schedule_and_deadlines(self.user)
            task.deadline = NOW - timedelta(hours=1)
            task.save()
            after = AIServiceBridge.analyze_schedule_and_deadlines(self.user)
        self.assertNotEqual(before.pk, after.pk)
        self.assertEqual(after.risk_level, "CRITICAL")

    def test_daily_summary_cache_is_invalidated_after_task_completion(self):
        task = self.task()
        task.deadline = NOW + timedelta(hours=4)
        task.save()
        with patch("apps.ai_assistant.services.requests.post", side_effect=OSError):
            before = AIServiceBridge.daily_summary(self.user)
            task.mark_completed()
            after = AIServiceBridge.daily_summary(self.user)
        self.assertNotEqual(before.pk, after.pk)

    def test_daily_briefing_retries_failed_email_without_duplicate_insight(self):
        self.task()
        with (
            patch("apps.ai_assistant.services.requests.post", side_effect=OSError),
            patch("apps.notifications.tasks.send_mail", side_effect=OSError),
        ):
            daily_briefings()
        notification = Notification.objects.get(user=self.user)
        self.assertIsNone(notification.emailed_at)
        with patch("apps.notifications.tasks.send_mail", return_value=1) as sender:
            daily_briefings()
        notification.refresh_from_db()
        self.assertIsNotNone(notification.emailed_at)
        self.assertEqual(Notification.objects.filter(user=self.user).count(), 1)
        self.assertEqual(AIInsight.objects.filter(user=self.user).count(), 1)
        self.assertGreaterEqual(sender.call_count, 1)

    def test_user_cannot_modify_another_users_data(self):
        course = Course.objects.create(user=self.other, name="Riêng tư")
        task = Task.objects.create(
            user=self.other, title="Riêng tư", deadline=NOW + timedelta(days=3)
        )
        busy = BusyPeriod.objects.create(
            user=self.other, title="Riêng tư", start_time=NOW,
            end_time=NOW + timedelta(hours=1),
        )
        block = ScheduleBlock.objects.create(
            user=self.other, title="Riêng tư", start_time=NOW,
            end_time=NOW + timedelta(hours=1),
        )
        for name, pk in [
            ("courses:edit", course.pk), ("courses:delete", course.pk),
            ("tasks:edit", task.pk), ("tasks:delete", task.pk),
            ("tasks:toggle_status", task.pk), ("scheduler:busy_edit", busy.pk),
            ("scheduler:busy_delete", busy.pk), ("scheduler:block_edit", block.pk),
            ("scheduler:block_delete", block.pk),
        ]:
            with self.subTest(route=name):
                self.assertEqual(self.client.post(reverse(name, args=[pk]), {}).status_code, 404)

    def test_existing_file_widget_uses_private_download_route(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            resource = StudyResource.objects.create(
                user=self.user, title="Ghi chú", file=SimpleUploadedFile("notes.txt", b"Notes")
            )
            response = self.client.get(reverse("resources:edit", args=[resource.pk]))
            self.assertContains(response, 'href="' + reverse("resources:download", args=[resource.pk]) + '"')
            self.assertNotContains(response, 'href="' + resource.file.url + '"')

    def test_replacing_resource_file_deletes_old_file_after_commit(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            resource = StudyResource.objects.create(
                user=self.user, title="Ghi chú", file=SimpleUploadedFile("old.txt", b"Old notes")
            )
            old_name, storage = resource.file.name, resource.file.storage
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                response = self.client.post(reverse("resources:edit", args=[resource.pk]), {
                    "title": "Ghi chú", "file": SimpleUploadedFile("new.txt", b"New notes"),
                })
                self.assertEqual(response.status_code, 302)
                self.assertTrue(storage.exists(old_name))
            self.assertEqual(len(callbacks), 1)
            self.assertFalse(storage.exists(old_name))
            resource.refresh_from_db()
            self.assertTrue(storage.exists(resource.file.name))

    def test_clearing_resource_file_does_not_delete_it_on_rollback(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            resource = StudyResource.objects.create(
                user=self.user, title="Ghi chú", file=SimpleUploadedFile("old.txt", b"Old notes")
            )
            original, storage = resource.file.name, resource.file.storage
            with transaction.atomic():
                response = self.client.post(reverse("resources:edit", args=[resource.pk]), {
                    "title": "Ghi chú", "file-clear": "on", "url": "https://example.org/notes",
                })
                self.assertEqual(response.status_code, 302)
                transaction.set_rollback(True)
            resource.refresh_from_db()
            self.assertEqual(resource.file.name, original)
            self.assertTrue(storage.exists(original))

    def test_malformed_numeric_task_filters_do_not_raise(self):
        self.task()
        for query in ("priority=²", "course=²", "priority=" + "9" * 5000, "course=" + "9" * 5000):
            with self.subTest(query=query[:30]):
                self.assertEqual(self.client.get("/tasks/?" + query).status_code, 200)

    def test_completed_task_is_not_shown_as_unscheduled(self):
        task = self.task()
        task.mark_completed()
        response = self.client.get("/tasks/", {"status": "COMPLETED"})
        self.assertContains(response, "Đã hoàn thành")
        self.assertContains(response, 'aria-label="Đánh dấu chưa hoàn thành"')
        self.assertNotContains(response, "Chưa xếp lịch")
