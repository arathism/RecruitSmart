import os
import json
from flask import render_template, request, redirect, url_for, flash, current_app, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
from app.candidate import bp
from app import db
from app.models import Resume, Job, MatchScore, SkillGap, CareerRoadmap, JobApplication, Notification, SkillTest, SkillTestResult, GithubVerification, SecurityEvent, SalaryPrediction, LinkedInAudit
from app.utils.decorators import candidate_required
from app.utils.ai_parser import parse_resume, calculate_ats_score, match_resume_to_job, generate_career_roadmap
from app.utils.file_handler import allowed_file, save_uploaded_file
from app.utils.upload_security import (validate_file_signature, scan_pdf_for_malicious_content,
    scan_for_malware_signature, scan_docx_for_macros, scan_docx_for_zip_bomb)
from app.utils.github_verifier import verify_github_portfolio
from app.utils.pdf_report import generate_candidate_report
from app.utils.resume_validator import is_resume
from app.utils.authenticity_checker import analyze_resume_authenticity
from app.utils.salary_predictor import predict_salary
from app.utils.linkedin_auditor import audit_linkedin_profile, parse_full_profile_text, is_url_only
from app.utils.career_fit import compute_career_fit
from app.utils.cover_letter import generate_cover_letter
from app.utils.interview_questions import generate_interview_questions

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
@candidate_required
def dashboard():
    resumes = Resume.query.filter_by(user_id=current_user.id).order_by(Resume.created_at.desc()).all()
    applications = JobApplication.query.filter_by(candidate_id=current_user.id).order_by(JobApplication.applied_at.desc()).all()
    roadmaps = CareerRoadmap.query.filter_by(user_id=current_user.id, is_active=True).all()
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
    github_verification = GithubVerification.query.filter_by(user_id=current_user.id).first()

    # "Recommended For You" -- genuinely personalized by resume skill overlap,
    # not just the newest postings. Falls back to newest-first only when the
    # candidate has no resume yet to personalize against.
    primary_resume = next((r for r in resumes if r.is_primary), resumes[0] if resumes else None)
    active_jobs = Job.query.filter_by(status='active').order_by(Job.posted_at.desc()).limit(50).all()

    if primary_resume and primary_resume.get_skills_list():
        candidate_skills = set(s.lower() for s in primary_resume.get_skills_list())
        scored_jobs = []
        for job in active_jobs:
            required = set(s.lower() for s in job.get_required_skills_list())
            if not required:
                continue
            overlap_pct = round(len(candidate_skills & required) / len(required) * 100)
            if overlap_pct > 0:
                scored_jobs.append((job, overlap_pct))
        scored_jobs.sort(key=lambda pair: pair[1], reverse=True)
        recommended_jobs = [job for job, _ in scored_jobs[:5]]
        recommended_job_scores = {job.id: pct for job, pct in scored_jobs[:5]}
    else:
        recommended_jobs = active_jobs[:5]
        recommended_job_scores = {}

    # Resume Ranking -- shows the candidate ONLY their own rank/percentile
    # among every primary resume on the platform (by ATS score). No other
    # candidate's name, score, or details are ever exposed by this --
    # it's a single number about where you personally stand, nothing more.
    resume_rank = None
    resume_rank_total = None
    resume_percentile = None
    if primary_resume and primary_resume.is_primary and primary_resume.ats_score is not None:
        all_scores = sorted(
            (s for (s,) in db.session.query(Resume.ats_score).filter(
                Resume.is_primary == True, Resume.ats_score.isnot(None)).all()),
            reverse=True
        )
        resume_rank_total = len(all_scores)
        # Rank = 1-indexed position of the candidate's own score in the
        # descending-sorted list of every primary resume's ATS score.
        #
        # Bug fix (Aug 2026): this crashed with "ValueError: X is not in
        # list" whenever a candidate had resumes uploaded but none of them
        # was actually flagged is_primary in the database -- the fallback
        # above (`primary_resume = next(..., resumes[0] if resumes else
        # None)`) still picked a resume to show on the dashboard even
        # though it wasn't a real primary, but this ranking query only
        # ever looks at `Resume.is_primary == True` rows, so that
        # resume's score was never in `all_scores` and .index() raised.
        # Guarded above with `primary_resume.is_primary` so ranking is
        # only computed for a resume that's genuinely counted in the
        # comparison group, and guarded again here in case of a
        # same-instant race with another request changing primary status.
        if primary_resume.ats_score in all_scores:
            resume_rank = all_scores.index(primary_resume.ats_score) + 1
            resume_percentile = round((1 - (resume_rank - 1) / resume_rank_total) * 100) if resume_rank_total else None

    return render_template('candidate/dashboard.html', resumes=resumes, applications=applications, roadmaps=roadmaps,
                            notifications=notifications, recommended_jobs=recommended_jobs,
                            recommended_job_scores=recommended_job_scores, github_verification=github_verification,
                            resume_rank=resume_rank, resume_rank_total=resume_rank_total, resume_percentile=resume_percentile)

@bp.route('/upload-resume', methods=['POST'])
@login_required
@candidate_required
def upload_resume():
    if 'resume' not in request.files:
        flash('No file selected', 'danger')
        return redirect(url_for('candidate.dashboard'))
    file = request.files['resume']
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('candidate.dashboard'))
    if file and allowed_file(file.filename):
        claimed_ext = file.filename.rsplit('.', 1)[1].lower()

        # Security: hard-blocks genuinely dangerous files (executables,
        # scripts). Structural "doesn't look like a textbook PDF" cases are
        # no longer blocking -- see validate_file_signature's docstring --
        # they just carry a non-fatal warning shown alongside the result.
        is_valid, sig_error, sig_warning = validate_file_signature(file.stream, claimed_ext)
        if not is_valid:
            log_activity(current_user.id, 'upload_rejected_security',
                         f'Rejected upload "{file.filename}": {sig_error}')
            event = SecurityEvent(user_id=current_user.id, event_type='malicious_upload_blocked',
                                   severity='high', description=f'File "{file.filename}": {sig_error}',
                                   ip_address=request.remote_addr)
            db.session.add(event)
            db.session.commit()
            flash(sig_error, 'danger')
            return redirect(url_for('candidate.dashboard'))

        filename = save_uploaded_file(file, current_user.id)
        if filename:
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)

            # Second pass, on the saved file: format-specific deep scans that
            # a magic-byte check alone can't catch.
            security_error = None
            if claimed_ext == 'pdf':
                is_safe, security_error = scan_pdf_for_malicious_content(file_path)
            elif claimed_ext == 'docx':
                is_safe, security_error = scan_docx_for_macros(file_path)
                if is_safe:
                    is_safe, security_error = scan_docx_for_zip_bomb(file_path)

            # Universal check regardless of file type: known malware test signature
            if not security_error:
                is_safe, security_error = scan_for_malware_signature(file_path)

            if security_error:
                try:
                    os.remove(file_path)
                except OSError:
                    pass
                log_activity(current_user.id, 'upload_rejected_security',
                             f'Rejected upload "{file.filename}": {security_error}')
                event = SecurityEvent(user_id=current_user.id, event_type='malicious_upload_blocked',
                                       severity='high', description=f'File "{file.filename}": {security_error}',
                                       ip_address=request.remote_addr)
                db.session.add(event)
                db.session.commit()
                flash(security_error, 'danger')
                return redirect(url_for('candidate.dashboard'))

            parsed_data = parse_resume(file_path, file.filename.rsplit('.', 1)[1].lower())

            # Reject forms, certificates, job descriptions etc. before any
            # resume-only scoring or saving happens.
            ok, reason = is_resume(parsed_data.get('text', ''), file.filename)
            if not ok:
                try:
                    os.remove(file_path)
                except OSError:
                    pass
                flash(reason, 'warning')
                return redirect(url_for('candidate.dashboard'))

            ats_result = calculate_ats_score(parsed_data)
            file_ext = file.filename.rsplit('.', 1)[1].lower()

            # Resume Authenticity Check -- runs independently of the ATS score.
            # ATS only checks whether the right keywords are present; this checks
            # whether the document itself is internally consistent, unedited,
            # original (not copy-pasted from another candidate), and not just
            # generic filler text.
            other_resumes = db.session.query(Resume.user_id, Resume.parsed_text).filter(Resume.user_id != current_user.id).all()
            authenticity_result = analyze_resume_authenticity(
                text=parsed_data.get('text', ''), file_path=file_path, file_type=file_ext,
                candidate_full_name=current_user.get_full_name(),
                claimed_experience_years=parsed_data.get('experience_years'),
                other_resumes=other_resumes
            )

            resume = Resume(user_id=current_user.id, filename=filename, original_filename=secure_filename(file.filename),
                file_type=file_ext, file_size=os.path.getsize(file_path),
                parsed_text=parsed_data.get('text', ''), extracted_skills=json.dumps(parsed_data.get('skills', [])),
                extracted_experience=json.dumps(parsed_data.get('experience', [])), extracted_education=json.dumps(parsed_data.get('education', [])),
                ats_score=ats_result['score'], ats_feedback=json.dumps(ats_result['feedback']),
                ai_summary=parsed_data.get('summary', ''), skill_categories=json.dumps(parsed_data.get('skill_categories', {})),
                experience_years=parsed_data.get('experience_years', 0), is_primary=True if not Resume.query.filter_by(user_id=current_user.id).first() else False,
                authenticity_score=authenticity_result['score'], authenticity_tier=authenticity_result['tier'],
                authenticity_flags=json.dumps(authenticity_result['flags']), authenticity_checked_at=datetime.utcnow())
            db.session.add(resume)
            db.session.commit()
            log_activity(current_user.id, 'resume_uploaded', f'Uploaded {file.filename}')
            create_notification(current_user.id, 'Resume Uploaded', f'Your resume has been uploaded. ATS Score: {ats_result["score"]}%', 'application', url_for('candidate.view_resume', resume_id=resume.id))
            if sig_warning:
                flash(sig_warning, 'warning')
            flash(f'Resume uploaded! ATS Score: {ats_result["score"]}% · Authenticity: {authenticity_result["tier"]}', 'success')
            return redirect(url_for('candidate.view_resume', resume_id=resume.id))
    flash('Invalid file type. Allowed: PDF, DOCX, TXT', 'danger')
    return redirect(url_for('candidate.dashboard'))

@bp.route('/resume/<int:resume_id>')
@login_required
@candidate_required
def view_resume(resume_id):
    resume = Resume.query.get_or_404(resume_id)
    if resume.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('candidate.dashboard'))
    return render_template('candidate/resume_detail.html', resume=resume)

@bp.route('/resume/<int:resume_id>/delete', methods=['POST'])
@login_required
@candidate_required
def delete_resume(resume_id):
    resume = Resume.query.get_or_404(resume_id)
    if resume.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('candidate.dashboard'))

    was_primary = resume.is_primary
    original_filename = resume.original_filename

    # Remove the stored file from disk (ignore if it's already gone).
    try:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], resume.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass

    try:
        # job_applications.resume_id is a plain foreign key (no cascade), so on
        # Postgres (Render) deleting a resume that was used in an application
        # raised IntegrityError -> 500. Keep the application, just detach it.
        JobApplication.query.filter_by(resume_id=resume.id).update(
            {JobApplication.resume_id: None}, synchronize_session=False)
        db.session.delete(resume)  # match_scores cascade via the model
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Resume delete failed for id={resume_id}: {e}')
        flash('Could not delete this resume. Please try again.', 'danger')
        return redirect(url_for('candidate.dashboard'))

    # If the deleted resume was the primary one, promote the most recently
    # uploaded remaining resume (if any) so the candidate always has a clear
    # primary resume for matching/career-fit/etc.
    if was_primary:
        next_resume = Resume.query.filter_by(user_id=current_user.id).order_by(Resume.created_at.desc()).first()
        if next_resume:
            next_resume.is_primary = True
            db.session.commit()

    log_activity(current_user.id, 'resume_deleted', f'Deleted {original_filename}')
    flash('Resume deleted.', 'success')
    return redirect(url_for('candidate.dashboard'))

@bp.route('/resume/<int:resume_id>/skills/add', methods=['POST'])
@login_required
@candidate_required
def add_resume_skill(resume_id):
    """Automated parsing can't catch every phrasing or every skill list we
    haven't thought of -- this lets a candidate correct/extend the extracted
    skill list themselves rather than being stuck with whatever the parser
    found. Recalculates the ATS score afterward so it reflects the correction."""
    resume = Resume.query.get_or_404(resume_id)
    if resume.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('candidate.dashboard'))

    new_skill = request.form.get('skill', '').strip()
    if new_skill:
        skills = resume.get_skills_list()
        if new_skill.title() not in skills and new_skill not in skills:
            skills.append(new_skill.title())
            resume.extracted_skills = json.dumps(skills)
            ats_result = calculate_ats_score({'text': resume.parsed_text or '', 'skills': skills})
            resume.ats_score = ats_result['score']
            resume.ats_feedback = json.dumps(ats_result['feedback'])
            db.session.commit()
            flash(f'Added "{new_skill.title()}" to your skills.', 'success')
        else:
            flash('That skill is already listed.', 'info')
    return redirect(url_for('candidate.view_resume', resume_id=resume_id))

@bp.route('/resume/<int:resume_id>/skills/remove', methods=['POST'])
@login_required
@candidate_required
def remove_resume_skill(resume_id):
    resume = Resume.query.get_or_404(resume_id)
    if resume.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('candidate.dashboard'))

    skill_to_remove = request.form.get('skill', '').strip()
    skills = [s for s in resume.get_skills_list() if s.lower() != skill_to_remove.lower()]
    resume.extracted_skills = json.dumps(skills)
    ats_result = calculate_ats_score({'text': resume.parsed_text or '', 'skills': skills})
    resume.ats_score = ats_result['score']
    resume.ats_feedback = json.dumps(ats_result['feedback'])
    db.session.commit()
    flash(f'Removed "{skill_to_remove}" from your skills.', 'info')
    return redirect(url_for('candidate.view_resume', resume_id=resume_id))

@bp.route('/salary-insights', methods=['GET', 'POST'])
@login_required
@candidate_required
def salary_insights():
    """AI-assisted salary estimation, personalized with the candidate's own
    resume skills/experience and (if available) their GitHub Portfolio
    Verification score -- so this isn't a generic calculator, it's using
    signals this platform already collected about them.

    With one resume: one estimate, unchanged from before. With more than
    one resume (e.g. a cybersecurity resume and a separate web-dev
    resume), the same job title/location the candidate typed is priced
    once per resume -- each using that resume's own skills and years of
    experience -- since two resumes for different roles will genuinely
    yield different estimates and shouldn't be averaged into one number.
    The template shows every resume's estimate side by side."""
    resumes = Resume.query.filter_by(user_id=current_user.id) \
        .order_by(Resume.is_primary.desc(), Resume.created_at.desc()).all()
    primary_resume = resumes[0] if resumes else None
    github_verification = GithubVerification.query.filter_by(user_id=current_user.id).first()
    history = SalaryPrediction.query.filter_by(user_id=current_user.id).order_by(SalaryPrediction.created_at.desc()).limit(5).all()

    resume_results = []  # list of {'resume': Resume|None, 'result': predict_salary() dict}
    if request.method == 'POST':
        job_title = request.form.get('job_title', '').strip()
        location = request.form.get('location', '').strip()
        manual_experience = request.form.get('experience_years', type=int)
        github_score = github_verification.portfolio_score if github_verification else None

        if job_title:
            targets = resumes if resumes else [None]
            for r in targets:
                experience_years = manual_experience if manual_experience is not None else ((r.experience_years if r else 0) or 0)
                skills = r.get_skills_list() if r else []
                res = predict_salary(job_title, location, experience_years, skills, github_score)
                resume_results.append({'resume': r, 'result': res})

                prediction = SalaryPrediction(
                    user_id=current_user.id, job_title=job_title, location=location, experience_years=experience_years,
                    predicted_min=int(res['predicted_min']), predicted_max=int(res['predicted_max']),
                    predicted_avg=int(res['predicted_avg']), confidence=res['confidence'],
                    factors=json.dumps(([f"Resume: {r.original_filename}"] if r else []) + res['factors'])
                )
                db.session.add(prediction)
            db.session.commit()
            log_activity(current_user.id, 'salary_prediction_generated', f'Predicted salary for {job_title}')
        else:
            flash('Please enter a job title.', 'warning')

    return render_template('candidate/salary_insights.html', resume_results=resume_results, primary_resume=primary_resume,
                            github_verification=github_verification, history=history)

@bp.route('/linkedin-review', methods=['GET', 'POST'])
@login_required
@candidate_required
def linkedin_review():
    """Analyzes pasted LinkedIn profile text (headline/About/experience) --
    not a live scrape or API fetch, since LinkedIn's ToS prohibits automated
    scraping and there's no public API for reading arbitrary profiles."""
    result = None
    url_only_detected = False
    headline = about_text = experience_text = ''
    skills_count = 0
    if request.method == 'POST':
        full_paste = request.form.get('full_profile_text', '').strip()
        headline = request.form.get('headline', '').strip()
        about_text = request.form.get('about_text', '').strip()
        experience_text = request.form.get('experience_text', '').strip()
        skills_count = request.form.get('skills_count', type=int) or 0

        # Catch the single most common mistake here: pasting just the
        # profile's URL instead of its actual text content. A link has zero
        # words for us to analyze -- scoring that as if it were a real
        # (very empty) profile would be actively misleading, so we stop and
        # explain instead of producing a fake-looking low score.
        if full_paste and is_url_only(full_paste) and not (headline or about_text or experience_text):
            url_only_detected = True
        else:
            # If the candidate pasted their whole profile in one go, auto-detect
            # the sections from it -- any individual field they also typed in
            # manually takes precedence over the auto-detected value.
            if full_paste:
                parsed = parse_full_profile_text(full_paste)
                headline = headline or parsed['headline']
                about_text = about_text or parsed['about_text']
                experience_text = experience_text or parsed['experience_text']
                skills_count = skills_count or parsed['skills_count']

            result = audit_linkedin_profile(headline, about_text, experience_text, skills_count)
            audit = LinkedInAudit(
                user_id=current_user.id, headline=headline, about_text=about_text, experience_text=experience_text,
                skills_count=skills_count, score=result['score'], impression=result['impression'],
                quick_wins=json.dumps(result['quick_wins'])
            )
            db.session.add(audit)
            db.session.commit()
            log_activity(current_user.id, 'linkedin_audit_generated', f'LinkedIn profile audit scored {result["score"]}/100')

    last_audit = LinkedInAudit.query.filter_by(user_id=current_user.id).order_by(LinkedInAudit.created_at.desc()).first()
    detected = None
    if request.method == 'POST' and result is not None:
        detected = {'headline': headline, 'about_text': about_text, 'experience_text': experience_text, 'skills_count': skills_count}
    return render_template('candidate/linkedin_review.html', result=result, last_audit=last_audit, detected=detected,
                            url_only_detected=url_only_detected)

@bp.route('/career-fit')
@login_required
@candidate_required
def career_fit():
    """Ranks a curated set of common role categories by skill-overlap.
    With one resume this runs against that resume alone (unchanged
    single-column view). With more than one -- e.g. a cybersecurity
    resume and a separate web-dev resume -- it runs the identical
    analysis independently per resume, never blended into one averaged
    score, and the template renders every resume's results side by
    side."""
    resumes = Resume.query.filter_by(user_id=current_user.id) \
        .order_by(Resume.is_primary.desc(), Resume.created_at.desc()).all()

    resume_results = []
    for r in resumes:
        skills = r.get_skills_list()
        if skills:
            resume_results.append({'resume': r, 'results': compute_career_fit(skills)})

    primary_resume = resumes[0] if resumes else None
    return render_template('candidate/career_fit.html', resume_results=resume_results, primary_resume=primary_resume)

@bp.route('/build-resume', methods=['GET', 'POST'])
@login_required
@candidate_required
def build_resume():
    if request.method == 'POST':
        data = {'full_name': request.form.get('full_name'), 'email': request.form.get('email'), 'phone': request.form.get('phone'),
            'location': request.form.get('location'), 'summary': request.form.get('summary'),
            'experience': request.form.getlist('experience[]'), 'education': request.form.getlist('education[]'),
            'skills': request.form.get('skills', '').split(','), 'certifications': request.form.getlist('certifications[]')}
        resume_text = f"{data['full_name']}\n{data['email']} | {data['phone']} | {data['location']}\n\nPROFESSIONAL SUMMARY\n{data['summary']}\n\nSKILLS\n{', '.join(data['skills'])}\n\nEXPERIENCE\n"
        for exp in data['experience']:
            resume_text += f"\n{exp}\n"
        resume_text += "\nEDUCATION\n"
        for edu in data['education']:
            resume_text += f"\n{edu}\n"
        filename = f"resume_{current_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        with open(file_path, 'w') as f:
            f.write(resume_text)
        parsed_data = parse_resume(file_path, 'txt')
        ats_result = calculate_ats_score(parsed_data)
        # Bug fix (Aug 2026): this used to hardcode is_primary=False no
        # matter what, even for a candidate's very first resume ever. That
        # left them with a resume that's never flagged primary in the
        # database, which the dashboard's ranking query silently assumed
        # couldn't happen -- it crashed with "ValueError: X is not in
        # list" because it looks up the primary resume's score inside a
        # query filtered to Resume.is_primary == True, and this resume was
        # never in that set. upload_resume() already gets this right
        # (is_primary=True only for a user's first resume); mirroring that
        # same rule here.
        is_first_resume = not Resume.query.filter_by(user_id=current_user.id).first()
        resume = Resume(user_id=current_user.id, filename=filename, original_filename='built_resume.txt', file_type='txt',
            file_size=os.path.getsize(file_path), parsed_text=resume_text, extracted_skills=json.dumps(parsed_data.get('skills', [])),
            ats_score=ats_result['score'], ats_feedback=json.dumps(ats_result['feedback']), is_primary=is_first_resume)
        db.session.add(resume)
        db.session.commit()
        flash('Resume built successfully!', 'success')
        return redirect(url_for('candidate.view_resume', resume_id=resume.id))
    return render_template('candidate/build_resume.html')

@bp.route('/jobs')
@login_required
@candidate_required
def browse_jobs():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    location = request.args.get('location', '')
    job_type = request.args.get('job_type', '')
    query = Job.query.filter_by(status='active')
    if search:
        query = query.filter(Job.title.contains(search) | Job.description.contains(search))
    if location:
        query = query.filter(Job.location.contains(location))
    if job_type:
        query = query.filter_by(job_type=job_type)
    jobs = query.order_by(Job.posted_at.desc()).paginate(page=page, per_page=10, error_out=False)
    return render_template('candidate/jobs.html', jobs=jobs, search=search, location=location, job_type=job_type)

@bp.route('/job/<int:job_id>')
@login_required
@candidate_required
def view_job(job_id):
    job = Job.query.get_or_404(job_id)
    job.view_count += 1
    db.session.commit()
    existing_application = JobApplication.query.filter_by(candidate_id=current_user.id, job_id=job_id).first()
    match_score = None
    primary_resume = Resume.query.filter_by(user_id=current_user.id, is_primary=True).first()
    if primary_resume:
        match_score = MatchScore.query.filter_by(resume_id=primary_resume.id, job_id=job_id).first()
    resumes = Resume.query.filter_by(user_id=current_user.id).order_by(Resume.created_at.desc()).all()
    return render_template('candidate/job_detail.html', job=job, existing_application=existing_application, match_score=match_score, resumes=resumes)

@bp.route('/job/<int:job_id>/cover-letter')
@login_required
@candidate_required
def generate_job_cover_letter(job_id):
    """Template-based cover letter draft, personalized with the candidate's
    real matched skills for this specific job -- not a call to an external
    LLM. Deterministic and free to run as many times as needed."""
    job = Job.query.get_or_404(job_id)
    primary_resume = Resume.query.filter_by(user_id=current_user.id, is_primary=True).first()
    match_score = None
    if primary_resume:
        match_score = MatchScore.query.filter_by(resume_id=primary_resume.id, job_id=job_id).first()

    matched_skills = match_score.get_matching_skills_list() if match_score else (primary_resume.get_skills_list()[:5] if primary_resume else [])
    company_name = job.recruiter.company_name if job.recruiter else None

    letter = generate_cover_letter(
        candidate_name=current_user.get_full_name(), job_title=job.title, company_name=company_name,
        matched_skills=matched_skills, years_experience=primary_resume.experience_years if primary_resume else None
    )
    log_activity(current_user.id, 'cover_letter_generated', f'Generated cover letter for {job.title}')
    return render_template('candidate/cover_letter.html', job=job, letter=letter)

@bp.route('/job/<int:job_id>/interview-prep')
@login_required
@candidate_required
def job_interview_prep(job_id):
    """Rule-based practice question set drawn from a curated bank keyed by
    this job's required skills -- not a live AI interviewer."""
    job = Job.query.get_or_404(job_id)
    questions = generate_interview_questions(job.title, job.get_required_skills_list())
    log_activity(current_user.id, 'interview_prep_generated', f'Generated interview prep for {job.title}')
    return render_template('candidate/interview_prep.html', job=job, questions=questions)

@bp.route('/interview-prep', methods=['GET', 'POST'])
@login_required
@candidate_required
def interview_prep():
    """Standalone version, not tied to a specific job posting -- uses the
    candidate's primary resume skills by default, or a manually entered
    role/skill list."""
    questions = None
    job_title = ''
    if request.method == 'POST':
        job_title = request.form.get('job_title', '').strip()
        skills_input = request.form.get('skills', '').strip()
        if skills_input:
            skills = [s.strip() for s in skills_input.split(',') if s.strip()]
        else:
            primary_resume = Resume.query.filter_by(user_id=current_user.id, is_primary=True).first()
            skills = primary_resume.get_skills_list() if primary_resume else []
        if job_title:
            questions = generate_interview_questions(job_title, skills)
            log_activity(current_user.id, 'interview_prep_generated', f'Generated interview prep for {job_title}')
        else:
            flash('Please enter a job title.', 'warning')

    primary_resume = Resume.query.filter_by(user_id=current_user.id, is_primary=True).first()
    return render_template('candidate/interview_prep_standalone.html', questions=questions, job_title=job_title, primary_resume=primary_resume)

@bp.route('/apply-job/<int:job_id>', methods=['POST'])
@login_required
@candidate_required
def apply_job(job_id):
    job = Job.query.get_or_404(job_id)
    existing = JobApplication.query.filter_by(candidate_id=current_user.id, job_id=job_id).first()
    if existing:
        flash('You have already applied for this job', 'warning')
        return redirect(url_for('candidate.view_job', job_id=job_id))
    cover_letter = request.form.get('cover_letter', '')
    resume_id = request.form.get('resume_id')
    application = JobApplication(candidate_id=current_user.id, job_id=job_id, resume_id=resume_id, cover_letter=cover_letter, status='pending')
    job.application_count += 1
    db.session.add(application)
    db.session.commit()
    log_activity(current_user.id, 'job_applied', f'Applied to {job.title}')
    create_notification(current_user.id, 'Application Submitted', f'Your application for "{job.title}" has been submitted.', 'application', url_for('candidate.view_job', job_id=job_id))
    create_notification(job.recruiter_id, 'New Application', f'{current_user.get_full_name()} applied for "{job.title}"', 'application', url_for('recruiter.view_applications', job_id=job_id))
    flash('Application submitted successfully!', 'success')
    return redirect(url_for('candidate.view_job', job_id=job_id))

@bp.route('/match-job/<int:job_id>')
@login_required
@candidate_required
def match_job(job_id):
    job = Job.query.get_or_404(job_id)
    primary_resume = Resume.query.filter_by(user_id=current_user.id, is_primary=True).first()
    if not primary_resume:
        flash('Please upload a resume first to get AI match scores', 'warning')
        return redirect(url_for('candidate.dashboard'))
    match_result = match_resume_to_job(primary_resume, job)
    match_score = MatchScore.query.filter_by(resume_id=primary_resume.id, job_id=job_id).first()
    if not match_score:
        match_score = MatchScore(resume_id=primary_resume.id, job_id=job_id)
        db.session.add(match_score)
    match_score.overall_score = match_result['overall_score']
    match_score.semantic_score = match_result['semantic_score']
    match_score.skill_score = match_result['skill_score']
    match_score.experience_score = match_result['experience_score']
    match_score.ontology_score = match_result.get('ontology_score')
    match_score.ml_confidence = match_result.get('ml_confidence')
    match_score.matching_skills = json.dumps(match_result['matching_skills'])
    match_score.missing_skills = json.dumps(match_result['missing_skills'])
    match_score.recommendation = match_result['recommendation']
    match_score.ai_feedback = match_result['feedback']
    match_score.explanation_data = json.dumps({
        'reasons': match_result.get('explanation_reasons', []),
        'counterfactuals': match_result.get('counterfactuals', []),
        'ontology_matches': match_result.get('ontology_matches', []),
    })
    db.session.commit()
    for gap in match_result['skill_gaps']:
        skill_gap = SkillGap(match_score_id=match_score.id, skill_name=gap['skill'], importance=gap['importance'],
            learning_resources=json.dumps(gap['resources']), estimated_time=gap['estimated_time'])
        db.session.add(skill_gap)
    db.session.commit()
    log_activity(current_user.id, 'job_matched', f'Matched with {job.title}: {match_result["overall_score"]}%')
    return render_template('candidate/match_result.html', match_score=match_score, job=job)

@bp.route('/career-roadmap', methods=['GET', 'POST'])
@login_required
@candidate_required
def career_roadmap():
    if request.method == 'POST':
        target_role = request.form.get('target_role', '').strip()
        target_industry = request.form.get('target_industry', '').strip()
        if not target_role:
            flash('Please enter a target role', 'danger')
            return redirect(url_for('candidate.career_roadmap'))
        primary_resume = Resume.query.filter_by(user_id=current_user.id, is_primary=True).first()
        current_skills = primary_resume.get_skills_list() if primary_resume else []
        roadmap_data = generate_career_roadmap(target_role, target_industry, current_skills)
        roadmap = CareerRoadmap(user_id=current_user.id, target_role=target_role, target_industry=target_industry,
            readiness_score=roadmap_data['readiness_score'], estimated_months=roadmap_data['estimated_months'],
            milestones=json.dumps(roadmap_data['milestones']), learning_paths=json.dumps(roadmap_data['learning_paths']),
            skill_requirements=json.dumps(roadmap_data['skill_requirements']), ai_analysis=roadmap_data['analysis'],
            market_demand=roadmap_data['market_demand'], salary_range=roadmap_data['salary_range'])
        db.session.add(roadmap)
        db.session.commit()
        log_activity(current_user.id, 'roadmap_created', f'Created roadmap for {target_role}')
        flash(f'Career roadmap for "{target_role}" created!', 'success')
        return redirect(url_for('candidate.view_roadmap', roadmap_id=roadmap.id))
    roadmaps = CareerRoadmap.query.filter_by(user_id=current_user.id).order_by(CareerRoadmap.created_at.desc()).all()
    return render_template('candidate/career_roadmap.html', roadmaps=roadmaps)

@bp.route('/roadmap/<int:roadmap_id>')
@login_required
@candidate_required
def view_roadmap(roadmap_id):
    roadmap = CareerRoadmap.query.get_or_404(roadmap_id)
    if roadmap.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('candidate.career_roadmap'))
    return render_template('candidate/roadmap_detail.html', roadmap=roadmap)

@bp.route('/skill-tests')
@login_required
@candidate_required
def skill_tests():
    tests = SkillTest.query.filter_by(is_active=True).all()
    user_results = SkillTestResult.query.filter_by(user_id=current_user.id).all()
    return render_template('candidate/skill_tests.html', tests=tests, user_results=user_results)

@bp.route('/take-test/<int:test_id>', methods=['GET', 'POST'])
@login_required
@candidate_required
def take_test(test_id):
    test = SkillTest.query.get_or_404(test_id)
    questions = json.loads(test.questions) if test.questions else []
    if request.method == 'POST':
        answers = {}
        correct = 0
        for i, q in enumerate(questions):
            answer = request.form.get(f'question_{i}')
            answers[str(i)] = answer
            if answer == q.get('correct_answer'):
                correct += 1
        total = len(questions)
        score = int((correct / total) * 100) if total > 0 else 0
        is_passed = score >= test.passing_score
        result = SkillTestResult(test_id=test_id, user_id=current_user.id, score=score, total_questions=total,
            correct_answers=correct, answers=json.dumps(answers), is_passed=is_passed)
        db.session.add(result)
        db.session.commit()
        flash(f'Test completed! Score: {score}% ({"Passed" if is_passed else "Failed"})', 'success' if is_passed else 'warning')
        return redirect(url_for('candidate.skill_tests'))
    return render_template('candidate/take_test.html', test=test, questions=questions)

@bp.route('/applications')
@login_required
@candidate_required
def my_applications():
    applications = JobApplication.query.filter_by(candidate_id=current_user.id).order_by(JobApplication.applied_at.desc()).all()
    return render_template('candidate/applications.html', applications=applications)

@bp.route('/application/<int:app_id>/feedback')
@login_required
@candidate_required
def application_feedback(app_id):
    """Answers the question every rejected candidate actually has: 'why?'
    Instead of a bare status change, this combines three things in one
    place -- the recruiter's stated reason (if given), an automatically
    computed skill gap versus that specific job's requirements, and a
    content-based recommendation of other open roles that are a better
    fit for the skills the candidate already has."""
    application = JobApplication.query.get_or_404(app_id)
    if application.candidate_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('candidate.my_applications'))

    job = Job.query.get(application.job_id)
    resume = Resume.query.get(application.resume_id) if application.resume_id else Resume.query.filter_by(user_id=current_user.id, is_primary=True).first()
    candidate_skills = set(s.lower() for s in (resume.get_skills_list() if resume else []))
    required_skills = job.get_required_skills_list()

    matching_skills = [s for s in required_skills if s.lower() in candidate_skills]
    missing_skills = [s for s in required_skills if s.lower() not in candidate_skills]
    match_pct = round(len(matching_skills) / len(required_skills) * 100) if required_skills else 0

    # Content-based recommendation: score every other open job by how much
    # its required-skill set overlaps with skills the candidate actually
    # has, and surface the best-fitting ones as alternatives.
    other_jobs = Job.query.filter(Job.status == 'active', Job.id != job.id).all()
    scored_jobs = []
    for other in other_jobs:
        other_required = set(s.lower() for s in other.get_required_skills_list())
        if not other_required:
            continue
        overlap = len(candidate_skills & other_required)
        if overlap == 0:
            continue
        score = round(overlap / len(other_required) * 100)
        scored_jobs.append((score, other))
    scored_jobs.sort(key=lambda x: x[0], reverse=True)
    suggested_jobs = scored_jobs[:3]

    return render_template('candidate/application_feedback.html', application=application, job=job,
                            matching_skills=matching_skills, missing_skills=missing_skills,
                            match_pct=match_pct, suggested_jobs=suggested_jobs)

@bp.route('/notifications')
@login_required
@candidate_required
def notifications():
    page = request.args.get('page', 1, type=int)
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('candidate/notifications.html', notifications=notifications)

@bp.route('/mark-notification-read/<int:notification_id>', methods=['POST'])
@login_required
@candidate_required
def mark_notification_read(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    if notification.user_id == current_user.id:
        notification.mark_as_read()
    return redirect(url_for('candidate.notifications'))


# ---------------------------------------------------------------------------
# GitHub Portfolio Verification
# ---------------------------------------------------------------------------

@bp.route('/github-verify', methods=['GET', 'POST'])
@login_required
@candidate_required
def github_verify():
    if request.method == 'POST':
        username = request.form.get('github_username', '').strip()
        if not username:
            flash('Please enter a GitHub username.', 'danger')
            return redirect(url_for('candidate.github_verify'))

        primary_resume = Resume.query.filter_by(user_id=current_user.id, is_primary=True).first()
        resume_skills = primary_resume.get_skills_list() if primary_resume else []

        result = verify_github_portfolio(username, resume_skills)
        if result.get('error'):
            flash(result['error'], 'danger')
            return redirect(url_for('candidate.github_verify'))

        verification = GithubVerification.query.filter_by(user_id=current_user.id).first()
        if not verification:
            verification = GithubVerification(user_id=current_user.id)
            db.session.add(verification)

        a = result['analytics']
        verification.github_username = result['username']
        verification.profile_url = result['profile_url']
        verification.avatar_url = result['avatar_url']
        verification.public_repos = a['public_repos']
        verification.followers = a['followers']
        verification.total_stars = a['total_stars']
        verification.portfolio_score = result['score']
        verification.portfolio_tier = result['tier']
        verification.top_languages = json.dumps(a['top_languages'])
        verification.verified_skills = json.dumps(a['verified_skills'])
        verification.confirmed_skills = json.dumps(result['skill_comparison']['confirmed_skills'])
        verification.unconfirmed_skills = json.dumps(result['skill_comparison']['unconfirmed_skills'])
        verification.authenticity_rate = result['skill_comparison']['authenticity_rate']
        verification.raw_analytics = json.dumps(a)
        verification.verified_at = datetime.utcnow()
        db.session.commit()

        log_activity(current_user.id, 'github_verified', f"Verified GitHub portfolio: {result['username']} (score {result['score']})")
        create_notification(current_user.id, 'GitHub Portfolio Verified',
                             f"Your portfolio score is {result['score']}/100 ({result['tier']}).",
                             'general', url_for('candidate.github_verify'))
        flash(f"GitHub portfolio verified! Score: {result['score']}/100 ({result['tier']})", 'success')
        return redirect(url_for('candidate.github_verify'))

    verification = GithubVerification.query.filter_by(user_id=current_user.id).first()
    top_repos = []
    framework_skills_detected = []
    if verification and verification.raw_analytics:
        try:
            raw = json.loads(verification.raw_analytics)
            top_repos = raw.get('top_repos', [])
            framework_skills_detected = raw.get('framework_skills_detected', [])
        except Exception:
            top_repos = []
    return render_template('candidate/github_verify.html', verification=verification, top_repos=top_repos,
                            framework_skills_detected=framework_skills_detected)


# ---------------------------------------------------------------------------
# PDF Report Generator
# ---------------------------------------------------------------------------

@bp.route('/resume/<int:resume_id>/report')
@login_required
@candidate_required
def download_resume_report(resume_id):
    resume = Resume.query.get_or_404(resume_id)
    if resume.user_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('candidate.dashboard'))

    verification = GithubVerification.query.filter_by(user_id=current_user.id).first()
    github_data = None
    if verification:
        github_data = {
            'username': verification.github_username,
            'score': verification.portfolio_score,
            'tier': verification.portfolio_tier,
            'analytics': {
                'public_repos': verification.public_repos,
                'followers': verification.followers,
                'total_stars': verification.total_stars,
                'verified_skills': verification.get_verified_skills(),
            },
            'skill_comparison': {'authenticity_rate': verification.authenticity_rate},
        }

    buffer = generate_candidate_report(current_user, resume, github_data=github_data)
    log_activity(current_user.id, 'report_downloaded', f'Downloaded PDF report for resume {resume.original_filename}')
    filename = f"RecruitSmart_Report_{current_user.get_full_name().replace(' ', '_')}.pdf"
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)


@bp.route('/match-job/<int:job_id>/report')
@login_required
@candidate_required
def download_match_report(job_id):
    job = Job.query.get_or_404(job_id)
    primary_resume = Resume.query.filter_by(user_id=current_user.id, is_primary=True).first()
    if not primary_resume:
        flash('Please upload a resume first.', 'warning')
        return redirect(url_for('candidate.dashboard'))
    match_score = MatchScore.query.filter_by(resume_id=primary_resume.id, job_id=job_id).first()
    if not match_score:
        flash('Please run the AI match first.', 'warning')
        return redirect(url_for('candidate.view_job', job_id=job_id))

    verification = GithubVerification.query.filter_by(user_id=current_user.id).first()
    github_data = None
    if verification:
        github_data = {
            'username': verification.github_username,
            'score': verification.portfolio_score,
            'tier': verification.portfolio_tier,
            'analytics': {
                'public_repos': verification.public_repos,
                'followers': verification.followers,
                'total_stars': verification.total_stars,
                'verified_skills': verification.get_verified_skills(),
            },
            'skill_comparison': {'authenticity_rate': verification.authenticity_rate},
        }

    buffer = generate_candidate_report(current_user, primary_resume, match_score=match_score, job=job, github_data=github_data)
    log_activity(current_user.id, 'match_report_downloaded', f'Downloaded match report for {job.title}')
    filename = f"RecruitSmart_MatchReport_{job.title.replace(' ', '_')}.pdf"
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)
