"""Tests for GitHub Portfolio Verification (app/utils/github_verifier.py) --
specifically the resume-vs-GitHub skill cross-referencing that produces the
"Confirmed by Code" / "Unconfirmed Claims" panels and the Authenticity %
shown on /candidate/github-verify."""
from app.utils.ai_parser import normalize_skill
from app.utils.github_verifier import compute_portfolio_score, cross_reference_resume_skills


class TestNormalizeSkill:
    def test_known_variant_spellings_collapse_to_canonical_form(self):
        assert normalize_skill("React.js") == "react"
        assert normalize_skill("react.js") == "react"
        assert normalize_skill("Express.JS") == "express"
        assert normalize_skill("Vue.js") == "vue"
        assert normalize_skill("Postgres") == "postgresql"

    def test_unrelated_skill_is_just_lowercased(self):
        assert normalize_skill("Python") == "python"
        assert normalize_skill("  Docker  ") == "docker"

    def test_empty_input_returns_empty_string(self):
        assert normalize_skill("") == ""
        assert normalize_skill(None) == ""


class TestCrossReferenceResumeSkills:
    def test_variant_spelling_is_confirmed_when_canonical_form_is_verified(self):
        """Regression test: a resume listing 'React.js' must be counted as
        confirmed when GitHub verification found 'react' -- they're the same
        skill. Previously these were compared as raw strings, so 'React.js'
        showed up as permanently unconfirmed even when the underlying skill
        was proven by real code."""
        resume_skills = ["react.js", "python"]
        verified_skills = ["react", "python"]

        result = cross_reference_resume_skills(resume_skills, verified_skills)
        assert "react" in result["confirmed_skills"]
        assert not any("react" in s for s in result["unconfirmed_skills"])
        assert result["authenticity_rate"] == 100

    def test_both_spellings_on_resume_do_not_double_count(self):
        """If a resume somehow has both 'react' and 'react.js' as separate
        extracted tags, they should collapse to one skill for scoring
        purposes, not inflate the denominator and drag the rate down."""
        resume_skills = ["react", "react.js", "python"]
        verified_skills = ["react", "python"]

        result = cross_reference_resume_skills(resume_skills, verified_skills)
        assert result["authenticity_rate"] == 100

    def test_genuinely_unverifiable_skill_still_shows_unconfirmed(self):
        """Skills GitHub's API genuinely can't confirm (e.g. tools like Nmap
        or soft claims like 'Cybersecurity') should still show as
        unconfirmed -- the fix is about not double-penalizing spelling
        variants, not about inflating scores generally."""
        resume_skills = ["python", "nmap", "cybersecurity"]
        verified_skills = ["python"]

        result = cross_reference_resume_skills(resume_skills, verified_skills)
        assert "nmap" in result["unconfirmed_skills"]
        assert "cybersecurity" in result["unconfirmed_skills"]
        assert result["authenticity_rate"] == 33

    def test_empty_resume_skills_returns_zero_rate_not_crash(self):
        result = cross_reference_resume_skills([], ["python"])
        assert result["authenticity_rate"] == 0
        assert result["confirmed_skills"] == []

    def test_bonus_skills_are_verified_but_not_claimed(self):
        resume_skills = ["python"]
        verified_skills = ["python", "docker"]
        result = cross_reference_resume_skills(resume_skills, verified_skills)
        assert result["bonus_verified_skills"] == ["docker"]


class TestComputePortfolioScore:
    def test_score_and_tier_are_internally_consistent(self):
        analytics = {
            "own_repo_count": 19,
            "total_stars": 19,
            "followers": 1,
            "top_languages": [{"name": "Python"}, {"name": "JavaScript"}, {"name": "HTML"}],
        }
        score, tier, breakdown = compute_portfolio_score(analytics)
        assert score == sum(breakdown.values())
        if score >= 80:
            assert tier == "Excellent"
        elif score >= 60:
            assert tier == "Strong"

    def test_score_never_exceeds_100(self):
        analytics = {
            "own_repo_count": 500,
            "total_stars": 5000,
            "followers": 5000,
            "top_languages": [{"name": f"lang{i}"} for i in range(20)],
        }
        score, tier, breakdown = compute_portfolio_score(analytics)
        assert score <= 100

    def test_empty_profile_scores_zero(self):
        analytics = {"own_repo_count": 0, "total_stars": 0, "followers": 0, "top_languages": []}
        score, tier, breakdown = compute_portfolio_score(analytics)
        assert score == 0
        assert tier == "Limited"
