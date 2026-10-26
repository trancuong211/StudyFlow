"""Task 5: explainable scores, real proposals, ownership and stale/replay safety."""

from datetime import datetime, timedelta, timezone as utc
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from ai_service.api.schemas import TaskInputSchema
from ai_service.services.risk import score_task
from apps.ai_assistant.planning import (
    MAX_AGE, ProposalPlanner, apply_proposal, current_task_risks, risk_cards,
)
from apps.ai_assistant.services import AIServiceBridge
from apps.calendar_sync.models import GoogleCalendarEvent
from apps.pomodoro.models import PomodoroSession
from apps.scheduler.engine.optimizer import ScheduleOptimizer
from apps.scheduler.models import BusyPeriod, ScheduleBlock
from apps.tasks.models import Task

NOW = datetime(2026, 10, 26, 0, tzinfo=utc.utc)  # 07:00 in Vietnam


class Task5Tests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('task5', email='task5@example.test', password='DemoStudy2026!')
        self.other = get_user_model().objects.create_user('other-task5', email='other-task5@example.test')
        self.client.force_login(self.user)
        clock = patch('django.utils.timezone.now', return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def task(self, **kwargs):
        return Task.objects.create(**{'user': self.user, 'title': 'Ôn Python',
            'estimated_duration': 60, 'deadline': NOW+timedelta(days=1), **kwargs})

    def block(self, task, **kwargs):
        return ScheduleBlock.objects.create(**{'user': self.user, 'task': task, 'title': 'Khung học',
            'start_time': NOW+timedelta(hours=2), 'end_time': NOW+timedelta(hours=3),
            'is_auto_generated': True, **kwargs})

    def score(self, **kwargs):
        data = {'id': 1, 'title': 'A', 'deadline': NOW+timedelta(days=5), 'priority': 'Cao',
            'estimated_duration': 120, 'is_scheduled': False, 'remaining_minutes': 120,
            'planned_minutes': 0, **kwargs}
        return score_task(TaskInputSchema(**data), NOW)

    def test_scores_and_thresholds_are_explainable_and_bounded(self):
        cases = [({}, 'MEDIUM', 59), ({'deadline': NOW+timedelta(hours=48)}, 'HIGH', 85),
            ({'deadline': NOW-timedelta(seconds=1)}, 'CRITICAL', 100),
            ({'planned_minutes': 120}, 'LOW', 0),
            ({'planned_minutes': 120, 'overloaded': True}, 'HIGH', 70),
            ({'available_minutes': 0, 'cumulative_unscheduled_minutes': 120}, 'HIGH', 99),
            ({'remaining_minutes': 0, 'deadline': NOW-timedelta(days=1)}, 'LOW', 0)]
        for data, level, score in cases:
            with self.subTest(data=data):
                result = self.score(**data)
                self.assertEqual((result.risk_level, result.score), (level, score))
                self.assertTrue(result.reasons)

    def test_partial_coverage_lowers_score_and_completed_capacity_does_not_raise_it(self):
        self.assertLess(self.score(planned_minutes=90).score, self.score().score)
        result = self.score(planned_minutes=120, available_minutes=0, cumulative_unscheduled_minutes=500)
        self.assertEqual(result.score, 0)

    def test_risk_badge_for_future_deadline_is_red_and_per_task(self):
        task = self.task()
        response = self.client.get(reverse('tasks:list'))
        self.assertContains(response, 'data-risk-level="HIGH"')
        self.assertContains(response, f'data-task-risk="{task.pk}"')
        self.assertContains(response, '85/100')
        task.mark_completed()
        self.assertNotContains(self.client.get(reverse('tasks:list')), 'data-risk-level="HIGH"')

    def test_live_risks_do_not_call_provider_or_create_insights(self):
        self.task()
        with patch('apps.ai_assistant.services.requests.post') as provider:
            cards, extra = risk_cards(self.user)
        provider.assert_not_called()
        self.assertEqual(extra, 0)
        self.assertEqual(cards[0]['risk_level'], 'HIGH')
        self.assertTrue(cards[0]['proposal'])
        self.assertFalse(self.user.ai_insights.exists())

    def test_add_proposal_applies_only_after_post_and_is_preserved(self):
        task = self.task()
        proposal = ProposalPlanner(self.user).propose(task)
        self.assertFalse(ScheduleBlock.objects.exists())
        url = reverse('ai_assistant:apply_suggestion')
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url, {'token': proposal['token']})
        self.assertEqual(response.status_code, 302)
        block = ScheduleBlock.objects.get(task=task)
        self.assertEqual((block.start_time, block.end_time), (proposal['start'], proposal['end']))
        self.assertTrue(block.is_locked)
        ScheduleOptimizer(self.user).run()
        self.assertEqual(ScheduleBlock.objects.filter(task=task).count(), 1)

    def test_partial_proposal_respects_daily_cap_and_marks_partial(self):
        self.user.daily_study_goal_hours = 1
        self.user.save()
        task = self.task(estimated_duration=180)
        proposal = ProposalPlanner(self.user).propose(task)
        self.assertEqual(proposal['minutes'], 60)
        self.assertTrue(proposal['partial'])

    def test_move_conflicting_auto_block_keeps_duration(self):
        task = self.task()
        block = self.block(task)
        BusyPeriod.objects.create(user=self.user, title='Ca làm', start_time=block.start_time, end_time=block.end_time)
        proposal = ProposalPlanner(self.user).propose(task)
        self.assertEqual(proposal['kind'], 'move')
        apply_proposal(self.user, proposal['token'])
        block.refresh_from_db()
        self.assertEqual(block.duration_minutes, 60)
        self.assertNotEqual(block.start_time, NOW+timedelta(hours=2))
        self.assertEqual(ScheduleBlock.objects.count(), 1)

    def test_move_from_overloaded_day_to_another_day(self):
        self.user.daily_study_goal_hours = 1
        self.user.save()
        task = self.task(deadline=NOW+timedelta(days=3))
        block = self.block(task)
        self.block(None, start_time=NOW+timedelta(hours=4), end_time=NOW+timedelta(hours=5), is_auto_generated=False)
        proposal = ProposalPlanner(self.user).propose(task)
        self.assertEqual(proposal['kind'], 'move')
        self.assertGreater(proposal['start'].date(), NOW.date())
        apply_proposal(self.user, proposal['token'])
        block.refresh_from_db()
        self.assertTrue(block.is_locked)

    def test_locked_and_manual_blocks_are_not_moved(self):
        for auto, locked in [(False, False), (True, True)]:
            with self.subTest(auto=auto, locked=locked):
                task = self.task(title=str((auto, locked)))
                block = self.block(task, is_auto_generated=auto, is_locked=locked)
                BusyPeriod.objects.create(user=self.user, title='Bận', start_time=block.start_time, end_time=block.end_time)
                proposal = ProposalPlanner(self.user).propose(task)
                self.assertEqual(proposal['kind'], 'add')
                apply_proposal(self.user, proposal['token'])
                block.refresh_from_db()
                self.assertEqual(block.start_time, NOW+timedelta(hours=2))

    def test_no_proposal_when_overdue_or_no_availability_or_already_covered(self):
        self.assertIsNone(ProposalPlanner(self.user).propose(self.task(deadline=NOW)))
        covered = self.task()
        self.block(covered)
        self.assertIsNone(ProposalPlanner(self.user).propose(covered))
        BusyPeriod.objects.create(user=self.user, title='Bận cả ngày', start_time=NOW, end_time=NOW+timedelta(days=3))
        self.assertIsNone(ProposalPlanner(self.user).propose(self.task()))

    def test_proposals_avoid_google_busy_respect_hours_and_deadline(self):
        task = self.task(deadline=NOW+timedelta(hours=4))
        GoogleCalendarEvent.objects.create(user=self.user, google_id='busy', title='Bận',
            start_time=NOW+timedelta(hours=1), end_time=NOW+timedelta(hours=2))
        proposal = ProposalPlanner(self.user).propose(task)
        self.assertGreaterEqual(proposal['start'], NOW+timedelta(hours=2))
        self.assertLessEqual(proposal['end'], task.deadline)
        self.assertGreaterEqual(proposal['start'].hour, self.user.study_start_hour)

    def test_proposal_cannot_be_forged_replayed_or_used_by_another_user(self):
        task = self.task()
        proposal = ProposalPlanner(self.user).propose(task)
        for user, token in [(self.other, proposal['token']), (self.user, proposal['token']+'x')]:
            with self.assertRaises(ValidationError):
                apply_proposal(user, token)
        apply_proposal(self.user, proposal['token'])
        with self.assertRaises(ValidationError):
            apply_proposal(self.user, proposal['token'])
        self.assertEqual(ScheduleBlock.objects.count(), 1)

    def test_expired_proposal_is_rejected(self):
        task = self.task()
        with patch('django.core.signing.time.time', return_value=100000):
            proposal = ProposalPlanner(self.user).propose(task)
        with patch('django.core.signing.time.time', return_value=100000+MAX_AGE+1):
            with self.assertRaises(ValidationError):
                apply_proposal(self.user, proposal['token'])
        self.assertFalse(ScheduleBlock.objects.exists())

    def test_calendar_settings_progress_or_deadline_changes_invalidate_proposal(self):
        task = self.task()
        changes = [
            lambda: BusyPeriod.objects.create(user=self.user, title='Bận', start_time=NOW+timedelta(hours=1), end_time=NOW+timedelta(hours=2)),
            lambda: Task.objects.filter(pk=task.pk).update(deadline=NOW+timedelta(days=2)),
            lambda: get_user_model().objects.filter(pk=self.user.pk).update(daily_study_goal_hours=1),
            lambda: PomodoroSession.objects.create(user=self.user, task=task, start_time=NOW-timedelta(hours=1), duration_minutes=25, completed=True),
        ]
        for change in changes:
            self.user.refresh_from_db()
            task.refresh_from_db()
            proposal = ProposalPlanner(self.user).propose(task)
            change()
            with self.assertRaises(ValidationError):
                apply_proposal(self.user, proposal['token'])
        self.assertFalse(ScheduleBlock.objects.exists())

    def test_csrf_and_login_required(self):
        url = reverse('ai_assistant:apply_suggestion')
        self.assertEqual(Client().post(url, {}).status_code, 302)
        secure_client = Client(enforce_csrf_checks=True)
        secure_client.force_login(self.user)
        self.assertEqual(secure_client.post(url, {}).status_code, 403)

    def test_service_cannot_override_local_task_scores(self):
        task = self.task()
        response = Mock()
        response.json.return_value = {'title': 'Diễn giải', 'summary': 'Nhận xét',
            'risk_level': 'LOW', 'advice': 'Lời khuyên', 'source': 'openai',
            'task_risks': [{'task_id': task.pk, 'title': task.title, 'score': 0,
                'risk_level': 'LOW', 'missing_minutes': 0, 'reasons': []}]}
        with patch('apps.ai_assistant.services.requests.post', return_value=response):
            insight = AIServiceBridge.analyze_schedule_and_deadlines(self.user)
        self.assertEqual(insight.risk_level, 'HIGH')
        self.assertEqual(insight.details['task_risks'][0]['task_id'], task.pk)
        self.assertGreaterEqual(insight.details['task_risks'][0]['score'], 70)

    def test_user_timezone_and_red_card_render(self):
        self.user.timezone = 'America/New_York'
        self.user.save()
        self.task()
        response = self.client.get(reverse('ai_assistant:insights'))
        self.assertContains(response, 'data-risk-level="HIGH"')
        self.assertContains(response, 'Áp dụng khung học')
        self.assertNotContains(response, 'Ôn tập của người khác')

    def test_other_users_tasks_are_not_scored_or_proposed(self):
        self.task(user=self.other, title='Ôn tập của người khác')
        self.assertEqual(current_task_risks(self.user), [])
        self.assertEqual(risk_cards(self.user), ([], 0))

    def test_calendar_event_is_red_for_deadline_risk_without_busy_conflict(self):
        task = self.task(estimated_duration=120)
        block = self.block(task)
        events = self.client.get(reverse('scheduler:api_events')).json()
        event = next(item for item in events if item['id'] == block.pk)
        self.assertEqual(event['backgroundColor'], '#b91c1c')
        self.assertFalse(event['extendedProps']['hasConflict'])
        self.assertGreaterEqual(event['extendedProps']['riskScore'], 70)
        self.assertEqual(event['extendedProps']['riskLevel'], 'HIGH')

    def test_task_deep_link_is_scoped_and_not_limited_to_first_20(self):
        for i in range(21):
            self.task(title=f'Việc {i}')
        selected = self.task(title='Việc cuối danh sách')
        response = self.client.get(reverse('ai_assistant:insights'), {'task': selected.pk})
        self.assertEqual(len(response.context['risk_cards']), 1)
        self.assertEqual(response.context['risk_cards'][0]['task_id'], selected.pk)
        other = self.task(user=self.other, title='Bí mật')
        response = self.client.get(reverse('ai_assistant:insights'), {'task': other.pk})
        self.assertEqual(response.context['risk_cards'], [])


@skipUnless(connection.vendor == 'postgresql', 'Row-lock concurrency requires PostgreSQL')
class ProposalConcurrencyTests(TransactionTestCase):
    def test_concurrent_apply_accepts_only_one_request(self):
        user = get_user_model().objects.create_user('concurrent-task5', email='concurrent@example.test')
        task = Task.objects.create(user=user, title='Áp dụng đồng thời', estimated_duration=60,
                                   deadline=NOW+timedelta(days=2))
        barrier = Barrier(2)
        with patch('django.utils.timezone.now', return_value=NOW):
            proposal = ProposalPlanner(user).propose(task)

            def apply_once():
                try:
                    barrier.wait(timeout=10)
                    apply_proposal(user, proposal['token'])
                    return True
                except ValidationError:
                    return False
                finally:
                    connections.close_all()

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(apply_once) for _ in range(2)]
                results = [future.result(timeout=20) for future in futures]
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(ScheduleBlock.objects.filter(task=task).count(), 1)
