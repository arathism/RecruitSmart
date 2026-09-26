from flask import render_template, redirect, url_for, flash, request, session, current_app, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from urllib.parse import urlparse
from datetime import datetime
import re

from app.auth import bp
from app import db, limiter, oauth
from app.models import User, ActivityLog, Notification, PlatformSettings
from app.utils.decorators import logout_required
from app.utils.email import send_verification_email, send_password_reset_email
from app.utils.otp import send_registration_otp, verify_registration_otp, issue_verified_token, check_verified_token

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


@bp.route('/send-otp', methods=['POST'])
@logout_required
@limiter.limit('5 per hour')
def send_otp():
    data = request.get_json(silent=True) or request.form
    email = (data.get('email') or '').strip().lower()

    if not email or not EMAIL_RE.match(email):
        return jsonify(success=False, message='Please enter a valid email address.'), 400

    if User.query.filter_by(email=email).first():
        return jsonify(success=False, message='That email is already registered. Try signing in instead.'), 400

    ok, message = send_registration_otp(email)
    return jsonify(success=ok, message=message), (200 if ok else 429)


@bp.route('/verify-otp', methods=['POST'])
@logout_required
@limiter.limit('20 per hour')
def verify_otp():
    data = request.get_json(silent=True) or request.form
    email = (data.get('email') or '').strip().lower()
    code = (data.get('otp') or '').strip()

    if not email or not code:
        return jsonify(success=False, message='Missing email or code.'), 400

    ok, message = verify_registration_otp(email, code)
    if not ok:
        return jsonify(success=False, message=message), 400

    token = issue_verified_token(email)
    return jsonify(success=True, message=message, token=token), 200

def validate_password(password):
    """Validate password strength."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one number"
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character"
    return True, "Password is strong"

def log_activity(user_id, action, details=None):
    """Log user activity."""
    log = ActivityLog(
        user_id=user_id,
        action=action,
        details=details,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string[:500] if request.user_agent else None
    )
    db.session.add(log)
    db.session.commit()

def create_notification(user_id, title, message, notification_type='general', link=None):
    """Create a notification for user."""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        link=link
    )
    db.session.add(notification)
    db.session.commit()

@bp.route('/register', methods=['GET', 'POST'])
@logout_required
@limiter.limit('10 per hour')
def register():
    platform_settings = PlatformSettings.get()
    if not platform_settings.allow_new_registrations:
        flash('New registrations are temporarily disabled by the site administrator. Please check back later.', 'warning')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        otp_token = request.form.get('otp_token', '')
        agree_terms = request.form.get('agree_terms')
        role = request.form.get('role', 'candidate')
        company_name = request.form.get('company_name', '').strip()
        company_website = request.form.get('company_website', '').strip()
        work_position = request.form.get('work_position', '').strip()

        name_parts = full_name.split(None, 1)
        first_name = name_parts[0] if name_parts else ''
        last_name = name_parts[1] if len(name_parts) > 1 else first_name

        errors = []

        if not email or not EMAIL_RE.match(email):
            errors.append("Please enter a valid email address")

        if User.query.filter_by(email=email).first():
            errors.append("Email already registered")

        if not check_verified_token(otp_token, email):
            errors.append("Please verify your email address with the OTP we sent before registering")

        is_valid, msg = validate_password(password)
        if not is_valid:
            errors.append(msg)

        if password != confirm_password:
            errors.append("Passwords do not match")

        if not full_name or len(full_name) < 2:
            errors.append("Full name must be at least 2 characters")

        if not phone or not re.match(r"^[0-9]{7,15}$", phone):
            errors.append("Please enter a valid phone number")

        if not agree_terms:
            errors.append("You must agree to the Terms & Conditions")

        if role not in ['candidate', 'recruiter']:
            errors.append("Invalid role selected")

        if role == 'recruiter' and not company_name:
            errors.append("Company name is required to register as a recruiter")

        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('auth/register.html',
                                 email=email, full_name=full_name, phone=phone, role=role)

        user = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=role,
            email_verified=True,
            gdpr_consent=True,
            gdpr_consent_date=datetime.utcnow(),
            company_name=company_name if role == 'recruiter' else None,
            company_website=company_website if role == 'recruiter' else None,
            work_position=work_position if role == 'recruiter' else None,
            recruiter_status=('pending' if platform_settings.require_recruiter_verification else 'approved') if role == 'recruiter' else 'not_applicable'
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        log_activity(user.id, 'user_registered', f'Registered as {role}')

        if role == 'recruiter' and platform_settings.require_recruiter_verification:
            # Notify all admins that a new recruiter account needs verification
            admins = User.query.filter_by(role='admin').all()
            for admin in admins:
                create_notification(admin.id, 'New Recruiter Pending Verification',
                                     f'{user.get_full_name()} ({company_name}) registered as a recruiter and needs approval.',
                                     'general', url_for('admin.users', role='recruiter'))
            flash('Registration successful! Your recruiter account is pending verification by our team before you can post jobs. We will notify you once approved.', 'success')
        else:
            flash('Registration successful! You can now sign in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')

@bp.route('/login', methods=['GET', 'POST'])
@logout_required
@limiter.limit('15 per minute')
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)

        user = User.query.filter_by(email=email).first()

        if not user:
            flash('Invalid email or password', 'danger')
            return render_template('auth/login.html')

        if user.is_locked():
            flash(f'Account is locked. Please try again after {user.locked_until.strftime("%H:%M")}', 'danger')
            return render_template('auth/login.html')

        if not user.check_password(password):
            user.failed_login_attempts += 1

            if user.failed_login_attempts >= 5:
                user.lock_account(30)
                flash('Too many failed attempts. Account locked for 30 minutes.', 'danger')
            else:
                remaining = 5 - user.failed_login_attempts
                flash(f'Invalid email or password. {remaining} attempts remaining.', 'danger')

            db.session.commit()
            return render_template('auth/login.html')

        user.failed_login_attempts = 0
        user.locked_until = None
        db.session.commit()

        # Password is correct. If 2FA is enabled, do NOT log the user in yet
        # -- park the pending login in the session and require a valid TOTP
        # code first. (Previously two_factor_enabled/two_factor_secret were
        # stored but never actually checked here, so "2FA" was configurable
        # but not enforced at login -- this closes that gap.)
        if user.two_factor_enabled:
            session['pending_2fa_user_id'] = user.id
            session['pending_2fa_remember'] = bool(remember)
            next_page = request.args.get('next')
            if next_page and urlparse(next_page).netloc == '':
                session['pending_2fa_next'] = next_page
            return redirect(url_for('auth.verify_2fa'))

        user.last_login = datetime.utcnow()
        db.session.commit()
        login_user(user, remember=remember)
        log_activity(user.id, 'user_login')

        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            if user.is_admin():
                next_page = url_for('admin.dashboard')
            elif user.is_recruiter():
                next_page = url_for('recruiter.dashboard')
            else:
                next_page = url_for('candidate.dashboard')

        return redirect(next_page)

    return render_template('auth/login.html')


@bp.route('/verify-2fa', methods=['GET', 'POST'])
@limiter.limit('10 per hour')
def verify_2fa():
    """Second step of login for any user with two_factor_enabled=True.
    Only reachable with a pending_2fa_user_id already parked in the
    session by the password step above -- it never accepts an email or
    password itself, so it can't be used to bypass the first factor."""
    user_id = session.get('pending_2fa_user_id')
    if not user_id:
        return redirect(url_for('auth.login'))
    user = User.query.get(user_id)
    if not user or not user.two_factor_enabled:
        session.pop('pending_2fa_user_id', None)
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        code = request.form.get('code', '')
        if user.verify_totp(code):
            remember = session.pop('pending_2fa_remember', False)
            next_page = session.pop('pending_2fa_next', None)
            session.pop('pending_2fa_user_id', None)

            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user, remember=remember)
            log_activity(user.id, 'user_login')

            if not next_page:
                if user.is_admin():
                    next_page = url_for('admin.dashboard')
                elif user.is_recruiter():
                    next_page = url_for('recruiter.dashboard')
                else:
                    next_page = url_for('candidate.dashboard')
            return redirect(next_page)

        flash('Invalid or expired code. Please try again.', 'danger')

    # Re-derive the same QR every time from the user's already-stored
    # secret (not a new one) so a second/third person who knows the shared
    # login can pair their own authenticator app to the SAME account by
    # scanning it here, while someone who already has it set up just types
    # their 6-digit code. This is intentional for accounts meant to be
    # shared by a small trusted group (e.g. a team's admin login) -- every
    # device that scans this gets a valid code generator for this account.
    import pyotp
    otpauth_uri = pyotp.TOTP(user.two_factor_secret).provisioning_uri(name=user.email, issuer_name='RecruitSmart')
    return render_template('auth/verify_2fa.html', email=user.email, otpauth_uri=otpauth_uri, secret=user.two_factor_secret)

@bp.route('/logout')
@login_required
def logout():
    log_activity(current_user.id, 'user_logout')
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('main.index'))

def _oauth_role_selection_redirect():
    next_page = request.args.get('next')
    if not next_page or urlparse(next_page).netloc != '':
        return None
    return next_page

def _login_or_create_oauth_user(email, first_name, last_name, provider, provider_user_id):
    """Shared logic for Google/LinkedIn callbacks: link to an existing
    account by email if one exists (so someone who registered with a
    password can also sign in with Google/LinkedIn afterwards), otherwise
    create a new, pre-verified candidate account -- an OAuth provider
    having already confirmed the email address stands in for our own
    email-verification step."""
    id_field = 'google_id' if provider == 'google' else 'linkedin_id'

    user = User.query.filter_by(email=email).first()
    if user:
        setattr(user, id_field, provider_user_id)
    else:
        user = User(
            email=email,
            first_name=first_name or 'New',
            last_name=last_name or 'User',
            role='candidate',
            email_verified=True,
            is_verified=True,
            gdpr_consent=True,
            gdpr_consent_date=datetime.utcnow(),
            recruiter_status='not_applicable',
        )
        setattr(user, id_field, provider_user_id)
        # OAuth accounts have no usable password of their own; set an
        # unguessable random one so User.set_password's invariants (a
        # password hash always exists) still hold, while normal password
        # login for this account remains effectively impossible.
        import secrets
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.utcnow()
    db.session.commit()

    login_user(user)
    log_activity(user.id, f'user_login_{provider}')

    next_page = _oauth_role_selection_redirect()
    if not next_page:
        if user.is_admin():
            next_page = url_for('admin.dashboard')
        elif user.is_recruiter():
            next_page = url_for('recruiter.dashboard')
        else:
            next_page = url_for('candidate.dashboard')
    return redirect(next_page)

@bp.route('/google/login')
@logout_required
def google_login():
    if not hasattr(oauth, 'google'):
        flash('Google sign-in isn\u2019t configured on this server yet. Set GOOGLE_CLIENT_ID and '
              'GOOGLE_CLIENT_SECRET in your .env file, or sign in with email and password instead.', 'warning')
        return redirect(url_for('auth.login'))
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@bp.route('/google/callback')
@logout_required
def google_callback():
    if not hasattr(oauth, 'google'):
        flash('Google sign-in isn\u2019t configured on this server.', 'warning')
        return redirect(url_for('auth.login'))
    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get('userinfo') or oauth.google.userinfo(token=token)
    except Exception as e:
        flash('Google sign-in failed or was cancelled. Please try again.', 'danger')
        return redirect(url_for('auth.login'))

    email = (userinfo.get('email') or '').strip().lower()
    if not email or not userinfo.get('email_verified', True):
        flash('Your Google account email could not be verified. Please try a different sign-in method.', 'danger')
        return redirect(url_for('auth.login'))

    return _login_or_create_oauth_user(
        email=email,
        first_name=userinfo.get('given_name'),
        last_name=userinfo.get('family_name'),
        provider='google',
        provider_user_id=userinfo.get('sub'),
    )

@bp.route('/linkedin/login')
@logout_required
def linkedin_login():
    if not hasattr(oauth, 'linkedin'):
        flash('LinkedIn sign-in isn\u2019t configured on this server yet. Set LINKEDIN_CLIENT_ID and '
              'LINKEDIN_CLIENT_SECRET in your .env file, or sign in with email and password instead.', 'warning')
        return redirect(url_for('auth.login'))
    redirect_uri = url_for('auth.linkedin_callback', _external=True)
    return oauth.linkedin.authorize_redirect(redirect_uri)

@bp.route('/linkedin/callback')
@logout_required
def linkedin_callback():
    if not hasattr(oauth, 'linkedin'):
        flash('LinkedIn sign-in isn\u2019t configured on this server.', 'warning')
        return redirect(url_for('auth.login'))
    try:
        token = oauth.linkedin.authorize_access_token()
        userinfo = oauth.linkedin.get('userinfo', token=token).json()
    except Exception:
        flash('LinkedIn sign-in failed or was cancelled. Please try again.', 'danger')
        return redirect(url_for('auth.login'))

    email = (userinfo.get('email') or '').strip().lower()
    if not email:
        flash('Your LinkedIn account email could not be retrieved. Please try a different sign-in method.', 'danger')
        return redirect(url_for('auth.login'))

    return _login_or_create_oauth_user(
        email=email,
        first_name=userinfo.get('given_name'),
        last_name=userinfo.get('family_name'),
        provider='linkedin',
        provider_user_id=userinfo.get('sub'),
    )

@bp.route('/verify-email/<token>')
def verify_email(token):
    from app.utils.email import verify_token
    user_id = verify_token(token, purpose='verify-email', max_age_seconds=86400)
    if not user_id:
        flash('That verification link is invalid or has expired. Please request a new one from your profile.', 'danger')
        return redirect(url_for('auth.login'))

    user = User.query.get(user_id)
    if not user:
        flash('That verification link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.login'))

    user.email_verified = True
    db.session.commit()
    flash('Email verified successfully!', 'success')
    return redirect(url_for('auth.login'))

@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@logout_required
def reset_password(token):
    from app.utils.email import verify_token
    user_id = verify_token(token, purpose='reset-password', max_age_seconds=3600)
    if not user_id:
        flash('That password reset link is invalid or has expired. Please request a new one.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.get(user_id)
    if not user:
        flash('That password reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        is_valid, msg = validate_password(password)
        if not is_valid:
            flash(msg, 'danger')
            return render_template('auth/reset_password.html', token=token)

        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('auth/reset_password.html', token=token)

        user.set_password(password)
        user.unlock_account()
        db.session.commit()
        log_activity(user.id, 'password_reset')
        flash('Your password has been reset. Please sign in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)

@bp.route('/forgot-password', methods=['GET', 'POST'])
@logout_required
@limiter.limit('5 per hour')
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()

        if user:
            try:
                send_password_reset_email(user)
            except:
                pass

        flash('If an account exists with that email, you will receive password reset instructions.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.first_name = request.form.get('first_name', current_user.first_name).strip()
        current_user.last_name = request.form.get('last_name', current_user.last_name).strip()
        current_user.phone = request.form.get('phone', '').strip()
        current_user.location = request.form.get('location', '').strip()
        current_user.bio = request.form.get('bio', '').strip()

        db.session.commit()
        log_activity(current_user.id, 'profile_updated')
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html')

@bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not current_user.check_password(current_password):
        flash('Current password is incorrect', 'danger')
        return redirect(url_for('auth.profile'))

    is_valid, msg = validate_password(new_password)
    if not is_valid:
        flash(msg, 'danger')
        return redirect(url_for('auth.profile'))

    if new_password != confirm_password:
        flash('New passwords do not match', 'danger')
        return redirect(url_for('auth.profile'))

    current_user.set_password(new_password)
    db.session.commit()

    log_activity(current_user.id, 'password_changed')
    flash('Password changed successfully!', 'success')
    return redirect(url_for('auth.profile'))

@bp.route('/security')
@login_required
def security():
    """Lets a user see their own account's security activity -- recent
    logins, password changes, failed login attempts, and resume upload
    rejections -- so they can spot unauthorized access themselves rather
    than relying entirely on the platform to catch it for them."""
    security_actions = ('user_login', 'user_logout', 'password_changed', 'profile_updated',
                         'upload_rejected_security', 'user_registered')
    page = request.args.get('page', 1, type=int)
    logs = ActivityLog.query.filter(
        ActivityLog.user_id == current_user.id,
        ActivityLog.action.in_(security_actions)
    ).order_by(ActivityLog.created_at.desc()).paginate(page=page, per_page=15, error_out=False)
    return render_template('auth/security.html', logs=logs)

@bp.route('/toggle-2fa', methods=['POST'])
@login_required
def toggle_2fa():
    """Disables 2FA only. Enabling now goes through setup_2fa below, so a
    user can't accidentally lock themselves out by flipping this on without
    ever confirming their authenticator app actually has a working code --
    the previous version enabled 2FA immediately with no confirmation step."""
    if current_user.two_factor_enabled:
        # 2FA is mandatory for every account type now (previously admin-only),
        # so it can no longer be disabled from here regardless of role.
        flash('Two-factor authentication is required on your account and cannot be disabled.', 'danger')
        return redirect(url_for('auth.profile'))

    return redirect(url_for('auth.setup_2fa'))


@bp.route('/setup-2fa', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    """Generates a pending TOTP secret and requires the user to enter one
    real code from their authenticator app before two_factor_enabled is
    flipped on. A fresh secret is generated per GET (kept in the session,
    not saved to the user yet) so refreshing this page never reuses a
    secret the user may have already scanned and moved past."""
    if current_user.two_factor_enabled:
        return redirect(url_for('auth.profile'))

    import pyotp

    if request.method == 'POST':
        pending_secret = session.get('pending_2fa_secret')
        code = request.form.get('code', '')
        if not pending_secret:
            flash('Your setup session expired. Please start again.', 'danger')
            return redirect(url_for('auth.setup_2fa'))

        if pyotp.TOTP(pending_secret).verify(code.strip(), valid_window=1):
            current_user.two_factor_secret = pending_secret
            current_user.two_factor_enabled = True
            db.session.commit()
            session.pop('pending_2fa_secret', None)
            log_activity(current_user.id, 'two_factor_enabled')
            flash('Two-factor authentication is now active on your account.', 'success')
            return redirect(url_for('admin.dashboard') if current_user.is_admin() else url_for('auth.profile'))

        flash('That code did not match. Scan the QR code again and try the current 6-digit code.', 'danger')

    secret = session.get('pending_2fa_secret')
    if not secret:
        secret = pyotp.random_base32()
        session['pending_2fa_secret'] = secret

    otpauth_uri = pyotp.TOTP(secret).provisioning_uri(name=current_user.email, issuer_name='RecruitSmart')
    return render_template('auth/setup_2fa.html', secret=secret, otpauth_uri=otpauth_uri,
                            is_admin=current_user.is_admin())
