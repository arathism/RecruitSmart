# 🎯 Recruit Smart

> **AI-Powered Recruitment Platform** — Smart resume parsing, intelligent job matching, verified GitHub portfolios, and personalized career roadmaps.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-green.svg)](https://flask.palletsprojects.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 🌐 Live Demo

**[[https://recruitsmart-ai.onrender.com](https://recruitsmart-ai.onrender.com)]**

> Hosted on Render's free tier — the instance spins down after periods of inactivity, so the first request after a while may take 30–50 seconds to wake up.

## 🏆 What Makes RecruitSmart Different (Publication Highlights)

Most academic recruitment-system projects stop at "parse a resume, compute a keyword-match score." RecruitSmart goes further with two features designed specifically to stand out in a crowded field of similar student projects:

### 🔐 1. GitHub Portfolio Verification (Anti-Exaggeration Engine)

**Beyond languages — real framework detection:** GitHub's own API only reports programming languages (Python, JavaScript), never frameworks. RecruitSmart goes a step further by reading actual dependency manifests (`package.json`, `requirements.txt`, `pom.xml`, `Gemfile`, `go.mod`, `Cargo.toml`, etc.) from a candidate's most recently active repos, so real framework usage — React, Flask, Django, Express, Spring, Next.js, TailwindCSS, and more — gets confirmed too, not just the underlying language. This directly improves the accuracy of the "Confirmed by Code" list and the authenticity-rate percentage shown to recruiters.

Resume keyword-matching is trivially gamed — a candidate can list "Python" and "Machine Learning" without ever having written a line of either. RecruitSmart's verification engine (`app/utils/github_verifier.py`) calls the **GitHub REST API** to:
- Pull a candidate's real public repositories, languages, stars, and followers
- Compute a transparent, weighted **Portfolio Authenticity Score (0–100)** across five explainable sub-scores (repository activity, community recognition, network reach, language diversity, consistency)
- **Cross-reference resume-claimed skills against GitHub-proven skills**, splitting them into "Confirmed by Code" vs. "Unconfirmed Claims"
- Give recruiters an at-a-glance authenticity signal next to every AI match score

This is the project's core novelty: it turns RecruitSmart from a keyword matcher into a **fact-checked** recruitment system.

### 🕵️ 2. Resume Authenticity Checker (Fraud/Fabrication Screening)
A plain ATS only checks whether a resume *contains* the right keywords — it has no opinion on whether the resume is genuine. RecruitSmart adds an independent, explainable Authenticity Score (`app/utils/authenticity_checker.py`) built from four real checks that run automatically on every upload:
1. **Timeline consistency** — flags overlapping "full-time" date ranges, dates in the future, and claimed total experience that doesn't match the dates actually printed on the resume
2. **PDF metadata forensics** — inspects the PDF's own creation/modification timestamps and author field for impossible or mismatched values
3. **Content authenticity** — flags resumes that are mostly generic buzzwords ("results-driven team player") with no concrete numbers, tools, or outcomes — a known template/AI-filler pattern
4. **Duplicate/template detection** — fuzzy-matches every new resume against every other resume already on the platform, flagging near-identical matches to a *different* candidate

Every flag is written in plain English and tied to a specific check, so a recruiter (or an examiner) can see exactly why a resume was flagged — this is a heuristic screening signal, like a plagiarism checker's similarity score, not a definitive fraud verdict, and the README/UI say so explicitly.

### 🦠 3. Malicious Resume Scanner (Cybersecurity)
Resume uploads are a real, documented attack vector — HR/recruiting teams are a favorite phishing target precisely because they're obligated to open attachments from strangers all day. Beyond basic file-type/magic-byte validation (already present), RecruitSmart adds:
- **Macro detection** — blocks any `.docx` containing an embedded VBA project (`word/vbaProject.bin`), the classic "enable content and get infected" attack
- **Zip-bomb protection** — DOCX/XLSX/PPTX files are zip archives; a crafted file can be a few KB on disk but decompress into gigabytes. RecruitSmart inspects the zip directory's declared sizes *before* extracting anything and rejects abnormal compression ratios or excessive uncompressed size
- **Malware signature detection** — scans for the EICAR test string, the harmless signature every antivirus vendor recognizes for testing, so the feature is safely demonstrable without needing real malware
- **Malicious-PDF heuristics** — flags PDFs containing `/JavaScript`, `/OpenAction`, or `/Launch`, since a legitimate resume never needs to execute code or auto-launch anything

Every blocked upload is logged to a `SecurityEvent` table and visible in a new admin **Security Center** (`/admin/security`), alongside locked-account and failed-login tracking. This is a heuristic/signature-based scanner, not a full antivirus engine — worth stating plainly if asked, since no automated scanner can catch 100% of malware.

RecruitSmart also sets standard OWASP security headers on every response (`X-Frame-Options`, `X-Content-Type-Options`, `Content-Security-Policy`, `Referrer-Policy`), and already had CSRF protection (Flask-WTF) and rate-limiting + account lockout on auth endpoints (Flask-Limiter) built in.

### 🔗 4. LinkedIn Profile Review
Paste your headline, About section, and one experience entry, and get a "recruiter's 10-second impression" plus a prioritized checklist of the highest-impact fixes (missing About section, generic headline, no quantifiable achievements, too few listed skills). **Important honesty note:** this does not scrape or fetch your live LinkedIn profile — LinkedIn's Terms of Service prohibit automated scraping and there's no public API for reading arbitrary profiles, so the candidate pastes their own text instead. The UI states this plainly.

### 📊 5. Skill Demand Dashboard (Recruiter)
Real supply-vs-demand aggregation across the platform's own data — no projections, no fabricated figures. Shows which skills are most common among candidate resumes ("supply") vs. most requested in active job postings ("demand"), plus a scarcity ranking (demand rate minus supply rate) to flag genuinely hard-to-fill skills. Every number is a direct count; nothing here pretends to predict the future.

### ✉️ 6. AI Cover Letter Generator
Template-based, not an external LLM call — same deterministic, explainable framing as the rest of the platform's "AI" features. Generates a personalized draft using the candidate's real matched skills for a specific job, their name, and years of experience, available with one click from any job's detail page.

### 🎤 7. AI Interview Question Generator
A curated question bank keyed by skill (Python, SQL, React, Nmap, OWASP, and more), combined with a fixed set of behavioral questions. Available per-job (matched to that job's required skills) or standalone (using the candidate's resume skills or a manually entered role).

### 🎯 8. Resume-Based Job Recommendations
The candidate dashboard's "Recommended For You" section is now genuinely personalized — it's no longer just the newest job postings. Every active job is ranked by real skill overlap against the candidate's primary resume, with a match percentage shown on each recommendation, and falls back to newest-first only when the candidate has no resume yet.

### 💰 6. AI Salary Insights (Explainable Multi-Factor Model)
A transparent salary estimator personalized with signals the platform already has about the candidate — not a generic calculator. Given a job title, it combines:
- A base salary band per role category (software/data/DevOps/security/etc.)
- An experience-years multiplier
- A metro-city / remote location adjustment
- An in-demand-skills bonus (cloud, ML, Kubernetes, etc. detected from the resume)
- A **GitHub Portfolio Verification bonus** — directly reusing the platform's own verified-skills signal rather than treating it as a separate feature

Every adjustment is shown as a labeled, human-readable factor (never a black-box number), and the UI states plainly that this is a rule-based illustrative model, not a figure sourced from live market data — an intentionally honest framing for a student project.

### ✅ 9. Rejection Feedback: Skill Gap + Better-Fit Job Suggestions
When a recruiter rejects an application, the candidate doesn't just see "Rejected" — they get a dedicated feedback page combining: the recruiter's own written reason (if given), an automatically computed skill gap versus that specific job's requirements, and a content-based recommendation of other open roles that better match the skills they already have (scored by skill-overlap against every other active job on the platform).

### 🛡️ 10. Recruiter Verification & Approval Workflow (Security)
By default, anyone could register with `role=recruiter` and immediately gain access to every candidate's resume data and contact details — a real privacy risk in a system handling personal data. RecruitSmart closes this gap:
- Recruiter sign-up requires **company name, website, and job title**
- New recruiter accounts start in a **`pending`** state — job posting, candidate browsing, and application management are all blocked (`recruiter_verified_required` decorator) until an admin approves them
- Admins get a dedicated **verification queue** (`/admin/users`) to approve or reject recruiters with a reason
- Candidates are notified automatically once their recruiter account is approved

### 📄 11. One-Click AI PDF Report Generator
Using `reportlab` (`app/utils/pdf_report.py`), RecruitSmart generates three kinds of professional, presentation-ready PDF reports with no external dependencies (no wkhtmltopdf/Chrome needed):
- **Candidate ATS Report** — score, feedback, and extracted skills
- **Job Match Report** — full score breakdown, matching/missing skills, and GitHub verification summary, for a specific job
- **Recruiter Shortlist Report** — a ranked table of every AI-matched candidate for a job posting, ready to hand to a hiring committee or placement cell

These reports make the AI's reasoning portable outside the browser — genuinely useful for a placement office, and a strong demo artifact for a project defense/publication.

### 🧠 12. TF-IDF + Cosine Similarity Semantic Matching (Genuine ML Component)
Most of this project's "AI" is intentionally transparent rule-based scoring (see the honesty notes throughout this README) — that's a deliberate, defensible design choice for a student project without a labeled training dataset. One piece, however, is a real, textbook NLP technique: the semantic-relevance portion of the match score (`app/utils/ml_match.py`) uses **scikit-learn's `TfidfVectorizer`** to vectorize the resume's full text and the job description/requirements, then **cosine similarity** to score how closely their vocabularies align. This is the standard baseline model used in academic document-similarity and resume-matching literature, it's unsupervised (needs no labeled data), and it's fully explainable if asked in a viva — see the module's docstring for the reasoning. The blended `overall_score` still combines this with explicit required-skill overlap and experience fit, since text similarity alone is a weak signal on its own.

### 💬 13. Site-Wide Help Assistant (Search-Based Support Chat)
A floating chat widget (`app/templates/_help_widget.html`, `app/static/js/help_widget.js`) available on every page, backed by a rate-limited, CSRF-protected `/api/help/search` endpoint (`app/utils/help_bot.py`). It answers common questions (resume upload, match scoring, account security, 2FA, phishing awareness) via keyword + fuzzy matching against a curated FAQ set — deliberately not a third-party LLM call, so no user input ever leaves the platform. Built with the same security discipline as the rest of the app: 20 requests/minute rate limit, CSRF-token verification, and every displayed string rendered with `textContent` (never `innerHTML`), which is what actually rules out XSS here rather than just trusting the backend.

## ✨ Features

### 🎨 Modern UI
- **Dark/Light Mode** toggle
- **Responsive Design** — works on mobile, tablet, desktop
- **Smooth Animations** — AOS, custom CSS animations
- **Glassmorphism Effects** — modern card designs
- **Real-time Updates** — WebSocket notifications

### 🔐 Security
- **Role-Based Access Control** — Admin, Recruiter, Candidate
- **Two-Factor Authentication** — TOTP support
- **Account Lockout** — 5 failed attempts = 30min lock
- **Password Strength** — Enforced complexity rules
- **Rate Limiting** — API endpoint protection
- **CSRF Protection** — All forms protected
- **GDPR Compliant** — Data export/deletion

### 🤖 AI Features
- **Smart Resume Parsing** — PDF, DOCX, TXT, Image OCR
- **ATS Score Calculator** — Resume optimization tips
- **AI Job Matching** — Semantic similarity scoring
- **GitHub Portfolio Verification** — Verifies resume skills against real public code via the GitHub REST API
- **PDF Report Generator** — Downloadable candidate, match, and shortlist reports (reportlab)
- **Skill Gap Analysis** — Personalized learning paths
- **Career Roadmap** — AI-generated career paths
- **Salary Prediction** — Market rate estimation
- **Bias Detection** — Fair hiring algorithms

### 📊 Analytics
- **Real-time Dashboard** — Live statistics
- **Recruiter Analytics** — Hiring funnel metrics
- **Candidate Insights** — Application tracking
- **Admin Reports** — System-wide analytics

### 📧 Communication
- **Email Templates** — Beautiful HTML emails
- **Real-time Notifications** — WebSocket push
- **Interview Scheduling** — Calendar integration
- **In-app Messaging** — Candidate-recruiter chat

### 🔌 Integrations
- **Social Login** — Google, LinkedIn OAuth
- **API Documentation** — Swagger/OpenAPI
- **REST API** — Full CRUD endpoints
- **WebSocket** — Real-time features

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- pip
- Virtual environment (recommended)

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/recruit-smart-ai.git
cd recruit-smart-ai

# 2. Create virtual environment
python -m venv venv

# 3. Activate (Windows)
venv\Scriptsctivate
# Activate (Mac/Linux)
# source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Set up environment
copy .env.example .env
# Edit .env with your settings

# 6. Initialize database
flask db init
flask db migrate -m "Initial migration"
flask db upgrade

# 7. Run the application
python run.py
```

### Or use the batch file (Windows)
```bash
# Double-click START_SERVER.bat
```

## 📖 Usage

### Default Login
| Role | Email | Password |
|------|-------|----------|
| Admin | admin@recruitsmart.ai | Set via `ADMIN_PASSWORD` env var (or check the server log on first startup — a random password is generated automatically if you don't set one). See `.env.example`. |

### User Flows

**Candidate:**
1. Register -> Upload Resume -> Get ATS Score
2. Browse Jobs -> AI Match -> Apply
3. Career Roadmap -> Skill Gaps -> Learning Path

**Recruiter:**
1. Register -> Post Job -> AI Parse
2. View Matches -> Rank Candidates -> Shortlist
3. Schedule Interviews -> Send Offers

**Admin:**
1. Dashboard -> User Management
2. Analytics -> System Reports
3. Settings -> Configuration

## 📁 Project Structure

```
recruit_smart/
├── app/
│   ├── auth/          # Authentication (login, register, OAuth)
│   ├── main/          # Main routes (home, about, contact)
│   ├── candidate/     # Candidate features
│   ├── recruiter/     # Recruiter features
│   ├── admin/         # Admin dashboard
│   ├── api/           # REST API endpoints
│   ├── templates/     # HTML templates
│   ├── static/        # CSS, JS, images
│   └── utils/         # Helper functions
├── docs/              # Documentation
├── tests/             # Unit tests
├── migrations/        # Database migrations
├── scripts/           # Utility scripts
├── requirements.txt   # Dependencies
├── config.py          # Configuration
└── run.py             # Entry point
```

## 🛠️ Tech Stack

This list intentionally matches `requirements.txt` and what's actually imported in the code — worth double-checking against your own codebase before quoting a tech stack in a report, since it's an easy thing for an examiner to catch out.

- **Backend:** Flask, Flask-SQLAlchemy, Flask-Login, Flask-Migrate (Alembic)
- **Frontend:** Bootstrap 5, vanilla JavaScript, Font Awesome
- **AI/ML:** scikit-learn (TF-IDF vectorization + cosine similarity for semantic job matching — see Publication Highlight #12), NumPy
- **Database:** SQLite (dev/demo) — swappable to PostgreSQL in production via `DATABASE_URL`
- **Auth:** Flask-Login sessions, TOTP-based Two-Factor Authentication (`pyotp`), optional Google/LinkedIn OAuth
- **Security:** Flask-WTF (CSRF), Flask-Limiter (rate limiting), OWASP response headers, custom file-signature upload validation
- **Document generation:** ReportLab (PDF reports), python-docx / PyPDF2 / pdfplumber (resume parsing)
- **Real-time (optional):** Flask-SocketIO, if the `flask-socketio` package is installed — the app runs fine without it too

## 🧪 Testing

```bash
pytest
pytest --cov=app
```

## 📄 License

MIT License — see [LICENSE](LICENSE) file.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## 📞 Support

- Email: support@recruitsmart.ai
- Documentation: [docs](docs/)
- Issues: [GitHub Issues](https://github.com/yourusername/recruit-smart-ai/issues)

---

**Made with love for modern recruitment**
