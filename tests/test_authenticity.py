"""Tests for the resume authenticity checker (app/utils/authenticity_checker.py) --
the four heuristic checks and their combined scoring."""
from app.utils.authenticity_checker import (
    check_timeline_consistency,
    check_content_authenticity,
    check_duplicate_content,
    analyze_resume_authenticity,
)


class TestTimelineConsistency:
    def test_normal_resume_no_flags(self):
        text = "Software Engineer, Acme Corp, 2020-2022\nJunior Developer, Beta Inc, 2018-2020"
        penalty, flags = check_timeline_consistency(text)
        assert penalty == 0
        assert flags == []

    def test_future_dated_job_is_flagged(self):
        text = "Senior Engineer, FutureCorp, 2027-2030"
        penalty, flags = check_timeline_consistency(text)
        assert penalty > 0
        assert any("future" in f for f in flags)

    def test_end_before_start_is_flagged(self):
        text = "Developer, SomeCo, 2022-2018"
        penalty, flags = check_timeline_consistency(text)
        assert penalty > 0
        assert any("ends before it starts" in f for f in flags)

    def test_expected_graduation_year_not_flagged(self):
        # A current student's degree with a future expected-graduation year
        # is normal and must NOT be treated as a fabricated future job date.
        text = "B.Tech Computer Science, AGMRCET, 2023-2027"
        penalty, flags = check_timeline_consistency(text)
        assert penalty == 0
        assert flags == []

    def test_overlapping_full_time_roles_flagged(self):
        text = "Engineer, CompanyA, 2019-2022\nEngineer, CompanyB, 2020-2023"
        penalty, flags = check_timeline_consistency(text)
        assert penalty > 0
        assert any("Overlapping" in f for f in flags)

    def test_claimed_experience_far_exceeds_dated_ranges(self):
        text = "Developer, CompanyA, 2021-2022"
        penalty, flags = check_timeline_consistency(text, claimed_experience_years=10)
        assert penalty > 0
        assert any("years of experience" in f for f in flags)


class TestContentAuthenticity:
    def test_buzzword_heavy_no_substance_is_flagged(self):
        text = (
            "Highly motivated results-driven team player and self-starter with "
            "a proven track record and excellent communication skills, hardworking "
            "detail-oriented go-getter who is a real people person and fast learner "
            "with a strong work ethic. " * 3
        )
        penalty, flags = check_content_authenticity(text)
        assert penalty > 0

    def test_concrete_achievements_not_flagged_for_buzzwords(self):
        text = (
            "Built and shipped a Django REST API that increased checkout conversion "
            "by 18% and reduced page load time for 50000 users. Migrated a legacy "
            "MySQL database to PostgreSQL, deployed on AWS, and led a team of 4 engineers."
        )
        penalty, flags = check_content_authenticity(text)
        assert not any("generic phrases" in f for f in flags)

    def test_very_short_resume_flagged(self):
        penalty, flags = check_content_authenticity("Software engineer.")
        assert penalty > 0
        assert any("very short" in f for f in flags)


class TestDuplicateContent:
    def test_no_other_resumes_returns_zero(self):
        penalty, flags = check_duplicate_content("Some resume text that is long enough.", [])
        assert penalty == 0
        assert flags == []

    def test_near_identical_resume_flagged(self):
        text = "Experienced software engineer with Python, Flask, and PostgreSQL. " * 5
        other = [(1, text)]
        penalty, flags = check_duplicate_content(text, other)
        assert penalty > 0
        assert flags

    def test_dissimilar_resumes_not_flagged(self):
        text = "Experienced software engineer with Python, Flask, and PostgreSQL. " * 5
        other = [(1, "Professional chef with 10 years of French pastry experience. " * 5)]
        penalty, flags = check_duplicate_content(text, other)
        assert penalty == 0

    def test_too_short_text_skipped(self):
        penalty, flags = check_duplicate_content("short", [(1, "also short")])
        assert penalty == 0
        assert flags == []


class TestAnalyzeResumeAuthenticity:
    def test_clean_resume_scores_high_confidence(self):
        text = (
            "Software Engineer, Acme Corp, 2021-2023. Built and shipped a Django "
            "REST API that increased throughput by 25% for 10000 users. Migrated "
            "the database and deployed the service on AWS."
        )
        result = analyze_resume_authenticity(text)
        assert result["score"] > 60
        assert result["tier"] in ("High Confidence", "Moderate Confidence")
        assert set(result["checks_run"]) == {
            "Timeline Consistency", "PDF Metadata Forensics",
            "Content Authenticity", "Duplicate/Template Detection",
        }

    def test_problematic_resume_scores_lower(self):
        text = "Engineer, FutureCorp, 2028-2030."
        result = analyze_resume_authenticity(text)
        assert result["score"] < 100
        assert len(result["flags"]) > 0

    def test_flags_are_deduplicated(self):
        text = "Engineer, A, 2028-2030\nEngineer, B, 2028-2030"
        result = analyze_resume_authenticity(text)
        assert len(result["flags"]) == len(set(result["flags"]))

    def test_score_never_negative(self):
        text = "Engineer, A, 2030-2040\nEngineer, B, 2030-2040\nEngineer, C, 2030-2040"
        result = analyze_resume_authenticity(text, claimed_experience_years=50)
        assert result["score"] >= 0
