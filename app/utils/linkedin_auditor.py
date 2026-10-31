"""
LinkedIn Profile Auditor
--------------------------
IMPORTANT, state this plainly if asked: this does NOT scrape or fetch data
from LinkedIn. LinkedIn's Terms of Service prohibit automated scraping, and
there's no public API for reading arbitrary profiles. Instead, the candidate
pastes their own profile sections (headline, About, one experience entry)
directly into a form, and this module runs the same kind of rule-based
completeness/quality checks a career coach would do manually -- headline
quality, About-section presence and length, quantifiable achievements in
experience bullets, and skill count -- then produces a score, a one-line
"recruiter's first impression," and a prioritized checklist of the highest-
impact fixes.
"""
import re

GENERIC_HEADLINE_PATTERNS = [
    r"^student at", r"^looking for", r"^seeking opportunities",
    r"^aspiring", r"^undergraduate at", r"^b\.?e\.? (student|in)",
]

CONCRETE_SIGNAL_PATTERN = re.compile(
    r"(\d+%|\$\d|\d+x\b|\bincreased\b|\bdecreased\b|\breduced\b|\bimproved\b|"
    r"\bbuilt\b|\bshipped\b|\bdeployed\b|\bled\b|\d+\s*(users|teams|projects|members))",
    re.IGNORECASE,
)


URL_ONLY_PATTERN = re.compile(r"^https?://\S+$")


def is_url_only(text):
    """True if the pasted text is just a bare URL (or a URL plus a couple
    stray words) with no real profile content -- which is exactly zero
    text for the auditor to analyze. This is the honest, correct response
    to that case: explain why a link alone can't be audited, rather than
    silently scoring an empty profile and showing a misleadingly low
    result as if it reflected the real profile."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    words = stripped.split()
    if len(words) <= 3 and any(URL_ONLY_PATTERN.match(w) or "linkedin.com" in w for w in words):
        return True
    return False


SECTION_MARKERS = ["about", "experience", "education", "skills", "licenses & certifications",
                    "licenses and certifications", "projects", "recommendations", "activity", "interests"]


def parse_full_profile_text(raw_text):
    """Best-effort auto-split of a whole pasted LinkedIn profile (e.g. from
    selecting and copying the entire profile page) into headline/About/
    experience/skills-count, using LinkedIn's own section header words
    ("About", "Experience", "Skills"...) as split points. LinkedIn's
    copy-paste output varies by browser and profile settings, so this is
    a heuristic, not a guaranteed-perfect parse -- the individual fields
    below remain available so a candidate can correct anything that came
    out wrong."""
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    lower_lines = [l.lower() for l in lines]

    section_indices = {}
    for i, l in enumerate(lower_lines):
        for marker in SECTION_MARKERS:
            if l == marker or l.startswith(marker + " "):
                if marker not in section_indices:
                    section_indices[marker] = i
                break

    about_idx = section_indices.get("about")
    stop_idx = about_idx if about_idx is not None else section_indices.get("experience", len(lines))
    headline_candidates = lines[1:stop_idx] if stop_idx and stop_idx > 1 else []
    headline = headline_candidates[0] if headline_candidates else (lines[0] if lines else "")

    about_text = ""
    if about_idx is not None:
        exp_idx = section_indices.get("experience", len(lines))
        about_text = " ".join(lines[about_idx + 1:exp_idx])

    experience_text = ""
    exp_idx = section_indices.get("experience")
    if exp_idx is not None:
        later_idxs = [v for v in section_indices.values() if v > exp_idx]
        end_idx = min(later_idxs) if later_idxs else len(lines)
        experience_text = " ".join(lines[exp_idx + 1:end_idx])

    skills_count = 0
    skills_idx = section_indices.get("skills")
    if skills_idx is not None:
        later_idxs = [v for v in section_indices.values() if v > skills_idx]
        end_idx = min(later_idxs) if later_idxs else len(lines)
        skills_count = len(lines[skills_idx + 1:end_idx])

    return {
        "headline": headline,
        "about_text": about_text,
        "experience_text": experience_text,
        "skills_count": skills_count,
    }


def audit_linkedin_profile(headline="", about_text="", experience_text="", skills_count=0):
    """Returns: {score, impression, quick_wins: [ {priority, text}, ... ], breakdown}"""
    quick_wins = []
    score = 0
    breakdown = {}

    # --- Headline (0-20 points) ---
    headline = (headline or "").strip()
    headline_lower = headline.lower()
    is_generic = any(re.search(p, headline_lower) for p in GENERIC_HEADLINE_PATTERNS)
    if not headline:
        breakdown["headline"] = 0
        quick_wins.append({"priority": 1, "text": "Add a headline. This is the single most-viewed part of your profile — a blank or default one costs you the most visibility."})
    elif is_generic or len(headline) < 20:
        breakdown["headline"] = 8
        score += 8
        quick_wins.append({"priority": 1, "text": "Rewrite your headline to name specific skills/roles (e.g. \"CS Student | Cybersecurity & Full-Stack Dev | Python, React\") instead of just your job title or school."})
    else:
        breakdown["headline"] = 20
        score += 20

    # --- About section (0-25 points) ---
    about_text = (about_text or "").strip()
    about_words = len(about_text.split())
    if not about_text:
        breakdown["about"] = 0
        quick_wins.append({"priority": 1, "text": "Add an About section. Profiles without one read as incomplete/inactive to recruiters within seconds."})
    elif about_words < 40:
        breakdown["about"] = 10
        score += 10
        quick_wins.append({"priority": 2, "text": f"Your About section is quite short ({about_words} words). Aim for 3-5 sentences covering who you are, what you've built, and what you're looking for."})
    else:
        breakdown["about"] = 25
        score += 25

    # --- Experience quality (0-30 points) ---
    experience_text = (experience_text or "").strip()
    exp_words = len(experience_text.split())
    concrete_hits = len(CONCRETE_SIGNAL_PATTERN.findall(experience_text))
    if not experience_text:
        breakdown["experience"] = 0
        quick_wins.append({"priority": 1, "text": "Add at least one experience or project entry with a few bullet points describing what you did."})
    elif concrete_hits == 0 and exp_words > 10:
        breakdown["experience"] = 12
        score += 12
        quick_wins.append({"priority": 2, "text": "Your experience bullets don't mention any numbers or concrete outcomes yet. Add specifics — \"reduced load time by 30%\" beats \"improved performance.\""})
    else:
        breakdown["experience"] = min(30, 15 + concrete_hits * 5)
        score += breakdown["experience"]

    # --- Skills count (0-25 points) ---
    skills_count = skills_count or 0
    if skills_count == 0:
        breakdown["skills"] = 0
        quick_wins.append({"priority": 2, "text": "List your skills on your profile. Profiles with 15+ skills get significantly more recruiter searches to match against."})
    elif skills_count < 15:
        breakdown["skills"] = 12
        score += 12
        quick_wins.append({"priority": 3, "text": f"You have {skills_count} skills listed — LinkedIn's own data shows profiles with 15+ skills get more recruiter searches. Add more of your actual tools/languages."})
    else:
        breakdown["skills"] = 25
        score += 25

    score = min(100, score)

    # --- Recruiter's 10-second impression ---
    if score >= 80:
        impression = "This profile reads as a credible, specific, and complete professional identity — a recruiter would understand what you do and where you'd fit within seconds."
    elif score >= 50:
        impression = "This candidate has real substance but the profile doesn't fully showcase it yet — a recruiter would need to dig to understand the full picture."
    else:
        impression = "This profile currently reads as thin or incomplete. A recruiter skimming for 10 seconds would likely move on without a strong impression either way."

    quick_wins.sort(key=lambda w: w["priority"])

    return {
        "score": score,
        "impression": impression,
        "quick_wins": quick_wins[:5],
        "breakdown": breakdown,
    }
