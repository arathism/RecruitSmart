"""
Run this from inside the recruit_smart_PUBLICATION folder, with your
virtual environment active, e.g.:

    python reset_admin_password.py

It finds the admin@recruitsmart.ai account and resets its password to
whatever is set in your .env file (ADMIN_PASSWORD), without touching
any other data (jobs, candidates, applications, etc).
"""
import os
from app import create_app, db
from app.models import User

app = create_app()

with app.app_context():
    admin_email = app.config.get("ADMIN_EMAIL", "admin@recruitsmart.ai")
    new_password = app.config.get("ADMIN_PASSWORD")

    if not new_password:
        print("ADMIN_PASSWORD is not set in your .env file. Set it first, then re-run this script.")
        raise SystemExit(1)

    user = User.query.filter_by(email=admin_email).first()

    if not user:
        print(f"No user found with email {admin_email}. Nothing to reset.")
        raise SystemExit(1)

    user.set_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    db.session.commit()

    print("=" * 60)
    print(f"Password reset for: {admin_email}")
    print(f"New password: {new_password}")
    print("Failed login attempts and any lockout have been cleared too.")
    print("=" * 60)
