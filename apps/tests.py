"""Unit test cho StudyFlow: trang, bộ lọc, API block, AI fallback, completed_at, CSRF, múi giờ."""
import json
import os
import re
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.ai_assistant.models import AIInsight
from apps.calendar_sync.models import GoogleCalendarToken
from apps.courses.models import Course
from apps.scheduler.engine.optimizer import ScheduleOptimizer
from apps.scheduler.models import ScheduleBlock
from apps.tasks.models import Task

# 20:00 UTC = 03:00 ngày hôm sau theo giờ Asia/Ho_Chi_Minh
FIXED_NOW = datetime(2026, 1, 1, 20, 0, 0, tzinfo=dt_timezone.utc)
LOCAL_TODAY = date(2026, 1, 2)  # ngày hiện tại theo giờ VN tại FIXED_NOW


class SmokePageTests(TestCase):
    """Mục 1 & 5: mọi trang chính trả 200, bộ lọc tham số sai không gây 500."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='smoke', password='pass12345')

    def setUp(self):
        self.client.force_login(self.user)

    def test_all_pages_return_200(self):
        paths = [
            '/',
            '/accounts/profile/',
            '/courses/',
            '/tasks/',
            '/scheduler/',
            '/pomodoro/',
            '/ai/',
        ]
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, f'{path} -> {response.status_code}')

    def test_invalid_filter_params_do_not_500(self):
        response = self.client.get('/tasks/?course=abc&priority=abc')
        self.assertEqual(response.status_code, 200)

    def test_invalid_status_filter_does_not_500(self):
        response = self.client.get('/tasks/?status=khong-ton-tai')
        self.assertEqual(response.status_code, 200)

    def test_sidebar_uses_existing_calendar_url(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn('calendar_sync:sync', content)
        self.assertIn(reverse('calendar_sync:settings'), content)

    def test_sidebar_overlay_hidden_by_default(self):
        """Mục 10: overlay không còn class sidebar-overlay ở trạng thái mặc định."""
        content = self.client.get('/').content.decode()
        match = re.search(r'<div[^>]*id="sidebarOverlay"[^>]*>', content)
        self.assertIsNotNone(match, 'không tìm thấy phần tử #sidebarOverlay')
        self.assertNotIn('sidebar-overlay', match.group(0))


class TaskTests(TestCase):
    """Mục 7 & 9: completed_at theo form và trạng thái chuyển bằng POST."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='taskuser', password='pass12345')
        cls.task = Task.objects.create(
            user=cls.user,
            title='Bài tập Toán',
            deadline=timezone.now() + timedelta(days=3),
            status=Task.Status.TODO,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _form_data(self, status, course_name=''):
        return {
            'course_name': course_name,
            'title': 'Bài tập Toán',
            'description': '',
            'priority': str(Task.Priority.HIGH),
            'estimated_duration': '60',
            'deadline': '2026-01-05T10:00',
            'status': status,
            'difficulty': str(Task.Difficulty.MEDIUM),
        }

    def test_completed_at_set_when_form_changes_to_completed(self):
        response = self.client.post(reverse('tasks:edit', args=[self.task.pk]), self._form_data('COMPLETED'))
        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.COMPLETED)
        self.assertIsNotNone(self.task.completed_at)

    def test_completed_at_cleared_when_form_changes_from_completed(self):
        self.task.mark_completed()
        self.assertIsNotNone(self.task.completed_at)
        response = self.client.post(reverse('tasks:edit', args=[self.task.pk]), self._form_data('TODO'))
        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)
        self.assertIsNone(self.task.completed_at)

    def test_toggle_status_get_returns_405(self):
        response = self.client.get(reverse('tasks:toggle_status', args=[self.task.pk]))
        self.assertEqual(response.status_code, 405)

    def test_toggle_status_post_sets_and_clears_completed_at(self):
        url = reverse('tasks:toggle_status', args=[self.task.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.COMPLETED)
        self.assertIsNotNone(self.task.completed_at)

        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.TODO)
        self.assertIsNone(self.task.completed_at)


class TaskCourseInputTests(TestCase):
    """Ô "Môn học" ở form thêm/sửa task là ô text tự nhập (không còn dropdown)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='courseuser', password='pass12345')

    def setUp(self):
        self.client.force_login(self.user)

    def _data(self, course_name, title='Task mới'):
        return {
            'course_name': course_name,
            'title': title,
            'description': '',
            'priority': str(Task.Priority.MEDIUM),
            'estimated_duration': '45',
            'deadline': '2026-02-01T09:00',
            'status': Task.Status.TODO,
            'difficulty': str(Task.Difficulty.MEDIUM),
        }

    def test_create_form_renders_text_input_for_course(self):
        response = self.client.get(reverse('tasks:create'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('name="course_name"', content)
        match = re.search(r'<input[^>]*name="course_name"[^>]*>', content)
        self.assertIsNotNone(match)
        self.assertIn('type="text"', match.group(0))
        self.assertNotIn('name="course"', content)

    def test_create_task_creates_new_course_by_name(self):
        response = self.client.post(reverse('tasks:create'), self._data('Đại số'))
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title='Task mới')
        self.assertIsNotNone(task.course)
        self.assertEqual(task.course.name, 'Đại số')
        self.assertEqual(task.course.user_id, self.user.pk)

    def test_create_task_reuses_existing_course_case_insensitive(self):
        Course.objects.create(user=self.user, name='Vật lý')
        response = self.client.post(reverse('tasks:create'), self._data('  vậT LÝ  '))
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title='Task mới')
        self.assertEqual(Course.objects.filter(user=self.user).count(), 1)
        self.assertEqual(task.course.name, 'Vật lý')

    def test_create_task_without_course_name(self):
        response = self.client.post(reverse('tasks:create'), self._data(''))
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title='Task mới')
        self.assertIsNone(task.course)
        self.assertFalse(Course.objects.filter(user=self.user).exists())

    def test_edit_form_prefills_course_name(self):
        course = Course.objects.create(user=self.user, name='Hóa học')
        task = Task.objects.create(
            user=self.user, course=course, title='Bài tập hóa',
            deadline=timezone.now() + timedelta(days=2),
        )
        content = self.client.get(reverse('tasks:edit', args=[task.pk])).content.decode()
        self.assertIn('name="course_name"', content)
        self.assertIn(f'value="{course.name}"', content)

    def test_edit_task_can_clear_course(self):
        course = Course.objects.create(user=self.user, name='Sinh học')
        task = Task.objects.create(
            user=self.user, course=course, title='Bài tập sinh',
            deadline=timezone.now() + timedelta(days=2),
        )
        response = self.client.post(reverse('tasks:edit', args=[task.pk]), self._data('', title='Bài tập sinh'))
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertIsNone(task.course)


class SchedulerTests(TestCase):
    """Mục 6 & 9: kéo–thả block, auto-schedule bằng POST."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='scheduser', password='pass12345')
        cls.block = ScheduleBlock.objects.create(
            user=cls.user,
            title='Khung học',
            start_time=timezone.now() + timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=2),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def _post_block(self, data):
        url = reverse('scheduler:api_update_block', args=[self.block.pk])
        return self.client.post(url, data=json.dumps(data), content_type='application/json')

    def test_update_block_with_null_end_does_not_400(self):
        response = self._post_block({
            'start': '2026-01-01T10:00:00+07:00',
            'end': None,
        })
        self.assertNotEqual(response.status_code, 400)
        self.assertEqual(response.status_code, 200)
        self.block.refresh_from_db()
        self.assertIsNotNone(self.block.start_time)

    def test_update_block_handles_z_suffix(self):
        response = self._post_block({
            'start': '2026-01-01T10:00:00Z',
            'end': '2026-01-01T11:00:00Z',
        })
        self.assertEqual(response.status_code, 200)
        self.block.refresh_from_db()
        self.assertEqual(self.block.end_time, datetime(2026, 1, 1, 11, 0, tzinfo=dt_timezone.utc))

    def test_update_block_end_before_start_returns_400(self):
        response = self._post_block({
            'start': '2026-01-01T11:00:00Z',
            'end': '2026-01-01T10:00:00Z',
        })
        self.assertEqual(response.status_code, 400)

    def test_update_block_without_end_keeps_old_end(self):
        old_end = self.block.end_time
        response = self._post_block({'start': '2026-01-01T10:00:00+07:00'})
        self.assertEqual(response.status_code, 200)
        self.block.refresh_from_db()
        self.assertEqual(self.block.end_time, old_end)

    def test_auto_schedule_get_returns_405(self):
        response = self.client.get(reverse('scheduler:auto_schedule'))
        self.assertEqual(response.status_code, 405)

    def test_auto_schedule_post_redirects(self):
        response = self.client.post(reverse('scheduler:auto_schedule'))
        self.assertEqual(response.status_code, 302)


class AIAssistantTests(TestCase):
    """Mục 4: AI service lỗi (non-200) vẫn trả insight, view không 500."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='aiuser', password='pass12345')

    def setUp(self):
        self.client.force_login(self.user)

    def test_service_error_falls_back_to_heuristic(self):
        fake_response = mock.Mock(status_code=500)
        with mock.patch('apps.ai_assistant.services.requests.post', return_value=fake_response):
            response = self.client.post(reverse('ai_assistant:generate_insight'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(AIInsight.objects.filter(user=self.user).exists())

    def test_service_exception_falls_back_to_heuristic(self):
        with mock.patch('apps.ai_assistant.services.requests.post', side_effect=Exception('boom')):
            response = self.client.post(reverse('ai_assistant:generate_insight'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(AIInsight.objects.filter(user=self.user).exists())

    def test_bad_json_falls_back_to_heuristic(self):
        fake_response = mock.Mock(status_code=200)
        fake_response.json.side_effect = ValueError('not json')
        with mock.patch('apps.ai_assistant.services.requests.post', return_value=fake_response):
            response = self.client.post(reverse('ai_assistant:generate_insight'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(AIInsight.objects.filter(user=self.user).exists())

    def test_insights_page_returns_200(self):
        response = self.client.get(reverse('ai_assistant:insights'))
        self.assertEqual(response.status_code, 200)


class TimeZoneTests(TestCase):
    """Mục 8: đầu/cuối ngày và khởi tạo lịch theo giờ địa phương."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='tzuser', password='pass12345')

    def setUp(self):
        self.client.force_login(self.user)

    def test_dashboard_today_bounds_use_local_day(self):
        # 00:00 đúng giờ VN ngày 02/01 → phải thuộc "hôm nay"
        block_midnight = ScheduleBlock.objects.create(
            user=self.user,
            title='Đúng 00:00 VN',
            start_time=timezone.make_aware(datetime(2026, 1, 2, 0, 0)),
            end_time=timezone.make_aware(datetime(2026, 1, 2, 0, 30)),
        )
        # 01:00 giờ VN ngày 02/01 (nằm trong "hôm nay" theo VN nhưng trước 20:00 UTC)
        block_today = ScheduleBlock.objects.create(
            user=self.user,
            title='Sáng sớm VN',
            start_time=timezone.make_aware(datetime(2026, 1, 2, 1, 0)),
            end_time=timezone.make_aware(datetime(2026, 1, 2, 2, 0)),
        )
        # 23:59 giờ VN ngày 01/01 (hôm trước theo VN)
        block_yesterday = ScheduleBlock.objects.create(
            user=self.user,
            title='Đêm hôm trước',
            start_time=timezone.make_aware(datetime(2026, 1, 1, 23, 59)),
            end_time=timezone.make_aware(datetime(2026, 1, 1, 23, 59, 30)),
        )

        with mock.patch('apps.dashboard.views.timezone.now', return_value=FIXED_NOW):
            response = self.client.get(reverse('dashboard:index'))

        self.assertEqual(response.status_code, 200)
        today_blocks = list(response.context['today_schedule_blocks'])
        self.assertIn(block_midnight, today_blocks)
        self.assertIn(block_today, today_blocks)
        self.assertNotIn(block_yesterday, today_blocks)

    def test_optimizer_starts_from_local_date_and_covers_7_days(self):
        with mock.patch('apps.scheduler.engine.optimizer.timezone.now', return_value=FIXED_NOW):
            optimizer = ScheduleOptimizer(user=self.user)
            self.assertEqual(optimizer.start_date, LOCAL_TODAY)
            slots = optimizer.find_free_slots([])

        days = sorted({slot_start.date() for slot_start, _ in slots})
        self.assertEqual(len(days), 7, f'chỉ có {len(days)} ngày: {days}')
        self.assertEqual(days[0], LOCAL_TODAY)
        self.assertEqual(days[-1], LOCAL_TODAY + timedelta(days=6))

    def test_optimizer_first_slot_starts_after_local_midnight(self):
        with mock.patch('apps.scheduler.engine.optimizer.timezone.now', return_value=FIXED_NOW):
            optimizer = ScheduleOptimizer(user=self.user)
            slots = optimizer.find_free_slots([])
        first_start = min(slot_start for slot_start, _ in slots)
        self.assertEqual(first_start, timezone.make_aware(datetime(2026, 1, 2, 8, 0)))


class CalendarOAuthTests(TestCase):
    """Mục 11: luồng OAuth thật — thiếu config / state sai thì báo lỗi, không lưu token giả."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='googleuser', password='pass12345')

    def setUp(self):
        self.client.force_login(self.user)

    def test_connect_without_credentials_shows_error(self):
        env = {'GOOGLE_CLIENT_ID': '', 'GOOGLE_CLIENT_SECRET': ''}
        with mock.patch.dict(os.environ, env):
            response = self.client.get(reverse('calendar_sync:connect'))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GoogleCalendarToken.objects.filter(user=self.user).exists())
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_google_connected)

    def test_callback_with_wrong_state_is_rejected(self):
        self.session = self.client.session
        self.session['google_oauth_state'] = 'state-moi-ghi-nho'
        self.session.save()
        response = self.client.get(
            reverse('calendar_sync:oauth2callback'),
            {'code': 'abc123', 'state': 'state-sai'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GoogleCalendarToken.objects.filter(user=self.user).exists())
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_google_connected)

    def test_callback_without_code_is_rejected(self):
        response = self.client.get(reverse('calendar_sync:oauth2callback'))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GoogleCalendarToken.objects.filter(user=self.user).exists())
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_google_connected)
