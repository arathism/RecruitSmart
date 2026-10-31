"""Tests for email verification tokens, the password-reset flow, the
Google/LinkedIn OAuth login routes' "not configured" fallback behaviour,
and the email-OTP registration flow (send-otp / verify-otp / register)."""
import re

from app.utils.email import generate_token, verify_token


def _extract_dev_code(caplog):
    """Pull the 6-digit code back out of the '[DEV] Mail not configured --
    OTP for x@y is 123456' warning that app/utils/otp.py always logs when
    no MAIL_USERNAME is set (true in TestingConfig, same as a local
    `python run.py` before .env is filled in). The code only rides along
    in the *HTTP response* when current_app.debug is True, which
    TestingConfig deliberately doesn't set -- so the log is the reliable
    way to recover it in tests."""
    for record in reversed(caplog.records):
        match = re.search(r"OTP for \S+ is (\d{6})", record.message)
        if match:
            return match.group(1)
    raise AssertionError("no '[DEV] ... OTP for ... is ######' log record found")


class TestTokenHelpers:
    def test_round_trip_returns_user_id(self, app):
        with app.app_context():
            token = generate_token(42, 'verify-email')
            assert verify_token(token, 'verify-email') == 42

    def test_wrong_purpose_rejected(self, app):
        with app.app_context():
            token = generate_token(42, 'verify-email')
            assert verify_token(token, 'reset-password') is None

    def test_garbage_token_rejected(self, app):
        with app.app_context():
            assert verify_token('not-a-real-token', 'verify-email') is None

    def test_expired_token_rejected(self, app):
        with app.app_context():
            token = generate_token(42, 'verify-email')
            # max_age_seconds=-1 guarantees the token is already "older"
            # than the allowed age no matter how fast this test runs --
            # max_age_seconds=0 is flaky, since a token generated and
            # checked within the same clock second can still read as 0
            # seconds old and pass.
            assert verify_token(token, 'verify-email', max_age_seconds=-1) is None


class TestEmailVerificationRoute:
    def test_valid_token_verifies_user(self, client, app, make_user):
        user = make_user(email="verifyme@example.com")
        assert user.email_verified is False

        with app.app_context():
            token = generate_token(user.id, 'verify-email')

        resp = client.get(f"/auth/verify-email/{token}", follow_redirects=True)
        assert resp.status_code == 200

        from app.models import User
        with app.app_context():
            refreshed = User.query.filter_by(email="verifyme@example.com").first()
            assert refreshed.email_verified is True

    def test_invalid_token_does_not_verify(self, client, app, make_user):
        user = make_user(email="badtoken@example.com")
        resp = client.get("/auth/verify-email/garbage-token", follow_redirects=True)
        assert resp.status_code == 200

        from app.models import User
        with app.app_context():
            refreshed = User.query.filter_by(email="badtoken@example.com").first()
            assert refreshed.email_verified is False


class TestPasswordResetFlow:
    def test_reset_page_loads_with_valid_token(self, client, app, make_user):
        user = make_user(email="resetme@example.com", password="OldPass1!")
        with app.app_context():
            token = generate_token(user.id, 'reset-password')
        resp = client.get(f"/auth/reset-password/{token}")
        assert resp.status_code == 200

    def test_invalid_token_redirects_away(self, client):
        resp = client.get("/auth/reset-password/garbage-token", follow_redirects=True)
        assert resp.status_code == 200

    def test_submitting_new_password_updates_it(self, client, app, make_user):
        user = make_user(email="resetflow@example.com", password="OldPass1!")
        with app.app_context():
            token = generate_token(user.id, 'reset-password')

        resp = client.post(f"/auth/reset-password/{token}", data={
            "password": "BrandNewPass1!",
            "confirm_password": "BrandNewPass1!",
        }, follow_redirects=True)
        assert resp.status_code == 200

        from app.models import User
        with app.app_context():
            refreshed = User.query.filter_by(email="resetflow@example.com").first()
            assert refreshed.check_password("BrandNewPass1!") is True
            assert refreshed.check_password("OldPass1!") is False

    def test_mismatched_confirmation_does_not_change_password(self, client, app, make_user):
        user = make_user(email="mismatch@example.com", password="OldPass1!")
        with app.app_context():
            token = generate_token(user.id, 'reset-password')

        client.post(f"/auth/reset-password/{token}", data={
            "password": "BrandNewPass1!",
            "confirm_password": "SomethingElse1!",
        }, follow_redirects=True)

        from app.models import User
        with app.app_context():
            refreshed = User.query.filter_by(email="mismatch@example.com").first()
            assert refreshed.check_password("OldPass1!") is True


class TestOAuthNotConfiguredFallback:
    """In the test config, no real Google/LinkedIn credentials are set, so
    these routes must fail gracefully (flash + redirect) rather than crash --
    this is exactly the state the app will be in for anyone who hasn't added
    their own OAuth credentials to .env yet."""

    def test_google_login_without_credentials_redirects_to_login(self, client):
        resp = client.get("/auth/google/login", follow_redirects=True)
        assert resp.status_code == 200
        assert resp.request.path == "/auth/login"

    def test_linkedin_login_without_credentials_redirects_to_login(self, client):
        resp = client.get("/auth/linkedin/login", follow_redirects=True)
        assert resp.status_code == 200
        assert resp.request.path == "/auth/login"


class TestSendOtpRoute:
    """Covers POST /auth/send-otp -- the first step of email OTP
    registration. No MAIL_USERNAME is set in the testing config, so these
    exercise the dev-mode fallback path in app/utils/otp.py."""

    def test_valid_new_email_sends_code(self, client):
        resp = client.post("/auth/send-otp", json={"email": "newperson@example.com"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_invalid_email_format_rejected(self, client):
        resp = client.post("/auth/send-otp", json={"email": "not-an-email"})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_already_registered_email_rejected(self, client, make_user):
        make_user(email="already@example.com")
        resp = client.post("/auth/send-otp", json={"email": "already@example.com"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "already registered" in data["message"].lower()

    def test_resend_within_cooldown_is_rejected(self, client):
        first = client.post("/auth/send-otp", json={"email": "cooldown@example.com"})
        assert first.get_json()["success"] is True

        second = client.post("/auth/send-otp", json={"email": "cooldown@example.com"})
        assert second.status_code == 429
        data = second.get_json()
        assert data["success"] is False
        assert "wait" in data["message"].lower()

    def test_missing_email_rejected(self, client):
        resp = client.post("/auth/send-otp", json={})
        assert resp.status_code == 400


class TestVerifyOtpRoute:
    """Covers POST /auth/verify-otp -- checking the code the user typed
    back in, and issuing the short-lived 'this email was OTP-verified'
    token that /auth/register requires."""

    def _send_and_get_code(self, client, email, caplog):
        caplog.clear()
        client.post("/auth/send-otp", json={"email": email})
        return _extract_dev_code(caplog)

    def test_correct_code_returns_token(self, client, caplog):
        email = "verifyotp@example.com"
        code = self._send_and_get_code(client, email, caplog)

        resp = client.post("/auth/verify-otp", json={"email": email, "otp": code})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["token"]

    def test_incorrect_code_rejected(self, client, caplog):
        email = "wrongcode@example.com"
        self._send_and_get_code(client, email, caplog)

        resp = client.post("/auth/verify-otp", json={"email": email, "otp": "000000"})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_code_cannot_be_reused_after_success(self, client, caplog):
        email = "reuse@example.com"
        code = self._send_and_get_code(client, email, caplog)

        first = client.post("/auth/verify-otp", json={"email": email, "otp": code})
        assert first.get_json()["success"] is True

        second = client.post("/auth/verify-otp", json={"email": email, "otp": code})
        assert second.status_code == 400
        assert second.get_json()["success"] is False

    def test_too_many_wrong_attempts_locks_out_code(self, client, caplog):
        email = "lockout@example.com"
        code = self._send_and_get_code(client, email, caplog)

        for _ in range(5):
            resp = client.post("/auth/verify-otp", json={"email": email, "otp": "111111"})
            assert resp.get_json()["success"] is False

        # Even the correct code should now be rejected -- the record was
        # deleted after MAX_VERIFY_ATTEMPTS, so this simulates a fresh
        # "no code on file" state rather than a false accept.
        resp = client.post("/auth/verify-otp", json={"email": email, "otp": code})
        assert resp.get_json()["success"] is False

    def test_verify_without_sending_first_is_rejected(self, client):
        resp = client.post("/auth/verify-otp", json={"email": "never-sent@example.com", "otp": "123456"})
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_missing_email_or_code_rejected(self, client):
        resp = client.post("/auth/verify-otp", json={"email": "someone@example.com"})
        assert resp.status_code == 400


class TestRegisterRequiresOtpVerification:
    """Covers the server-side enforcement in auth.register: the OTP flow
    can't be bypassed by posting straight to /register without a valid
    otp_token proving that email was actually verified."""

    def _registration_payload(self, email, otp_token=""):
        return {
            "email": email,
            "password": "StrongPass1!",
            "confirm_password": "StrongPass1!",
            "full_name": "Test Person",
            "phone": "9876543210",
            "otp_token": otp_token,
            "agree_terms": "on",
            "role": "candidate",
        }

    def test_register_without_otp_token_is_rejected(self, client, app):
        resp = client.post("/auth/register",
                            data=self._registration_payload("nooToken@example.com"),
                            follow_redirects=True)
        assert resp.status_code == 200

        from app.models import User
        with app.app_context():
            assert User.query.filter_by(email="nootoken@example.com").first() is None

    def test_register_with_otp_token_for_different_email_is_rejected(self, client, app):
        from app.utils.otp import issue_verified_token
        with app.app_context():
            token = issue_verified_token("someone-else@example.com")

        resp = client.post("/auth/register",
                            data=self._registration_payload("mismatchedtoken@example.com", otp_token=token),
                            follow_redirects=True)
        assert resp.status_code == 200

        from app.models import User
        with app.app_context():
            assert User.query.filter_by(email="mismatchedtoken@example.com").first() is None

    def test_full_send_verify_register_flow_succeeds(self, client, app, caplog):
        email = "fullflow@example.com"

        caplog.clear()
        client.post("/auth/send-otp", json={"email": email})
        code = _extract_dev_code(caplog)

        verify_resp = client.post("/auth/verify-otp", json={"email": email, "otp": code})
        token = verify_resp.get_json()["token"]

        resp = client.post("/auth/register",
                            data=self._registration_payload(email, otp_token=token),
                            follow_redirects=True)
        assert resp.status_code == 200

        from app.models import User
        with app.app_context():
            created = User.query.filter_by(email=email).first()
            assert created is not None
            assert created.email_verified is True
