"""
Configurações do projeto Studio Fitness.
"""
import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Só lê o .env em desenvolvimento local; em produção (Vercel/Render) as
# variáveis reais devem vir do painel da plataforma, nunca do arquivo.
if not (os.environ.get("VERCEL") or os.environ.get("RENDER")):
    load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("SECRET_KEY") or "django-insecure-chave-de-desenvolvimento-trocar"

DEBUG = os.environ.get("DEBUG", "False") == "True"

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]

# Vercel expõe a URL do deployment atual (e do projeto) nessas variáveis.
_VERCEL_HOSTS = [
    os.environ.get("VERCEL_URL"),
    os.environ.get("VERCEL_BRANCH_URL"),
    os.environ.get("VERCEL_PROJECT_PRODUCTION_URL"),
]
ALLOWED_HOSTS += [h for h in _VERCEL_HOSTS if h and h not in ALLOWED_HOSTS]
if os.environ.get("VERCEL"):
    ALLOWED_HOSTS.append(".vercel.app")

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]
CSRF_TRUSTED_ORIGINS += [f"https://{h}" for h in _VERCEL_HOSTS if h]
if os.environ.get("VERCEL"):
    CSRF_TRUSTED_ORIGINS.append("https://*.vercel.app")

# Granularidade das sugestões de horário (minutos)
AGENDA_PASSO_MINUTOS = int(os.environ.get("AGENDA_PASSO_MINUTOS") or "5")

# Horário de abertura/fechamento do estúdio (hora cheia, 0-23) — fonte única
# em apps/agenda/expediente.py
AGENDA_ABERTURA_HORA = int(os.environ.get("AGENDA_ABERTURA_HORA") or "7")
AGENDA_FECHAMENTO_HORA = int(os.environ.get("AGENDA_FECHAMENTO_HORA") or "21")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.contas",
    "apps.cadastros",
    "apps.planos",
    "apps.agenda",
    "apps.avaliacoes",
    "apps.modulos",
    "apps.painel",
    "apps.assistente",
]

AUTH_USER_MODEL = "contas.Usuario"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.modulos.context_processors.eixos_visiveis",
                "apps.assistente.context_processors.assistente_ativo",
                "apps.painel.context_processors.alertas_topbar",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(DATABASE_URL, conn_max_age=600, ssl_require=True),
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/contas/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/contas/login/"

# --- Assistente da agenda (chat com LLM) ---------------------------------
# Provedores gratuitos (formato OpenAI chat/completions), tentados na ordem
# de LLM_PROVEDORES até um responder; sem nenhuma chave configurada, o
# assistente fica indisponível e o botão correspondente não deve aparecer.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Ativo só se a env var pedir E houver ao menos uma chave configurada —
# assim um `.env` com ASSISTENTE_ATIVO=True esquecido, mas sem chave, não
# quebra nada: o app funciona normal e o botão do assistente some.
ASSISTENTE_ATIVO = (
    os.environ.get("ASSISTENTE_ATIVO", "False") == "True" and bool(GROQ_API_KEY or GEMINI_API_KEY)
)

LLM_PROVEDORES = [
    p.strip() for p in os.environ.get("LLM_PROVEDORES", "groq,gemini").split(",") if p.strip()
]

LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S") or "12")

# base_url de cada provedor não é segredo (fica fixo no código, em llm.py);
# aqui só a chave/modelo, que são específicos do ambiente.
LLM_PROVEDORES_CONFIG = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "chave": GROQ_API_KEY,
        "modelo": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "chave": GEMINI_API_KEY,
        "modelo": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    },
}

# Mensagens por usuário permitidas na janela de rate limit (ver
# apps/assistente/conversa.py). Usa o cache padrão (LocMemCache, já que não
# há CACHES configurado no projeto) — funciona bem para um único worker,
# mas cada worker do gunicorn em produção tem seu próprio cache em memória,
# então o limite real acaba sendo "por worker", não globalmente por usuário.
# Aceitável para um rate limit best-effort num app de baixo tráfego.
ASSISTENTE_RATE_LIMIT_MSGS = int(os.environ.get("ASSISTENTE_RATE_LIMIT_MSGS") or "20")
ASSISTENTE_RATE_LIMIT_JANELA_S = int(os.environ.get("ASSISTENTE_RATE_LIMIT_JANELA_S") or "600")
