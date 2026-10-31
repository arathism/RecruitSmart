from flask import jsonify, request, url_for
from flask_login import login_required, current_user
from app import limiter
from app.api import bp
from app.models import Job, User, Resume, MatchScore, JobApplication, Notification
from app.utils.help_bot import search_faq, ALLOWED_LINK_ENDPOINTS

@bp.route('/jobs')
def api_jobs():
    page = request.args.get('page', 1, type=int)
    jobs = Job.query.filter_by(status='active').paginate(page=page, per_page=20, error_out=False)
    return jsonify({
        'jobs': [{
            'id': j.id,
            'title': j.title,
            'location': j.location,
            'is_remote': j.is_remote,
            'job_type': j.job_type,
            'salary': j.get_salary_display(),
            'posted_at': j.posted_at.isoformat() if j.posted_at else None
        } for j in jobs.items],
        'total': jobs.total,
        'pages': jobs.pages,
        'current_page': jobs.page
    })

@bp.route('/job/<int:job_id>')
def api_job(job_id):
    job = Job.query.get_or_404(job_id)
    return jsonify({
        'id': job.id,
        'title': job.title,
        'description': job.description,
        'requirements': job.requirements,
        'location': job.location,
        'is_remote': job.is_remote,
        'job_type': job.job_type,
        'salary': job.get_salary_display(),
        'required_skills': job.get_required_skills_list(),
        'preferred_skills': job.get_preferred_skills_list(),
        'posted_at': job.posted_at.isoformat() if job.posted_at else None
    })

@bp.route('/stats')
def api_stats():
    return jsonify({
        'total_users': User.query.count(),
        'total_jobs': Job.query.count(),
        'total_applications': JobApplication.query.count(),
        'total_resumes': Resume.query.count()
    })

@bp.route('/notifications')
@login_required
def api_notifications():
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).all()
    return jsonify([{
        'id': n.id,
        'title': n.title,
        'message': n.message,
        'type': n.notification_type,
        'created_at': n.created_at.isoformat() if n.created_at else None
    } for n in notifications])


@bp.route('/help/search', methods=['POST'])
@limiter.limit('20 per minute')
def api_help_search():
    """Backs the site-wide help/search chat widget.

    Security notes (this endpoint is reachable while logged out, so it gets
    the same scrutiny as login/register):
      - Rate-limited per IP (Flask-Limiter) to stop it being used to hammer
        the server or scrape the whole FAQ set instantly.
      - CSRF-protected like every other POST route (Flask-WTF checks the
        X-CSRFToken header automatically; no per-route change needed).
      - The request body is read defensively: a non-JSON or oversized body
        is rejected rather than crashing the endpoint.
      - The user's query string is only ever used for a case-insensitive
        keyword comparison against a fixed, developer-authored FAQ list
        (see app/utils/help_bot.py) -- it is never echoed back, stored,
        rendered as HTML, or used to build a URL/query, so there is no
        reflected-XSS or injection surface here.
      - Any "link" returned is resolved through url_for() against a fixed
        allow-list of endpoint names baked into help_bot.py -- never a raw
        URL -- which rules out using this endpoint for open-redirect abuse.
    """
    data = request.get_json(silent=True) or {}
    query = data.get('query', '')

    if not isinstance(query, str):
        return jsonify({'error': 'invalid_query'}), 400
    if len(query) > 300:
        return jsonify({'error': 'query_too_long'}), 400

    results = search_faq(query)

    payload = []
    for r in results:
        link_url, link_label = None, None
        if r.get('link') and r['link'][0] in ALLOWED_LINK_ENDPOINTS:
            endpoint, label = r['link']
            try:
                link_url = url_for(endpoint)
                link_label = label
            except Exception:
                link_url = None
        payload.append({
            'id': r['id'],
            'question': r['question'],
            'answer': r['answer'],
            'link_url': link_url,
            'link_label': link_label,
        })

    return jsonify({'results': payload, 'query_echo_length': len(query.strip())})
