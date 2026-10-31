"""
resume_validator.py
Drop into: app/utils/resume_validator.py  (or next to your upload route)

Usage:
    from app.utils.resume_validator import is_resume
    ok, reason = is_resume(text, filename)
    if not ok:
        flash(reason, "danger")
        return redirect(request.url)
"""
import re

# Section headings that real resumes have
SECTION_PATTERNS = {
    "education": r"education|academic (background|qualification)s?",
    "experience": r"(work |professional )?experience|internships?|employment",
    "skills": r"(technical |key |core )?skills|technologies|tech stack",
    "projects": r"projects?|academic projects?",
    "summary": r"(professional |career )?summary|objective|profile|about me",
    "certifications": r"certifications?|courses|achievements|awards",
}

# Phrases that show up in forms, receipts, syllabi, etc. but not in resumes
NEGATIVE_PHRASES = [
    "application form", "application no", "application number",
    "applicant name", "name of the applicant", "signature of the applicant",
    "father's name", "mother's name", "date of birth", "declaration",
    "i hereby declare", "for office use", "hall ticket", "admit card",
    "registration number", "fee paid", "payment receipt", "invoice",
    "terms and conditions", "question paper", "syllabus", "marks card",
    "marksheet", "grade card", "transaction id", "challan", "category:",
    "candidate's signature", "photo and signature",
]

NEGATIVE_FILENAME = [
    "application", "form", "invoice", "receipt", "syllabus", "marksheet",
    "hall_ticket", "admit", "challan", "certificate", "question",
]

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(\+?\d[\d\s-]{8,14}\d)")
LINK_RE = re.compile(r"linkedin\.com|github\.com", re.I)


def _find_sections(text):
    """Count distinct resume sections that appear as short heading-like lines."""
    found = set()
    for line in text.splitlines():
        clean = line.strip().strip(":-–—•| ").lower()
        if not clean or len(clean) > 45 or len(clean.split()) > 5:
            continue
        for name, pat in SECTION_PATTERNS.items():
            if re.search(r"^(" + pat + r")\b", clean):
                found.add(name)
    return found


def is_resume(text, filename=""):
    """Return (True, "") if it looks like a resume, else (False, reason)."""
    text = text or ""
    low = text.lower()
    words = len(text.split())

    # Scanned/graphical PDFs have almost no extractable text. The app already
    # shows a warning for those, so we can't judge them here -- let them pass.
    if words < 40:
        return True, ""

    sections = _find_sections(text)
    has_email = bool(EMAIL_RE.search(text))
    has_phone = bool(PHONE_RE.search(text))
    has_link = bool(LINK_RE.search(text))
    negatives = [p for p in NEGATIVE_PHRASES if p in low]

    fname = (filename or "").lower()
    bad_name = any(k in fname for k in NEGATIVE_FILENAME)

    score = len(sections) * 2 + has_email + has_phone + has_link
    score -= len(negatives) * 3
    if bad_name:
        score -= 2

    contact = has_email or has_phone
    structure_ok = len(sections) >= 2 and contact
    too_long = words > 2500  # study notes, books, question banks, etc.

    if too_long or len(negatives) >= 2 or score < 5 or not structure_ok:
        return False, (
            "This doesn't look like a resume (it may be a form, certificate "
            "or other document). Please upload your resume with sections like "
            "Education, Skills, Projects or Experience."
        )
    return True, ""


if __name__ == "__main__":
    resume = """Arathi S M
arathi@gmail.com +91 98765 43210 github.com/arathism
Summary
Final year student building Flask apps.
Education
B.E. Computer Software Engineering, VTU
Skills
Python, Flask, SQL, Git
Projects
RecruitSmart AI - resume screening platform
Experience
Web Development Intern
""" + "Built features and shipped code. " * 20

    form = """Application Form
Application No: DT20268508383
Applicant Name: Adityasingh
Father's Name: R
Date of Birth: 01/01/2003
Education
Skills
Declaration
I hereby declare that the information is true.
Signature of the applicant
""" + "Fill all fields carefully. " * 40

    print("resume ->", is_resume(resume, "my_resume.pdf"))
    print("form   ->", is_resume(form, "DT20268508383_Application_Form.pdf"))