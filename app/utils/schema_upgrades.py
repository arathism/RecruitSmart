"""
Lightweight, additive-only schema upgrades.
--------------------------------------------
db.create_all() (called at startup in app/__init__.py) only creates
TABLES that don't exist yet -- it never adds new COLUMNS to a table that
already exists on disk. This project ships a committed instance/*.db file
and doesn't have an Alembic migrations/ directory set up, so a plain
`db.create_all()` alone would silently leave any newly-added model column
(e.g. MatchScore.ontology_score, MatchScore.explanation_data, added for
the explainable-AI / skill-ontology features) missing from an existing
database, causing errors the first time that column is written to.

This module is a small, dependency-free stand-in for a real migration
tool: it inspects the live SQLite schema and adds any missing columns
with `ALTER TABLE ... ADD COLUMN`, which SQLite supports directly. It is:
  - additive-only (never drops/renames/alters existing columns), so it
    cannot destroy data;
  - idempotent (checks what's already there before doing anything), so
    it's safe to call on every app startup;
  - a no-op on a fresh database, since db.create_all() will have already
    created the column correctly as part of the table.

For a production system you'd reach for Flask-Migrate/Alembic revisions
instead of this; this is a pragmatic, minimal-dependency approach that
fits a project already carrying a single committed SQLite file.
"""
from sqlalchemy import inspect, text


# (table_name, column_name, column_type_sql)
_NEW_COLUMNS = [
    ("match_scores", "ontology_score", "INTEGER"),
    ("match_scores", "explanation_data", "TEXT"),
]


def ensure_schema_upgrades(db):
    """Call once at app startup, inside an app context, after db.create_all()."""
    try:
        inspector = inspect(db.engine)
        existing_tables = set(inspector.get_table_names())
        with db.engine.begin() as conn:
            for table, column, col_type in _NEW_COLUMNS:
                if table not in existing_tables:
                    continue  # db.create_all() will have created it correctly already
                existing_columns = {c["name"] for c in inspector.get_columns(table)}
                if column in existing_columns:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
    except Exception:
        # Never let a schema-upgrade hiccup take the whole app down --
        # worst case, the new column stays absent and the feature that
        # depends on it degrades (get_explanation_data() already handles
        # a missing/empty value gracefully).
        pass


def ensure_every_candidate_has_a_primary_resume(db):
    """Data-repair pass (Aug 2026), idempotent and safe to run on every
    startup.

    Bug: build_resume() used to hardcode is_primary=False even for a
    candidate's very first resume ever (fixed separately in
    app/candidate/routes.py). Anyone who hit that code path before the fix
    is left with a resume row -- or several -- where NONE has
    is_primary=True. The dashboard silently falls back to showing one of
    those resumes anyway (`resumes[0]`), but the resume-ranking query only
    ever looks at rows where is_primary is True, so looking up that
    resume's own score inside that filtered list raises
    "ValueError: X is not in list" and crashes the dashboard page.

    Fixing the code path stops new occurrences, but doesn't repair rows
    already sitting in that broken state in an existing database -- this
    does that: for every user who has at least one resume but zero marked
    primary, promote their most recently created resume to primary. Never
    touches a user who already has a primary resume.

    Deliberately written as plain Python over a small, already-fetched
    result set (grouping in-memory) rather than a SQL aggregate/cast
    query -- this project's user/resume counts are small (student-project
    scale), and a simple approach here is easier to verify correct than a
    cross-database-portable HAVING/CAST expression.
    """
    try:
        from app.models import Resume
        all_resumes = Resume.query.order_by(Resume.created_at.desc()).all()
        resumes_by_user = {}
        for r in all_resumes:
            resumes_by_user.setdefault(r.user_id, []).append(r)

        repaired_any = False
        for user_id, user_resumes in resumes_by_user.items():
            if not any(r.is_primary for r in user_resumes):
                # user_resumes is already sorted newest-first (query above),
                # so [0] is the most recently created resume for this user.
                user_resumes[0].is_primary = True
                repaired_any = True

        if repaired_any:
            db.session.commit()
    except Exception:
        # Same philosophy as ensure_schema_upgrades: a repair-pass hiccup
        # should never block app startup.
        db.session.rollback()
