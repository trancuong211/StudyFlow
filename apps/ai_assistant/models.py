from django.db import models
from django.conf import settings

class AIInsight(models.Model):
    """
    Lưu trữ kết quả phân tích lịch bận, cảnh báo rủi ro deadline và tóm tắt của AI.
    Được cache lại để tránh tốn chi phí gọi API OpenAI/Claude liên tục.
    """
    class InsightType(models.TextChoices):
        DEADLINE_RISK = 'DEADLINE_RISK', 'Cảnh báo rủi ro trễ hạn'
        DAILY_SUMMARY = 'DAILY_SUMMARY', 'Tóm tắt công việc trong ngày'
        SCHEDULE_DENSITY = 'SCHEDULE_DENSITY', 'Phân tích mật độ lịch bận'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_insights',
        verbose_name='Người dùng'
    )
    insight_type = models.CharField(
        'Loại phân tích',
        max_length=30,
        choices=InsightType.choices,
        default=InsightType.DAILY_SUMMARY
    )
    title = models.CharField('Tiêu đề tóm tắt', max_length=200)
    content = models.TextField('Nội dung phân tích của AI')
    actionable_advice = models.TextField('Lời khuyên hành động', blank=True)
    is_dismissed = models.BooleanField('Đã xem / Đã ẩn', default=False)
    risk_level = models.CharField('Mức rủi ro', max_length=10, default='LOW', choices=[(x, x) for x in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')])
    source = models.CharField('Nguồn phân tích', max_length=30, default='rules')
    context_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField('Thời điểm tạo', auto_now_add=True)

    class Meta:
        verbose_name = 'AI Insight'
        verbose_name_plural = 'Danh sách AI Insights'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_insight_type_display()}] {self.title}"
