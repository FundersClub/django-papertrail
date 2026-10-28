import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SECRET_KEY = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890'
INTERNAL_IPS = ['127.0.0.1']
LOGGING_CONFIG = None


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'papertrail',
    'tests',
]

MEDIA_URL = '/media/'   # Avoids https://code.djangoproject.com/ticket/21451

MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'tests.urls'
STATIC_ROOT = os.path.join(BASE_DIR, 'tests', 'static')
STATIC_URL = '/static/'

DATABASES = {
    'default': {
        'NAME': ':memory:',
        'ENGINE': 'django.db.backends.sqlite3',
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
