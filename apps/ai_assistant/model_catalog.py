from urllib.parse import urlparse

FREE = 'free'
PAID = 'paid'
UNKNOWN = 'unknown'

TIER_LABELS = {
    FREE: 'Miễn phí',
    PAID: 'Trả phí',
    UNKNOWN: 'Không rõ',
}

_FREE_TIER_HOSTS = ('groq.com', 'localhost', '127.0.0.1', 'ollama')
_GEMINI_HOSTS = ('generativelanguage.googleapis.com',)


def _is_zero(value):
    try:
        return float(value) == 0
    except (TypeError, ValueError):
        return False


def classify_model_tier(model_id, model_data, provider, base_url):
    model_id = (model_id or '').lower()
    model_data = model_data or {}

    pricing = model_data.get('pricing')
    if isinstance(pricing, dict) and pricing:
        prompt = pricing.get('prompt')
        completion = pricing.get('completion')
        if prompt is not None and completion is not None:
            if _is_zero(prompt) and _is_zero(completion):
                return FREE
            return PAID

    if model_id.endswith(':free'):
        return FREE

    if provider in ('openai', 'anthropic'):
        return PAID

    host = (urlparse(base_url or '').hostname or '').lower()
    if any(known in host for known in _FREE_TIER_HOSTS):
        return FREE
    if any(known in host for known in _GEMINI_HOSTS) or model_id.startswith('gemini'):
        return FREE

    return UNKNOWN


def sort_models(models):
    order = {FREE: 0, UNKNOWN: 1, PAID: 2}
    return sorted(models, key=lambda item: (order.get(item['tier'], 3), item['id']))
