"""Tests for the TF-IDF + cosine-similarity matching engine
(app/utils/ml_match.py) -- the project's core ML component."""
from app.utils.ml_match import compute_semantic_similarity, rank_resumes_for_job


class TestComputeSemanticSimilarity:
    def test_identical_text_scores_high(self):
        text = "Experienced Python developer with Flask, Django and REST API design skills."
        score = compute_semantic_similarity(text, text)
        assert score >= 90

    def test_related_text_scores_higher_than_unrelated(self):
        resume = "Python developer skilled in Flask, Django, REST APIs and PostgreSQL."
        job = "Looking for a backend engineer experienced in Python, Flask and databases."
        unrelated_job = "Looking for a professional chef skilled in French pastry."
        related_score = compute_semantic_similarity(resume, job)
        unrelated_score = compute_semantic_similarity(resume, unrelated_job)
        assert 0 < related_score <= 100
        assert related_score > unrelated_score

    def test_unrelated_text_scores_low(self):
        resume = "Professional chef specializing in French pastry and bakery management."
        job = "Senior Kubernetes and Terraform infrastructure engineer role."
        score = compute_semantic_similarity(resume, job)
        assert score <= 40

    def test_empty_resume_returns_zero(self):
        assert compute_semantic_similarity("", "Some job description text here.") == 0

    def test_empty_job_returns_zero(self):
        assert compute_semantic_similarity("Some resume text here.", "") == 0

    def test_both_empty_returns_zero(self):
        assert compute_semantic_similarity("", "") == 0

    def test_whitespace_only_returns_zero(self):
        assert compute_semantic_similarity("   ", "   ") == 0

    def test_score_is_within_bounds(self):
        score = compute_semantic_similarity("react native mobile developer", "backend java engineer")
        assert 0 <= score <= 100

    def test_pure_stopwords_does_not_crash(self):
        # After stopword removal this could leave an empty vocabulary --
        # must degrade to 0, not raise.
        score = compute_semantic_similarity("the a an is of", "the a an is of")
        assert score == 0


class TestRankResumesForJob:
    def test_ranks_best_match_first(self):
        job = "Python backend developer with Flask and PostgreSQL experience"
        resumes = {
            1: "Java Spring Boot enterprise developer",
            2: "Python Flask developer with PostgreSQL and REST API experience",
            3: "Graphic designer skilled in Photoshop and Illustrator",
        }
        ranked = rank_resumes_for_job(resumes, job)
        assert ranked[0][0] == 2

    def test_returns_sorted_descending(self):
        job = "Data scientist with machine learning and pandas experience"
        resumes = {
            1: "Marketing specialist with social media experience",
            2: "Data scientist skilled in machine learning, pandas, and scikit-learn",
        }
        ranked = rank_resumes_for_job(resumes, job)
        scores = [score for _, score in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_empty_resume_dict_returns_empty_list(self):
        assert rank_resumes_for_job({}, "Some job text") == []

    def test_empty_job_text_returns_empty_list(self):
        assert rank_resumes_for_job({1: "Some resume text"}, "") == []

    def test_respects_top_n(self):
        job = "Software engineer"
        resumes = {i: f"Candidate {i} software engineer with Python experience" for i in range(5)}
        ranked = rank_resumes_for_job(resumes, job, top_n=2)
        assert len(ranked) == 2

    def test_skips_resumes_with_no_text(self):
        job = "Software engineer with Python experience"
        resumes = {1: "Python software engineer", 2: "", 3: "   "}
        ranked = rank_resumes_for_job(resumes, job)
        ids = [rid for rid, _ in ranked]
        assert 2 not in ids and 3 not in ids


class TestMatchResumeToJob:
    """Tests for the blended overall match score in app/utils/ai_parser.py
    (match_resume_to_job) -- skill_score + semantic_score + experience_score
    combined into the single number shown on the candidate's Match Result
    page. This is a separate function from compute_semantic_similarity
    above, and previously had no direct test coverage at all, which is how
    a real scoring bug (see the two tests below) went unnoticed."""

    def _make_resume(self, db_session, **overrides):
        from app.models import Resume
        defaults = dict(
            user_id=1, filename="r.pdf", original_filename="r.pdf", file_type="pdf",
            parsed_text="", extracted_skills="[]", experience_years=0,
        )
        defaults.update(overrides)
        resume = Resume(**defaults)
        db_session.add(resume)
        db_session.commit()
        return resume

    def _make_job(self, db_session, **overrides):
        from app.models import Job
        defaults = dict(
            recruiter_id=1, title="Job", description="A job.", requirements="",
            required_skills="[]", preferred_skills="[]",
            experience_min=0, experience_max=10,
        )
        defaults.update(overrides)
        job = Job(**defaults)
        db_session.add(job)
        db_session.commit()
        return job

    def test_full_required_skill_match_is_not_labeled_partial(self, app, db_session):
        """Regression test: a candidate matching 100% of required skills and
        meeting the job's minimum experience must not land in
        'partial_match' territory just because of a noisy semantic-text
        signal or an overly harsh experience formula. (Previously: 100%
        skill match + meeting min experience still scored 57-58%% /
        'partial_match' -- see conversation history for the repro.)"""
        with app.app_context():
            resume = self._make_resume(
                db_session,
                parsed_text=("Skilled in Python, JavaScript, TypeScript, Java, C++, HTML, CSS, "
                             "Tailwind, React, React.js, Next.js, REST API, Node.js, Express, Flask, "
                             "SQL, MySQL, MongoDB, Linux, Git, GitHub, Data Science, Cybersecurity, "
                             "Nmap, Nikto, Wireshark, Burp Suite, OWASP, Penetration Testing."),
                extracted_skills='["css","react","html","javascript","tailwind","next.js","typescript"]',
                experience_years=1.0,
            )
            job = self._make_job(
                db_session,
                title="Frontend Developer (React)",
                description=("Nimbus Cloud Systems is hiring a Frontend Developer to build "
                              "responsive, accessible interfaces for our cloud-storage dashboard "
                              "product."),
                requirements="1-3 years building production React applications; strong HTML/CSS fundamentals.",
                required_skills='["react","javascript","html","css"]',
                preferred_skills='["typescript","tailwind","next.js"]',
                experience_min=1, experience_max=3,
            )

            from app.utils.ai_parser import match_resume_to_job
            result = match_resume_to_job(resume, job)

            assert result["skill_score"] == 100
            assert result["missing_skills"] == []
            assert result["overall_score"] >= 70, (
                f"100% required-skill match + meeting min experience scored only "
                f"{result['overall_score']}% ({result['recommendation']})"
            )
            assert result["recommendation"] in ("good_match", "strong_match")

    def test_meeting_minimum_experience_gets_strong_baseline_credit(self, app, db_session):
        """A candidate who exactly meets a job's stated minimum experience
        is, by definition, qualified on that axis -- they shouldn't be
        scored as if they were a third as qualified just because the job's
        range extends further above the minimum."""
        with app.app_context():
            resume = self._make_resume(db_session, experience_years=1.0)
            job = self._make_job(db_session, experience_min=1, experience_max=3)

            from app.utils.ai_parser import match_resume_to_job
            result = match_resume_to_job(resume, job)
            assert result["experience_score"] >= 70

    def test_below_minimum_experience_scores_lower_than_meeting_it(self, app, db_session):
        with app.app_context():
            under_qualified = self._make_resume(db_session, experience_years=0.0)
            qualified = self._make_resume(db_session, experience_years=1.0)
            job = self._make_job(db_session, experience_min=1, experience_max=3)

            from app.utils.ai_parser import match_resume_to_job
            under_result = match_resume_to_job(under_qualified, job)
            qualified_result = match_resume_to_job(qualified, job)
            assert under_result["experience_score"] < qualified_result["experience_score"]

    def test_exceeding_max_experience_scores_full_marks(self, app, db_session):
        with app.app_context():
            resume = self._make_resume(db_session, experience_years=5.0)
            job = self._make_job(db_session, experience_min=1, experience_max=3)

            from app.utils.ai_parser import match_resume_to_job
            result = match_resume_to_job(resume, job)
            assert result["experience_score"] == 100

    def test_no_required_skills_specified_is_flagged_not_faked(self, app, db_session):
        with app.app_context():
            resume = self._make_resume(db_session, experience_years=2.0)
            job = self._make_job(db_session, required_skills="[]", experience_min=0, experience_max=5)

            from app.utils.ai_parser import match_resume_to_job
            result = match_resume_to_job(resume, job)
            assert result["no_required_skills_specified"] is True
            assert result["skill_score"] == 0

    def test_zero_matching_skills_scores_low(self, app, db_session):
        with app.app_context():
            resume = self._make_resume(
                db_session,
                parsed_text="Professional chef specializing in French pastry.",
                extracted_skills='["baking","pastry"]',
                experience_years=0,
            )
            job = self._make_job(
                db_session,
                description="Senior Kubernetes and Terraform infrastructure engineer role.",
                required_skills='["kubernetes","terraform","aws"]',
                experience_min=3, experience_max=8,
            )

            from app.utils.ai_parser import match_resume_to_job
            result = match_resume_to_job(resume, job)
            assert result["skill_score"] == 0
            assert result["overall_score"] < 40
            assert result["recommendation"] == "weak_match"
