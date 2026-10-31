import os
from datetime import timedelta
from dotenv import load_dotenv

# python-dotenv was already listed in requirements.txt but never actually
# called anywhere in the codebase, so .env was silently ignored and every
# setting fell back to its os.environ.get(...) default (or, for
# ADMIN_PASSWORD, to None -- breaking any script/tooling that expects it
# to be set). This loads .env into the process environment before Config
# reads anything from os.environ below.
load_dotenv()

class Config:
    """Base configuration."""

    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # Database
    # Render (and some other hosts) give a Postgres URL starting with
    # "postgres://", but SQLAlchemy 2.x requires "postgresql://" -- without
    # this fix, the app crashes on startup the moment DATABASE_URL is a real
    # Postgres connection string instead of the local sqlite default.
    _raw_db_url = os.environ.get('DATABASE_URL') or 'sqlite:///recruit_smart.db'
    if _raw_db_url.startswith('postgres://'):
        _raw_db_url = _raw_db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Mail
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@recruitsmart.ai')

    # Upload
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app', 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt', 'png', 'jpg', 'jpeg'}

    # Security
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = False  # Set True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # CSRF protection (Flask-WTF) -- this was previously turned OFF platform-wide,
    # which left every POST form (login, job posting, admin actions, etc.) open to
    # cross-site request forgery. It is now on by default everywhere except the
    # automated test config below, where tests post forms without a browser session.
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # Rate Limiting
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
    RATELIMIT_STRATEGY = 'fixed-window'

    # Admin
    # No hardcoded fallback password here on purpose -- the previous default
    # ('admin123') was published in this repo's own .env.example, which
    # means any deployment that forgot to set ADMIN_PASSWORD would have a
    # publicly-guessable admin login. If ADMIN_PASSWORD isn't set,
    # app/utils/seed_data.py generates a random one at first startup and
    # prints it once to the server log instead of falling back to a weak
    # known value.
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@recruitsmart.ai')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

    # OAuth
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
    LINKEDIN_CLIENT_ID = os.environ.get('LINKEDIN_CLIENT_ID')
    LINKEDIN_CLIENT_SECRET = os.environ.get('LINKEDIN_CLIENT_SECRET')

    # Features
    ENABLE_AI_MATCHING = True
    ENABLE_NOTIFICATIONS = True
    ENABLE_ANALYTICS = True

    # Pagination
    PER_PAGE = 10

    # File Processing
    MAX_RESUME_SIZE = 5 * 1024 * 1024  # 5MB

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_ECHO = False

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    # pool_size/pool_recycle are QueuePool options and only apply to
    # Postgres/MySQL-style engines -- sqlite uses a different pool class that
    # rejects these kwargs, so only set them when DATABASE_URL is actually a
    # Postgres URL. Prevents a startup crash if DATABASE_URL isn't set yet.
    if Config.SQLALCHEMY_DATABASE_URI.startswith('postgresql://'):
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_size': 10,
            'pool_recycle': 3600,
            'pool_pre_ping': True
        }

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False  # disabled only for automated tests posting forms directly

config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
