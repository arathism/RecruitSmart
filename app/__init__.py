import os
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from flask_wtf import CSRFProtect
from authlib.integrations.flask_client import OAuth
from config import config_by_name

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address)
cors = CORS()
csrf = CSRFProtect()
oauth = OAuth()

# Optional SocketIO
try:
    from flask_socketio import SocketIO
    socketio = SocketIO()
    HAS_SOCKETIO = True
except ImportError:
    socketio = None
    HAS_SOCKETIO = False

def create_app(config_name=None):
    """Application factory pattern."""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(config_by_name[config_name])

    # Render (and most hosts) terminate HTTPS at a proxy and forward requests
    # to the app over plain HTTP internally, setting X-Forwarded-* headers.
    # Without this, Flask thinks every request is HTTP, which breaks
    # OAuth callback URLs (url_for(..., _external=True) would generate
    # http:// instead of https://) and secure-cookie behavior.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    cors.init_app(app)
    csrf.init_app(app)
    oauth.init_app(app)

    # --- Google / LinkedIn OAuth client registration -----------------------
    # Both are only registered when their credentials are actually present
    # in config (GOOGLE_CLIENT_ID/SECRET, LINKEDIN_CLIENT_ID/SECRET -- see
    # .env.example). If they're missing, `google`/`linkedin` in app.oauth
    # simply won't exist, and the login routes below detect that and show a
    # friendly "not configured yet" message instead of crashing. This means
    # the app runs (and every other feature works) with zero OAuth setup,
    # and OAuth login switches on the moment real credentials are added to
    # .env -- no code changes needed at that point.
    if app.config.get('GOOGLE_CLIENT_ID') and app.config.get('GOOGLE_CLIENT_SECRET'):
        oauth.register(
            name='google',
            client_id=app.config['GOOGLE_CLIENT_ID'],
            client_secret=app.config['GOOGLE_CLIENT_SECRET'],
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )

    if app.config.get('LINKEDIN_CLIENT_ID') and app.config.get('LINKEDIN_CLIENT_SECRET'):
        # LinkedIn's current API is "Sign In with LinkedIn using OpenID Connect" --
        # the older raw OAuth2 /v2/me + /v2/emailAddress endpoints are deprecated
        # for new apps, so this uses the OIDC userinfo endpoint instead.
        oauth.register(
            name='linkedin',
            client_id=app.config['LINKEDIN_CLIENT_ID'],
            client_secret=app.config['LINKEDIN_CLIENT_SECRET'],
            access_token_url='https://www.linkedin.com/oauth/v2/accessToken',
            authorize_url='https://www.linkedin.com/oauth/v2/authorization',
            api_base_url='https://api.linkedin.com/v2/',
            userinfo_endpoint='https://api.linkedin.com/v2/userinfo',
            client_kwargs={'scope': 'openid profile email'},
        )

    if HAS_SOCKETIO and socketio:
        socketio.init_app(app, cors_allowed_origins="*")

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    # Register blueprints
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.candidate import bp as candidate_bp
    app.register_blueprint(candidate_bp, url_prefix='/candidate')

    from app.recruiter import bp as recruiter_bp
    app.register_blueprint(recruiter_bp, url_prefix='/recruiter')

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    with app.app_context():
        upload_dir = app.config['UPLOAD_FOLDER']
        os.makedirs(upload_dir, exist_ok=True)

    @app.context_processor
    def inject_globals():
        from datetime import datetime
        try:
            from app.models import PlatformSettings
            settings = PlatformSettings.get()
            app_name = settings.site_name
        except Exception:
            app_name = 'Recruit Smart'
        return {'app_name': app_name, 'app_version': '2.0.0', 'current_year': datetime.utcnow().year}

    @app.before_request
    def enforce_maintenance_mode():
        from flask import request, render_template
        from flask_login import current_user
        # Maintenance mode blocks everyone except logged-in admins and the
        # routes needed to log in / serve static assets, so an admin can
        # always get back in to turn it off again.
        if request.endpoint in (None, 'static'):
            return
        if request.blueprint in ('auth', 'admin'):
            return
        try:
            from app.models import PlatformSettings
            settings = PlatformSettings.get()
        except Exception:
            return
        if settings.maintenance_mode and not (current_user.is_authenticated and current_user.is_admin()):
            return render_template('errors/maintenance.html', message=settings.maintenance_message), 503

    @app.after_request
    def set_security_headers(response):
        """Standard OWASP Secure Headers -- these cost nothing to add and
        close off several well-known browser-side attack classes:
        clickjacking (X-Frame-Options), MIME-sniffing attacks
        (X-Content-Type-Options), and referrer leakage (Referrer-Policy).
        A basic Content-Security-Policy is also set to restrict where
        scripts/styles can be loaded from, reducing XSS impact."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self'"
        )
        return response

    @app.after_request
    def set_security_headers(response):
        """Standard OWASP-recommended response headers. These cost nothing and
        close off several classes of attack (clickjacking, MIME-sniffing,
        reflected XSS in older browsers) that a huge number of student/demo
        Flask projects simply never set."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com data:; "
            "img-src 'self' data: https:; "
            "connect-src 'self';"
        )
        if app.config.get('SESSION_COOKIE_SECURE'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    @app.errorhandler(404)
    def not_found(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    @app.errorhandler(429)
    def rate_limit_handler(error):
        return render_template('errors/429.html'), 429

    with app.app_context():
        db.create_all()
        from app.utils.schema_upgrades import ensure_schema_upgrades, ensure_every_candidate_has_a_primary_resume
        ensure_schema_upgrades(db)
        ensure_every_candidate_has_a_primary_resume(db)
        from app.utils.seed_data import create_admin_user, create_sample_skill_tests, create_sample_jobs
        create_admin_user()
        create_sample_skill_tests()
        create_sample_jobs()

    return app

# User loader callback - MUST be outside create_app
@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))

from flask import render_template
