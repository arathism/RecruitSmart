"""Email OTP verification for registration.

Flow: user types their email -> POST /auth/send-otp generates a 6-digit
code, hashes it, stores it in the `registration_otps` table (keyed by
email) with a short expiry, and emails the plain code to the user. The
user types the code back in -> POST /auth/verify-otp checks it against
the stored hash. On success we issue a short-lived signed token (via
itsdangerous, same mechanism as email-verification/reset-password links)
proving *this* email was OTP-verified. That token rides along as a
hidden field on the registration form and is checked again server-side
in auth.register, so someone can't just skip the JS flow and POST
straight to /register.

A DB table (rather than an in-memory dict) is used deliberately: this app
runs behind multiple gunicorn worker processes in production, and an
in-memory store would only be visible to whichever worker happened to
handle the original /send-otp request.
"""
import random
import string
from datetime import datetime, timedelta

from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash, check_password_hash

from app import db
from app.models import RegistrationOTP
from app.utils.email import send_email

OTP_LENGTH = 6
OTP_TTL_MINUTES = 10
RESEND_COOLDOWN_SECONDS = 30
MAX_VERIFY_ATTEMPTS = 5


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'], salt='registration-otp')


def _generate_code():
    return ''.join(random.choices(string.digits, k=OTP_LENGTH))


def send_registration_otp(email):
    """Generate a fresh OTP, store its hash, and email the plain code.

    Returns (ok, message). ok=False means "don't send", with a
    user-facing reason (e.g. cooldown still active).
    """
    email = email.strip().lower()
    now = datetime.utcnow()

    record = RegistrationOTP.query.filter_by(email=email).first()
    if record and (now - record.sent_at).total_seconds() < RESEND_COOLDOWN_SECONDS:
        wait = int(RESEND_COOLDOWN_SECONDS - (now - record.sent_at).total_seconds())
        return False, f'Please wait {wait}s before requesting another code.'

    code = _generate_code()
    if not record:
        record = RegistrationOTP(email=email)
        db.session.add(record)
    record.code_hash = generate_password_hash(code)
    record.attempts = 0
    record.sent_at = now
    record.expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)
    db.session.commit()

    # Local-dev fallback: if this server has no MAIL_USERNAME/MAIL_PASSWORD
    # set (e.g. running `python run.py` locally without a .env yet), don't
    # even attempt an SMTP connection -- it will just fail. Instead, log the
    # code to the console and hand it back in the response so registration
    # is still testable end-to-end before mail is configured. This never
    # triggers once real MAIL_USERNAME/MAIL_PASSWORD are set (e.g. after
    # deploying with those env vars filled in), so it can't leak a real
    # code to the browser in production.
    if not current_app.config.get('MAIL_USERNAME'):
        current_app.logger.warning(f"[DEV] Mail not configured -- OTP for {email} is {code}")
        dev_note = f' (dev mode, mail not configured -- your code is {code})' if current_app.debug else ''
        return True, f'Verification code sent.{dev_note}'

    subject = "Your RecruitSmart verification code"
    body = (
        f"Your RecruitSmart verification code is: {code}\n\n"
        f"This code expires in {OTP_TTL_MINUTES} minutes. "
        f"If you didn't request this, you can ignore this email."
    )
    html = (
        f"<div style='font-family:Arial,sans-serif;max-width:480px;margin:0 auto;'>"
        f"<h2 style='color:#6366f1;'>Verify your email</h2>"
        f"<p>Your RecruitSmart verification code is:</p>"
        f"<p style='font-size:32px;font-weight:800;letter-spacing:8px;color:#1e293b;'>{code}</p>"
        f"<p style='color:#64748b;'>This code expires in {OTP_TTL_MINUTES} minutes. "
        f"If you didn't request this, you can safely ignore this email.</p>"
        f"</div>"
    )
    sent = send_email(subject, [email], body=body, html=html)
    if not sent:
        db.session.delete(record)
        db.session.commit()
        return False, 'Could not send the verification email. Please try again in a moment.'
    return True, 'Verification code sent.'


def verify_registration_otp(email, code):
    """Check a submitted code. Returns (ok, message)."""
    email = email.strip().lower()
    code = (code or '').strip()
    now = datetime.utcnow()

    record = RegistrationOTP.query.filter_by(email=email).first()
    if not record:
        return False, 'Please request a new verification code.'

    if now > record.expires_at:
        db.session.delete(record)
        db.session.commit()
        return False, 'That code has expired. Please request a new one.'

    if record.attempts >= MAX_VERIFY_ATTEMPTS:
        db.session.delete(record)
        db.session.commit()
        return False, 'Too many incorrect attempts. Please request a new code.'

    if not code or not check_password_hash(record.code_hash, code):
        record.attempts += 1
        db.session.commit()
        return False, 'Incorrect code. Please try again.'

    # Success -- consume it so it can't be reused.
    db.session.delete(record)
    db.session.commit()
    return True, 'Email verified.'


def issue_verified_token(email):
    return _serializer().dumps({'email': email.strip().lower()})


def check_verified_token(token, email):
    """True if `token` proves `email` completed OTP verification recently."""
    if not token:
        return False
    try:
        data = _serializer().loads(token, max_age=OTP_TTL_MINUTES * 60 + 300)
    except (BadSignature, SignatureExpired):
        return False
    return isinstance(data, dict) and data.get('email') == email.strip().lower()
