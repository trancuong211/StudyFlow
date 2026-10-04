"""Opt-in Chromium checks: python manage.py test apps.browser_checks.

Uses a separate Django test database and temporary media, never the local demo DB.
Requires requirements-dev.txt and `python -m playwright install chromium`.
"""

import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from apps.courses.models import Course
from apps.calendar_sync.models import GoogleCalendarEvent
from apps.notifications.models import Notification
from apps.pomodoro.models import PomodoroSession
from apps.resources.models import StudyResource
from apps.scheduler.models import BusyPeriod, ScheduleBlock
from apps.tasks.models import Task


@override_settings(
    DEBUG=True,
    AUTH_RATE_LIMIT_ENABLED=False,
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class BrowserChecks(StaticLiveServerTestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory(prefix="studyflow-browser-")
        self.addCleanup(self.media.cleanup)
        config = override_settings(MEDIA_ROOT=self.media.name)
        config.enable()
        self.addCleanup(config.disable)
        provider = patch("apps.ai_assistant.services.requests.post", side_effect=OSError)
        provider.start()
        self.addCleanup(provider.stop)
        self.user = get_user_model().objects.create_user(
            "browser-review", email="browser@example.test", password="BrowserStudy2026!"
        )
        self.course = Course.objects.create(user=self.user, name="Python")
        self.task = Task.objects.create(
            user=self.user, course=self.course, title="Ôn tập Python",
            deadline=timezone.now() + timedelta(days=5), estimated_duration=120,
        )
        Notification.objects.create(
            user=self.user, title="Nhắc thử", content="Ôn tập hôm nay", dedup_key="browser-review"
        )
        if self._testMethodName == "test_pages_fit_mobile_tablet_and_desktop":
            self.user.full_name = "Sinh viên " + "x" * 140
            self.user.save()
            self.course.name = "Môn_học_" + "x" * 140
            self.course.save()
            self.task.title = "Công_việc_" + "x" * 190
            self.task.save()
            self.resource = StudyResource.objects.create(
                user=self.user, title="Tài_liệu_" + "x" * 190,
                url="https://example.test/notes", description="x" * 500,
            )
            PomodoroSession.objects.create(
                user=self.user, task=self.task, start_time=timezone.now() - timedelta(hours=1),
                end_time=timezone.now(), duration_minutes=25, completed=True,
            )
            ScheduleBlock.objects.create(
                user=self.user, task=self.task, title=self.task.title,
                start_time=timezone.now() + timedelta(hours=2),
                end_time=timezone.now() + timedelta(hours=3),
            )
        if self._testMethodName == "test_calendar_displays_overnight_events_and_readonly_actions":
            morning = timezone.localtime().replace(hour=1, minute=0, second=0, microsecond=0)
            GoogleCalendarEvent.objects.create(
                user=self.user, google_id="synthetic-overnight", title="Sự kiện lúc 1 giờ sáng",
                start_time=morning, end_time=morning + timedelta(hours=1),
            )
        self.runtime = sync_playwright().start()
        self.addCleanup(self.runtime.stop)
        self.browser = self.runtime.chromium.launch()
        self.addCleanup(self.browser.close)
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        self.addCleanup(self.context.close)
        # Keep checks independent of Google Fonts or other external services.
        self.context.route(
            "**/*", lambda route: route.continue_()
            if route.request.url.startswith(self.live_server_url) else route.abort()
        )
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))

    def goto(self, path):
        response = self.page.goto(self.live_server_url + path)
        self.assertEqual(response.status, 200, path)
        self.page.wait_for_load_state("networkidle")

    def login(self):
        self.goto("/accounts/login/")
        self.page.locator("#id_username").fill(self.user.username)
        self.page.locator("#id_password").fill("BrowserStudy2026!")
        self.page.get_by_role("button", name="Đăng nhập", exact=True).click()
        self.page.wait_for_url(self.live_server_url + "/")
        self.page.wait_for_load_state("networkidle")

    def test_anonymous_pages_fit_small_screens_and_sidebar_closes_with_escape(self):
        for width in (320, 375, 800, 1920):
            self.page.set_viewport_size({"width": width, "height": 1000})
            for path in ("/accounts/login/", "/accounts/register/", "/accounts/password/reset/"):
                self.goto(path)
                sizes = self.page.evaluate("""() => ({
                    viewport: window.innerWidth, page: document.documentElement.scrollWidth,
                    main: document.getElementById('mainContent').clientWidth,
                    content: document.getElementById('mainContent').scrollWidth
                })""")
                self.assertLessEqual(sizes["page"], sizes["viewport"] + 1, (width, path, sizes))
                self.assertLessEqual(sizes["content"], sizes["main"] + 1, (width, path, sizes))
                expect(self.page.locator("#sidebarToggle")).to_have_count(0)
        self.page.set_viewport_size({"width": 375, "height": 1000})
        self.login()
        self.page.get_by_role("button", name="Mở menu điều hướng").click()
        expect(self.page.locator("#sidebarToggle")).to_have_attribute("aria-expanded", "true")
        self.page.keyboard.press("Escape")
        expect(self.page.locator("#sidebarToggle")).to_have_attribute("aria-expanded", "false")
        self.assertEqual(self.errors, [])

    def test_pages_fit_mobile_tablet_and_desktop(self):
        self.login()
        artifacts = Path("test-results/ui-review")
        artifacts.mkdir(parents=True, exist_ok=True)
        paths = [
            "/", "/courses/", "/courses/create/", "/tasks/", "/tasks/create/",
            "/scheduler/", "/scheduler/block/new/", "/scheduler/busy/",
            "/scheduler/busy/new/", "/pomodoro/", "/resources/", "/resources/new/",
            "/notifications/", "/ai/", "/calendar/", "/accounts/profile/",
            "/accounts/password/change/",
            f"/courses/{self.course.pk}/edit/", f"/courses/{self.course.pk}/delete/",
            f"/tasks/{self.task.pk}/edit/", f"/tasks/{self.task.pk}/delete/",
            f"/resources/{self.resource.pk}/edit/", f"/resources/{self.resource.pk}/delete/",
            "/accounts/password/reset/",
        ]
        overflow = []
        for width in (375, 800, 1920):
            self.page.set_viewport_size({"width": width, "height": 1000})
            for path in paths:
                self.goto(path)
                sizes = self.page.evaluate("""() => {
                    const main = document.getElementById('mainContent');
                    return {viewport: window.innerWidth, page: document.documentElement.scrollWidth,
                        main: main.clientWidth, content: main.scrollWidth};
                }""")
                if sizes["page"] > sizes["viewport"] + 1 or sizes["content"] > sizes["main"] + 1:
                    overflow.append((width, path, sizes))
                if path in ("/", "/scheduler/", "/pomodoro/") and width in (375, 1920):
                    filename = path.strip("/") or "dashboard"
                    self.page.screenshot(path=str(artifacts / f"{filename}-{width}.png"), full_page=True)
        self.assertEqual(overflow, [], f"Horizontal overflow: {overflow}")
        self.assertEqual(self.errors, [])

    def test_calendar_displays_overnight_events_and_readonly_actions(self):
        self.login()
        self.goto("/scheduler/")
        event = self.page.locator(".fc-event").filter(has_text="Sự kiện lúc 1 giờ sáng")
        expect(event).to_be_visible()
        event.click()
        expect(self.page.locator("#event-dialog")).to_be_visible()
        expect(self.page.locator("#event-edit")).not_to_be_visible()
        expect(self.page.locator("#event-lock")).not_to_be_visible()
        self.page.locator("#event-close").click()
        expect(self.page.locator("#event-dialog")).not_to_be_visible()
        self.assertEqual(self.errors, [])

    def test_create_schedule_timer_resources_and_reminders(self):
        self.login()
        self.goto("/tasks/create/")
        self.page.locator("#id_course_name").fill("Python")
        self.page.locator("#id_title").fill("Bài tập mới từ trình duyệt")
        self.page.locator("#id_deadline").fill(
            timezone.localtime(timezone.now() + timedelta(days=6)).strftime("%Y-%m-%dT%H:%M")
        )
        self.page.get_by_role("button", name="Lưu công việc").click()
        self.page.wait_for_url(self.live_server_url + "/tasks/")
        expect(self.page.get_by_text("Bài tập mới từ trình duyệt", exact=True)).to_be_visible()

        self.goto("/scheduler/busy/new/")
        busy_start = timezone.localtime(timezone.now() + timedelta(days=1)).replace(hour=17, minute=0)
        self.page.locator("#id_title").fill("Ca làm thử")
        self.page.locator("#id_start_time").fill(busy_start.strftime("%Y-%m-%dT%H:%M"))
        self.page.locator("#id_end_time").fill((busy_start + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"))
        self.page.locator("#id_repeats_weekly").check()
        self.page.get_by_role("button", name="Lưu thay đổi").click()
        self.page.wait_for_url(self.live_server_url + "/scheduler/busy/")
        expect(self.page.get_by_text("Ca làm thử", exact=True)).to_be_visible()

        self.goto("/scheduler/")
        self.page.get_by_role("button", name="Tự động sắp lịch tuần").click()
        self.page.wait_for_load_state("networkidle")
        artifacts = Path("test-results/ui-review")
        artifacts.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(artifacts / "calendar-workflow-desktop.png"), full_page=True)
        expect(self.page.locator(".fc-event").first).to_be_visible()
        self.page.locator(".fc-event").filter(has_text="[Học]").first.click()
        expect(self.page.locator("#event-dialog")).to_be_visible()
        self.page.locator("#event-lock").click()
        expect(self.page.locator("#event-dialog")).not_to_be_visible()
        self.page.wait_for_load_state("networkidle")

        self.goto("/pomodoro/")
        self.page.locator("#task-select").select_option(str(self.task.pk))
        self.page.locator("#btn-toggle").click()
        expect(self.page.locator("#btn-toggle")).to_have_text("Tạm dừng")
        self.page.reload()
        expect(self.page.locator("#btn-toggle")).to_have_text("Tạm dừng")
        self.page.locator("#btn-toggle").click()
        expect(self.page.locator("#btn-toggle")).to_have_text("Tiếp tục")
        self.page.reload()
        expect(self.page.locator("#btn-toggle")).to_have_text("Tiếp tục")
        self.page.once("dialog", lambda dialog: dialog.accept())
        self.page.locator("#btn-reset").click()
        expect(self.page.locator("#btn-toggle")).to_have_text("Bắt đầu")

        self.goto("/resources/new/")
        self.page.locator("#id_title").fill("Ghi chú thử")
        self.page.locator("#id_file").set_input_files(
            {"name": "review.txt", "mimeType": "text/plain", "buffer": b"Browser review notes"}
        )
        self.page.get_by_role("button", name="Lưu thay đổi").click()
        self.page.wait_for_url(self.live_server_url + "/resources/")
        with self.page.expect_download() as downloaded:
            self.page.get_by_role("link", name="Tải tài liệu").click()
        self.assertEqual(Path(downloaded.value.path()).read_bytes(), b"Browser review notes")
        expect(self.page.get_by_text("Ghi chú thử", exact=True)).to_be_visible()
        self.page.get_by_role("link", name="Sửa", exact=True).click()
        with self.page.expect_download() as current_file:
            self.page.get_by_role("link", name="Tải tệp hiện tại").click()
        self.assertEqual(Path(current_file.value.path()).read_bytes(), b"Browser review notes")
        self.page.locator("#id_file").set_input_files(
            {"name": "updated.txt", "mimeType": "text/plain", "buffer": b"Updated browser notes"}
        )
        self.page.get_by_role("button", name="Lưu thay đổi").click()
        self.page.wait_for_url(self.live_server_url + "/resources/")
        with self.page.expect_download() as updated_file:
            self.page.get_by_role("link", name="Tải tài liệu").click()
        self.assertEqual(Path(updated_file.value.path()).read_bytes(), b"Updated browser notes")

        self.goto("/ai/")
        self.page.get_by_role("button", name="Phân tích deadline").click()
        self.page.wait_for_load_state("networkidle")
        expect(self.page.get_by_role("button", name="Ẩn bản phân tích")).to_be_visible()

        self.goto("/notifications/")
        self.page.get_by_role("button", name="Đánh dấu đã đọc").click()
        self.page.wait_for_load_state("networkidle")
        expect(self.page.get_by_role("button", name="Đánh dấu đã đọc")).to_have_count(0)
        self.assertEqual(self.errors, [])
