"""Model-level tests: password hashing, account lockout, role helpers,
and the JSON-backed list accessors on Resume."""
import json
from datetime import datetime, timedelta

from app.models import User, Resume


class TestUserPassword:
    def test_set_password_hashes_it(self, make_user):
        user = make_user(password="Secret123!")
        assert user.password_hash != "Secret123!"

    def test_check_password_correct(self, make_user):
        user = make_user(password="Secret123!")
        assert user.check_password("Secret123!") is True

    def test_check_password_incorrect(self, make_user):
        user = make_user(password="Secret123!")
        assert user.check_password("wrong-password") is False


class TestUserRoles:
    def test_role_helpers(self, make_user):
        candidate = make_user(email="c@example.com", role="candidate")
        recruiter = make_user(email="r@example.com", role="recruiter")
        admin = make_user(email="a@example.com", role="admin")

        assert candidate.is_candidate() and not candidate.is_recruiter() and not candidate.is_admin()
        assert recruiter.is_recruiter() and not recruiter.is_candidate()
        assert admin.is_admin() and not admin.is_recruiter()

    def test_recruiter_approval_status(self, db_session):
        recruiter = User(email="pending@example.com", role="recruiter",
                          first_name="Pending", last_name="Recruiter",
                          recruiter_status="pending")
        recruiter.set_password("Passw0rd!")
        db_session.add(recruiter)
        db_session.commit()

        assert recruiter.is_recruiter_pending() is True
        assert recruiter.is_recruiter_approved() is False

    def test_get_full_name_and_initials(self, make_user):
        user = make_user(first_name="Arathi", last_name="Shekhar")
        assert user.get_full_name() == "Arathi Shekhar"
        assert user.get_initials() == "AS"


class TestUserAccountLock:
    def test_not_locked_by_default(self, make_user):
        user = make_user()
        assert user.is_locked() is False

    def test_lock_account_sets_future_lockout(self, make_user, db_session):
        user = make_user()
        user.lock_account(minutes=30)
        assert user.is_locked() is True
        assert user.locked_until > datetime.utcnow()

    def test_unlock_account_clears_lockout(self, make_user):
        user = make_user()
        user.lock_account(minutes=30)
        user.failed_login_attempts = 4
        user.unlock_account()
        assert user.is_locked() is False
        assert user.failed_login_attempts == 0

    def test_lock_in_the_past_is_not_locked(self, make_user, db_session):
        user = make_user()
        user.locked_until = datetime.utcnow() - timedelta(minutes=5)
        db_session.commit()
        assert user.is_locked() is False


class TestResumeJsonAccessors:
    def _make_resume(self, db_session, user, **kwargs):
        resume = Resume(user_id=user.id, filename="r.pdf", original_filename="resume.pdf",
                         file_type="pdf", **kwargs)
        db_session.add(resume)
        db_session.commit()
        return resume

    def test_get_skills_list_parses_json(self, db_session, make_user):
        user = make_user()
        resume = self._make_resume(db_session, user, extracted_skills=json.dumps(["Python", "Flask"]))
        assert resume.get_skills_list() == ["Python", "Flask"]

    def test_get_skills_list_empty_when_none(self, db_session, make_user):
        user = make_user()
        resume = self._make_resume(db_session, user)
        assert resume.get_skills_list() == []

    def test_get_skills_list_handles_malformed_json(self, db_session, make_user):
        user = make_user()
        resume = self._make_resume(db_session, user, extracted_skills="not valid json")
        assert resume.get_skills_list() == []

    def test_get_authenticity_flags_parses_json(self, db_session, make_user):
        user = make_user()
        resume = self._make_resume(db_session, user, authenticity_flags=json.dumps(["flag one"]))
        assert resume.get_authenticity_flags() == ["flag one"]
