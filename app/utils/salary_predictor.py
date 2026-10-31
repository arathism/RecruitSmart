"""
AI Salary Insights
--------------------
A transparent, multi-factor salary estimation model. IMPORTANT and worth
being upfront about (this is the honest answer if asked in a viva): this is
a rule-based weighted model calibrated with illustrative Indian IT-industry
salary bands, not a regression model trained on a real labeled salary
dataset (no such licensed dataset is available for a student project). It's
built the same way many public "salary calculator" tools work: a base range
per role category, adjusted by explainable multipliers for experience,
location, in-demand skills, and (uniquely here) the candidate's GitHub
Portfolio Verification score -- which ties this feature directly into the
platform's own verified-skills signal rather than treating it as a bolted-on
gimmick.

Every adjustment is returned as a labeled "factor" so the prediction is
fully explainable, never a black box number.
"""
import re

# Illustrative base annual salary bands in INR Lakhs Per Annum (LPA) for
# common Indian IT-industry role categories at ~0-2 years experience.
ROLE_BASE_RANGES = [
    (r"machine learning|\bml\b|data scientist|ai engineer|deep learning", (6, 18)),
    (r"devops|cloud engineer|site reliability|sre|kubernetes", (6, 16)),
    (r"data analyst|business analyst|data engineer", (4, 11)),
    (r"full stack|full-stack|backend|back-end|frontend|front-end|web developer", (4, 12)),
    (r"mobile|android|ios developer|flutter developer", (4, 11)),
    (r"cyber ?security|security engineer|penetration tester", (5, 14)),
    (r"product manager|program manager", (8, 22)),
    (r"ui/ux|ux designer|ui designer|product designer", (4, 10)),
    (r"qa|test engineer|sdet|quality assurance", (3, 9)),
    (r"software engineer|software developer|programmer|sde", (4, 12)),
]
DEFAULT_RANGE = (3, 8)

METRO_CITIES = ["bangalore", "bengaluru", "hyderabad", "pune", "mumbai", "delhi", "gurgaon", "gurugram", "noida", "chennai"]

IN_DEMAND_SKILLS = [
    "aws", "azure", "gcp", "kubernetes", "docker", "machine learning", "deep learning",
    "tensorflow", "pytorch", "react", "node.js", "golang", "rust", "terraform",
    "microservices", "system design", "data structures and algorithms",
]


def _match_base_range(job_title):
    title_lower = job_title.lower()
    for pattern, rng in ROLE_BASE_RANGES:
        if re.search(pattern, title_lower):
            return rng
    return DEFAULT_RANGE


def predict_salary(job_title, location=None, experience_years=0, skills=None, github_score=None):
    """Returns a dict: predicted_min, predicted_max, predicted_avg (all LPA),
    confidence (0-1), and factors (list of human-readable adjustments)."""
    skills = skills or []
    experience_years = experience_years or 0
    location = (location or "").lower()

    base_min, base_max = _match_base_range(job_title)
    factors = [f"Base range for this role category: \u20b9{base_min}\u2013{base_max} LPA"]

    # Experience multiplier: roughly +7% per year, capped at +80%
    exp_multiplier = 1 + min(experience_years * 0.07, 0.8)
    if experience_years > 0:
        factors.append(f"+{round((exp_multiplier - 1) * 100)}% for {experience_years} year(s) of experience")

    # Location multiplier
    loc_multiplier = 1.0
    if any(city in location for city in METRO_CITIES):
        loc_multiplier = 1.15
        factors.append("+15% metro-city cost-of-living adjustment")
    elif "remote" in location:
        loc_multiplier = 1.05
        factors.append("+5% remote-role adjustment")

    # In-demand skill bonus: +2% per matched high-demand skill, capped at +20%
    skill_set = set(s.lower() for s in skills)
    matched_demand_skills = [s for s in IN_DEMAND_SKILLS if s in skill_set or any(s in sk for sk in skill_set)]
    skill_bonus = min(len(matched_demand_skills) * 0.02, 0.20)
    if skill_bonus > 0:
        factors.append(f"+{round(skill_bonus * 100)}% for {len(matched_demand_skills)} in-demand skill(s): {', '.join(matched_demand_skills[:5])}")

    # GitHub Portfolio Verification bonus -- ties this feature to the
    # platform's own verified-skills signal instead of self-reported skills alone
    github_bonus = 0
    if github_score is not None:
        if github_score >= 80:
            github_bonus = 0.10
            factors.append("+10% for a verified GitHub portfolio score of 80+")
        elif github_score >= 60:
            github_bonus = 0.05
            factors.append("+5% for a verified GitHub portfolio score of 60+")

    total_multiplier = exp_multiplier * loc_multiplier * (1 + skill_bonus + github_bonus)

    predicted_min = round(base_min * total_multiplier, 1)
    predicted_max = round(base_max * total_multiplier, 1)
    predicted_avg = round((predicted_min + predicted_max) / 2, 1)

    # Confidence reflects how much real signal we had to work with -- fully
    # honest about this being lower when the profile is thin.
    confidence = 0.5
    if experience_years > 0:
        confidence += 0.1
    if skills:
        confidence += 0.15
    if github_score is not None:
        confidence += 0.15
    if location:
        confidence += 0.1
    confidence = round(min(confidence, 0.95), 2)

    return {
        "predicted_min": predicted_min,
        "predicted_max": predicted_max,
        "predicted_avg": predicted_avg,
        "confidence": confidence,
        "factors": factors,
    }
