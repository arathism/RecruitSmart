import json
from flask import render_template, request, redirect, url_for, flash, abort, send_file
from flask_login import login_required, current_user
from datetime import datetime
from app.recruiter import bp
from app import db
from app.models import Job, MatchScore, JobApplication, Interview, Notification, User, Resume
from app.utils.decorators import recruiter_required, recruiter_verified_required
from app.utils.ai_parser import match_resume_to_job
from app.utils.pdf_report import generate_shortlist_report
from app.utils.skill_demand import compute_skill_demand

def log_activity(user_id, action, details=None):
    from app.models import ActivityLog
    from flask import request
    log = ActivityLog(user_id=user_id, action=action, details=details,
        ip_address=request.remote_addr, user_agent=request.user_agent.string[:500] if request.user_agent else None)
    db.session.add(log)
    db.session.commit()

def create_notification(user_id, title, message, notification_type='general', link=None):
    notification = Notification(user_id=user_id, title=title, message=message, notification_type=notification_type, link=link)
    db.session.add(notification)
    db.session.commit()

@bp.route('/dashboard')
@login_required
@recruiter_required
def dashboard():
    jobs = Job.query.filter_by(recruiter_id=current_user.id).order_by(Job.created_at.desc()).all()
    total_applications = sum(j.application_count for j in jobs)
    shortlisted = MatchScore.query.join(Job).filter(Job.recruiter_id == current_user.id, MatchScore.is_shortlisted == True).count()
    interviews = Interview.query.join(Job).filter(Job.recruiter_id == current_user.id, Interview.status == 'scheduled').count()
    return render_template('recruiter/dashboard.html', jobs=jobs, total_applications=total_applications, shortlisted=shortlisted, interviews=interviews)

@bp.route('/post-job', methods=['GET', 'POST'])
@login_required
@recruiter_verified_required
def post_job():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        requirements = request.form.get('requirements', '').strip()
        responsibilities = request.form.get('responsibilities', '').strip()
        location = request.form.get('location', '').strip()
        is_remote = request.form.get('is_remote') == 'on'
        job_type = request.form.get('job_type', 'full_time')
        required_skills_list = [s.strip() for s in request.form.get('required_skills', '').split(',') if s.strip()]
        preferred_skills = request.form.get('preferred_skills', '').split(',')
        salary_min = request.form.get('salary_min', type=int)
        salary_max = request.form.get('salary_max', type=int)
        experience_min = request.form.get('experience_min', type=int) or 0
        experience_max = request.form.get('experience_max', type=int)

        # A job with no required skills breaks the entire AI matching pipeline
        # downstream (skill-match score, skill-gap analysis, recommendations)
        # in a way that's confusing rather than obviously broken -- it used to
        # silently show a misleading "0% match, no skill gaps, great fit!" to
        # every candidate. Catching it here, at the source, is far better
        # than trying to explain around it everywhere the score is displayed.
        errors = []
        if not title:
            errors.append('Job title is required.')
        if not description:
            errors.append('Job description is required.')
        if not required_skills_list:
            errors.append('At least one required skill is needed so candidates can get an accurate AI match score. '
                           'Without this, every applicant would see a meaningless 0% match.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('recruiter/post_job.html', form_data=request.form)

        job = Job(
            recruiter_id=current_user.id,
            title=title,
            description=description,
            requirements=requirements,
            responsibilities=responsibilities,
            location=location,
            is_remote=is_remote,
            job_type=job_type,
            required_skills=json.dumps(required_skills_list),
            preferred_skills=json.dumps([s.strip() for s in preferred_skills if s.strip()]),
            salary_min=salary_min,
            salary_max=salary_max,
            experience_min=experience_min,
            experience_max=experience_max,
            status='active'
        )
        db.session.add(job)
        db.session.commit()

        log_activity(current_user.id, 'job_posted', f'Posted {title}')
        flash(f'Job "{title}" posted successfully!', 'success')
        return redirect(url_for('recruiter.dashboard'))

    return render_template('recruiter/post_job.html')

@bp.route('/job/<int:job_id>/edit', methods=['GET', 'POST'])
@login_required
@recruiter_verified_required
def edit_job(job_id):
    """Lets a recruiter fix a job after posting it -- most importantly,
    add required skills to a job that was accidentally posted without any.
    A job with zero required skills breaks AI matching for every candidate
    (guaranteed 0% skill match, "no skill gaps, great fit!" shown
    nonsensically) with no way to recover short of this."""
    job = Job.query.get_or_404(job_id)
    if job.recruiter_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('recruiter.my_jobs'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        required_skills_list = [s.strip() for s in request.form.get('required_skills', '').split(',') if s.strip()]
        preferred_skills = request.form.get('preferred_skills', '').split(',')

        errors = []
        if not title:
            errors.append('Job title is required.')
        if not description:
            errors.append('Job description is required.')
        if not required_skills_list:
            errors.append('At least one required skill is needed so candidates can get an accurate AI match score.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('recruiter/edit_job.html', job=job)

        job.title = title
        job.description = description
        job.requirements = request.form.get('requirements', '').strip()
        job.responsibilities = request.form.get('responsibilities', '').strip()
        job.location = request.form.get('location', '').strip()
        job.is_remote = request.form.get('is_remote') == 'on'
        job.job_type = request.form.get('job_type', 'full_time')
        job.required_skills = json.dumps(required_skills_list)
        job.preferred_skills = json.dumps([s.strip() for s in preferred_skills if s.strip()])
        job.salary_min = request.form.get('salary_min', type=int)
        job.salary_max = request.form.get('salary_max', type=int)
        job.experience_min = request.form.get('experience_min', type=int) or 0
        job.experience_max = request.form.get('experience_max', type=int)
        db.session.commit()

        # Existing match scores were computed against the OLD (possibly
        # empty) required_skills list -- they're now stale/wrong and must
        # be cleared so they get recalculated against the corrected job
        # the next time a candidate (or the candidate themselves) re-runs
        # the match, rather than continuing to show a misleading old score.
        stale_matches = MatchScore.query.filter_by(job_id=job.id).all()
        for m in stale_matches:
            db.session.delete(m)
        db.session.commit()

        log_activity(current_user.id, 'job_edited', f'Edited job "{title}"')
        flash(f'Job "{title}" updated. Any previous AI match scores for this job have been cleared and will '
              f'recalculate correctly the next time a candidate runs a match.', 'success')
        return redirect(url_for('recruiter.my_jobs'))

    return render_template('recruiter/edit_job.html', job=job)

@bp.route('/job/<int:job_id>/delete', methods=['POST'])
@login_required
@recruiter_verified_required
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)
    if job.recruiter_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('recruiter.my_jobs'))

    title = job.title
    db.session.delete(job)
    db.session.commit()
    log_activity(current_user.id, 'job_deleted', f'Deleted job "{title}"')
    flash(f'Job "{title}" deleted.', 'info')
    return redirect(url_for('recruiter.my_jobs'))

@bp.route('/skill-demand')
@login_required
@recruiter_verified_required
def skill_demand():
    """Real supply-vs-demand aggregation across the platform's actual data
    -- no projected/fabricated figures. Helps a recruiter see which skills
    they're asking for are actually scarce among real candidates here."""
    all_resume_skills = [r.get_skills_list() for r in Resume.query.filter_by(is_primary=True).all()]
    all_job_skills = [j.get_required_skills_list() for j in Job.query.filter_by(status='active').all()]
    demand_data = compute_skill_demand(all_resume_skills, all_job_skills)
    return render_template('recruiter/skill_demand.html', data=demand_data)

@bp.route('/jobs')
@login_required
@recruiter_required
def my_jobs():
    jobs = Job.query.filter_by(recruiter_id=current_user.id).order_by(Job.created_at.desc()).all()
    return render_template('recruiter/jobs.html', jobs=jobs)

@bp.route('/job/<int:job_id>/candidates')
@login_required
@recruiter_verified_required
def view_candidates(job_id):
    job = Job.query.get_or_404(job_id)
    if job.recruiter_id != current_user.id:
        abort(403)

    match_scores = MatchScore.query.filter_by(job_id=job_id).order_by(MatchScore.overall_score.desc()).all()
    return render_template('recruiter/candidates.html', job=job, match_scores=match_scores)

@bp.route('/job/<int:job_id>/candidates/report')
@login_required
@recruiter_verified_required
def download_shortlist_report(job_id):
    job = Job.query.get_or_404(job_id)
    if job.recruiter_id != current_user.id:
        abort(403)
    match_scores = MatchScore.query.filter_by(job_id=job_id).order_by(MatchScore.overall_score.desc()).all()
    buffer = generate_shortlist_report(job, match_scores)
    log_activity(current_user.id, 'shortlist_report_downloaded', f'Downloaded shortlist report for {job.title}')
    filename = f"RecruitSmart_Shortlist_{job.title.replace(' ', '_')}.pdf"
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)

@bp.route('/shortlist/<int:match_id>', methods=['POST'])
@login_required
@recruiter_verified_required
def shortlist_candidate(match_id):
    match = MatchScore.query.get_or_404(match_id)
    job = Job.query.get(match.job_id)
    if job.recruiter_id != current_user.id:
        abort(403)

    match.is_shortlisted = True
    match.is_rejected = False
    db.session.commit()

    # Notify candidate
    create_notification(
        match.resume.user_id,
        'You have been shortlisted!',
        f'Congratulations! You have been shortlisted for "{job.title}"',
        'application',
        url_for('candidate.my_applications')
    )

    flash('Candidate shortlisted!', 'success')
    return redirect(url_for('recruiter.view_candidates', job_id=job.id))

@bp.route('/reject/<int:match_id>', methods=['POST'])
@login_required
@recruiter_verified_required
def reject_candidate(match_id):
    match = MatchScore.query.get_or_404(match_id)
    job = Job.query.get(match.job_id)
    if job.recruiter_id != current_user.id:
        abort(403)

    match.is_rejected = True
    match.is_shortlisted = False
    db.session.commit()

    create_notification(
        match.resume.user_id,
        'Application Update',
        f'Your application for "{job.title}" has been reviewed.',
        'application'
    )

    flash('Candidate rejected', 'info')
    return redirect(url_for('recruiter.view_candidates', job_id=job.id))

@bp.route('/schedule-interview/<int:match_id>', methods=['GET', 'POST'])
@login_required
@recruiter_verified_required
def schedule_interview(match_id):
    match = MatchScore.query.get_or_404(match_id)
    job = Job.query.get(match.job_id)
    if job.recruiter_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        interview_type = request.form.get('interview_type', 'video')
        scheduled_at = datetime.fromisoformat(request.form.get('scheduled_at'))
        duration = request.form.get('duration', 60, type=int)
        location = request.form.get('location', '').strip()
        meeting_link = request.form.get('meeting_link', '').strip()

        interview = Interview(
            job_id=job.id,
            candidate_id=match.resume.user_id,
            recruiter_id=current_user.id,
            interview_type=interview_type,
            scheduled_at=scheduled_at,
            duration_minutes=duration,
            location=location,
            meeting_link=meeting_link
        )
        db.session.add(interview)
        db.session.commit()

        create_notification(
            match.resume.user_id,
            'Interview Scheduled',
            f'Interview for "{job.title}" scheduled on {scheduled_at.strftime("%Y-%m-%d %H:%M")}',
            'interview'
        )

        flash('Interview scheduled!', 'success')
        return redirect(url_for('recruiter.dashboard'))

    return render_template('recruiter/schedule_interview.html', match=match, job=job)

@bp.route('/applications/<int:job_id>')
@login_required
@recruiter_verified_required
def view_applications(job_id):
    job = Job.query.get_or_404(job_id)
    if job.recruiter_id != current_user.id:
        abort(403)
    applications = JobApplication.query.filter_by(job_id=job_id).order_by(JobApplication.applied_at.desc()).all()
    return render_template('recruiter/applications.html', job=job, applications=applications)

@bp.route('/update-application/<int:app_id>', methods=['POST'])
@login_required
@recruiter_verified_required
def update_application(app_id):
    application = JobApplication.query.get_or_404(app_id)
    job = Job.query.get(application.job_id)
    if job.recruiter_id != current_user.id:
        abort(403)

    new_status = request.form.get('status')
    recruiter_notes = request.form.get('recruiter_notes', '').strip()
    application.status = new_status
    application.reviewed_at = datetime.utcnow()
    if recruiter_notes:
        application.recruiter_notes = recruiter_notes
    db.session.commit()

    if new_status == 'rejected':
        message = f'Your application for "{job.title}" was not successful this time. Tap to see the specific reason, skill gaps, and better-fit roles we found for you.'
        link = url_for('candidate.application_feedback', app_id=application.id)
    else:
        message = f'Your application for "{job.title}" is now: {new_status.title()}'
        link = url_for('candidate.my_applications')

    create_notification(
        application.candidate_id,
        'Application Status Updated',
        message,
        'application',
        link
    )

    flash(f'Application status updated to {new_status}', 'success')
    return redirect(url_for('recruiter.view_applications', job_id=job.id))
