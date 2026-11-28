from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.scheduler.ics import escape_text, fold_line
from apps.scheduler.models import BusyPeriod, ScheduleBlock
from apps.tasks.models import Task


class ICSExportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "ics-user", email="ics@example.test", password="IcsExport2026!"
        )
        self.other_user = get_user_model().objects.create_user(
            "other-ics-user", email="other-ics@example.test", password="IcsExport2026!"
        )
        self.now = timezone.now()

    def create_task(self, user, title, status=Task.Status.TODO):
        return Task.objects.create(
            user=user,
            title=title,
            deadline=self.now + timedelta(days=2),
            status=status,
        )

    def test_export_requires_login(self):
        response = self.client.get(reverse("scheduler:export_ics"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_export_contains_only_users_blocks_and_open_tasks(self):
        block = ScheduleBlock.objects.create(
            user=self.user,
            title="Khung học của tôi",
            start_time=self.now + timedelta(days=1),
            end_time=self.now + timedelta(days=1, hours=1),
            notes="Ghi chú",
        )
        open_task = self.create_task(self.user, "Bài tập chưa xong")
        completed_task = self.create_task(
            self.user, "Bài tập đã xong", status=Task.Status.COMPLETED
        )
        ScheduleBlock.objects.create(
            user=self.other_user,
            title="Khung riêng người khác",
            start_time=self.now + timedelta(days=3),
            end_time=self.now + timedelta(days=3, hours=1),
        )
        self.create_task(self.other_user, "Task riêng người khác")
        BusyPeriod.objects.create(
            user=self.user,
            title="Lịch bận không xuất",
            start_time=self.now + timedelta(days=4),
            end_time=self.now + timedelta(days=4, hours=1),
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("scheduler:export_ics"))
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/calendar"))
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="studyflow.ics"',
        )
        self.assertIn("BEGIN:VCALENDAR", content)
        self.assertIn("END:VCALENDAR", content)
        self.assertIn(f"UID:block-{block.pk}@studyflow", content)
        self.assertIn(f"UID:task-{open_task.pk}@studyflow", content)
        self.assertIn("BEGIN:VALARM", content)
        self.assertNotIn(f"UID:task-{completed_task.pk}@studyflow", content)
        self.assertNotIn("Khung riêng người khác", content)
        self.assertNotIn("Task riêng người khác", content)
        self.assertNotIn("Lịch bận không xuất", content)
        self.assertGreaterEqual(content.count("BEGIN:VEVENT"), 2)

    def test_export_folds_escaped_vietnamese_text_with_crlf_and_octet_limit(self):
        title = "Tiếng Việt, có dấu; xuống dòng\n" + ("học tập " * 12)
        self.assertEqual(
            escape_text("A\\B;C,D\r\nE"),
            "A\\\\B\\;C\\,D\\nE",
        )
        folded = fold_line("SUMMARY:" + title)
        physical_lines = folded.split("\r\n")

        self.assertGreater(len(physical_lines), 1)
        self.assertTrue(all(len(line.encode("utf-8")) <= 75 for line in physical_lines))
        self.assertTrue(all(line.startswith(" ") for line in physical_lines[1:]))
        self.assertEqual(
            "".join(line[1:] if index else line for index, line in enumerate(physical_lines)),
            "SUMMARY:" + title,
        )

        ScheduleBlock.objects.create(
            user=self.user,
            title=title,
            start_time=self.now + timedelta(days=1),
            end_time=self.now + timedelta(days=1, hours=1),
        )
        self.client.force_login(self.user)
        content = self.client.get(reverse("scheduler:export_ics")).content.decode("utf-8")
        self.assertIn("SUMMARY:Tiếng Việt\\, có dấu\\; xuống dòng\\n", content)
        self.assertTrue(content.endswith("\r\n"))
        self.assertTrue(
            all(len(line.encode("utf-8")) <= 75 for line in content.split("\r\n")[:-1])
        )
        self.assertTrue(all(line.endswith("\r\n") for line in content.splitlines(keepends=True)))
