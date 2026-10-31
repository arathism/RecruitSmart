"""
Career Fit Analysis
----------------------
Answers "based on my resume, which jobs could I actually apply for?" --
using the exact same skill-overlap algorithm the dashboard's "Recommended
For You" section uses for real posted jobs (see candidate/routes.py
dashboard()), but against a built-in reference set of common tech role
categories instead of only whatever jobs happen to be posted right now.

This matters in practice: a freshly-deployed instance of this platform may
have zero or very few real job postings (recruiters haven't signed up and
posted yet), which would make "Recommended For You" show nothing useful.
Career Fit Analysis gives every candidate an immediate, concrete answer
regardless of how many real jobs exist yet, and doubles as a career-
exploration tool ("what am I actually suited for right now") independent
of the live job board.
"""

ROLE_CATEGORIES = {
    "Cybersecurity Analyst": ["nmap", "wireshark", "burp suite", "owasp", "vulnerability assessment",
                               "incident response", "linux"],
    "Junior Penetration Tester": ["nmap", "nikto", "burp suite", "dvwa", "owasp top 10",
                                   "penetration testing", "kali linux"],
    "SOC Analyst": ["wireshark", "incident response", "threat detection", "siem", "network security", "linux"],
    "Full Stack Developer (MERN)": ["react", "node.js", "express", "mongodb", "javascript", "html", "css", "rest api"],
    "Frontend Developer (React)": ["react", "next.js", "javascript", "typescript", "html", "css", "tailwind"],
    "Backend Developer (Node.js)": ["node.js", "express", "mongodb", "sql", "rest api", "git"],
    "Software Engineer (General)": ["python", "java", "javascript", "sql", "git",
                                      "data structures and algorithms"],
    "Data Analyst": ["python", "sql", "data science", "mysql", "pandas"],
    "Data Scientist / ML": ["python", "numpy", "pandas", "tensorflow", "pytorch", "scikit-learn", "data science"],
    "DevOps Engineer": ["linux", "docker", "kubernetes", "aws", "git", "ci/cd"],
    "Computer Vision Engineer": ["python", "opencv", "computer vision", "numpy", "mediapipe"],
    "Mobile App Developer": ["flutter", "dart", "android", "kotlin", "swift", "react native"],
    "QA / Test Engineer": ["selenium", "test automation", "junit", "manual testing", "sql"],
    "Database Administrator": ["sql", "mysql", "postgresql", "mongodb", "database management system"],
    "UI/UX Designer": ["figma", "ui/ux design", "wireframing", "prototyping", "adobe xd"],
}


def compute_career_fit(candidate_skills):
    """Returns every role category ranked by skill-overlap percentage, using
    the identical formula the dashboard uses for real job postings:
    matched_skills / total_required_skills * 100."""
    candidate_set = set(s.lower() for s in candidate_skills)
    results = []

    for title, required in ROLE_CATEGORIES.items():
        required_set = set(required)
        matched = sorted(candidate_set & required_set)
        missing = sorted(required_set - candidate_set)
        pct = round(len(matched) / len(required_set) * 100) if required_set else 0

        if pct >= 70:
            tier = "Strong Match"
        elif pct >= 40:
            tier = "Good Match"
        else:
            tier = "Weak Match"

        results.append({
            "title": title,
            "match_pct": pct,
            "tier": tier,
            "matched_skills": matched,
            "missing_skills": missing,
        })

    results.sort(key=lambda r: r["match_pct"], reverse=True)
    return results
