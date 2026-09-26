"""
Help Assistant Knowledge Base
------------------------------
Powers the in-app chat/search widget. This is intentionally NOT a call out to
a third-party LLM API -- it is a small, self-contained keyword-matching
search over a curated FAQ set. That is a deliberate security choice as much
as a simplicity one:

  * No user text is ever sent to an external service, logged with a prompt,
    or used to construct a command/query -- it is only ever compared,
    case-insensitively, against a fixed in-memory list of keywords.
  * There is nothing here an attacker can "inject" into, because the search
    function never concatenates user input into HTML, SQL, or a shell
    command -- see search_faq() below.

Each entry has:
  - id: stable identifier (used client-side for analytics-free dedup only)
  - keywords: words/phrases that should surface this answer
  - question: a representative question, shown as a suggestion chip
  - answer: plain-text answer (rendered with textContent on the client,
    never innerHTML, so it can never be used for stored/reflected XSS)
  - link: (endpoint_name, label) tuple, restricted to a fixed allow-list of
    named Flask endpoints -- never a raw user-suppliable URL, which rules out
    open-redirect style abuse of the widget.
"""
import re
from difflib import SequenceMatcher

FAQ_ENTRIES = [
    {
        "id": "upload-resume",
        "keywords": ["upload resume", "add resume", "attach resume", "cv", "resume", "parse resume"],
        "question": "How do I upload my resume?",
        "answer": "Go to your Candidate Dashboard and click \"Build/Upload Resume.\" We accept PDF, DOCX, and TXT files up to 5MB. Every upload is scanned for a valid file signature and stripped of any embedded scripts before it's stored -- renaming a file's extension will not bypass this check.",
        "link": ("candidate.build_resume", "Go to Resume Builder"),
    },
    {
        "id": "match-score",
        "keywords": ["match score", "how is match calculated", "ai matching", "job match", "career fit", "compatibility"],
        "question": "How is my job match score calculated?",
        "answer": "Our matching engine compares the skills, experience, and keywords extracted from your resume against each job's required and preferred skills, producing an overall compatibility score along with a skill-gap breakdown so you know exactly what to work on.",
        "link": ("candidate.career_fit", "View Career Fit"),
    },
    {
        "id": "browse-jobs",
        "keywords": ["browse jobs", "find jobs", "search jobs", "apply job", "job listing", "open positions"],
        "question": "How do I browse or apply to jobs?",
        "answer": "Use \"Browse Jobs\" from your dashboard to filter by location, remote status, and job type. Open any listing and click Apply -- your most recent resume and match score are attached automatically.",
        "link": ("candidate.browse_jobs", "Browse Jobs"),
    },
    {
        "id": "interview-prep",
        "keywords": ["interview prep", "interview questions", "practice interview", "mock interview"],
        "question": "Does RecruitSmart help with interview prep?",
        "answer": "Yes -- the Interview Prep tool generates likely questions tailored to a specific job posting, based on the required skills and seniority level, so you can practice before the real thing.",
        "link": ("candidate.interview_prep", "Open Interview Prep"),
    },
    {
        "id": "career-roadmap",
        "keywords": ["career roadmap", "skill roadmap", "learning path", "career growth", "upskilling"],
        "question": "What is the Career Roadmap feature?",
        "answer": "Career Roadmap looks at the gap between your current skills and your target roles, then lays out a step-by-step learning path to close it, with milestones you can track over time.",
        "link": ("candidate.career_roadmap", "View Career Roadmap"),
    },
    {
        "id": "salary-insights",
        "keywords": ["salary", "pay range", "compensation", "how much does it pay"],
        "question": "Can I see expected salary ranges?",
        "answer": "Salary Insights estimates a realistic compensation range for roles matching your profile, based on title, location, and experience level, so you can negotiate with real data.",
        "link": ("candidate.salary_insights", "View Salary Insights"),
    },
    {
        "id": "post-job",
        "keywords": ["post a job", "create job listing", "hire", "recruiter post job", "new job posting"],
        "question": "How do I post a job as a recruiter?",
        "answer": "From the Recruiter Dashboard, click \"Post Job\" and fill in the role details, required/preferred skills, and salary band. New recruiter accounts are manually verified first, which keeps candidate data safe from fake employer accounts.",
        "link": ("recruiter.post_job", "Post a Job"),
    },
    {
        "id": "view-candidates",
        "keywords": ["view candidates", "find talent", "candidate pool", "ranked candidates"],
        "question": "How do recruiters find matching candidates?",
        "answer": "The Candidates view ranks applicants for each job by match score, so you can quickly see who is closest to a strong fit before you review resumes in detail. Open one of your job postings from the list below, then click \"View Candidates.\"",
        "link": ("recruiter.my_jobs", "View My Job Postings"),
    },
    {
        "id": "account-password",
        "keywords": ["reset password", "forgot password", "change password", "can't log in", "cannot login"],
        "question": "How do I reset my password?",
        "answer": "Click \"Forgot password\" on the sign-in page and we'll email you a secure, single-use reset link. For your own safety, never reuse a password from another site for your RecruitSmart account.",
        "link": ("auth.forgot_password", "Reset Password"),
    },
    {
        "id": "2fa",
        "keywords": ["2fa", "two factor", "two-factor", "authenticator", "otp", "mfa", "secure my account"],
        "question": "How do I turn on two-factor authentication?",
        "answer": "Open Profile > Security and enable Two-Factor Authentication. You'll scan a QR code with an authenticator app (Google Authenticator, Authy, etc.); after that, sign-in requires your password plus a rotating 6-digit code, so a leaked password alone can't get into your account.",
        "link": ("auth.profile", "Go to Profile & Security"),
    },
    {
        "id": "phishing",
        "keywords": ["phishing", "suspicious email", "scam", "fake email", "is this email real", "spoof"],
        "question": "How do I spot a phishing email pretending to be RecruitSmart?",
        "answer": "We will never email you asking for your password, 2FA code, or payment to \"unlock\" your account. Genuine RecruitSmart links always point to this domain -- hover over any link before clicking, and report anything suspicious via Contact Us.",
        "link": ("main.contact", "Report to Support"),
    },
    {
        "id": "data-privacy",
        "keywords": ["is my data safe", "data privacy", "who sees my resume", "gdpr", "data protection", "privacy"],
        "question": "Is my data secure and who can see it?",
        "answer": "Your resume is only visible to recruiters for jobs you actively apply to, or that a verified recruiter searches for a match against -- never sold or shared with third parties. All traffic runs over HTTPS in production, passwords are hashed (never stored in plain text), and every form submission is protected against cross-site request forgery.",
        "link": ("main.privacy", "Read Privacy Policy"),
    },
    {
        "id": "file-upload-safety",
        "keywords": ["safe to upload", "virus scan", "malware", "file security", "upload safe"],
        "question": "Is it safe to upload my resume file?",
        "answer": "Every uploaded file is checked against its real file signature (not just its extension), and rejected outright if it's actually an executable, script, or a PDF carrying embedded JavaScript/auto-launch actions -- a common malware delivery trick.",
        "link": None,
    },
    {
        "id": "rate-limit",
        "keywords": ["too many requests", "rate limit", "429", "blocked", "locked out"],
        "question": "Why am I seeing a \"too many requests\" error?",
        "answer": "To stop automated abuse (credential stuffing, scraping), sensitive actions like login and password reset are rate-limited per IP address. If you hit this, wait a minute and try again -- it clears automatically and does not affect your account.",
        "link": None,
    },
    {
        "id": "contact-support",
        "keywords": ["contact support", "talk to a human", "help me", "get help", "customer service"],
        "question": "How do I contact a real person for support?",
        "answer": "Use the Contact page and describe your issue -- our team typically responds within one business day. For account-security concerns specifically, mention that in the subject line so it gets prioritized.",
        "link": ("main.contact", "Contact Support"),
    },
    {
        "id": "security-center",
        "keywords": ["security center", "admin security", "audit log", "security dashboard"],
        "question": "What is the Security Center? (Admins)",
        "answer": "Admins can review platform-wide security signals -- rate-limit hits, failed logins, flagged uploads, and recruiter verification status -- from the Security Center in the admin dashboard.",
        "link": ("admin.security_center", "Open Security Center"),
    },
]

# Generic greetings/small talk handled without a keyword match, so the bot
# doesn't feel broken on "hi" or "thanks".
_GREETINGS = {"hi", "hello", "hey", "yo", "hola"}
_THANKS = {"thanks", "thank you", "thx", "ty", "appreciate it"}


def _normalize(text):
    """Lowercase and strip to bare words/spaces only. This is the ONLY
    processing ever applied to user input -- it is never interpolated into
    a template, query, or shell command, so there is no injection surface
    here regardless of what a user types."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def search_faq(raw_query, limit=4):
    """Keyword + fuzzy match over FAQ_ENTRIES. Returns a list of plain dicts
    safe to json-serialize directly -- every string in the response comes
    from FAQ_ENTRIES (developer-authored, fixed at deploy time), never from
    raw_query itself, so there is no way for a search to "answer back" with
    attacker-controlled text."""
    query = _normalize(raw_query)[:200]  # hard cap regardless of caller

    if not query:
        return []

    if query in _GREETINGS:
        return [{
            "id": "greeting",
            "question": None,
            "answer": "Hi! Ask me anything about using RecruitSmart -- resumes, job matching, "
                      "your account, or account security -- and I'll point you in the right direction.",
            "link": None,
        }]
    if query in _THANKS:
        return [{
            "id": "thanks",
            "question": None,
            "answer": "You're welcome! Anything else I can help you find?",
            "link": None,
        }]

    query_words = set(query.split())
    scored = []
    for entry in FAQ_ENTRIES:
        best = 0.0
        for kw in entry["keywords"]:
            kw_norm = _normalize(kw)
            if kw_norm in query or query in kw_norm:
                best = max(best, 1.0)
                continue
            kw_words = set(kw_norm.split())
            overlap = len(query_words & kw_words)
            if overlap:
                best = max(best, 0.5 + 0.15 * overlap)
                continue
            ratio = SequenceMatcher(None, kw_norm, query).ratio()
            if ratio > 0.6:
                best = max(best, ratio * 0.6)
        if best > 0.25:
            scored.append((best, entry))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    results = []
    for score, entry in scored[:limit]:
        results.append({
            "id": entry["id"],
            "question": entry["question"],
            "answer": entry["answer"],
            "link": entry["link"],
        })
    return results


# Fixed allow-list mapping endpoint names -> whether they exist, checked at
# call time via Flask's url_for + a try/except in the API layer. Kept here
# so the knowledge base is the single source of truth for which endpoints
# the widget is allowed to link to.
ALLOWED_LINK_ENDPOINTS = {entry["link"][0] for entry in FAQ_ENTRIES if entry["link"]}
