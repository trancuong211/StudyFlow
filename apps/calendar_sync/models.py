from django.db import models
from django.conf import settings
from .fields import EncryptedTextField

class GoogleCalendarToken(models.Model):
    """
    Model GoogleCalendarToken: lưu trữ access/refresh token và thông tin đồng bộ Google Calendar.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='google_calendar_token',
        verbose_name='Người dùng'
    )
    access_token = EncryptedTextField('Access Token')
    refresh_token = EncryptedTextField('Refresh Token', blank=True, null=True)
    token_uri = models.CharField('Token URI', max_length=255, default='https://oauth2.googleapis.com/token')
    client_id = models.CharField('Client ID', max_length=255, blank=True)
    client_secret = EncryptedTextField('Client Secret', blank=True)
    expiry = models.DateTimeField(null=True, blank=True)
    scopes = models.TextField('Scopes', default='https://www.googleapis.com/auth/calendar')
    calendar_id = models.CharField('Google Calendar ID', max_length=255, default='primary')
    last_synced_at = models.DateTimeField('Lần đồng bộ gần nhất', null=True, blank=True)
    created_at = models.DateTimeField('Ngày tạo', auto_now_add=True)
    updated_at = models.DateTimeField('Ngày cập nhật', auto_now=True)

    class Meta:
        verbose_name = 'Google Calendar Token'
        verbose_name_plural = 'Google Calendar Tokens'

    def __str__(self):
        return f"{self.user.username} - Google Calendar Token"

# Alias để tương thích
CalendarSync = GoogleCalendarToken


class GoogleCalendarEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='google_events')
    google_id = models.CharField(max_length=255)
    title = models.CharField(max_length=200)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_busy = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'google_id'], name='unique_google_event')]


class CalendarExport(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    block = models.OneToOneField('scheduler.ScheduleBlock', null=True, blank=True, on_delete=models.SET_NULL)
    google_id = models.CharField(max_length=255)
    fingerprint = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'google_id'], name='unique_calendar_export')]
