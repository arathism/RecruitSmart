from flask import current_app, url_for
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app import mail

# --- Secure, real (non-placeholder) tokens for email verification and
# password reset. Previously these emails linked to a hardcoded
# "test-token" for every user, and /verify-email/<token> accepted any
# token at all without checking it -- meaning email verification and
# password reset were both non-functional. itsdangerous signs a payload
# (the user's id + a purpose string) with the app's SECRET_KEY, so a
# token can be verified as genuine, tied to exactly one user, and made
# to expire after a set time. ---

def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def generate_token(user_id, purpose):
    return _serializer().dumps({'user_id': user_id, 'purpose': purpose})


def verify_token(token, purpose, max_age_seconds=3600):
    """Returns the user_id if the token is genuine, unexpired, and for the
    right purpose. Returns None otherwise (never raises)."""
    try:
        data = _serializer().loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict) or data.get('purpose') != purpose:
        return None
    return data.get('user_id')


def send_email(subject, recipients, body=None, html=None):
    msg = Message(subject, recipients=recipients, body=body, html=html)
    try:
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Email send failed (check MAIL_USERNAME/MAIL_PASSWORD in .env): {e}")
        return False


def send_verification_email(user):
    token = generate_token(user.id, 'verify-email')
    link = url_for('auth.verify_email', token=token, _external=True)
    subject = "You have been registered to RecruitSmart"
    body = (
        f"Hi {user.first_name},\n\n"
        f"You have been registered to RecruitSmart as a {user.role}.\n\n"
        f"Please confirm your email address by clicking the link below "
        f"(valid for 24 hours):\n\n{link}\n\n"
        f"If you didn't create a RecruitSmart account, you can ignore this email."
    )
    return send_email(subject, [user.email], body=body)


def send_password_reset_email(user):
    token = generate_token(user.id, 'reset-password')
    link = url_for('auth.reset_password', token=token, _external=True)
    subject = "Password Reset - Recruit Smart"
    body = (
        f"Hi {user.first_name},\n\n"
        f"We received a request to reset your password. Click the link below "
        f"to choose a new one (valid for 1 hour):\n\n{link}\n\n"
        f"If you didn't request this, you can safely ignore this email -- "
        f"your password will not be changed."
    )
    return send_email(subject, [user.email], body=body)
