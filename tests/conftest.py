"""
Shared pytest fixtures for the RecruitSmart test suite.

`app` builds a fresh Flask app using the project's own TestingConfig
(in-memory SQLite, CSRF disabled) so tests never touch the real
recruit_smart.db file or need real Google/LinkedIn/Gmail credentials.
`client` gives a Flask test client for route-level tests; `db_session`
gives direct DB access for model-level tests.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from app import create_app, db as _db


@pytest.fixture()
def app():
    application = create_app("testing")
    with application.app_context():
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db_session(app):
    return _db.session


@pytest.fixture()
def make_user(db_session):
    """Factory fixture: make_user(email=..., role=..., password=...) -> User"""
    from app.models import User

    def _make(email="candidate@example.com", role="candidate", password="Passw0rd!",
              first_name="Test", last_name="User", **extra):
        user = User(email=email, role=role, first_name=first_name, last_name=last_name, **extra)
        user.set_password(password)
        if role == "recruiter":
            user.recruiter_status = "approved"
        db_session.add(user)
        db_session.commit()
        return user

    return _make
