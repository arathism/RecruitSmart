from app import db
from app.models import User, SkillTest, Job
from flask import current_app
import json
import secrets
from datetime import datetime, timedelta

def create_admin_user():
    """Creates the admin account on first startup. Deliberately does NOT
    fall back to a hardcoded default password: this project's own
    .env.example used to document 'admin123' as the example ADMIN_PASSWORD,
    which meant any real deployment that forgot to set the env var would
    have a publicly-guessable admin login (the example value is sitting in
    a public repo). If ADMIN_PASSWORD isn't set, a random strong password
    is generated and printed ONCE to the server log -- copy it from the
    log on first deploy, then change it immediately from the admin's own
    profile page (2FA is mandatory for admins regardless, see
    app/utils/decorators.py)."""
    admin_email = current_app.config.get("ADMIN_EMAIL", "admin@recruitsmart.ai")
    admin_password = current_app.config.get("ADMIN_PASSWORD")
    existing = User.query.filter_by(email=admin_email).first()
    if not existing:
        generated = False
        if not admin_password:
            admin_password = secrets.token_urlsafe(12)
            generated = True
        admin = User(email=admin_email, first_name="Admin", last_name="User", role="admin",
            email_verified=True, is_verified=True, gdpr_consent=True)
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()
        if generated:
            print("=" * 60)
            print(f"ADMIN ACCOUNT CREATED: {admin_email}")
            print(f"GENERATED PASSWORD (shown once, not stored anywhere): {admin_password}")
            print("Log in now and change this password immediately.")
            print("Set ADMIN_PASSWORD as an env var to control this yourself next time.")
            print("=" * 60)
        else:
            print(f"Admin user created: {admin_email}")

def create_sample_skill_tests():
    """Seeds the skill-test catalog. Tops up by title instead of bailing out
    the moment any test exists -- on an older database that already had the
    original 2 tests, this now adds the newer ones too instead of silently
    skipping them forever."""
    tests = [
        {
            "title": "Python Fundamentals",
            "description": "Test your basic Python programming knowledge",
            "skill_category": "Programming",
            "difficulty": "easy",
            "questions": json.dumps([
                {"question": "What is the output of print(2 ** 3)?", "options": ["6", "8", "9", "4"], "correct_answer": "8"},
                {"question": "Which data type is mutable?", "options": ["tuple", "string", "list", "int"], "correct_answer": "list"},
                {"question": "What does len([1, 2, 3]) return?", "options": ["2", "3", "4", "1"], "correct_answer": "3"},
                {"question": "Which keyword defines a function in Python?", "options": ["func", "def", "function", "lambda"], "correct_answer": "def"},
                {"question": "What does the range(3) function produce?", "options": ["0, 1, 2", "1, 2, 3", "0, 1, 2, 3", "1, 2"], "correct_answer": "0, 1, 2"}
            ]),
            "time_limit_minutes": 10,
            "passing_score": 70
        },
        {
            "title": "SQL Basics",
            "description": "Test your SQL query knowledge",
            "skill_category": "Databases",
            "difficulty": "medium",
            "questions": json.dumps([
                {"question": "Which SQL keyword retrieves data?", "options": ["GET", "FETCH", "SELECT", "PULL"], "correct_answer": "SELECT"},
                {"question": "What does JOIN do?", "options": ["Delete data", "Combine tables", "Sort data", "Filter data"], "correct_answer": "Combine tables"},
                {"question": "Which clause filters groups?", "options": ["WHERE", "HAVING", "GROUP BY", "ORDER BY"], "correct_answer": "HAVING"},
                {"question": "Which keyword removes duplicate rows from results?", "options": ["UNIQUE", "DISTINCT", "FILTER", "NODUP"], "correct_answer": "DISTINCT"},
                {"question": "Which statement adds a new row to a table?", "options": ["ADD", "INSERT", "CREATE", "APPEND"], "correct_answer": "INSERT"}
            ]),
            "time_limit_minutes": 15,
            "passing_score": 70
        },
        {
            "title": "JavaScript Fundamentals",
            "description": "Test your core JavaScript programming knowledge",
            "skill_category": "Programming",
            "difficulty": "easy",
            "questions": json.dumps([
                {"question": "Which keyword declares a block-scoped variable in JS?", "options": ["var", "let", "static", "dim"], "correct_answer": "let"},
                {"question": "What does === check that == does not?", "options": ["Value only", "Type as well as value", "Nothing extra", "Reference only"], "correct_answer": "Type as well as value"},
                {"question": "Which method adds an item to the end of an array?", "options": ["push()", "pop()", "shift()", "append()"], "correct_answer": "push()"},
                {"question": "What is the result of typeof \"hello\"?", "options": ["string", "text", "char", "object"], "correct_answer": "string"},
                {"question": "Which built-in function converts JSON text into an object?", "options": ["JSON.stringify()", "JSON.parse()", "JSON.toObject()", "Object.parse()"], "correct_answer": "JSON.parse()"}
            ]),
            "time_limit_minutes": 10,
            "passing_score": 70
        },
        {
            "title": "HTML & CSS Basics",
            "description": "Test your understanding of core web markup and styling",
            "skill_category": "Web Development",
            "difficulty": "easy",
            "questions": json.dumps([
                {"question": "Which HTML tag is used to link an external CSS file?", "options": ["<style>", "<script>", "<link>", "<css>"], "correct_answer": "<link>"},
                {"question": "Which CSS property controls text size?", "options": ["text-size", "font-size", "size", "text-style"], "correct_answer": "font-size"},
                {"question": "Which HTML tag defines an unordered list?", "options": ["<ol>", "<list>", "<ul>", "<li>"], "correct_answer": "<ul>"},
                {"question": "Which CSS layout model arranges items in a single row or column?", "options": ["Grid", "Flexbox", "Float", "Table"], "correct_answer": "Flexbox"},
                {"question": "Which attribute provides alternate text for an image?", "options": ["title", "alt", "src", "desc"], "correct_answer": "alt"}
            ]),
            "time_limit_minutes": 10,
            "passing_score": 70
        },
        {
            "title": "Data Structures & Algorithms",
            "description": "Test your fundamentals of common data structures and algorithmic thinking",
            "skill_category": "Programming",
            "difficulty": "medium",
            "questions": json.dumps([
                {"question": "Which data structure follows Last-In-First-Out (LIFO)?", "options": ["Queue", "Stack", "Array", "Linked List"], "correct_answer": "Stack"},
                {"question": "What is the average time complexity of binary search on a sorted array?", "options": ["O(n)", "O(n^2)", "O(log n)", "O(1)"], "correct_answer": "O(log n)"},
                {"question": "Which data structure follows First-In-First-Out (FIFO)?", "options": ["Stack", "Queue", "Tree", "Graph"], "correct_answer": "Queue"},
                {"question": "What is the worst-case time complexity of bubble sort?", "options": ["O(n log n)", "O(n)", "O(n^2)", "O(log n)"], "correct_answer": "O(n^2)"},
                {"question": "Which structure is best suited for representing hierarchical data?", "options": ["Array", "Tree", "Stack", "Queue"], "correct_answer": "Tree"}
            ]),
            "time_limit_minutes": 15,
            "passing_score": 70
        },
        {
            "title": "Cloud & DevOps Basics",
            "description": "Test your fundamentals of cloud computing and DevOps practices",
            "skill_category": "Cloud & DevOps",
            "difficulty": "medium",
            "questions": json.dumps([
                {"question": "What does CI/CD stand for?", "options": ["Code Integration/Code Deployment", "Continuous Integration/Continuous Deployment", "Container Image/Container Deployment", "Central Index/Central Database"], "correct_answer": "Continuous Integration/Continuous Deployment"},
                {"question": "Which tool is primarily used for containerization?", "options": ["Docker", "Jenkins", "Terraform", "Git"], "correct_answer": "Docker"},
                {"question": "What is the primary purpose of Kubernetes?", "options": ["Version control", "Container orchestration", "Code compilation", "Database management"], "correct_answer": "Container orchestration"},
                {"question": "Which AWS service provides scalable object storage?", "options": ["EC2", "S3", "RDS", "Lambda"], "correct_answer": "S3"},
                {"question": "What does IaC (Infrastructure as Code) primarily enable?", "options": ["Manual server setup", "Defining infrastructure through versioned config files", "Faster internet speed", "GUI-only deployments"], "correct_answer": "Defining infrastructure through versioned config files"}
            ]),
            "time_limit_minutes": 15,
            "passing_score": 70
        },
        {
            "title": "Cybersecurity Basics",
            "description": "Test your understanding of core security concepts",
            "skill_category": "Security",
            "difficulty": "medium",
            "questions": json.dumps([
                {"question": "What does SQL injection primarily exploit?", "options": ["Weak passwords", "Unsanitized user input in queries", "Slow network speed", "Outdated browsers"], "correct_answer": "Unsanitized user input in queries"},
                {"question": "What is the purpose of two-factor authentication?", "options": ["Faster login", "An extra layer of identity verification beyond a password", "Encrypting the database", "Blocking all bots"], "correct_answer": "An extra layer of identity verification beyond a password"},
                {"question": "What does HTTPS add on top of HTTP?", "options": ["Faster loading", "Encrypted communication", "Better SEO", "Larger file support"], "correct_answer": "Encrypted communication"},
                {"question": "What is phishing?", "options": ["A network speed test", "Tricking users into revealing sensitive information", "A firewall configuration", "A type of encryption"], "correct_answer": "Tricking users into revealing sensitive information"},
                {"question": "What is the main purpose of a firewall?", "options": ["Speed up traffic", "Filter and control incoming/outgoing network traffic", "Store passwords", "Compress files"], "correct_answer": "Filter and control incoming/outgoing network traffic"}
            ]),
            "time_limit_minutes": 15,
            "passing_score": 70
        },
        {
            "title": "Workplace Communication",
            "description": "Test your understanding of effective workplace and team communication",
            "skill_category": "Soft Skills",
            "difficulty": "easy",
            "questions": json.dumps([
                {"question": "What is 'active listening' primarily about?", "options": ["Waiting for your turn to speak", "Fully concentrating on and understanding the speaker", "Multitasking while listening", "Interrupting to add ideas quickly"], "correct_answer": "Fully concentrating on and understanding the speaker"},
                {"question": "What is the best way to give constructive feedback?", "options": ["Focus only on what went wrong", "Be specific, respectful, and solution-oriented", "Give feedback publicly to set an example", "Avoid giving feedback to prevent conflict"], "correct_answer": "Be specific, respectful, and solution-oriented"},
                {"question": "In a disagreement with a teammate, what's the healthiest first step?", "options": ["Escalate to a manager immediately", "Understand their perspective before responding", "Ignore the issue", "Assume they are wrong"], "correct_answer": "Understand their perspective before responding"},
                {"question": "What makes an email professional and effective?", "options": ["Being vague to sound polite", "A clear subject line and concise, respectful content", "Using as many words as possible", "Skipping greetings and closings"], "correct_answer": "A clear subject line and concise, respectful content"},
                {"question": "What is a key trait of good time management at work?", "options": ["Doing everything at the last minute", "Prioritizing tasks based on urgency and importance", "Working on the easiest tasks first regardless of deadline", "Avoiding planning altogether"], "correct_answer": "Prioritizing tasks based on urgency and importance"}
            ]),
            "time_limit_minutes": 10,
            "passing_score": 70
        }
    ]
    existing_titles = {t.title for t in SkillTest.query.all()}
    added = 0
    for test_data in tests:
        if test_data["title"] in existing_titles:
            continue
        test = SkillTest(**test_data)
        db.session.add(test)
        added += 1
    if added:
        db.session.commit()
        print(f"Seeded {added} new skill test(s)")


def create_sample_jobs():
    """A freshly-cloned copy of this project starts with an EMPTY jobs
    table -- only the admin user and skill tests were auto-seeded. That
    meant Browse Jobs, Career Fit, Salary Insights comparisons, and the
    recruiter Candidates view all had nothing to show on first run.

    This seeds several distinct, pre-approved company recruiter accounts
    (not one generic "Demo Recruiter") and a larger, varied spread of
    active job postings, so the platform looks and behaves like a live
    multi-employer job board out of the box -- important for a demo/viva
    where "Demo Recruiter / Demo Co." on every listing looks obviously
    fake.

    Honesty note, worth keeping in mind for a report/viva: these are
    invented companies with invented postings written for this project --
    NOT real employers or real openings. Attributing fabricated job
    listings to actual real companies would be misleading, so every
    company name below is fictional by design, even though the postings
    are written in the same style/detail level as genuine listings.
    """
    if Job.query.first():
        return  # already seeded (or a real recruiter has posted jobs)

    companies = [
        {"key": "nimbus", "company_name": "Nimbus Cloud Systems", "first": "Priya", "last": "Nair",
         "email": "priya.nair@nimbuscloud.io"},
        {"key": "vertex", "company_name": "Vertex Analytics Pvt Ltd", "first": "Rohan", "last": "Kulkarni",
         "email": "rohan.kulkarni@vertexanalytics.in"},
        {"key": "brightpath", "company_name": "BrightPath Technologies", "first": "Ananya", "last": "Iyer",
         "email": "ananya.iyer@brightpathtech.com"},
        {"key": "fortify", "company_name": "Fortify Security Solutions", "first": "Karan", "last": "Mehta",
         "email": "karan.mehta@fortifysec.io"},
        {"key": "orbitmobile", "company_name": "Orbit Mobile Labs", "first": "Sneha", "last": "Reddy",
         "email": "sneha.reddy@orbitmobilelabs.com"},
    ]

    recruiters = {}
    for c in companies:
        recruiter = User.query.filter_by(email=c["email"]).first()
        if not recruiter:
            recruiter = User(
                email=c["email"], first_name=c["first"], last_name=c["last"], role="recruiter",
                email_verified=True, is_verified=True, gdpr_consent=True,
                company_name=c["company_name"], recruiter_status="approved",
            )
            recruiter.set_password("Recruiter@123")
            db.session.add(recruiter)
        recruiters[c["key"]] = recruiter
    db.session.commit()
    print("Company recruiter accounts created (password for all: Recruiter@123):")
    for c in companies:
        print(f"  - {c['email']}  [{c['company_name']}]")

    now = datetime.utcnow()
    sample_jobs = [
        {
            "company": "nimbus", "title": "Frontend Developer (React)", "location": "Pune", "is_remote": False, "job_type": "full_time",
            "description": "Nimbus Cloud Systems is hiring a Frontend Developer to build responsive, accessible interfaces for our cloud-storage dashboard product. You'll work closely with design and backend teams to ship features end-to-end, from component design to production deployment.",
            "requirements": "1-3 years building production React applications; strong HTML/CSS fundamentals; comfort working directly with a design system.",
            "required_skills": ["react", "javascript", "html", "css"],
            "preferred_skills": ["typescript", "tailwind", "next.js"],
            "salary_min": 600000, "salary_max": 1100000, "experience_min": 1, "experience_max": 3,
        },
        {
            "company": "nimbus", "title": "Frontend Intern", "location": "Pune", "is_remote": False, "job_type": "internship",
            "description": "A 3-6 month internship on the Nimbus frontend team, building and polishing real UI components that ship to production, under the guidance of senior engineers.",
            "requirements": "Currently pursuing or recently completed a degree in Computer Science or a related field; a portfolio of personal or academic projects is a plus.",
            "required_skills": ["html", "css", "javascript"],
            "preferred_skills": ["react", "git"],
            "salary_min": 15000, "salary_max": 25000, "salary_period": "monthly",
            "experience_min": 0, "experience_max": 0,
        },
        {
            "company": "vertex", "title": "Backend Developer (Python/Flask)", "location": "Bangalore", "is_remote": True, "job_type": "full_time",
            "description": "Vertex Analytics is looking for a Backend Developer to design and maintain the REST APIs and data pipelines behind our analytics platform, using Python, Flask, and PostgreSQL.",
            "requirements": "2+ years backend development; comfortable with relational database design and REST API design.",
            "required_skills": ["python", "flask", "sql", "rest api"],
            "preferred_skills": ["docker", "aws", "postgresql"],
            "salary_min": 800000, "salary_max": 1600000, "experience_min": 2, "experience_max": 5,
        },
        {
            "company": "vertex", "title": "Data Analyst", "location": "Pune", "is_remote": False, "job_type": "full_time",
            "description": "Turn raw client data into actionable dashboards and reports for Vertex's analytics clients, using SQL and Python.",
            "requirements": "Strong SQL skills; comfortable with Python for data analysis (pandas); able to present findings clearly to non-technical stakeholders.",
            "required_skills": ["sql", "python", "data analysis"],
            "preferred_skills": ["tableau", "power bi", "excel"],
            "salary_min": 500000, "salary_max": 900000, "experience_min": 0, "experience_max": 3,
        },
        {
            "company": "vertex", "title": "DevOps Engineer", "location": "Remote", "is_remote": True, "job_type": "full_time",
            "description": "Build and maintain the CI/CD pipelines and cloud infrastructure that keep Vertex's analytics platform running reliably at scale.",
            "requirements": "Hands-on experience with containerization and at least one major cloud provider; comfortable owning production incidents.",
            "required_skills": ["docker", "kubernetes", "aws", "linux"],
            "preferred_skills": ["terraform", "ci/cd", "jenkins"],
            "salary_min": 900000, "salary_max": 1800000, "experience_min": 2, "experience_max": 6,
        },
        {
            "company": "brightpath", "title": "Full Stack Developer (MERN)", "location": "Hyderabad", "is_remote": False, "job_type": "full_time",
            "description": "BrightPath Technologies is expanding its product team and looking for a Full Stack Developer to own features end-to-end across a React frontend and a Node.js/Express/MongoDB backend.",
            "requirements": "Experience across the full MERN stack; comfortable owning a feature from UI to database.",
            "required_skills": ["react", "node.js", "express", "mongodb"],
            "preferred_skills": ["javascript", "git", "rest api"],
            "salary_min": 700000, "salary_max": 1400000, "experience_min": 1, "experience_max": 4,
        },
        {
            "company": "brightpath", "title": "Junior Software Engineer", "location": "Chennai", "is_remote": False, "job_type": "full_time",
            "description": "An entry-level opening on BrightPath's core engineering team for a recent graduate ready to grow into a well-rounded full-stack developer, with structured mentorship in the first 6 months.",
            "requirements": "Solid grasp of data structures/algorithms and at least one programming language, demonstrated through academic or personal projects.",
            "required_skills": ["python", "java", "data structures and algorithms", "git"],
            "preferred_skills": ["sql", "javascript"],
            "salary_min": 400000, "salary_max": 700000, "experience_min": 0, "experience_max": 1,
        },
        {
            "company": "brightpath", "title": "QA / Test Engineer", "location": "Pune", "is_remote": False, "job_type": "part_time",
            "description": "Write and maintain automated test suites and perform structured manual testing ahead of each BrightPath release cycle.",
            "requirements": "Experience with at least one test automation framework and a methodical approach to bug reporting.",
            "required_skills": ["selenium", "manual testing", "sql"],
            "preferred_skills": ["pytest", "jira"],
            "salary_min": 300000, "salary_max": 600000, "experience_min": 0, "experience_max": 3,
        },
        {
            "company": "fortify", "title": "Cybersecurity Analyst", "location": "Remote", "is_remote": True, "job_type": "full_time",
            "description": "Fortify Security Solutions is hiring a Cybersecurity Analyst to monitor client environments, investigate incidents, and help harden infrastructure against common attack patterns.",
            "requirements": "Familiarity with common security tools and a solid understanding of networking fundamentals; a certification (Security+, Google Cybersecurity, or similar) is a plus.",
            "required_skills": ["wireshark", "incident response", "network security", "linux"],
            "preferred_skills": ["siem", "owasp"],
            "salary_min": 700000, "salary_max": 1500000, "experience_min": 1, "experience_max": 4,
        },
        {
            "company": "fortify", "title": "Junior Penetration Tester", "location": "Hubli", "is_remote": False, "job_type": "full_time",
            "description": "Join Fortify's offensive-security team to perform supervised penetration tests and vulnerability assessments for client web applications and internal networks.",
            "requirements": "Practical experience with tools like Nmap, Burp Suite, and Nikto (coursework, labs like DVWA, or internships all count); understanding of the OWASP Top 10.",
            "required_skills": ["nmap", "burp suite", "owasp top 10", "penetration testing"],
            "preferred_skills": ["kali linux", "nikto"],
            "salary_min": 500000, "salary_max": 1000000, "experience_min": 0, "experience_max": 2,
        },
        {
            "company": "fortify", "title": "SOC Analyst (Entry Level)", "location": "Pune", "is_remote": False, "job_type": "full_time",
            "description": "Monitor security alerts, triage incidents, and escalate genuine threats as part of Fortify's 24x7 Security Operations Center rotation.",
            "requirements": "Understanding of common attack patterns and log analysis; willingness to work rotational shifts.",
            "required_skills": ["incident response", "threat detection", "network security"],
            "preferred_skills": ["siem", "linux"],
            "salary_min": 450000, "salary_max": 850000, "experience_min": 0, "experience_max": 2,
        },
        {
            "company": "orbitmobile", "title": "Mobile App Developer (Flutter)", "location": "Mumbai", "is_remote": False, "job_type": "contract",
            "description": "A 6-month contract with Orbit Mobile Labs to build and ship a cross-platform mobile app using Flutter, from wireframe to app-store release.",
            "requirements": "Shipped at least one Flutter app to the Play Store or App Store; comfortable working directly with a small, fast-moving team.",
            "required_skills": ["flutter", "dart"],
            "preferred_skills": ["android", "ios", "firebase"],
            "salary_min": 600000, "salary_max": 1200000, "experience_min": 1, "experience_max": 4,
        },
        {
            "company": "orbitmobile", "title": "Computer Vision Engineer", "location": "Bangalore", "is_remote": True, "job_type": "full_time",
            "description": "Orbit Mobile Labs is building real-time gesture and motion-tracking features for our next mobile app. We're looking for someone who can take a computer-vision prototype from OpenCV/MediaPipe notebook to a smooth, on-device experience.",
            "requirements": "Hands-on project experience with OpenCV or MediaPipe (academic, personal, or professional); comfortable with Python.",
            "required_skills": ["python", "opencv", "computer vision"],
            "preferred_skills": ["mediapipe", "numpy"],
            "salary_min": 700000, "salary_max": 1500000, "experience_min": 0, "experience_max": 3,
        },
    ]

    for i, job_data in enumerate(sample_jobs):
        recruiter = recruiters[job_data["company"]]
        job = Job(
            recruiter_id=recruiter.id,
            title=job_data["title"],
            description=job_data["description"],
            requirements=job_data["requirements"],
            location=job_data["location"],
            is_remote=job_data["is_remote"],
            job_type=job_data["job_type"],
            required_skills=json.dumps(job_data["required_skills"]),
            preferred_skills=json.dumps(job_data["preferred_skills"]),
            salary_min=job_data.get("salary_min"),
            salary_max=job_data.get("salary_max"),
            salary_period=job_data.get("salary_period", "yearly"),
            experience_min=job_data.get("experience_min", 0),
            experience_max=job_data.get("experience_max"),
            status="active",
            is_featured=(i % 3 == 0),  # spread featured listings across companies, not just the first few
            posted_at=now - timedelta(days=i),
        )
        db.session.add(job)
    db.session.commit()
    print(f"{len(sample_jobs)} sample jobs created across {len(companies)} companies")
