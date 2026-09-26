from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from app.admin import bp
from app import db
from app.models import User, Job, Resume, JobApplication, MatchScore, Interview, ActivityLog, Notification, SkillTest, PlatformSettings, SecurityEvent, AdminAuditLog
from datetime import datetime
from app.utils.decorators import admin_required


def log_admin_action(action, target_type=None, target_id=None, target_label=None, details=None):
    """Writes one row to admin_audit_logs for every privileged admin action.
    actor_email/target_label are denormalized (copied at write time) so the
    audit trail stays readable even if the actor's or target's account is
    later renamed or deleted -- an audit log that breaks when its subject
    is removed defeats the point of having one."""
    entry = AdminAuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        details=details,
        ip_address=request.remote_addr,
    )
    db.session.add(entry)
    db.session.commit()

@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    stats = {
        'total_users': User.query.count(),
        'total_candidates': User.query.filter_by(role='candidate').count(),
        'total_recruiters': User.query.filter_by(role='recruiter').count(),
        'total_jobs': Job.query.count(),
        'active_jobs': Job.query.filter_by(status='active').count(),
        'total_applications': JobApplication.query.count(),
        'total_resumes': Resume.query.count(),
        'total_interviews': Interview.query.count(),
        'locked_accounts': User.query.filter(User.locked_until.isnot(None)).count(),
        'unverified_users': User.query.filter_by(email_verified=False).count(),
        'pending_recruiters': User.query.filter_by(role='recruiter', recruiter_status='pending').count()
    }

    recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
    recent_jobs = Job.query.order_by(Job.created_at.desc()).limit(10).all()
    recent_logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(20).all()

    return render_template('admin/dashboard.html', stats=stats, recent_users=recent_users, recent_jobs=recent_jobs, recent_logs=recent_logs)

@bp.route('/users')
@login_required
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    role = request.args.get('role', '')
    search = request.args.get('search', '')

    query = User.query
    if role:
        query = query.filter_by(role=role)
    if search:
        query = query.filter(User.email.contains(search) | User.first_name.contains(search) | User.last_name.contains(search))

    users = query.order_by(User.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    pending_recruiters = User.query.filter_by(role='recruiter', recruiter_status='pending').order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users, role=role, search=search, pending_recruiters=pending_recruiters)

@bp.route('/user/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Cannot modify your own account', 'danger')
        return redirect(url_for('admin.users'))

    user.is_active = not user.is_active
    db.session.commit()
    log_admin_action('user_deactivated' if not user.is_active else 'user_activated',
                      target_type='user', target_id=user.id, target_label=user.email)
    flash(f'User {user.email} {"activated" if user.is_active else "deactivated"}', 'success')
    return redirect(url_for('admin.users'))

@bp.route('/user/<int:user_id>/unlock', methods=['POST'])
@login_required
@admin_required
def unlock_user(user_id):
    user = User.query.get_or_404(user_id)
    user.unlock_account()
    log_admin_action('user_unlocked', target_type='user', target_id=user.id, target_label=user.email)
    flash(f'Account {user.email} unlocked', 'success')
    return redirect(url_for('admin.users'))

@bp.route('/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Cannot delete your own account', 'danger')
        return redirect(url_for('admin.users'))

    deleted_email = user.email
    deleted_id = user.id
    db.session.delete(user)
    db.session.commit()
    # Logged AFTER commit with values captured beforehand: target_id/target_label
    # are denormalized specifically so this row still makes sense once the
    # user row it refers to no longer exists.
    log_admin_action('user_deleted', target_type='user', target_id=deleted_id, target_label=deleted_email)
    flash(f'User {deleted_email} deleted', 'success')
    return redirect(url_for('admin.users'))

@bp.route('/recruiter/<int:user_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_recruiter(user_id):
    """Approves a pending recruiter after the admin has manually checked their
    company details. This is the human checkpoint in the recruiter-verification
    security workflow -- it's what stops anyone from self-declaring as a
    recruiter and instantly getting access to every candidate's resume data."""
    user = User.query.get_or_404(user_id)
    if user.role != 'recruiter':
        flash('This user is not a recruiter.', 'danger')
        return redirect(url_for('admin.users'))

    user.recruiter_status = 'approved'
    user.recruiter_verified_at = datetime.utcnow()
    user.recruiter_verified_by = current_user.id
    user.recruiter_rejection_reason = None
    db.session.commit()

    notification = Notification(
        user_id=user.id, title='Recruiter Account Approved',
        message=f'Your recruiter account for {user.company_name} has been verified. You can now post jobs and view matched candidates.',
        notification_type='general', link=url_for('recruiter.dashboard')
    )
    db.session.add(notification)
    db.session.commit()
    log_admin_action('recruiter_approved', target_type='recruiter', target_id=user.id,
                      target_label=f'{user.email} ({user.company_name})')

    flash(f'{user.get_full_name()} ({user.company_name}) approved as a verified recruiter.', 'success')
    return redirect(url_for('admin.users', role='recruiter'))

@bp.route('/recruiter/<int:user_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_recruiter(user_id):
    user = User.query.get_or_404(user_id)
    if user.role != 'recruiter':
        flash('This user is not a recruiter.', 'danger')
        return redirect(url_for('admin.users'))

    reason = request.form.get('reason', '').strip() or 'Company details could not be verified.'
    user.recruiter_status = 'rejected'
    user.recruiter_rejection_reason = reason
    user.recruiter_verified_by = current_user.id
    db.session.commit()

    notification = Notification(
        user_id=user.id, title='Recruiter Verification Rejected',
        message=reason, notification_type='general', link=url_for('recruiter.dashboard')
    )
    db.session.add(notification)
    db.session.commit()
    log_admin_action('recruiter_rejected', target_type='recruiter', target_id=user.id,
                      target_label=f'{user.email} ({user.company_name})', details=reason)

    flash(f'{user.get_full_name()} was rejected as a recruiter.', 'info')
    return redirect(url_for('admin.users', role='recruiter'))

@bp.route('/jobs')
@login_required
@admin_required
def jobs():
    page = request.args.get('page', 1, type=int)
    jobs = Job.query.order_by(Job.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/jobs.html', jobs=jobs)

@bp.route('/analytics')
@login_required
@admin_required
def analytics():
    # User growth by month
    user_growth = db.session.query(
        func.strftime('%Y-%m', User.created_at).label('month'),
        func.count(User.id).label('count')
    ).group_by('month').order_by('month').all()

    # Job postings by month
    job_growth = db.session.query(
        func.strftime('%Y-%m', Job.created_at).label('month'),
        func.count(Job.id).label('count')
    ).group_by('month').order_by('month').all()

    # Application stats
    app_stats = {
        'pending': JobApplication.query.filter_by(status='pending').count(),
        'reviewing': JobApplication.query.filter_by(status='reviewing').count(),
        'shortlisted': JobApplication.query.filter_by(status='shortlisted').count(),
        'rejected': JobApplication.query.filter_by(status='rejected').count(),
        'hired': JobApplication.query.filter_by(status='hired').count()
    }

    return render_template('admin/analytics.html', user_growth=user_growth, job_growth=job_growth, app_stats=app_stats)

@bp.route('/skill-tests', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_tests():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('skill_category')
        difficulty = request.form.get('difficulty')
        questions_json = request.form.get('questions')
        time_limit = request.form.get('time_limit', type=int)
        passing_score = request.form.get('passing_score', 70, type=int)

        test = SkillTest(
            title=title,
            description=description,
            skill_category=category,
            difficulty=difficulty,
            questions=questions_json,
            time_limit_minutes=time_limit,
            passing_score=passing_score
        )
        db.session.add(test)
        db.session.commit()
        flash('Skill test created!', 'success')
        return redirect(url_for('admin.manage_tests'))

    tests = SkillTest.query.order_by(SkillTest.created_at.desc()).all()
    return render_template('admin/skill_tests.html', tests=tests)

@bp.route('/security')
@login_required
@admin_required
def security_center():
    """A dedicated view for security-relevant activity: blocked malicious
    file uploads, locked accounts from repeated failed logins, and pending
    recruiter verifications -- the three real security surfaces this
    platform actually has, in one place instead of scattered across pages."""
    page = request.args.get('page', 1, type=int)
    events = SecurityEvent.query.order_by(SecurityEvent.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    stats = {
        'total_blocked_uploads': SecurityEvent.query.filter_by(event_type='malicious_upload_blocked').count(),
        'locked_accounts': User.query.filter(User.locked_until.isnot(None)).count(),
        'pending_recruiters': User.query.filter_by(role='recruiter', recruiter_status='pending').count(),
        'high_severity_events': SecurityEvent.query.filter_by(severity='high').count(),
    }

    recent_failed_logins = User.query.filter(User.failed_login_attempts > 0).order_by(User.failed_login_attempts.desc()).limit(10).all()
    admin_audit_logs = AdminAuditLog.query.order_by(AdminAuditLog.created_at.desc()).limit(25).all()

    return render_template('admin/security.html', events=events, stats=stats,
                            recent_failed_logins=recent_failed_logins, admin_audit_logs=admin_audit_logs)

@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    platform_settings = PlatformSettings.get()
    if request.method == 'POST':
        platform_settings.site_name = request.form.get('site_name', platform_settings.site_name).strip() or platform_settings.site_name
        platform_settings.support_email = request.form.get('support_email', platform_settings.support_email).strip() or platform_settings.support_email
        platform_settings.allow_new_registrations = 'allow_new_registrations' in request.form
        platform_settings.require_recruiter_verification = 'require_recruiter_verification' in request.form
        platform_settings.maintenance_mode = 'maintenance_mode' in request.form
        platform_settings.maintenance_message = request.form.get('maintenance_message', platform_settings.maintenance_message).strip() or platform_settings.maintenance_message
        db.session.commit()
        log_admin_action('platform_settings_updated', target_type='settings',
                          details=f'maintenance_mode={platform_settings.maintenance_mode}, '
                                   f'allow_new_registrations={platform_settings.allow_new_registrations}, '
                                   f'require_recruiter_verification={platform_settings.require_recruiter_verification}')
        flash('Settings updated — changes are live immediately, no restart needed.', 'success')
        return redirect(url_for('admin.settings'))
    return render_template('admin/settings.html', settings=platform_settings)
