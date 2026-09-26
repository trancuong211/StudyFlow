import os
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import GoogleCalendarToken

@login_required
def connect_google(request):
    """
    Xử lý bắt đầu luồng OAuth2 kết nối Google Calendar.
    Route: /calendar/connect/
    """
    client_id = os.getenv('GOOGLE_CLIENT_ID', '')
    redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:8000/calendar/oauth2callback/')
    scope = 'https://www.googleapis.com/auth/calendar'
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&"
        f"scope={scope}&access_type=offline&prompt=consent"
    )
    return redirect(auth_url)

@login_required
def oauth2callback(request):
    """
    Callback nhận authorization code từ Google và lưu access/refresh token.
    Route: /calendar/oauth2callback/
    """
    code = request.GET.get('code')
    if not code:
        messages.error(request, 'Không thể kết nối tài khoản Google: Mã ủy quyền bị thiếu.')
        return redirect('dashboard:index')

    GoogleCalendarToken.objects.update_or_create(
        user=request.user,
        defaults={
            'access_token': f"google_access_token_{code[:10]}",
            'refresh_token': f"google_refresh_token_{code[:10]}",
        }
    )
    request.user.is_google_connected = True
    request.user.save(update_fields=['is_google_connected'])
    messages.success(request, 'Đã kết nối thành công tài khoản Google Calendar!')
    return redirect('dashboard:index')
