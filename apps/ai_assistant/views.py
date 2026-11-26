import logging

import requests
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import AIConfigurationForm
from .model_catalog import TIER_LABELS, classify_model_tier, sort_models
from .models import AIConfiguration, AIInsight
from .services import AIServiceBridge

logger = logging.getLogger(__name__)

OPENAI_DEFAULT_BASE = 'https://api.openai.com/v1'
ANTHROPIC_DEFAULT_BASE = 'https://api.anthropic.com'


def _extract_model_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ('data', 'models'):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _fetch_openai_models(api_key, base_url):
    base = (base_url or OPENAI_DEFAULT_BASE).rstrip('/')
    response = requests.get(
        f'{base}/models',
        headers={'Authorization': f'Bearer {api_key}'},
        timeout=15,
    )
    if response.status_code in (401, 403):
        raise ValueError('API key không hợp lệ hoặc không có quyền truy cập.')
    if response.status_code >= 400:
        raise ValueError(f'Dịch vụ trả về lỗi {response.status_code}.')
    try:
        payload = response.json()
    except ValueError:
        raise ValueError('Dịch vụ trả về dữ liệu không hợp lệ.')
    return _extract_model_list(payload)


def _fetch_anthropic_models(api_key, base_url):
    base = (base_url or ANTHROPIC_DEFAULT_BASE).rstrip('/')
    response = requests.get(
        f'{base}/v1/models',
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
        },
        timeout=15,
    )
    if response.status_code in (401, 403):
        raise ValueError('API key không hợp lệ hoặc không có quyền truy cập.')
    if response.status_code >= 400:
        raise ValueError(f'Dịch vụ trả về lỗi {response.status_code}.')
    try:
        payload = response.json()
    except ValueError:
        raise ValueError('Dịch vụ trả về dữ liệu không hợp lệ.')
    return _extract_model_list(payload)

@login_required
def insights_view(request):
    """Trang xem danh sách các thông báo phân tích và cảnh báo của AI."""
    insights = AIInsight.objects.filter(user=request.user)
    return render(request, 'ai_assistant/insights.html', {'insights': insights})

@login_required
@require_POST
def generate_insight(request):
    """Kích hoạt yêu cầu AI phân tích lại lịch và deadline."""
    try:
        insight = AIServiceBridge.analyze_schedule_and_deadlines(request.user)
    except Exception:
        logger.exception('Phân tích AI thất bại cho user_id=%s', request.user.pk)
        messages.error(request, 'Không thể hoàn tất phân tích AI. Vui lòng thử lại sau.')
    else:
        messages.success(request, f'AI đã hoàn tất phân tích: {insight.title}')
    return redirect('ai_assistant:insights')

@login_required
def ai_settings(request):
    """Trang cấu hình nhà cung cấp AI và API key riêng của người dùng."""
    config, _ = AIConfiguration.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = AIConfigurationForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã lưu cài đặt AI.')
            return redirect('ai_assistant:settings')
    else:
        form = AIConfigurationForm(instance=config)

    return render(request, 'ai_assistant/settings.html', {'form': form, 'config': config})

@login_required
@require_POST
def ai_models(request):
    """Trả về danh sách model mà API key hiện tại có thể sử dụng."""
    provider = (request.POST.get('provider') or '').strip()
    api_key = (request.POST.get('api_key') or '').strip()
    base_url = (request.POST.get('base_url') or '').strip()

    valid_providers = {choice.value for choice in AIConfiguration.Provider}
    if provider not in valid_providers:
        return JsonResponse(
            {'error': 'Nhà cung cấp không hợp lệ.', 'models': []},
            status=400,
        )

    if not api_key:
        config = AIConfiguration.objects.filter(user=request.user).first()
        if config:
            api_key = config.get_api_key()
    if not api_key:
        return JsonResponse(
            {'error': 'Vui lòng nhập API key để tải danh sách model.', 'models': []},
            status=400,
        )

    try:
        if provider == AIConfiguration.Provider.ANTHROPIC:
            raw_models = _fetch_anthropic_models(api_key, base_url)
        else:
            raw_models = _fetch_openai_models(api_key, base_url)
    except requests.RequestException:
        logger.warning(
            'Không tải được danh sách model cho user_id=%s',
            request.user.pk,
            exc_info=True,
        )
        return JsonResponse(
            {
                'error': 'Không kết nối được tới dịch vụ AI. Kiểm tra API key hoặc Base URL.',
                'models': [],
            },
            status=502,
        )
    except ValueError as exc:
        return JsonResponse({'error': str(exc), 'models': []}, status=400)

    models = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        model_id = item.get('id')
        if not model_id:
            continue
        tier = classify_model_tier(model_id, item, provider, base_url)
        models.append({
            'id': model_id,
            'name': item.get('name') or item.get('display_name') or model_id,
            'tier': tier,
            'tier_label': TIER_LABELS[tier],
        })

    models = sort_models(models)
    return JsonResponse({'models': models, 'count': len(models), 'error': None})
