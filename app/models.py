from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import json
from app import db

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='candidate')
    phone = db.Column(db.String(20))
    location = db.Column(db.String(100))
    bio = db.Column(db.Text)
    profile_image = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    email_verified = db.Column(db.Boolean, default=False)
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_secret = db.Column(db.String(32))
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    last_login = db.Column(db.DateTime)
    google_id = db.Column(db.String(100), unique=True)
    linkedin_id = db.Column(db.String(100), unique=True)
    gdpr_consent = db.Column(db.Boolean, default=False)
    gdpr_consent_date = db.Column(db.DateTime)
    data_export_requested = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- Recruiter Verification (security: prevents anyone from self-registering
    # as a recruiter and immediately gaining access to candidate resumes/data) ---
    company_name = db.Column(db.String(150))
    company_website = db.Column(db.String(200))
    work_position = db.Column(db.String(100))
    recruiter_status = db.Column(db.String(20), default='not_applicable')  # not_applicable, pending, approved, rejected
    recruiter_verified_at = db.Column(db.DateTime)
    recruiter_verified_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    recruiter_rejection_reason = db.Column(db.String(300))

    def is_recruiter_approved(self):
        return self.role == 'recruiter' and self.recruiter_status == 'approved'

    def is_recruiter_pending(self):
        return self.role == 'recruiter' and self.recruiter_status == 'pending'

    resumes = db.relationship('Resume', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    jobs = db.relationship('Job', backref='recruiter', lazy='dynamic', cascade='all, delete-orphan')
    roadmaps = db.relationship('CareerRoadmap', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    # Fix: specify foreign_keys for interviews relationship
    interviews_as_candidate = db.relationship('Interview', foreign_keys='Interview.candidate_id', backref='candidate', lazy='dynamic', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    applications = db.relationship('JobApplication', backref='candidate', lazy='dynamic', cascade='all, delete-orphan')
    messages_sent = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic')
    messages_received = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy='dynamic')
    activity_logs = db.relationship('ActivityLog', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    skill_tests = db.relationship('SkillTestResult', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    github_verification = db.relationship('GithubVerification', backref='user', uselist=False, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_locked(self):
        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        return False

    def lock_account(self, minutes=30):
        self.locked_until = datetime.utcnow() + timedelta(minutes=minutes)
        db.session.commit()

    def unlock_account(self):
        self.locked_until = None
        self.failed_login_attempts = 0
        db.session.commit()

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_initials(self):
        return f"{self.first_name[0]}{self.last_name[0]}".upper()

    def is_admin(self):
        return self.role == 'admin'

    def is_recruiter(self):
        return self.role == 'recruiter'

    def is_candidate(self):
        return self.role == 'candidate'

    def verify_totp(self, token):
        """Checks a 6-digit TOTP code against this user's secret. Returns
        False (never raises) if 2FA isn't enabled, no secret is set, or the
        code is malformed -- callers can treat this as a plain pass/fail.
        valid_window=1 tolerates +/-30s of clock drift between the server
        and the user's authenticator app, which is standard TOTP practice."""
        if not self.two_factor_enabled or not self.two_factor_secret or not token:
            return False
        import pyotp
        try:
            return pyotp.TOTP(self.two_factor_secret).verify(token.strip(), valid_window=1)
        except Exception:
            return False

    def get_notification_count(self):
        return Notification.query.filter_by(user_id=self.id, is_read=False).count()

    def __repr__(self):
        return f'<User {self.email}>'

class Resume(db.Model):
    __tablename__ = 'resumes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)
    file_type = db.Column(db.String(10), nullable=False)
    file_size = db.Column(db.Integer)
    parsed_text = db.Column(db.Text)
    extracted_skills = db.Column(db.Text)
    extracted_experience = db.Column(db.Text)
    extracted_education = db.Column(db.Text)
    ats_score = db.Column(db.Integer, default=0)
    ats_feedback = db.Column(db.Text)
    ai_summary = db.Column(db.Text)
    skill_categories = db.Column(db.Text)
    experience_years = db.Column(db.Float)
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    matches = db.relationship('MatchScore', backref='resume', lazy='dynamic', cascade='all, delete-orphan')

    # --- Resume Authenticity Check (heuristic fraud/fabrication screening) ---
    authenticity_score = db.Column(db.Integer)
    authenticity_tier = db.Column(db.String(30))
    authenticity_flags = db.Column(db.Text)
    authenticity_checked_at = db.Column(db.DateTime)

    def get_authenticity_flags(self):
        if self.authenticity_flags:
            try:
                return json.loads(self.authenticity_flags)
            except Exception:
                return []
        return []

    def get_skills_list(self):
        if self.extracted_skills:
            try:
                return json.loads(self.extracted_skills)
            except:
                return []
        return []

    def get_ats_feedback_list(self):
        if self.ats_feedback:
            try:
                return json.loads(self.ats_feedback)
            except:
                return []
        return []

    def __repr__(self):
        return f'<Resume {self.original_filename}>'

class Job(db.Model):
    __tablename__ = 'jobs'
    id = db.Column(db.Integer, primary_key=True)
    recruiter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text)
    responsibilities = db.Column(db.Text)
    location = db.Column(db.String(100))
    is_remote = db.Column(db.Boolean, default=False)
    job_type = db.Column(db.String(20), default='full_time')
    required_skills = db.Column(db.Text)
    preferred_skills = db.Column(db.Text)
    salary_min = db.Column(db.Integer)
    salary_max = db.Column(db.Integer)
    salary_currency = db.Column(db.String(3), default='USD')
    salary_period = db.Column(db.String(10), default='yearly')
    experience_min = db.Column(db.Integer, default=0)
    experience_max = db.Column(db.Integer)
    status = db.Column(db.String(20), default='active')
    is_featured = db.Column(db.Boolean, default=False)
    ai_parsed_skills = db.Column(db.Text)
    ai_summary = db.Column(db.Text)
    view_count = db.Column(db.Integer, default=0)
    application_count = db.Column(db.Integer, default=0)
    posted_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    matches = db.relationship('MatchScore', backref='job', lazy='dynamic', cascade='all, delete-orphan')
    applications = db.relationship('JobApplication', backref='job', lazy='dynamic', cascade='all, delete-orphan')
    interviews = db.relationship('Interview', backref='job', lazy='dynamic', cascade='all, delete-orphan')

    def get_required_skills_list(self):
        if self.required_skills:
            try:
                return json.loads(self.required_skills)
            except:
                return []
        return []

    def get_preferred_skills_list(self):
        if self.preferred_skills:
            try:
                return json.loads(self.preferred_skills)
            except:
                return []
        return []

    def get_salary_display(self):
        if self.salary_min and self.salary_max:
            return f"${self.salary_min:,} - ${self.salary_max:,} {self.salary_period}"
        elif self.salary_min:
            return f"From ${self.salary_min:,} {self.salary_period}"
        elif self.salary_max:
            return f"Up to ${self.salary_max:,} {self.salary_period}"
        return "Not specified"

    def __repr__(self):
        return f'<Job {self.title}>'

class MatchScore(db.Model):
    __tablename__ = 'match_scores'
    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(db.Integer, db.ForeignKey('resumes.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    overall_score = db.Column(db.Integer, default=0)
    semantic_score = db.Column(db.Integer, default=0)
    skill_score = db.Column(db.Integer, default=0)
    experience_score = db.Column(db.Integer, default=0)
    # ml_confidence: output of the platform's one genuinely TRAINED
    # supervised model (see app/utils/train_match_model.py). Nullable
    # because it's only populated when the trained model file is present
    # (see app/utils/trained_match_model.py's graceful fallback) -- never
    # required for the rule-based overall_score above to work.
    ml_confidence = db.Column(db.Integer, nullable=True)
    # ontology_score / explanation_data: added for the explainable-AI +
    # skill-ontology features (see app/utils/skill_ontology.py and
    # app/utils/ai_parser.py's explain_match()/counterfactual_suggestions()).
    # Nullable so this degrades gracefully on any MatchScore row computed
    # before this feature existed, and so a database that hasn't been
    # migrated yet (see ensure_schema_upgrades() in app/__init__.py) doesn't
    # break existing reads.
    ontology_score = db.Column(db.Integer, nullable=True)
    explanation_data = db.Column(db.Text, nullable=True)
    matching_skills = db.Column(db.Text)
    missing_skills = db.Column(db.Text)
    skill_gaps = db.relationship('SkillGap', backref='match_score', lazy='dynamic', cascade='all, delete-orphan')
    recommendation = db.Column(db.String(20))
    ai_feedback = db.Column(db.Text)
    is_shortlisted = db.Column(db.Boolean, default=False)
    is_rejected = db.Column(db.Boolean, default=False)
    recruiter_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_explanation_data(self):
        """Parsed {"reasons": [...], "counterfactuals": [...], "ontology_matches": [...]}
        dict produced by app.utils.ai_parser.match_resume_to_job(), or a
        safe empty shape if this MatchScore predates the feature / failed
        to parse."""
        if self.explanation_data:
            try:
                return json.loads(self.explanation_data)
            except Exception:
                pass
        return {"reasons": [], "counterfactuals": [], "ontology_matches": []}

    def get_matching_skills_list(self):
        if self.matching_skills:
            try:
                return json.loads(self.matching_skills)
            except:
                return []
        return []

    def get_missing_skills_list(self):
        if self.missing_skills:
            try:
                return json.loads(self.missing_skills)
            except:
                return []
        return []

    def get_score_color(self):
        if self.recommendation == 'incomplete_listing':
            return 'secondary'
        if self.overall_score >= 80:
            return 'success'
        elif self.overall_score >= 60:
            return 'warning'
        else:
            return 'danger'

    def __repr__(self):
        return f'<MatchScore {self.overall_score}%>'

class SkillGap(db.Model):
    __tablename__ = 'skill_gaps'
    id = db.Column(db.Integer, primary_key=True)
    match_score_id = db.Column(db.Integer, db.ForeignKey('match_scores.id'), nullable=False)
    skill_name = db.Column(db.String(100), nullable=False)
    importance = db.Column(db.String(20), default='medium')
    current_level = db.Column(db.String(20))
    target_level = db.Column(db.String(20))
    learning_resources = db.Column(db.Text)
    estimated_time = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_learning_resources(self):
        if self.learning_resources:
            try:
                return json.loads(self.learning_resources)
            except Exception:
                return []
        return []

class JobApplication(db.Model):
    __tablename__ = 'job_applications'
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    resume_id = db.Column(db.Integer, db.ForeignKey('resumes.id'))
    cover_letter = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    recruiter_notes = db.Column(db.Text)
    reviewed_at = db.Column(db.DateTime)
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<JobApplication {self.status}>'

class CareerRoadmap(db.Model):
    __tablename__ = 'career_roadmaps'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    target_role = db.Column(db.String(100), nullable=False)
    target_industry = db.Column(db.String(100))
    readiness_score = db.Column(db.Integer, default=0)
    estimated_months = db.Column(db.Integer)
    milestones = db.Column(db.Text)
    learning_paths = db.Column(db.Text)
    skill_requirements = db.Column(db.Text)
    ai_analysis = db.Column(db.Text)
    market_demand = db.Column(db.String(20))
    salary_range = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_milestones_list(self):
        if self.milestones:
            try:
                return json.loads(self.milestones)
            except:
                return []
        return []

    def get_learning_paths_list(self):
        if self.learning_paths:
            try:
                return json.loads(self.learning_paths)
            except:
                return []
        return []

    def __repr__(self):
        return f'<CareerRoadmap {self.target_role}>'

class Interview(db.Model):
    __tablename__ = 'interviews'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recruiter_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    interview_type = db.Column(db.String(20), default='video')
    scheduled_at = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, default=60)
    location = db.Column(db.String(200))
    meeting_link = db.Column(db.String(500))
    status = db.Column(db.String(20), default='scheduled')
    candidate_feedback = db.Column(db.Text)
    recruiter_feedback = db.Column(db.Text)
    rating = db.Column(db.Integer)
    reminder_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Interview {self.scheduled_at}>'

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), default='general')
    link = db.Column(db.String(500))
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def mark_as_read(self):
        self.is_read = True
        self.read_at = datetime.utcnow()
        db.session.commit()

    def __repr__(self):
        return f'<Notification {self.title}>'

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Message {self.id}>'

class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ActivityLog {self.action}>'

class AdminAuditLog(db.Model):
    """Dedicated audit trail for admin actions specifically (as opposed to
    ActivityLog, which is general-purpose and mostly candidate/recruiter
    activity). Every route that lets an admin change platform state --
    activate/deactivate/delete a user, approve/reject a recruiter, change
    platform settings -- writes one row here. This was a named gap in the
    project's own Future Scope ("Admin action audit log"); closing it means
    every privileged action has a permanent, queryable record of who did
    what, to whom, and when -- independent of the actor's own account
    later being modified or deleted."""
    __tablename__ = 'admin_audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    actor_email = db.Column(db.String(120), nullable=False)  # denormalized: survives actor deletion
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(50))       # e.g. 'user', 'recruiter', 'settings'
    target_id = db.Column(db.Integer)
    target_label = db.Column(db.String(200))      # denormalized: survives target deletion
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f'<AdminAuditLog {self.action} by {self.actor_email}>'

class SkillTest(db.Model):
    __tablename__ = 'skill_tests'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    skill_category = db.Column(db.String(50), nullable=False)
    difficulty = db.Column(db.String(20), default='medium')
    questions = db.Column(db.Text, nullable=False)
    time_limit_minutes = db.Column(db.Integer)
    passing_score = db.Column(db.Integer, default=70)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    results = db.relationship('SkillTestResult', backref='test', lazy='dynamic', cascade='all, delete-orphan')

class SkillTestResult(db.Model):
    __tablename__ = 'skill_test_results'
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('skill_tests.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    score = db.Column(db.Integer, default=0)
    total_questions = db.Column(db.Integer)
    correct_answers = db.Column(db.Integer)
    answers = db.Column(db.Text)
    time_taken_minutes = db.Column(db.Integer)
    is_passed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

class Company(db.Model):
    __tablename__ = 'companies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    website = db.Column(db.String(200))
    logo = db.Column(db.String(200))
    location = db.Column(db.String(200))
    size = db.Column(db.String(50))
    industry = db.Column(db.String(100))
    is_verified = db.Column(db.Boolean, default=False)
    verification_documents = db.Column(db.Text)
    linkedin_url = db.Column(db.String(200))
    twitter_url = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    recruiters = db.relationship('User', secondary='company_recruiters', backref='companies')

company_recruiters = db.Table('company_recruiters',
    db.Column('company_id', db.Integer, db.ForeignKey('companies.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True)
)

class GithubVerification(db.Model):
    """Stores the result of cross-checking a candidate's resume skills
    against their real, public GitHub activity (repos, languages, stars).
    This backs the Portfolio Verification feature -- one of RecruitSmart's
    key differentiators from plain keyword-matching ATS tools."""
    __tablename__ = 'github_verifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    github_username = db.Column(db.String(100), nullable=False)
    profile_url = db.Column(db.String(200))
    avatar_url = db.Column(db.String(300))
    public_repos = db.Column(db.Integer, default=0)
    followers = db.Column(db.Integer, default=0)
    total_stars = db.Column(db.Integer, default=0)
    portfolio_score = db.Column(db.Integer, default=0)
    portfolio_tier = db.Column(db.String(20))
    top_languages = db.Column(db.Text)
    verified_skills = db.Column(db.Text)
    confirmed_skills = db.Column(db.Text)
    unconfirmed_skills = db.Column(db.Text)
    authenticity_rate = db.Column(db.Integer, default=0)
    raw_analytics = db.Column(db.Text)
    verified_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_list(self, field_value):
        if field_value:
            try:
                return json.loads(field_value)
            except Exception:
                return []
        return []

    def get_top_languages(self):
        return self.get_list(self.top_languages)

    def get_verified_skills(self):
        return self.get_list(self.verified_skills)

    def get_confirmed_skills(self):
        return self.get_list(self.confirmed_skills)

    def get_unconfirmed_skills(self):
        return self.get_list(self.unconfirmed_skills)

    def __repr__(self):
        return f'<GithubVerification {self.github_username} score={self.portfolio_score}>'


class LinkedInAudit(db.Model):
    """Stores the result of a candidate's pasted-profile LinkedIn audit.
    Not fetched from LinkedIn itself (no API/scraping) -- the candidate
    pastes their own headline/about/experience text, which is analyzed here."""
    __tablename__ = 'linkedin_audits'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    headline = db.Column(db.String(300))
    about_text = db.Column(db.Text)
    experience_text = db.Column(db.Text)
    skills_count = db.Column(db.Integer, default=0)
    score = db.Column(db.Integer, default=0)
    impression = db.Column(db.Text)
    quick_wins = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])

    def get_quick_wins(self):
        if self.quick_wins:
            try:
                return json.loads(self.quick_wins)
            except Exception:
                return []
        return []


class SecurityEvent(db.Model):
    """Records security-relevant events -- blocked malicious file uploads,
    and (in future) other flagged activity -- so an admin has an actual
    audit trail instead of security checks happening silently."""
    __tablename__ = 'security_events'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    event_type = db.Column(db.String(50), nullable=False)  # e.g. 'malicious_upload_blocked'
    severity = db.Column(db.String(20), default='medium')  # low, medium, high
    description = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])


class SalaryPrediction(db.Model):
    __tablename__ = 'salary_predictions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    job_title = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100))
    experience_years = db.Column(db.Integer)
    predicted_min = db.Column(db.Integer)
    predicted_max = db.Column(db.Integer)
    predicted_avg = db.Column(db.Integer)
    confidence = db.Column(db.Float)
    factors = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PlatformSettings(db.Model):
    """A single-row table holding site-wide configuration that the admin
    Settings page actually reads from and writes to. Kept as one row
    (singleton pattern) rather than scattered app config, so changes here
    take effect immediately without a server restart."""
    __tablename__ = 'platform_settings'
    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(100), default='RecruitSmart')
    support_email = db.Column(db.String(120), default='support@recruitsmart.ai')
    allow_new_registrations = db.Column(db.Boolean, default=True)
    require_recruiter_verification = db.Column(db.Boolean, default=True)
    maintenance_mode = db.Column(db.Boolean, default=False)
    maintenance_message = db.Column(db.String(300), default='RecruitSmart is currently undergoing scheduled maintenance. Please check back shortly.')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get():
        settings = PlatformSettings.query.first()
        if not settings:
            settings = PlatformSettings()
            db.session.add(settings)
            db.session.commit()
        return settings


class RegistrationOTP(db.Model):
    """Stores the hashed one-time code sent to an email during registration.

    A DB table (rather than an in-memory dict) is required here because the
    app runs behind multiple gunicorn worker processes in production -- an
    in-memory store would only be visible to whichever worker happened to
    handle the /send-otp request, so a later /verify-otp request landing on
    a different worker would never find it."""
    __tablename__ = 'registration_otps'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    code_hash = db.Column(db.String(256), nullable=False)
    attempts = db.Column(db.Integer, default=0)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
