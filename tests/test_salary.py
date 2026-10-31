"""Tests for the rule-based salary prediction model
(app/utils/salary_predictor.py)."""
from app.utils.salary_predictor import predict_salary


class TestPredictSalary:
    def test_returns_expected_keys(self):
        result = predict_salary("Software Engineer")
        for key in ("predicted_min", "predicted_max", "predicted_avg", "confidence", "factors"):
            assert key in result

    def test_min_is_not_greater_than_max(self):
        result = predict_salary("Data Scientist", location="Bangalore", experience_years=3)
        assert result["predicted_min"] <= result["predicted_max"]

    def test_avg_between_min_and_max(self):
        result = predict_salary("Full Stack Developer", experience_years=2)
        assert result["predicted_min"] <= result["predicted_avg"] <= result["predicted_max"]

    def test_more_experience_increases_prediction(self):
        junior = predict_salary("Software Engineer", experience_years=0)
        senior = predict_salary("Software Engineer", experience_years=8)
        assert senior["predicted_avg"] > junior["predicted_avg"]

    def test_metro_city_boosts_salary(self):
        non_metro = predict_salary("Software Engineer", location="Hubli", experience_years=2)
        metro = predict_salary("Software Engineer", location="Bangalore", experience_years=2)
        assert metro["predicted_avg"] > non_metro["predicted_avg"]

    def test_in_demand_skills_boost_salary(self):
        base = predict_salary("Software Engineer", experience_years=2, skills=[])
        boosted = predict_salary("Software Engineer", experience_years=2,
                                  skills=["aws", "kubernetes", "docker", "terraform"])
        assert boosted["predicted_avg"] > base["predicted_avg"]

    def test_github_score_boosts_salary(self):
        base = predict_salary("Software Engineer", experience_years=2)
        with_github = predict_salary("Software Engineer", experience_years=2, github_score=90)
        assert with_github["predicted_avg"] > base["predicted_avg"]

    def test_unknown_role_falls_back_to_default_range(self):
        result = predict_salary("Underwater Basket Weaver")
        assert result["predicted_min"] > 0

    def test_confidence_within_bounds(self):
        result = predict_salary("Software Engineer", location="Pune", experience_years=5,
                                 skills=["react"], github_score=70)
        assert 0 <= result["confidence"] <= 0.95

    def test_confidence_higher_with_more_signal(self):
        thin = predict_salary("Software Engineer")
        rich = predict_salary("Software Engineer", location="Chennai", experience_years=4,
                               skills=["aws", "docker"], github_score=85)
        assert rich["confidence"] > thin["confidence"]

    def test_role_matching_is_case_insensitive(self):
        result_lower = predict_salary("machine learning engineer")
        result_mixed = predict_salary("Machine Learning Engineer")
        assert result_lower["predicted_min"] == result_mixed["predicted_min"]


class TestSkillGapEstimates:
    """Regression tests for a real bug found while reviewing the skill-gap
    feature: 'estimated time to learn' used random.randint() -- so the same
    skill showed a different number every page load, and the salary range
    in the career roadmap used a second, unrelated random USD figure that
    contradicted the platform's own real salary_predictor. Both are now
    deterministic and internally consistent."""

    def test_estimated_learning_time_is_deterministic(self):
        from app.utils.ai_parser import _estimated_learning_time
        first = _estimated_learning_time("python")
        second = _estimated_learning_time("python")
        assert first == second

    def test_unknown_skill_gets_honest_fallback_not_fake_precision(self):
        from app.utils.ai_parser import _estimated_learning_time, DEFAULT_TIME_ESTIMATE
        assert _estimated_learning_time("some obscure niche tool") == DEFAULT_TIME_ESTIMATE

    def test_career_roadmap_salary_matches_real_predictor(self):
        from app.utils.ai_parser import generate_career_roadmap
        from app.utils.salary_predictor import predict_salary

        roadmap = generate_career_roadmap("Software Engineer", "Tech", ["python"])
        expected = predict_salary("Software Engineer", skills=["python"])
        assert str(expected["predicted_min"]) in roadmap["salary_range"]
        assert str(expected["predicted_max"]) in roadmap["salary_range"]

    def test_career_roadmap_market_demand_is_deterministic(self):
        from app.utils.ai_parser import generate_career_roadmap
        first = generate_career_roadmap("Data Scientist", "Tech", ["python", "sql"])
        second = generate_career_roadmap("Data Scientist", "Tech", ["python", "sql"])
        assert first["market_demand"] == second["market_demand"]

