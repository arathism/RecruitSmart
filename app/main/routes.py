from flask import render_template, jsonify
from flask_login import current_user
from sqlalchemy import func
from app import db
from app.main import bp
from app.models import Job, User, Resume, MatchScore, JobApplication, GithubVerification

@bp.route('/')
def index():
    """Every number shown on the landing page is a live query against the
    actual database -- nothing here is a placeholder/demo figure. This
    matters for a published project: every stat should be something you can
    point to a specific query for if asked."""
    featured_jobs = Job.query.filter_by(status='active', is_featured=True).order_by(Job.posted_at.desc()).limit(6).all()

    if not featured_jobs:
        # Fall back to any active jobs if none are marked "featured" yet
        featured_jobs = Job.query.filter_by(status='active').order_by(Job.posted_at.desc()).limit(6).all()

    avg_ats_score = db.session.query(func.avg(Resume.ats_score)).filter(Resume.ats_score.isnot(None)).scalar()
    avg_match_score = db.session.query(func.avg(MatchScore.overall_score)).scalar()

    stats = {
        'total_jobs': Job.query.filter_by(status='active').count(),
        'total_candidates': User.query.filter_by(role='candidate').count(),
        'total_recruiters': User.query.filter_by(role='recruiter', recruiter_status='approved').count(),
        'total_applications': JobApplication.query.count(),
        'total_resumes': Resume.query.count(),
        'total_matches': MatchScore.query.count(),
        'total_github_verifications': GithubVerification.query.count(),
        'avg_ats_score': round(avg_ats_score) if avg_ats_score else None,
        'avg_match_score': round(avg_match_score) if avg_match_score else None,
    }
    return render_template('index.html', featured_jobs=featured_jobs, stats=stats)

@bp.route('/about')
def about():
    return render_template('about.html')

@bp.route('/contact', methods=['GET', 'POST'])
def contact():
    from flask import request, flash, redirect, url_for
    if request.method == 'POST':
        flash('Thank you for your message! We will get back to you soon.', 'success')
        return redirect(url_for('main.contact'))
    return render_template('contact.html')

@bp.route('/privacy')
def privacy():
    return render_template('privacy.html')

@bp.route('/terms')
def terms():
    return render_template('terms.html')

@bp.route('/api/health')
def health_check():
    return jsonify({'status': 'healthy', 'version': '2.0.0'})
