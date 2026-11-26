from django.conf import settings
from django.db import models

from .crypto import decrypt_secret, encrypt_secret

DEFAULT_MODELS = {
    'openai': 'gpt-4o-mini',
    'anthropic': 'claude-3-5-sonnet-latest',
}


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
    risk_level = models.CharField(
        'Mức rủi ro',
        max_length=10,
        default='LOW',
        choices=[(x, x) for x in ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')]
    )
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


class AIConfiguration(models.Model):
    """
    Cấu hình AI riêng của từng người dùng: nhà cung cấp, model và API key.
    API key được mã hóa trước khi lưu vào database.
    """

    class Provider(models.TextChoices):
        OPENAI = 'openai', 'OpenAI'
        ANTHROPIC = 'anthropic', 'Anthropic Claude'
        CUSTOM = 'custom', 'OpenAI-compatible (OpenRouter, Gemini, Groq, Ollama...)'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_config',
        verbose_name='Người dùng'
    )
    provider = models.CharField(
        'Nhà cung cấp',
        max_length=20,
        choices=Provider.choices,
        default=Provider.OPENAI
    )
    model_name = models.CharField(
        'Model',
        max_length=100,
        blank=True,
        help_text='Danh sách model được tải tự động từ API key.'
    )
    base_url = models.URLField(
        'Base URL',
        blank=True,
        help_text='Bắt buộc với nhà cung cấp OpenAI-compatible, ví dụ https://openrouter.ai/api/v1'
    )
    api_key_encrypted = models.TextField('API key (đã mã hóa)', blank=True)
    key_hint = models.CharField('Gợi ý API key', max_length=16, blank=True)
    is_active = models.BooleanField('Đang sử dụng cấu hình này', default=True)
    created_at = models.DateTimeField('Thời điểm tạo', auto_now_add=True)
    updated_at = models.DateTimeField('Cập nhật lần cuối', auto_now=True)

    class Meta:
        verbose_name = 'Cấu hình AI'
        verbose_name_plural = 'Cấu hình AI'

    def __str__(self):
        return f"Cấu hình AI của {self.user}"

    def set_api_key(self, raw_key):
        raw_key = (raw_key or '').strip()
        if not raw_key:
            self.api_key_encrypted = ''
            self.key_hint = ''
            return
        self.api_key_encrypted = encrypt_secret(raw_key)
        self.key_hint = f'...{raw_key[-4:]}' if len(raw_key) > 4 else '••••'

    def get_api_key(self):
        return decrypt_secret(self.api_key_encrypted)

    @property
    def has_api_key(self):
        return bool(self.api_key_encrypted)

    def get_model_name(self):
        return self.model_name or DEFAULT_MODELS.get(self.provider, '')
