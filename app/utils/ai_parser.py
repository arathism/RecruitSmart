import re
import json
import random
from datetime import datetime
from collections import Counter

SKILL_DATABASE = [
    # Programming languages
    "python", "javascript", "typescript", "java", "c++", "c#", "c", "go", "rust",
    "ruby", "php", "kotlin", "swift", "dart", "scala", "r", "matlab", "perl", "objective-c",
    # Web / frontend
    "html", "css", "sass", "scss", "tailwind", "bootstrap", "react", "react.js",
    "angular", "vue", "vue.js", "next.js", "nuxt.js", "svelte", "jquery", "redux",
    "webpack", "vite", "graphql", "rest api", "restful api",
    # Backend / frameworks
    "node.js", "express", "express.js", "django", "flask", "fastapi", "spring",
    "spring boot", "laravel", ".net", "asp.net", "ruby on rails", "nestjs",
    # Databases
    "sql", "mysql", "postgresql", "postgres", "mongodb", "redis", "sqlite",
    "oracle", "cassandra", "dynamodb", "firebase", "firestore", "elasticsearch",
    # Cloud / DevOps
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "jenkins",
    "ci/cd", "terraform", "ansible", "nginx", "linux", "bash", "shell scripting",
    "powershell", "github actions", "gitlab ci",
    # Version control / tools
    "git", "github", "gitlab", "bitbucket", "jira", "confluence", "trello",
    "postman", "figma", "adobe xd", "photoshop", "illustrator",
    # Data science / AI-ML
    "machine learning", "deep learning", "artificial intelligence", "nlp",
    "natural language processing", "computer vision", "tensorflow", "pytorch",
    "keras", "opencv", "numpy", "pandas", "scikit-learn", "matplotlib", "seaborn",
    "data analysis", "data visualization", "data science", "big data", "spark",
    "hadoop", "tableau", "power bi", "excel", "google sheets", "statistics",
    # Mobile
    "android", "ios", "flutter", "react native", "xamarin",
    # Testing
    "selenium", "junit", "pytest", "jest", "cypress", "manual testing",
    "automation testing", "test automation",
    # Project management / methodology
    "project management", "agile", "scrum", "kanban", "product management",
    # Collaboration / soft skills
    "slack", "microsoft teams", "zoom", "communication", "leadership",
    "problem solving", "critical thinking", "teamwork", "time management",
    "adaptability", "creativity", "public speaking", "mentoring",
    # Misc / office
    "microsoft office", "ms office", "word", "powerpoint", "sharepoint",
    "salesforce", "sap", "wordpress", "shopify", "seo",
    # Core CS fundamentals (very common on student/fresher resumes, esp.
    # engineering coursework -- previously missing, which was causing valid
    # resumes to show "no skills detected")
    "data structures", "data structures and algorithms", "dsa", "algorithms",
    "oop", "oops", "object oriented programming", "object-oriented programming",
    "dbms", "database management system", "database management systems",
    "operating system", "operating systems", "computer networks",
    "computer network", "software engineering", "system design",
    "compiler design", "theory of computation", "automata theory",
    "competitive programming", "c programming", "cpp", "embedded systems",
    "microcontrollers", "iot", "internet of things", "digital electronics",
    "computer architecture", "software testing", "unit testing",
    "version control", "networking", "cyber security", "cybersecurity",
    "ethical hacking", "network security", "cryptography", "blockchain",
    "web3", "solidity", "smart contracts", "full stack development",
    "full stack", "frontend development", "backend development",
    "web development", "app development", "mobile app development",
    "api development", "microservices", "software development",
    "web design", "ui/ux", "ui/ux design", "ui design", "ux design",
    "canva", "video editing", "content writing", "technical writing",
    "unity", "unreal engine", "game development", "ar/vr", "linux administration",
    # Security / pentesting tools (common on cybersecurity-track resumes --
    # previously missing, meaning real security experience wasn't detected)
    "nmap", "nikto", "wireshark", "burp suite", "burpsuite", "dvwa",
    "owasp", "owasp top 10", "metasploit", "kali linux", "penetration testing",
    "pentesting", "vulnerability assessment", "incident response",
    "siem", "wireshark packet analysis", "firewall", "ids/ips",
    "vapt", "threat detection", "threat intelligence", "malware analysis",
    "digital forensics", "soc analyst", "risk assessment"
]

# Multi-word / symbol-bearing skills need substring matching since \b word
# boundaries don't work reliably around '.', '+', '#'. Everything else uses
# strict word-boundary matching to avoid false positives like "Java" matching
# inside "JavaScript".
_SPECIAL_SKILLS = {"c++", "c#", "node.js", "express.js", "react.js", "vue.js",
                   "next.js", "nuxt.js", ".net", "asp.net", "ci/cd", "rest api",
                   "restful api"}

# Skill-name synonyms: the extractor above deliberately keeps both spellings
# in SKILL_DATABASE (e.g. "react" and "react.js" are both matched when
# scanning resume text, so a resume that only ever writes "React.js" still
# gets credited with the skill). That's correct for *extraction*, but it
# breaks any code that later compares skill sets by exact string match --
# e.g. GitHub verification only ever reports the canonical "react" (there's
# no way to tell from repo language stats whether someone calls it "React"
# or "React.js"), so a candidate whose resume happens to say "React.js"
# would show that skill as permanently "unconfirmed" even though GitHub
# proves the same underlying skill. This map lets any set-comparison code
# collapse known variant spellings to one canonical form before comparing,
# so verification and matching aren't unfairly penalizing a resume for
# using an equally-valid spelling.
SKILL_SYNONYMS = {
    "react.js": "react",
    "vue.js": "vue",
    "express.js": "express",
    "nuxt.js": "nuxt.js",
    "postgres": "postgresql",
    "burpsuite": "burp suite",
    "cyber security": "cybersecurity",
    "pentesting": "penetration testing",
    "computer network": "computer networks",
    "operating system": "operating systems",
    "oops": "oop",
    "object oriented programming": "oop",
    "object-oriented programming": "oop",
    "database management system": "dbms",
    "database management systems": "dbms",
    "restful api": "rest api",
    "google cloud": "gcp",
    "ms office": "microsoft office",
}


def normalize_skill(skill):
    """Lowercase + collapse known synonym spellings to one canonical form.
    Use this before comparing any two skill sets (resume vs GitHub-verified,
    resume vs job-required, etc.) so equivalent skills aren't treated as
    different just because of spelling."""
    s = (skill or "").strip().lower()
    return SKILL_SYNONYMS.get(s, s)

COURSE_DATABASE = {
    "python": ["Python for Everybody (Coursera)", "Complete Python Bootcamp (Udemy)"],
    "javascript": ["JavaScript: The Complete Guide (Udemy)", "Eloquent JavaScript (Book)"],
    "react": ["React - The Complete Guide (Udemy)", "Epic React (Kent C. Dodds)"],
    "machine learning": ["Machine Learning by Andrew Ng (Coursera)", "Fast.ai"],
    "sql": ["SQL Bolt (Interactive)", "Mode Analytics SQL Tutorial"],
    "docker": ["Docker Mastery (Udemy)", "Docker Documentation"],
    "aws": ["AWS Certified Solutions Architect (Udemy)", "A Cloud Guru"],
    "data analysis": ["Google Data Analytics Certificate", "DataCamp"],
}

# Deterministic learning-time estimate, tiered by real, explainable
# complexity rather than a random number presented as fact. Previously this
# called random.randint(2, 8) -- meaning the "estimated time to learn" for
# the exact same skill changed on every single page load, which is not an
# estimate at all, it's noise dressed up as data. A fixed tier is honest:
# it's still a rough heuristic (clearly labeled as such), but at least it's
# the same rough heuristic every time, and its reasoning is inspectable.
SKILL_TIME_TIERS = {
    # Foundational/tooling skills -- typically fastest to get productive in
    "html": "1-2 weeks", "css": "1-2 weeks", "git": "1 week", "sql": "2-3 weeks",
    "communication": "ongoing practice", "linux": "2-3 weeks",
    # Core languages/frameworks -- moderate ramp-up to real productivity
    "python": "3-5 weeks", "javascript": "3-5 weeks", "java": "4-6 weeks",
    "react": "3-4 weeks", "node.js": "3-4 weeks", "docker": "2-4 weeks",
    "figma": "2-3 weeks", "adobe xd": "2-3 weeks",
    # Deeper/specialized skills -- realistically longer to become competent
    "machine learning": "6-10 weeks", "tensorflow": "5-8 weeks", "aws": "5-8 weeks",
    "kubernetes": "5-8 weeks", "data analysis": "4-6 weeks", "computer vision": "6-10 weeks",
}
DEFAULT_TIME_ESTIMATE = "a few weeks of focused practice"


def _estimated_learning_time(skill):
    return SKILL_TIME_TIERS.get(skill.lower().strip(), DEFAULT_TIME_ESTIMATE)


def _extract_pdf_text_pypdf2(file_path):
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception:
        return ""


def _extract_pdf_text_pdfplumber(file_path):
    """pdfplumber handles multi-column layouts and text-frame-based PDFs
    (very common in Canva/visually-designed resume templates) noticeably
    better than PyPDF2, which frequently returns empty or scrambled text
    for those. Used as a fallback, not the default, since it's slower."""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
        return text
    except Exception:
        return ""


def parse_resume(file_path, file_type):
    text = ""
    extraction_warning = None
    try:
        if file_type == "txt":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        elif file_type == "pdf":
            text = _extract_pdf_text_pypdf2(file_path)
            # If the primary extractor got suspiciously little text, this is
            # almost always a visually-designed PDF (text boxes/columns) or a
            # scanned image -- try a second extraction method before giving up.
            if len(text.strip()) < 60:
                fallback_text = _extract_pdf_text_pdfplumber(file_path)
                if len(fallback_text.strip()) > len(text.strip()):
                    text = fallback_text
            if len(text.strip()) < 60:
                extraction_warning = (
                    "We could only extract a small amount of readable text from this PDF. "
                    "This usually means it's a scanned image or uses a heavily graphical template "
                    "that hides real text behind design elements. For accurate ATS scoring and skill "
                    "detection, try re-exporting it as a text-based PDF, or upload a DOCX/TXT version instead."
                )
        elif file_type == "docx":
            try:
                from docx import Document
                doc = Document(file_path)
                for para in doc.paragraphs:
                    text += para.text + "\n"
                # Also pull text out of tables -- many resume templates put the
                # skills/experience section inside a table, which python-docx's
                # paragraph loop above silently skips.
                for table in doc.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            text += cell.text + "\n"
            except Exception:
                extraction_warning = "We couldn't read this DOCX file. Please try re-saving it or upload a PDF/TXT version instead."
    except Exception as e:
        text = ""
        extraction_warning = f"Error parsing file: {str(e)}"

    # Normalize whitespace/line breaks so skill matching isn't broken by PDFs
    # that insert stray spaces or line breaks mid-word (a common PyPDF2 quirk).
    normalized_text = re.sub(r"[ \t]+", " ", text)
    text_lower = normalized_text.lower()

    # Single/double-letter skill names collide with common English patterns
    # that a plain alnum word-boundary doesn't catch, because '&' and '-'
    # aren't alphanumeric and so still count as a "boundary": "R&D" reads as
    # standalone "R" (the language), "go-getter"/"go-to" reads as standalone
    # "Go" (the language), and "A, B, C" grade/option lists read as
    # standalone "C". These are real, verified false positives -- not
    # hypothetical -- confirmed by testing real resume phrasing. For these
    # specific ambiguous tokens, '&' and '-' are excluded from counting as
    # valid boundaries on top of the normal alnum check.
    AMBIGUOUS_SHORT_SKILLS = {"c", "r", "go"}

    found_skills = []
    for skill in SKILL_DATABASE:
        skill_lower = skill.lower()
        if skill_lower in _SPECIAL_SKILLS:
            # Symbol-bearing skills (c++, node.js, etc.) -- plain substring
            # match is safest since \b doesn't reliably bound on '.', '+', '#'.
            if skill_lower in text_lower:
                found_skills.append(skill.title())
        elif skill_lower in AMBIGUOUS_SHORT_SKILLS:
            if re.search(r"(?<![a-z0-9&\-])" + re.escape(skill_lower) + r"(?![a-z0-9&\-])", text_lower):
                found_skills.append(skill.title())
        else:
            # Word-boundary match avoids false positives like "Java" matching
            # inside "JavaScript", or "go" matching inside "algorithm".
            if re.search(r"(?<![a-z0-9])" + re.escape(skill_lower) + r"(?![a-z0-9])", text_lower):
                found_skills.append(skill.title())
    # De-duplicate while preserving first-seen order
    found_skills = list(dict.fromkeys(found_skills))

    experience_years = 0
    year_patterns = re.findall(r"(\d{4})\s*[-—]\s*(\d{4}|present|current)", text_lower)
    for start, end in year_patterns:
        try:
            start_year = int(start)
            end_year = datetime.utcnow().year if end in ["present", "current"] else int(end)
            experience_years += (end_year - start_year)
        except:
            pass

    if experience_years == 0:
        exp_match = re.search(r"(\d+)\+?\s*years?\s*(?:of\s*)?experience", text_lower)
        if exp_match:
            experience_years = int(exp_match.group(1))

    education = []
    edu_keywords = ["bachelor", "master", "phd", "degree", "university", "college", "b.tech", "m.tech", "b.e.", "diploma"]
    for keyword in edu_keywords:
        if keyword in text_lower:
            lines = normalized_text.split("\n")
            for line in lines:
                if keyword in line.lower() and len(line.strip()) > 10:
                    education.append(line.strip())
                    break

    skill_categories = {
        "Programming": [s for s in found_skills if s.lower() in ["python", "javascript", "typescript", "java", "c++", "c#", "c", "go", "rust", "ruby", "php", "kotlin", "swift", "dart", "scala"]],
        "Web Development": [s for s in found_skills if s.lower() in ["html", "css", "react", "react.js", "angular", "vue", "vue.js", "node.js", "next.js", "express", "express.js", "django", "flask"]],
        "Data Science": [s for s in found_skills if s.lower() in ["machine learning", "deep learning", "tensorflow", "pytorch", "pandas", "numpy", "scikit-learn", "data science", "nlp", "computer vision"]],
        "Cloud & DevOps": [s for s in found_skills if s.lower() in ["aws", "azure", "gcp", "docker", "kubernetes", "jenkins", "terraform", "ansible", "ci/cd"]],
        "Databases": [s for s in found_skills if s.lower() in ["sql", "mysql", "postgresql", "postgres", "mongodb", "redis", "firebase", "sqlite"]],
        "Security": [s for s in found_skills if s.lower() in ["nmap", "nikto", "wireshark", "burp suite", "burpsuite", "dvwa", "owasp",
            "owasp top 10", "metasploit", "kali linux", "penetration testing", "pentesting", "vulnerability assessment",
            "incident response", "siem", "firewall", "ids/ips", "vapt", "threat detection", "threat intelligence",
            "malware analysis", "digital forensics", "soc analyst", "risk assessment", "cyber security", "cybersecurity",
            "ethical hacking", "network security", "cryptography"]],
        "Soft Skills": [s for s in found_skills if s.lower() in ["communication", "leadership", "teamwork", "problem solving", "time management", "adaptability", "critical thinking"]]
    }

    if not found_skills and not extraction_warning and len(normalized_text.strip()) > 60:
        extraction_warning = ("We extracted text from this file but didn't recognize any skills from our "
                               "skill list. Try listing skills clearly under a \"Skills\" heading, separated by "
                               "commas or bullet points.")

    # Apply the fallback once, before it's used anywhere -- previously the
    # summary sentence below used the raw (possibly 0) value while the
    # returned "experience_years" field applied a silent "or 1" fallback,
    # so the summary text and the stored number could disagree (e.g. the
    # sentence saying "0+ years" while experience_years was actually 1).
    final_experience_years = experience_years or 1

    return {
        "text": normalized_text,
        "skills": found_skills,
        "experience": list(set(education))[:3] if education else ["Experience details extracted"],
        "education": list(set(education))[:3] if education else ["Education details extracted"],
        "summary": f"Professional with {final_experience_years}+ years of experience. Skilled in {', '.join(found_skills[:5]) if found_skills else 'various technologies'}.",
        "skill_categories": skill_categories,
        "experience_years": final_experience_years,
        "extraction_warning": extraction_warning
    }

def calculate_ats_score(parsed_data):
    # Fix (Aug 2026): the previous version started every resume at a flat
    # 50-point base and handed out large, easily-saturated bonuses on top
    # (+8 per section just for a keyword appearing anywhere, +10 for any
    # 10+ skills, +5/+5 for length/verbs). That meant almost any resume
    # with basic sections and a decent skill list capped out at 100
    # regardless of actual quality, while even a near-empty, one-line
    # resume ("I am looking for a job... Skills: Python, Excel") still
    # scored 66 -- the score wasn't discriminating between resumes at
    # all, it was just confirming a file had text in it.
    #
    # This version builds the score up from 0 across weighted dimensions,
    # tiers the skill/length/action-verb credit instead of using a single
    # pass/fail threshold, and adds a real quantifiable-achievement check
    # (numbers/percentages/metrics tied to concrete outcomes) plus a
    # penalty for generic buzzword filler with no evidence behind it.
    #
    # It also now returns a full point-by-point "breakdown" alongside the
    # score. No resume-scoring system -- this one included -- has a single
    # objectively "correct" score; what makes a score trustworthy instead
    # is that it's the same every time for the same resume (this function
    # has zero randomness) and that every point is traceable to a named,
    # inspectable rule rather than a black box. The breakdown below is
    # exactly the arithmetic that produced the final number, in order.
    score = 0
    feedback = []
    breakdown = []
    text = parsed_data.get("text", "").lower()
    skills = parsed_data.get("skills", [])

    # If text extraction largely failed, say so plainly instead of just
    # silently scoring a near-empty document low -- that reads as a bug,
    # not as "your resume needs work."
    if parsed_data.get("extraction_warning"):
        feedback.append(parsed_data["extraction_warning"])

    # --- Section presence (30 pts total, weighted by how much each
    # section actually matters to a recruiter/ATS) ---
    section_weights = [
        ("Contact Info", ["email", "phone", "address", "linkedin"], 5),
        ("Summary", ["summary", "objective", "profile"], 5),
        ("Experience", ["experience", "work history", "employment"], 10),
        ("Education", ["education", "degree", "university"], 5),
        ("Skills", ["skills", "technologies", "competencies"], 5),
    ]
    sections_earned = 0
    sections_max = sum(w for _, _, w in section_weights)
    for section, keywords, weight in section_weights:
        if any(kw in text for kw in keywords):
            score += weight
            sections_earned += weight
        else:
            feedback.append(f"Missing or unclear {section} section")
    breakdown.append(f"Sections present (Contact/Summary/Experience/Education/Skills): {sections_earned}/{sections_max}")

    # --- Skill depth (0-20 pts, tiered instead of one threshold) ---
    skill_count = len(skills)
    if skill_count >= 15:
        skill_pts = 20
    elif skill_count >= 10:
        skill_pts = 15
    elif skill_count >= 6:
        skill_pts = 10
        feedback.append("Add more relevant skills (aim for 10+)")
    elif skill_count >= 3:
        skill_pts = 5
        feedback.append("Add more relevant skills (aim for 10+)")
    else:
        skill_pts = 0
        feedback.append("Skills section is too sparse")
    score += skill_pts
    breakdown.append(f"Skills detected ({skill_count} found): {skill_pts}/20")

    # --- Length (0-10 pts; too long is penalized too, not just too short) ---
    word_count = len(text.split())
    if 350 <= word_count <= 900:
        length_pts = 10
    elif 150 <= word_count < 350:
        length_pts = 5
        feedback.append("Resume is a bit thin -- add more concrete detail (aim for 350+ words)")
    elif word_count > 900:
        length_pts = 5
        feedback.append("Resume may be too long/dense for a quick recruiter scan")
    else:
        length_pts = 0
        feedback.append("Resume is too short. Aim for 300+ words")
    score += length_pts
    breakdown.append(f"Length ({word_count} words): {length_pts}/10")

    # --- Action verbs (0-10 pts, scaled by variety rather than a single
    # >=3 threshold that every resume with a paragraph of prose clears) ---
    action_verbs = ["developed", "managed", "created", "implemented", "designed", "led", "built",
                     "optimized", "launched", "automated", "architected", "reduced", "increased",
                     "improved", "delivered", "spearheaded", "migrated", "deployed"]
    action_count = sum(1 for verb in action_verbs if verb in text)
    action_pts = min(10, action_count * 2)
    score += action_pts
    if action_count < 3:
        feedback.append("Use more action verbs")
    breakdown.append(f"Action verbs ({action_count} distinct found): {action_pts}/10")

    # --- Quantifiable achievements (0-20 pts) -- the strongest real signal
    # of resume quality and the thing the old scorer never checked at all.
    # Looks for a number/percent next to achievement-style units, not just
    # any digit (so a phone number or a year range doesn't count).
    metric_pattern = re.compile(
        r"(\d+(\.\d+)?\s*%|\$\s?\d+|\d+\+?\s*(?:x|percent|users|customers|clients|projects|hours|"
        r"days|weeks|months|million|thousand|lakh|crore|k\b))"
    )
    metric_hits = len(metric_pattern.findall(text))
    if metric_hits >= 3:
        metric_pts = 20
    elif metric_hits >= 1:
        metric_pts = 10
        feedback.append("Add more quantifiable achievements (numbers, percentages, metrics)")
    else:
        metric_pts = 0
        feedback.append("Add quantifiable achievements, e.g. \"reduced load time by 30%\" or \"served 500+ users\"")
    score += metric_pts
    breakdown.append(f"Quantifiable achievements ({metric_hits} found): {metric_pts}/20")

    # --- Impact bonus (0-5 pts): rewards resumes that combine real action
    # verbs with real metrics -- i.e. describe outcomes, not just duties.
    impact_bonus = 5 if (action_count >= 3 and metric_hits >= 2) else 0
    score += impact_bonus
    breakdown.append(f"Impact bonus (action verbs + metrics together): {impact_bonus}/5")

    # --- Generic buzzword penalty: resumes that lean on vague
    # self-description with zero concrete evidence behind it are a known
    # template/filler pattern and shouldn't score as well as one that backs
    # claims up with specifics.
    buzzwords = ["results-driven", "results driven", "team player", "hard worker",
                 "detail-oriented", "detail oriented", "go-getter", "think outside the box",
                 "synergy", "self-starter", "highly motivated", "passionate about"]
    buzzword_hits = sum(1 for b in buzzwords if b in text)
    buzzword_penalty = 0
    if buzzword_hits >= 2 and metric_hits == 0:
        buzzword_penalty = 10
        score -= buzzword_penalty
        feedback.append("Resume leans on generic buzzwords without concrete evidence -- replace with specific accomplishments")
    if buzzword_penalty:
        breakdown.append(f"Generic buzzword penalty: -{buzzword_penalty}")

    raw_score = score
    score = min(100, max(0, score))
    if parsed_data.get("extraction_warning"):
        # Don't let a parsing failure masquerade as a low-quality resume score
        score = min(score, 40)
    breakdown.append(f"Total: {score}/100" + (f" (raw sum {raw_score}, capped)" if raw_score != score else ""))

    if not feedback:
        feedback = ["Great resume! Well-structured.", "Consider adding quantifiable achievements."]

    # Also fold the breakdown into the feedback list itself, not just the
    # separate "breakdown" key -- the UI (resume_detail.html) only ever
    # renders resume.get_ats_feedback_list(), so without this the exact
    # point-by-point math would be computed but never actually shown to
    # the person looking at their score.
    feedback = feedback + ["— Score breakdown —"] + breakdown

    return {"score": score, "feedback": feedback, "breakdown": breakdown}

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "of", "to", "in", "on", "for", "with", "as", "by", "at",
    "is", "are", "was", "were", "be", "been", "being", "this", "that", "these", "those", "it", "its",
    "we", "you", "your", "our", "will", "would", "should", "can", "could", "may", "might", "must",
    "have", "has", "had", "do", "does", "did", "not", "no", "so", "than", "then", "there", "their",
    "who", "which", "what", "when", "where", "how", "all", "any", "each", "other", "such", "into",
    "about", "up", "out", "over", "under", "again", "further", "here", "also",
}


def match_resume_to_job(resume, job):
    resume_skills = set(normalize_skill(s) for s in resume.get_skills_list())
    required_skills = set(normalize_skill(s) for s in job.get_required_skills_list())
    preferred_skills = set(normalize_skill(s) for s in job.get_preferred_skills_list())

    matching = list(resume_skills & required_skills)
    missing = list(required_skills - resume_skills)
    preferred_matching = list(resume_skills & preferred_skills)

    # A job with NO required skills listed is a data-quality problem on the
    # recruiter's side, not a candidate skill gap. Scoring that as "0% skill
    # match, 0 missing skills, great fit!" (what the old code did) is
    # actively misleading -- it looks like a candidate is a perfect fit when
    # really the job just never specified anything to compare against.
    # We flag this explicitly so the UI can say so honestly instead of
    # guessing a number.
    no_required_skills_specified = len(required_skills) == 0

    if no_required_skills_specified:
        skill_score = 0
    else:
        skill_score = int((len(matching) / len(required_skills)) * 100)

    # Semantic relevance: TF-IDF vectorization + cosine similarity between
    # the resume's full parsed text and the job's text (see
    # app/utils/ml_match.py for the model itself and why this technique was
    # chosen).
    #
    # Fix (Aug 2026): the job-side text used to be *only* the free-text
    # description/requirements paragraphs. That under-represents what the
    # job actually needs, because recruiters write short, casual
    # descriptions and rely on the structured required/preferred skill tags
    # to carry the real specificity. Meanwhile the resume-side text is a
    # candidate's *entire* resume, which for a multi-skilled candidate (e.g.
    # someone with both web-dev and cybersecurity experience) legitimately
    # contains a lot of vocabulary that has nothing to do with any one job
    # posting. Comparing "everything a candidate has ever done" against "a
    # two-sentence job blurb" systematically produces very low cosine
    # similarity even for a candidate who matches every required skill --
    # that's not a meaningful signal, it's an artifact of document-length
    # asymmetry. Folding the job's own skill tags into the comparison text
    # gives TF-IDF real, specific vocabulary to match against, so the score
    # reflects topical relevance rather than penalizing broad, accomplished
    # resumes for having more to say than the job posting does.
    from app.utils.ml_match import compute_semantic_similarity
    job_text_for_matching = " ".join(filter(None, [
        job.title,
        job.description,
        job.requirements,
        " ".join(required_skills),
        " ".join(preferred_skills),
    ]))
    semantic_score = compute_semantic_similarity(resume.parsed_text, job_text_for_matching)

    # Experience fit: previously scored as exp_years / experience_max, which
    # means a candidate who exactly meets the job's stated *minimum*
    # experience -- the actual bar the recruiter set -- could still score as
    # low as 33% just because the job's range extends well above that
    # minimum. That's misleading: meeting a stated minimum should already
    # count as a strong fit, with the score climbing further only as a bonus
    # for experience beyond it, not as the only way to earn credit at all.
    exp_years = resume.experience_years or 0
    min_exp = job.experience_min or 0
    max_exp = job.experience_max or 10
    if exp_years >= max_exp:
        experience_score = 100
    elif exp_years >= min_exp:
        # Meeting the minimum guarantees a strong baseline (70); the
        # remaining 30 points scale up toward the top of the range.
        span = max(max_exp - min_exp, 1)
        experience_score = 70 + int(30 * (exp_years - min_exp) / span)
    else:
        # Below the stated minimum: scale proportionally, capped below the
        # "meets minimum" baseline so under-qualified candidates are still
        # visibly distinguished from those who meet the bar.
        experience_score = max(0, int((exp_years / max(min_exp, 1)) * 65))

    # Overall blend: required-skill match is the most concrete, defensible
    # signal for "does this candidate fit this job" (it's literally what the
    # recruiter marked as required), so it carries the most weight.
    # Semantic relevance is a real but noisier supporting signal -- useful
    # for surfacing topical fit beyond an exact skill-tag match, but not
    # reliable enough to weight as heavily as an explicit skill match.
    # Experience fit sits in between: concrete, but a single data point.
    overall = int((skill_score * 0.55) + (semantic_score * 0.20) + (experience_score * 0.25))

    if no_required_skills_specified:
        recommendation = "incomplete_listing"
    elif overall >= 85:
        recommendation = "strong_match"
    elif overall >= 70:
        recommendation = "good_match"
    elif overall >= 50:
        recommendation = "partial_match"
    else:
        recommendation = "weak_match"

    skill_gaps = []
    for skill in missing[:5]:
        resources = COURSE_DATABASE.get(skill.lower(), ["Coursera", "Udemy", "freeCodeCamp"])
        skill_gaps.append({
            "skill": skill.title(),
            "importance": "high" if skill in required_skills else "medium",
            "resources": resources[:3],
            "estimated_time": _estimated_learning_time(skill)
        })

    if no_required_skills_specified:
        feedback = ("This job listing hasn't specified any required skills yet, so an accurate skill-match "
                     "score can't be calculated. The score shown reflects description relevance and experience "
                     "fit only -- ask the recruiter to add required skills, or check back later.")
    else:
        feedback = f"Match Score: {overall}%. You match {len(matching)} of {len(required_skills)} required skills."

    # ML Confidence: a second, independent opinion from the platform's one
    # genuinely TRAINED supervised model (see train_match_model.py /
    # trained_match_model.py) -- fit against labeled data and persisted to
    # disk, unlike the rule-based overall_score above or the unsupervised
    # TF-IDF semantic_score. Shown as a supplementary cross-check, never as
    # a replacement for overall_score: the honest framing (see that module's
    # docstring) is that it's trained on synthetic labels, not real hiring
    # outcomes, so it should agree with the rule-based score most of the
    # time and is worth a second look when it doesn't -- not treated as a
    # ground-truth prediction.
    from app.utils.trained_match_model import predict_match_confidence
    ml_result = predict_match_confidence(
        skill_score=skill_score,
        semantic_score=semantic_score,
        experience_score=experience_score,
        authenticity_score=getattr(resume, "authenticity_score", None),
    )

    # Skill ontology / knowledge graph: does the candidate hold a *related*
    # skill (same category, e.g. PyTorch for a required scikit-learn) for
    # any skill they're missing outright? See app/utils/skill_ontology.py
    # for why this is scoped as supplementary evidence, not a substitute
    # for an exact skill match.
    from app.utils.skill_ontology import ontology_score, explain_relatedness
    ontology_matches = explain_relatedness(resume_skills, required_skills)
    ontology_score_value = ontology_score(resume_skills, required_skills)

    # Explainable AI: plain-language "main reasons" for the score, and
    # counterfactual "what would improve this" suggestions -- see
    # explain_match() below. Kept as a best-effort addition: if it fails
    # for any reason, the core match result above must still be returned.
    try:
        explanation = explain_match(
            overall=overall,
            skill_score=skill_score,
            semantic_score=semantic_score,
            experience_score=experience_score,
            matching=matching,
            missing=missing,
            no_required_skills_specified=no_required_skills_specified,
            ontology_matches=ontology_matches,
        )
        counterfactuals = counterfactual_suggestions(
            resume_skills=resume_skills,
            required_skills=required_skills,
            missing=missing,
            skill_score=skill_score,
            semantic_score=semantic_score,
            experience_score=experience_score,
            no_required_skills_specified=no_required_skills_specified,
        )
    except Exception:
        explanation = {"reasons": []}
        counterfactuals = []

    return {
        "overall_score": overall,
        "semantic_score": semantic_score,
        "skill_score": skill_score,
        "experience_score": experience_score,
        "ontology_score": ontology_score_value,
        "ontology_matches": ontology_matches,
        "ml_confidence": ml_result["confidence"],
        "ml_model_available": ml_result["model_available"],
        "ml_model_type": ml_result["model_type"],
        "matching_skills": matching + preferred_matching,
        "missing_skills": missing,
        "skill_gaps": skill_gaps,
        "recommendation": recommendation,
        "feedback": feedback,
        "no_required_skills_specified": no_required_skills_specified,
        "explanation_reasons": explanation["reasons"],
        "counterfactuals": counterfactuals,
    }


def explain_match(overall, skill_score, semantic_score, experience_score,
                   matching, missing, no_required_skills_specified,
                   ontology_matches):
    """Turns the score components into a short list of plain-language
    "main reasons" -- e.g. "+ Strong Python/ML match", "- Missing AWS
    certification" -- instead of leaving the person to interpret three
    raw percentages on their own. This is the "traceable decision"
    explainability layer: every bullet here is derived directly from a
    number already computed above, nothing is invented after the fact.
    """
    reasons = []

    if no_required_skills_specified:
        return {"reasons": ["This job hasn't listed required skills yet, so skill-based reasons can't be generated."]}

    if skill_score >= 80:
        reasons.append({"sign": "+", "text": f"Strong skill match ({len(matching)} required skills matched)"})
    elif skill_score >= 50:
        reasons.append({"sign": "+", "text": f"Partial skill match ({len(matching)} required skills matched)"})
    else:
        reasons.append({"sign": "-", "text": "Few required skills matched"})

    if missing:
        shown = ", ".join(m.title() for m in missing[:3])
        reasons.append({"sign": "-", "text": f"Missing: {shown}"})

    if experience_score >= 70:
        reasons.append({"sign": "+", "text": "Experience requirement satisfied"})
    elif experience_score < 40:
        reasons.append({"sign": "-", "text": "Experience below the job's stated range"})

    if semantic_score >= 60:
        reasons.append({"sign": "+", "text": "Resume content closely matches the job description's language"})
    elif semantic_score < 30:
        reasons.append({"sign": "-", "text": "Resume content has limited topical overlap with the job description"})

    if ontology_matches:
        first = ontology_matches[0]
        held = ", ".join(s.title() for s in first["related_skills_held"][:2])
        reasons.append({
            "sign": "~",
            "text": f"Related experience found: {held} is related to the required "
                    f"\"{first['required_skill'].title()}\" ({first['category']})",
        })

    return {"reasons": reasons}


def counterfactual_suggestions(resume_skills, required_skills, missing, skill_score,
                                semantic_score, experience_score, no_required_skills_specified,
                                max_suggestions=3):
    """"What would improve your match?" -- for each missing required skill,
    simulate adding just that one skill and recompute the blended overall
    score, so the candidate sees a concrete "Add Docker -> estimated 76%"
    rather than only being told they're missing something.

    This is a genuine counterfactual (re-running the same scoring formula
    with one input changed), not a guessed number -- it uses the exact
    weighting from match_resume_to_job() above, so if that formula ever
    changes, these projections automatically stay consistent with it.
    """
    if no_required_skills_specified or not missing or not required_skills:
        return []

    suggestions = []
    for skill in missing[:max_suggestions]:
        hypothetical_matching = (set(resume_skills) | {skill}) & set(required_skills)
        hypothetical_skill_score = int((len(hypothetical_matching) / len(required_skills)) * 100)
        hypothetical_overall = int(
            (hypothetical_skill_score * 0.55) + (semantic_score * 0.20) + (experience_score * 0.25)
        )
        suggestions.append({
            "skill": skill.title(),
            "estimated_overall_score": min(100, hypothetical_overall),
        })

    # Most-impactful suggestion first.
    suggestions.sort(key=lambda s: s["estimated_overall_score"], reverse=True)
    return suggestions

def generate_career_roadmap(target_role, target_industry, current_skills):
    target_skills = {
        "software engineer": ["python", "javascript", "git", "sql", "docker", "aws"],
        "data scientist": ["python", "machine learning", "sql", "pandas", "tensorflow", "statistics"],
        "devops engineer": ["docker", "kubernetes", "aws", "jenkins", "linux", "python"],
        "frontend developer": ["javascript", "react", "html", "css", "typescript", "webpack"],
        "backend developer": ["python", "java", "sql", "docker", "redis", "microservices"],
        "full stack developer": ["javascript", "python", "react", "node.js", "sql", "docker"],
        "product manager": ["communication", "leadership", "agile", "jira", "data analysis", "strategy"],
        "ux designer": ["figma", "adobe xd", "user research", "prototyping", "html", "css"],
    }

    role_lower = target_role.lower()
    needed_skills = target_skills.get(role_lower, ["python", "communication", "problem solving", "teamwork"])

    current_set = set(s.lower() for s in current_skills)
    gaps = [s for s in needed_skills if s not in current_set]

    readiness = max(0, 100 - int((len(gaps) / max(len(needed_skills), 1)) * 100))

    milestones = [
        {"title": "Foundation", "description": "Learn core concepts and tools", "duration": "1-2 months", "completed": readiness > 30},
        {"title": "Skill Building", "description": "Develop technical skills through projects", "duration": "2-4 months", "completed": readiness > 50},
        {"title": "Portfolio", "description": "Build projects and contribute to open source", "duration": "2-3 months", "completed": readiness > 70},
        {"title": "Job Ready", "description": "Apply to positions and network", "duration": "1-2 months", "completed": readiness > 90}
    ]

    learning_paths = []
    for gap in gaps[:5]:
        resources = COURSE_DATABASE.get(gap, ["Coursera", "Udemy", "YouTube"])
        learning_paths.append({
            "skill": gap.title(),
            "resources": resources[:3],
            "difficulty": "Beginner" if gap in ["html", "css", "communication"] else "Intermediate",
            "estimated_time": _estimated_learning_time(gap)
        })

    # Salary range: reuse the platform's own explainable salary_predictor
    # instead of a second, contradictory random number. This function used
    # to fabricate `random.randint(60, 120)k - random.randint(100, 200)k`
    # (in USD, with the range wide enough to be meaningless) even though
    # app/utils/salary_predictor.py already computes a real, factor-based
    # estimate in INR LPA for the same role -- having two different,
    # unrelated "salary" numbers for the same role on the same platform is
    # confusing and undermines the "explainable, not fabricated" position
    # taken everywhere else in this project.
    from app.utils.salary_predictor import predict_salary
    salary_result = predict_salary(target_role, skills=list(current_set))

    return {
        "readiness_score": readiness,
        "estimated_months": len(gaps) * 2 + 3,
        "milestones": milestones,
        "learning_paths": learning_paths,
        "skill_requirements": [{"skill": s.title(), "level": "Required"} for s in needed_skills],
        "analysis": f"Based on your current skills, you are {readiness}% ready for {target_role}. Focus on: {', '.join(gaps[:3]) if gaps else 'gaining practical experience'}.",
        "market_demand": "high" if len(gaps) <= 2 else ("medium" if len(gaps) <= 4 else "developing"),
        "salary_range": f"\u20b9{salary_result['predicted_min']}-{salary_result['predicted_max']} LPA"
    }
