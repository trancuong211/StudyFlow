"""End-to-end HTTP workflows, with isolated users and no external credentials."""

import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.courses.models import Course
from apps.notifications.models import Notification
from apps.resources.models import StudyResource
from apps.scheduler.models import BusyPeriod, ScheduleBlock
from apps.tasks.models import Task


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class HTTPWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "workflow", email="workflow@example.test", password="WorkflowStudy2026!"
        )
        self.client.force_login(self.user)

    def task(self):
        return Task.objects.create(
            user=self.user, title="Bài tập", deadline=timezone.now() + timedelta(days=5)
        )

    def test_register_login_profile_password_change_and_logout(self):
        self.client.logout()
        response = self.client.post("/accounts/register/", {
            "username": "new-student", "email": "new@example.test", "full_name": "Sinh viên mới",
            "timezone": "Asia/Ho_Chi_Minh", "daily_study_goal_hours": 3,
            "password1": "SecureOrbit2026!", "password2": "SecureOrbit2026!",
        })
        self.assertEqual(response.status_code, 302)
        student = get_user_model().objects.get(username="new-student")
        self.assertEqual(self.client.session["_auth_user_id"], str(student.pk))
        self.assertFalse(student.is_staff)
        response = self.client.post("/accounts/profile/", {
            "username": student.username, "email": student.email, "full_name": "Sinh viên mới",
            "timezone": "UTC", "daily_study_goal_hours": 2,
            "study_start_hour": 9, "study_end_hour": 18, "email_reminders": "on",
        })
        self.assertEqual(response.status_code, 302)
        student.refresh_from_db()
        self.assertEqual(student.timezone, "UTC")
        self.assertEqual(student.daily_study_goal_hours, 2)
        response = self.client.post("/accounts/password/change/", {
            "old_password": "SecureOrbit2026!", "new_password1": "GalaxyFocus2026!",
            "new_password2": "GalaxyFocus2026!",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.client.post("/accounts/logout/")
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertFalse(self.client.login(username=student.email, password="SecureOrbit2026!"))
        self.assertTrue(self.client.login(username=student.email.upper(), password="GalaxyFocus2026!"))
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_password_reset_link_updates_password_and_cannot_be_reused(self):
        self.client.logout()
        response = self.client.post("/accounts/password/reset/", {"email": self.user.email})
        self.assertEqual(response.status_code, 302)
        link = re.search(r"https?://[^\s]+(/accounts/password/reset/[^\s]+/)", mail.outbox[0].body)
        self.assertIsNotNone(link)
        response = self.client.get(link.group(1))
        self.assertEqual(response.status_code, 302)
        response = self.client.post(response.url, {
            "new_password1": "RecoveredStudy2026!", "new_password2": "RecoveredStudy2026!",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.client.login(username=self.user.username, password="RecoveredStudy2026!"))
        self.client.logout()
        self.assertContains(self.client.get(link.group(1), follow=True), "Liên kết không hợp lệ")

    def test_register_rejects_duplicate_email_ignoring_case(self):
        self.client.logout()
        response = self.client.post("/accounts/register/", {
            "username": "another", "email": self.user.email.upper(), "full_name": "Test",
            "timezone": "UTC", "daily_study_goal_hours": 2,
            "password1": "AnotherStudy2026!", "password2": "AnotherStudy2026!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertFalse(get_user_model().objects.filter(username="another").exists())

    def test_superuser_can_manage_users_and_regular_user_cannot(self):
        admin = get_user_model().objects.create_superuser(
            "review-admin", "admin@example.test", "AdminReview2026!"
        )
        self.assertEqual(self.client.get("/admin/accounts/user/").status_code, 302)
        self.client.force_login(admin)
        self.assertContains(self.client.get("/admin/accounts/user/"), self.user.username)
        self.assertEqual(self.client.get(f"/admin/accounts/user/{self.user.pk}/change/").status_code, 200)

    def test_course_create_update_and_delete_preserves_related_task_and_resource(self):
        data = {
            "name": "Python", "code": "PY01", "color": "#3B82F6", "credits": 3,
            "semester": "2026", "instructor": "Giảng viên", "is_active": "on",
        }
        self.assertEqual(self.client.post("/courses/create/", data).status_code, 302)
        course = Course.objects.get(user=self.user)
        self.assertEqual(self.client.post(reverse("courses:edit", args=[course.pk]), {
            **data, "name": "Python nâng cao",
        }).status_code, 302)
        course.refresh_from_db()
        self.assertEqual(course.name, "Python nâng cao")
        task = self.task()
        task.course = course
        task.save()
        resource = StudyResource.objects.create(
            user=self.user, course=course, title="Link", url="https://example.org/"
        )
        self.assertEqual(self.client.post(reverse("courses:delete", args=[course.pk])).status_code, 302)
        task.refresh_from_db()
        resource.refresh_from_db()
        self.assertIsNone(task.course_id)
        self.assertIsNone(resource.course_id)

    def test_task_filters_completion_reopen_and_delete(self):
        task = self.task()
        course = Course.objects.create(user=self.user, name="Python")
        task.course = course
        task.priority = Task.Priority.HIGH
        task.save()
        Task.objects.create(user=self.user, title="Khác", deadline=task.deadline)
        response = self.client.get("/tasks/", {"q": "Bài", "course": course.pk, "priority": "3"})
        self.assertEqual([item.pk for item in response.context["tasks"]], [task.pk])
        ScheduleBlock.objects.create(
            user=self.user, task=task, title="Học", start_time=timezone.now() + timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=2), is_locked=True,
        )
        toggle = reverse("tasks:toggle_status", args=[task.pk])
        self.assertEqual(self.client.post(toggle).status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.COMPLETED)
        self.assertIsNotNone(task.completed_at)
        self.assertFalse(task.schedule_blocks.exists())
        self.client.post(toggle)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.TODO)
        self.assertIsNone(task.completed_at)
        self.client.post(reverse("tasks:delete", args=[task.pk]))
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())

    def test_weekly_busy_create_update_delete(self):
        start = timezone.localtime(timezone.now() + timedelta(days=1))
        data = {
            "title": "Ca làm", "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=2)).isoformat(), "repeats_weekly": "on",
            "repeat_until": (start + timedelta(days=28)).date().isoformat(),
        }
        self.assertEqual(self.client.post("/scheduler/busy/new/", data).status_code, 302)
        busy = BusyPeriod.objects.get(user=self.user)
        self.assertTrue(busy.repeats_weekly)
        self.assertEqual(self.client.post(reverse("scheduler:busy_edit", args=[busy.pk]), {
            **data, "title": "Ca làm mới",
        }).status_code, 302)
        self.assertEqual(self.client.post(reverse("scheduler:busy_delete", args=[busy.pk])).status_code, 302)
        self.assertFalse(BusyPeriod.objects.filter(pk=busy.pk).exists())

    def test_manual_block_create_update_delete_and_schedule_status(self):
        task = self.task()
        start = timezone.now() + timedelta(days=1)
        data = {
            "title": "Học Python", "task": task.pk, "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=1)).isoformat(), "is_locked": "on",
        }
        self.assertEqual(self.client.post("/scheduler/block/new/", data).status_code, 302)
        block = ScheduleBlock.objects.get(user=self.user)
        task.refresh_from_db()
        self.assertTrue(task.is_scheduled)
        self.assertEqual(self.client.post(reverse("scheduler:block_edit", args=[block.pk]), {
            **data, "end_time": (start + timedelta(minutes=30)).isoformat(),
        }).status_code, 302)
        task.refresh_from_db()
        self.assertFalse(task.is_scheduled)
        self.client.post(reverse("scheduler:block_delete", args=[block.pk]))
        self.assertFalse(ScheduleBlock.objects.filter(pk=block.pk).exists())

    def test_resource_link_create_update_delete(self):
        data = {"title": "Ghi chú Python", "url": "https://example.org/notes"}
        self.assertEqual(self.client.post("/resources/new/", data).status_code, 302)
        resource = StudyResource.objects.get(user=self.user)
        self.assertEqual(self.client.post(reverse("resources:edit", args=[resource.pk]), {
            **data, "title": "Ghi chú mới",
        }).status_code, 302)
        self.assertContains(self.client.get("/resources/", {"q": "mới"}), "Ghi chú mới")
        self.assertEqual(self.client.post(reverse("resources:delete", args=[resource.pk])).status_code, 302)
        self.assertFalse(StudyResource.objects.filter(pk=resource.pk).exists())

    def test_notifications_cannot_be_read_by_another_account(self):
        owner = get_user_model().objects.create_user("notice-owner", email="owner@example.test")
        item = Notification.objects.create(user=owner, title="Riêng", content="Riêng", dedup_key="private")
        self.assertNotContains(self.client.get("/notifications/"), "Riêng")
        self.assertEqual(self.client.post(reverse("notifications:read", args=[item.pk])).status_code, 404)
        item.refresh_from_db()
        self.assertFalse(item.is_read)

    def test_calendar_rejects_invalid_date_ranges(self):
        for params in [
            {"start": "invalid"}, {"start": "2026-10-04", "end": "2026-10-03"},
            {"start": "2026-01-01", "end": "2026-12-31"},
        ]:
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/scheduler/api/events/", params).status_code, 400)
