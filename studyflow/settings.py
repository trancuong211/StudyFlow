"""
Django settings for StudyFlow project.
"""

from pathlib import Path
import os
import sys
import dj_database_url
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

# Load .env file
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Add apps folder to sys.path so apps can be imported directly or via apps.
sys.path.insert(0, str(BASE_DIR / 'apps'))

# SECURITY WARNING: keep the secret key used in production secret!
INSECURE_DEFAULT_SECRET_KEY = 'django-insecure-studyflow-super-secret-key-change-in-production'
SECRET_KEY = os.getenv('SECRET_KEY', INSECURE_DEFAULT_SECRET_KEY)

# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG mặc định là False; dev bật bằng cách đặt DEBUG=True trong .env
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')

ALLOWED_HOSTS = [
    h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()
]
if not DEBUG and (not SECRET_KEY or SECRET_KEY == INSECURE_DEFAULT_SECRET_KEY
                  or len(SECRET_KEY) < 32 or SECRET_KEY.startswith(('django-insecure-', 'change-me'))):
    raise ImproperlyConfigured(
        "SECRET_KEY mặc định/insecure không được dùng khi DEBUG=False. "
        "Hãy đặt SECRET_KEY mạnh trong .env (xem .env.example) hoặc bật DEBUG=True khi dev."
    )

# Application definition

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'django_celery_beat',
]

LOCAL_APPS = [
    'apps.accounts',
    'apps.courses',
    'apps.tasks',
    'apps.scheduler',
    'apps.pomodoro',
    'apps.calendar_sync',
    'apps.ai_assistant',
    'apps.dashboard',
    'apps.resources',
    'apps.notifications',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.accounts.limits.AuthenticationRateLimitMiddleware',
    'apps.accounts.timezones.UserTimezoneMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'studyflow.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'studyflow.wsgi.application'
ASGI_APPLICATION = 'studyflow.asgi.application'

# Database Configuration (PostgreSQL / SQLite)
# USE_SQLITE=True -> dùng SQLite; USE_SQLITE=False -> dùng PostgreSQL qua DATABASE_URL
USE_SQLITE = os.getenv('USE_SQLITE', 'True').lower() in ('true', '1', 't')

if USE_SQLITE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': dj_database_url.config(
            default=os.getenv(
                'DATABASE_URL',
                'postgres://studyflow_user:studyflow_password@localhost:5432/studyflow_db'
            ),
            conn_max_age=600,
        )
    }

# Custom User Model
AUTH_USER_MODEL = 'accounts.User'
AUTHENTICATION_BACKENDS = ['apps.accounts.backends.UsernameOrEmailBackend']

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'vi'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise: cho phép serve static ngay cả khi DEBUG=False / chưa chạy collectstatic
# (nếu không, CSS + Tailwind JS trả 404 → trang hiển thị như HTML thô, không giao diện).
# Production vẫn nên chạy `python manage.py collectstatic`.
WHITENOISE_USE_FINDERS = DEBUG

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', str(MEDIA_ROOT)))

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Login / Logout redirects
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard:index'
LOGOUT_REDIRECT_URL = 'accounts:login'

# Celery Configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CACHES = {'default': {
    'BACKEND': 'django.core.cache.backends.locmem.LocMemCache' if DEBUG else 'django.core.cache.backends.redis.RedisCache',
    'LOCATION': 'studyflow-dev' if DEBUG else CELERY_BROKER_URL,
}}
AUTH_RATE_LIMIT_ENABLED = os.getenv('AUTH_RATE_LIMIT_ENABLED', str(not DEBUG)).lower() == 'true'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# AI Service Settings
AI_SERVICE_URL = os.getenv('AI_SERVICE_URL', '') or 'http://' + os.getenv('AI_SERVICE_HOSTPORT', 'localhost:8001')
AI_SERVICE_TOKEN = os.getenv('AI_SERVICE_TOKEN', '')

# HTTPS settings for trusted deployment proxies and secure cookies.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', str(not DEBUG)).lower() == 'true'
SECURE_REDIRECT_EXEMPT = [r'^health/$']
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 3600 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv('SECURE_HSTS_INCLUDE_SUBDOMAINS', 'False').lower() == 'true'
SECURE_HSTS_PRELOAD = os.getenv('SECURE_HSTS_PRELOAD', 'False').lower() == 'true'
SITE_URL = os.getenv('SITE_URL', '').rstrip('/') or ('https://' + os.environ['RENDER_EXTERNAL_HOSTNAME'] if os.getenv('RENDER_EXTERNAL_HOSTNAME') else 'http://localhost:8000')
if os.getenv('RENDER_EXTERNAL_HOSTNAME'):
    ALLOWED_HOSTS.append(os.environ['RENDER_EXTERNAL_HOSTNAME'])
    CSRF_TRUSTED_ORIGINS.append('https://' + os.environ['RENDER_EXTERNAL_HOSTNAME'])
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'StudyFlow <noreply@studyflow.local>')
DATA_UPLOAD_MAX_MEMORY_SIZE = 11 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage' if not DEBUG else 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'deadline-and-study-reminders': {'task': 'apps.notifications.tasks.send_due_reminders', 'schedule': 300.0},
    'daily-briefings': {'task': 'apps.notifications.tasks.daily_briefings', 'schedule': crontab(minute='*/15')},
    'google-calendar-sync': {'task': 'apps.calendar_sync.tasks.sync_connected_calendars', 'schedule': 900.0},
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
    },
}
