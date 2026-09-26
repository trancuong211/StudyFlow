from django.db import models
from django.conf import settings

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
    access_token = models.TextField('Access Token')
    refresh_token = models.TextField('Refresh Token', blank=True, null=True)
    token_uri = models.CharField('Token URI', max_length=255, default='https://oauth2.googleapis.com/token')
    client_id = models.CharField('Client ID', max_length=255, blank=True)
    client_secret = models.CharField('Client Secret', max_length=255, blank=True)
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
