"""
Tests for two things added to close a previously-named Future Scope gap
("Admin action audit log + mandatory 2FA for admin accounts"):

1. TOTP verification actually being enforced at login (User.verify_totp,
   the /auth/verify-2fa step), where before, two_factor_enabled/secret were
   stored on the user but never checked anywhere.
2. Admin accounts being unable to use any admin route until 2FA is set up,
   and every mutating admin action writing a row to AdminAuditLog.
"""
import pyotp
import pytest

from app.models import AdminAuditLog


class TestTotpVerification:
    def test_verify_totp_with_correct_code_succeeds(self, make_user):
        user = make_user(email="totp1@example.com", two_factor_enabled=True,
                          two_factor_secret=pyotp.random_base32())
        code = pyotp.TOTP(user.two_factor_secret).now()
        assert user.verify_totp(code) is True

    def test_verify_totp_with_wrong_code_fails(self, make_user):
        user = make_user(email="totp2@example.com", two_factor_enabled=True,
                          two_factor_secret=pyotp.random_base32())
        assert user.verify_totp("000000") is False

    def test_verify_totp_when_disabled_always_fails(self, make_user):
        user = make_user(email="totp3@example.com", two_factor_enabled=False)
        assert user.verify_totp("123456") is False

    def test_verify_totp_handles_empty_code_without_raising(self, make_user):
        user = make_user(email="totp4@example.com", two_factor_enabled=True,
                          two_factor_secret=pyotp.random_base32())
        assert user.verify_totp("") is False
        assert user.verify_totp(None) is False


class TestLoginWithTwoFactor:
    def test_login_with_2fa_enabled_does_not_log_in_immediately(self, client, make_user):
        make_user(email="2fauser@example.com", password="Passw0rd1!",
                  two_factor_enabled=True, two_factor_secret=pyotp.random_base32())
        resp = client.post("/auth/login", data={
            "email": "2fauser@example.com", "password": "Passw0rd1!",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert resp.request.path == "/auth/verify-2fa"

    def test_verify_2fa_with_correct_code_completes_login(self, client, make_user):
        secret = pyotp.random_base32()
        make_user(email="2fauser2@example.com", password="Passw0rd1!",
                  two_factor_enabled=True, two_factor_secret=secret)
        client.post("/auth/login", data={
            "email": "2fauser2@example.com", "password": "Passw0rd1!",
        })
        code = pyotp.TOTP(secret).now()
        resp = client.post("/auth/verify-2fa", data={"code": code}, follow_redirects=True)
        assert resp.status_code == 200
        # A logged-in candidate landing page, not bounced back to login/verify-2fa
        assert resp.request.path not in ("/auth/login", "/auth/verify-2fa")

    def test_verify_2fa_with_wrong_code_does_not_log_in(self, client, make_user):
        make_user(email="2fauser3@example.com", password="Passw0rd1!",
                  two_factor_enabled=True, two_factor_secret=pyotp.random_base32())
        client.post("/auth/login", data={
            "email": "2fauser3@example.com", "password": "Passw0rd1!",
        })
        resp = client.post("/auth/verify-2fa", data={"code": "000000"}, follow_redirects=True)
        assert resp.status_code == 200
        assert resp.request.path == "/auth/verify-2fa"

    def test_verify_2fa_unreachable_without_a_pending_login(self, client):
        resp = client.get("/auth/verify-2fa", follow_redirects=True)
        assert resp.request.path == "/auth/login"


class TestMandatoryAdminTwoFactor:
    def test_admin_without_2fa_is_redirected_to_setup(self, client, make_user):
        make_user(email="admin1@example.com", password="Passw0rd1!", role="admin")
        client.post("/auth/login", data={
            "email": "admin1@example.com", "password": "Passw0rd1!",
        })
        resp = client.get("/admin/dashboard", follow_redirects=True)
        assert resp.status_code == 200
        assert resp.request.path == "/auth/setup-2fa"

    def test_admin_with_2fa_can_reach_dashboard(self, client, make_user):
        secret = pyotp.random_base32()
        make_user(email="admin2@example.com", password="Passw0rd1!", role="admin",
                  two_factor_enabled=True, two_factor_secret=secret)
        client.post("/auth/login", data={
            "email": "admin2@example.com", "password": "Passw0rd1!",
        })
        code = pyotp.TOTP(secret).now()
        client.post("/auth/verify-2fa", data={"code": code})
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200


class TestAdminAuditLog:
    def test_toggling_a_user_writes_an_audit_log_entry(self, client, make_user, db_session):
        secret = pyotp.random_base32()
        make_user(email="admin3@example.com", password="Passw0rd1!", role="admin",
                  two_factor_enabled=True, two_factor_secret=secret)
        target = make_user(email="target@example.com")

        client.post("/auth/login", data={
            "email": "admin3@example.com", "password": "Passw0rd1!",
        })
        code = pyotp.TOTP(secret).now()
        client.post("/auth/verify-2fa", data={"code": code})

        before = AdminAuditLog.query.count()
        client.post(f"/admin/user/{target.id}/toggle")
        after = AdminAuditLog.query.count()

        assert after == before + 1
        entry = AdminAuditLog.query.order_by(AdminAuditLog.id.desc()).first()
        assert entry.actor_email == "admin3@example.com"
        assert entry.target_label == "target@example.com"
        assert entry.action in ("user_deactivated", "user_activated")
