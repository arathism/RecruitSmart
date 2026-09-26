from functools import wraps
from flask import abort, redirect, url_for, flash
from flask_login import current_user


def _require_2fa_or_redirect():
    """Shared check: any authenticated user without TOTP set up gets sent to
    auth.setup_2fa before reaching a protected route. Originally this was
    admin-only; it's now enforced for every role (admin, recruiter,
    candidate) so every account type gets the same mandatory 2FA
    protection, not just admins."""
    if not current_user.two_factor_enabled:
        flash('Your account requires two-factor authentication. Please set it up to continue.', 'warning')
        return redirect(url_for('auth.setup_2fa'))
    return None


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            abort(403)
        redirect_response = _require_2fa_or_redirect()
        if redirect_response:
            return redirect_response
        return f(*args, **kwargs)
    return decorated_function

def recruiter_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_recruiter():
            abort(403)
        redirect_response = _require_2fa_or_redirect()
        if redirect_response:
            return redirect_response
        return f(*args, **kwargs)
    return decorated_function

def recruiter_verified_required(f):
    """Blocks recruiter-only actions that expose candidate data or create job
    postings until an admin has approved the recruiter's company details.
    This is the core anti-impersonation safeguard: without it, anyone could
    register as 'recruiter' and immediately browse every candidate's resume
    data, which is a real privacy/security risk in a project like this."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_recruiter():
            abort(403)
        redirect_response = _require_2fa_or_redirect()
        if redirect_response:
            return redirect_response
        if not current_user.is_recruiter_approved():
            flash('Your recruiter account is still pending verification by our team. '
                  'You will get full access (posting jobs, viewing candidates) once approved.', 'warning')
            return redirect(url_for('recruiter.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def candidate_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_candidate():
            abort(403)
        redirect_response = _require_2fa_or_redirect()
        if redirect_response:
            return redirect_response
        return f(*args, **kwargs)
    return decorated_function

def logout_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated:
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function
