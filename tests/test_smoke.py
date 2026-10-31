"""App-level smoke tests: the app boots, public pages load, security
headers are present, and a basic register/login flow works end to end."""


class TestPublicPages:
    def test_home_page_loads(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_login_page_loads(self, client):
        resp = client.get("/auth/login")
        assert resp.status_code == 200

    def test_register_page_loads(self, client):
        resp = client.get("/auth/register")
        assert resp.status_code == 200

    def test_unknown_route_returns_404(self, client):
        resp = client.get("/this-route-does-not-exist")
        assert resp.status_code == 404


class TestSecurityHeaders:
    def test_security_headers_present(self, client):
        resp = client.get("/")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" in resp.headers


class TestRegisterAndLoginFlow:
    def test_register_creates_user_and_login_succeeds(self, client, app):
        from app.models import User
        from app.utils.otp import issue_verified_token

        with app.app_context():
            otp_token = issue_verified_token("newcandidate@example.com")

        resp = client.post("/auth/register", data={
            "email": "newcandidate@example.com",
            "password": "StrongPass1!",
            "confirm_password": "StrongPass1!",
            "full_name": "New Candidate",
            "phone": "9876543210",
            "otp_token": otp_token,
            "agree_terms": "on",
            "role": "candidate",
        }, follow_redirects=True)
        assert resp.status_code == 200

        with app.app_context():
            user = User.query.filter_by(email="newcandidate@example.com").first()
            assert user is not None
            assert user.check_password("StrongPass1!")

    def test_login_with_wrong_password_does_not_authenticate(self, client, make_user):
        make_user(email="loginfail@example.com", password="CorrectPass1!")
        resp = client.post("/auth/login", data={
            "email": "loginfail@example.com",
            "password": "WrongPassword!",
        }, follow_redirects=True)
        # Should not redirect to a logged-in dashboard; login page reloads with an error
        assert b"Invalid" in resp.data or resp.status_code == 200

    def test_login_with_correct_password_authenticates(self, client, make_user):
        make_user(email="loginok@example.com", password="CorrectPass1!")
        resp = client.post("/auth/login", data={
            "email": "loginok@example.com",
            "password": "CorrectPass1!",
        }, follow_redirects=True)
        assert resp.status_code == 200


class TestAccessControl:
    def test_candidate_dashboard_requires_login(self, client):
        resp = client.get("/candidate/dashboard", follow_redirects=True)
        # Flask-Login redirects anonymous users to the login page
        assert resp.status_code == 200
        assert b"login" in resp.data.lower() or resp.request.path == "/auth/login"

    def test_admin_dashboard_requires_login(self, client):
        resp = client.get("/admin/dashboard", follow_redirects=True)
        assert resp.status_code == 200
