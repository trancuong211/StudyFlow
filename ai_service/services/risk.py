"""Explainable urgency scores, not probabilities of missing a deadline.

The same rules run in Django and FastAPI; LLM output never sets these values.
"""

from datetime import timedelta
from math import ceil

from ..api.schemas import TaskRiskResponse


def score_task(task, now):
    remaining = task.remaining_minutes if task.remaining_minutes is not None else task.estimated_duration
    missing = max(0, remaining - task.planned_minutes)
    reasons = []
    score = 0
    if remaining <= 0:
        reasons.append('Đã ghi nhận đủ thời gian học ước tính.')
    elif task.deadline <= now:
        score = 100
        reasons.append('Đã quá deadline nhưng vẫn còn thời gian cần học.')
    else:
        if missing:
            ratio = missing / remaining
            score = 40 + ceil(19 * ratio)
            reasons.append(f'Còn thiếu {missing} phút chưa được xếp lịch hợp lệ.')
            if task.deadline <= now + timedelta(hours=48):
                score = max(score, 70 + ceil(15 * ratio))
                reasons.append('Deadline trong 48 giờ tới.')
            if (task.available_minutes is not None
                    and task.cumulative_unscheduled_minutes > task.available_minutes):
                deficit = task.cumulative_unscheduled_minutes - task.available_minutes
                score = max(score, 85 + ceil(14 * deficit / max(1, task.cumulative_unscheduled_minutes)))
                reasons.append('Quỹ thời gian trước deadline không đủ cho các việc cùng hoặc sớm hạn hơn.')
        if task.overloaded:
            score = max(score, 70)
            reasons.append('Có khung học nằm trong ngày vượt mục tiêu học tập.')
        if not reasons:
            reasons.append('Đã có đủ lịch hợp lệ trước deadline.')
    level = 'CRITICAL' if score == 100 else 'HIGH' if score >= 70 else 'MEDIUM' if score >= 30 else 'LOW'
    return TaskRiskResponse(task_id=task.id, title=task.title, score=score,
                            risk_level=level, missing_minutes=missing, reasons=reasons)
