import os
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from google_auth_oauthlib.flow import Flow
from .models import GoogleCalendarToken
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import timezone as dt_timezone
from .services import sync_calendar
from .models import GoogleCalendarEvent, CalendarExport

SCOPES = ['https://www.googleapis.com/auth/calendar']
DEFAULT_REDIRECT_URI = 'http://localhost:8000/calendar/oauth2callback/'
GOOGLE_AUTH_URI = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URI = 'https://oauth2.googleapis.com/token'


def _client_config():
    """Cấu hình OAuth2 từ biến môi trường (không có secret thì trả về None)."""
    client_id = os.getenv('GOOGLE_CLIENT_ID', '')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET', '')
    if not client_id or not client_secret or client_id.startswith('your-') or client_secret.startswith('your-'):
        return None
    return {
        'web': {
            'client_id': client_id,
            'client_secret': client_secret,
            'auth_uri': GOOGLE_AUTH_URI,
            'token_uri': GOOGLE_TOKEN_URI,
        }
    }


def _redirect_uri():
    return os.getenv('GOOGLE_REDIRECT_URI', DEFAULT_REDIRECT_URI)


@login_required
def connect_google(request):
    """
    Bắt đầu luồng OAuth2 thật với Google (google-auth-oauthlib).
    Sinh `state` lưu vào session để kiểm tra ở callback.
    Route: /calendar/connect/
    """
    client_config = _client_config()
    if client_config is None:
        messages.error(
            request,
            'Thiếu GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET trong .env nên chưa thể kết nối Google Calendar.'
        )
        return redirect('scheduler:calendar')

    try:
        flow = Flow.from_client_config(client_config=client_config, scopes=SCOPES)
        # Flow.authorization_url sẽ URL-encode redirect_uri (và các tham số khác)
        flow.redirect_uri = _redirect_uri()
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
        )
    except Exception:
        messages.error(request, 'Không thể khởi tạo phiên kết nối Google. Kiểm tra cấu hình OAuth.')
        return redirect('scheduler:calendar')

    request.session['google_oauth_state'] = state
    return redirect(authorization_url)


@login_required
def oauth2callback(request):
    """
    Callback: kiểm tra state, đổi `code` lấy token thật và lưu vào GoogleCalendarToken.
    Chỉ đánh dấu đã kết nối khi đổi token thành công.
    Route: /calendar/oauth2callback/
    """
    error = request.GET.get('error')
    if error:
        messages.error(request, f'Bạn đã hủy hoặc Google từ chối kết nối ({error}).')
        return redirect('dashboard:index')

    code = request.GET.get('code')
    state = request.GET.get('state')
    session_state = request.session.pop('google_oauth_state', None)

    if not code:
        messages.error(request, 'Không thể kết nối tài khoản Google: Mã ủy quyền bị thiếu.')
        return redirect('dashboard:index')
    if not state or not session_state or state != session_state:
        messages.error(request, 'Phiên kết nối Google không hợp lệ (sai state). Vui lòng kết nối lại.')
        return redirect('dashboard:index')

    client_config = _client_config()
    if client_config is None:
        messages.error(
            request,
            'Thiếu GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET trong .env nên chưa thể kết nối Google Calendar.'
        )
        return redirect('dashboard:index')

    try:
        flow = Flow.from_client_config(client_config=client_config, scopes=SCOPES, state=state)
        flow.redirect_uri = _redirect_uri()
        flow.fetch_token(code=code, timeout=10)
        credentials = flow.credentials
    except Exception:
        messages.error(request, 'Không thể kết nối tài khoản Google. Kiểm tra cấu hình OAuth và thử lại.')
        return redirect('dashboard:index')

    if not credentials or not credentials.token:
        messages.error(request, 'Không thể kết nối tài khoản Google: Không nhận được access token.')
        return redirect('dashboard:index')

    existing = GoogleCalendarToken.objects.defer('access_token', 'refresh_token', 'client_secret').filter(user=request.user).first()
    try:
        old_refresh = existing.refresh_token if existing else ''
    except ValidationError:
        old_refresh = ''
    defaults = {
            'access_token': credentials.token,
            'refresh_token': credentials.refresh_token or old_refresh,
            'expiry': credentials.expiry.replace(tzinfo=dt_timezone.utc) if credentials.expiry else None,
            'token_uri': credentials.token_uri or GOOGLE_TOKEN_URI,
            'client_id': credentials.client_id or os.getenv('GOOGLE_CLIENT_ID', ''),
            'client_secret': credentials.client_secret or os.getenv('GOOGLE_CLIENT_SECRET', ''),
            'scopes': ' '.join(credentials.scopes or SCOPES),
        }
    if existing:
        for field, value in defaults.items():
            setattr(existing, field, value)
        existing.save()
    else:
        GoogleCalendarToken.objects.create(user=request.user, **defaults)
    request.user.is_google_connected = True
    request.user.save(update_fields=['is_google_connected'])
    messages.success(request, 'Đã kết nối thành công tài khoản Google Calendar!')
    return redirect('dashboard:index')


@login_required
def calendar_settings(request):
    return render(request, 'calendar_sync/settings.html', {
        'token': GoogleCalendarToken.objects.defer('access_token', 'refresh_token', 'client_secret').filter(user=request.user).first(),
        'event_count': GoogleCalendarEvent.objects.filter(user=request.user).count(),
        'configured': _client_config() is not None,
    })


@login_required
@require_POST
def sync_now(request):
    if not GoogleCalendarToken.objects.filter(user=request.user).exists():
        messages.error(request, 'Hãy kết nối Google Calendar trước.')
    else:
        try:
            result = sync_calendar(request.user)
            messages.success(request, f"Đã nhập {result['imported']} sự kiện bận và xuất {result['exported']} khung học. Hãy kiểm tra xung đột và lập lại lịch nếu cần.")
        except Exception:
            messages.error(request, 'Không thể đồng bộ Google. Kiểm tra kết nối, quyền Calendar hoặc kết nối lại tài khoản.')
    return redirect('calendar_sync:settings')


@login_required
@require_POST
def disconnect(request):
    # Disconnect locally; existing exported events remain in Google.
    GoogleCalendarToken.objects.filter(user=request.user).delete()
    GoogleCalendarEvent.objects.filter(user=request.user).delete()
    CalendarExport.objects.filter(user=request.user).delete()
    request.user.is_google_connected = False
    request.user.save(update_fields=['is_google_connected'])
    messages.success(request, 'Đã ngắt kết nối. Sự kiện đã xuất vẫn được giữ trong Google Calendar.')
    return redirect('calendar_sync:settings')
