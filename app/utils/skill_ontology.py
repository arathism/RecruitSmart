"""
Skill Ontology / Knowledge Graph
--------------------------------
Addresses the "your matcher treats skills as unrelated keywords" gap: two
skills that are the same underlying competency (e.g. "scikit-learn" and
"pytorch" are both Machine Learning frameworks; "aws" and "gcp" are both
Cloud Computing platforms) should not be scored as if they had nothing to
do with each other just because the exact strings don't match.

This is intentionally a hand-built, shallow taxonomy (category -> member
skills) rather than a learned embedding space or an external knowledge
base (e.g. ESCO/O*NET). That's a deliberate, defensible scope choice for a
project like this:
  - It's fully inspectable and explainable (you can point at the exact
    tree and say "here is why Docker and Kubernetes are considered
    related"), which matters for the explainability goals elsewhere in
    this codebase (see app/utils/ai_parser.py's counterfactual/reason
    generation).
  - It needs no external data/API dependency and never returns a
    different answer on two different days.
  - It is intentionally NOT a substitute for an exact skill match --
    related-skill credit is capped low (see ONTOLOGY_RELATED_CREDIT) so a
    candidate who has PyTorch but not TensorFlow is shown as "related
    experience found", not silently counted as if they listed the exact
    required skill.

If you want to compare this against a "real" research-grade ontology, the
honest framing for a report/paper is: "we implement our own lightweight
category-based ontology rather than adopting an existing knowledge graph
such as ESCO, and this is a scope limitation" -- don't claim it's
equivalent to a learned/curated industry taxonomy.
"""

# Category -> member skills (normalized, lowercase, matches the spellings
# produced by app.utils.ai_parser.normalize_skill).
SKILL_ONTOLOGY = {
    "Machine Learning": [
        "machine learning", "deep learning", "scikit-learn", "tensorflow",
        "pytorch", "keras", "xgboost", "computer vision", "nlp",
        "natural language processing", "artificial intelligence",
    ],
    "Cloud Computing": [
        "aws", "azure", "gcp", "google cloud", "firebase", "terraform",
        "kubernetes", "docker",
    ],
    "Data Engineering / Analysis": [
        "sql", "mysql", "postgresql", "mongodb", "data analysis",
        "data visualization", "data science", "big data", "spark",
        "hadoop", "pandas", "numpy", "tableau", "power bi", "excel",
        "statistics",
    ],
    "Frontend Development": [
        "html", "css", "sass", "scss", "tailwind", "bootstrap", "react",
        "angular", "vue", "next.js", "svelte", "jquery", "redux",
    ],
    "Backend Development": [
        "node.js", "express", "django", "flask", "fastapi", "spring",
        "spring boot", "laravel", ".net", "asp.net", "ruby on rails",
        "nestjs", "microservices", "api development", "rest api",
    ],
    "Programming Languages": [
        "python", "javascript", "typescript", "java", "c++", "c#", "c",
        "go", "rust", "ruby", "php", "kotlin", "swift", "dart", "scala",
    ],
    "DevOps / Infrastructure": [
        "docker", "kubernetes", "jenkins", "ci/cd", "terraform",
        "ansible", "nginx", "linux", "bash", "shell scripting",
        "github actions", "gitlab ci",
    ],
    "Mobile Development": [
        "android", "ios", "flutter", "react native", "xamarin", "swift",
        "kotlin",
    ],
    "Cybersecurity": [
        "cybersecurity", "network security", "cryptography",
        "penetration testing", "nmap", "wireshark", "burp suite",
        "metasploit", "kali linux", "vulnerability assessment", "siem",
        "digital forensics", "owasp",
    ],
    "Testing / QA": [
        "selenium", "junit", "pytest", "jest", "cypress",
        "manual testing", "automation testing", "test automation",
        "unit testing", "software testing",
    ],
    "Project / Process": [
        "project management", "agile", "scrum", "kanban",
        "product management",
    ],
}

# Cap on how much of a "required skill" a related-but-not-exact skill can
# earn. Kept deliberately low -- this is supporting evidence, not a
# substitute for the real thing.
ONTOLOGY_RELATED_CREDIT = 0.4

_SKILL_TO_CATEGORY = {}
for _category, _skills in SKILL_ONTOLOGY.items():
    for _skill in _skills:
        # A skill can legitimately sit in more than one category (e.g.
        # "docker" is both Cloud Computing and DevOps); keep all of them.
        _SKILL_TO_CATEGORY.setdefault(_skill, []).append(_category)


def categories_for_skill(skill):
    """Returns the list of ontology categories a (normalized) skill
    belongs to, or [] if it isn't in the taxonomy at all."""
    return _SKILL_TO_CATEGORY.get((skill or "").strip().lower(), [])


def related_skills(skill, exclude_self=True):
    """Returns the set of other skills that share a category with `skill`."""
    skill = (skill or "").strip().lower()
    related = set()
    for category in categories_for_skill(skill):
        related.update(SKILL_ONTOLOGY[category])
    if exclude_self:
        related.discard(skill)
    return related


def explain_relatedness(resume_skills, required_skills):
    """Given a candidate's normalized skill set and a job's normalized
    required-skill set, find required skills that are NOT directly held
    but where the candidate holds something in the same ontology category.

    Returns a list of dicts, one per such required skill:
        {
          "required_skill": "pytorch",
          "category": "Machine Learning",
          "related_skills_held": ["scikit-learn", "tensorflow"],
        }

    This is the data behind the "RecruitSmart can understand that these
    are related, rather than treating them as unrelated keywords" UI copy.
    """
    resume_skills = {s.strip().lower() for s in resume_skills}
    required_skills = {s.strip().lower() for s in required_skills}
    directly_missing = required_skills - resume_skills

    explanations = []
    for req in sorted(directly_missing):
        categories = categories_for_skill(req)
        if not categories:
            continue
        for category in categories:
            held_in_category = sorted(
                (set(SKILL_ONTOLOGY[category]) & resume_skills) - {req}
            )
            if held_in_category:
                explanations.append({
                    "required_skill": req,
                    "category": category,
                    "related_skills_held": held_in_category,
                })
                break  # one explanation per missing skill is plenty
    return explanations


def ontology_score(resume_skills, required_skills):
    """0-100 score representing how much of the required-skill list is
    covered either exactly OR by a related skill in the same ontology
    category (at ONTOLOGY_RELATED_CREDIT partial credit).

    Deliberately separate from the exact-match skill_score already
    computed in app.utils.ai_parser.match_resume_to_job -- this is a
    *supplementary* signal for the explanation UI and a small nudge to the
    blended overall score, not a replacement for exact-match scoring.
    """
    resume_skills = {s.strip().lower() for s in resume_skills}
    required_skills = {s.strip().lower() for s in required_skills}
    if not required_skills:
        return 0

    total_credit = 0.0
    for req in required_skills:
        if req in resume_skills:
            total_credit += 1.0
        else:
            related = related_skills(req) & resume_skills
            if related:
                total_credit += ONTOLOGY_RELATED_CREDIT
    return int(round((total_credit / len(required_skills)) * 100))
