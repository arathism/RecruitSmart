"""Tests for the resume parsing / skill-extraction / ATS-scoring pipeline
(app/utils/ai_parser.py), including regression tests for two real
false-positive skill-detection bugs found by running actual resume text
through the pipeline: "R&D" was detected as the R programming language,
and "go-getter"/"go-to" was detected as the Go programming language."""
from app.utils.ai_parser import parse_resume, calculate_ats_score


class TestSkillExtractionFalsePositives:
    def _extract(self, text):
        # parse_resume expects a file path + type; test the underlying skill
        # scan directly via a temp .txt file so this stays a fast unit test.
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(text)
            path = f.name
        try:
            return parse_resume(path, "txt")["skills"]
        finally:
            os.unlink(path)

    def test_r_and_d_does_not_falsely_detect_r_language(self):
        skills = self._extract("Worked in the R&D department building new products for two years.")
        assert "R" not in skills

    def test_go_getter_does_not_falsely_detect_go_language(self):
        skills = self._extract("Passionate go-getter with a go-to attitude and strong communication skills.")
        assert "Go" not in skills

    def test_legitimate_go_mention_still_detected(self):
        skills = self._extract("Backend services written in Go and deployed with Docker on AWS.")
        assert "Go" in skills

    def test_legitimate_r_mention_still_detected(self):
        skills = self._extract("Data analysis using R, Python, and SQL for statistical modeling.")
        assert "R" in skills

    def test_legitimate_c_mention_still_detected(self):
        skills = self._extract("Embedded systems programming in C and C++ for microcontrollers.")
        assert "C" in skills

    def test_java_not_falsely_matched_inside_javascript(self):
        skills = self._extract("Frontend development using JavaScript and modern frameworks.")
        assert "Java" not in skills
        assert "Javascript" in skills


class TestCalculateAtsScore:
    def test_extraction_failure_caps_score_low(self):
        parsed = {"text": "", "skills": [], "extraction_warning": "Could not extract text."}
        result = calculate_ats_score(parsed)
        assert result["score"] <= 40

    def test_well_structured_resume_scores_high(self):
        # A genuinely well-structured resume needs more than section
        # keywords and a long skill list -- it also backs claims up with
        # quantifiable outcomes (numbers/percentages), which is what
        # actually distinguishes a strong resume from a generic one.
        text = (
            "email phone linkedin summary objective experience work history "
            "employment education degree university skills technologies "
            "developed managed created implemented designed led built optimized "
            "reduced costs by 20 percent for 500 users over 3 months "
        ) * 15
        parsed = {"text": text, "skills": ["Python"] * 12, "extraction_warning": None}
        result = calculate_ats_score(parsed)
        assert result["score"] >= 80

    def test_sparse_resume_scores_low(self):
        parsed = {"text": "Software engineer.", "skills": [], "extraction_warning": None}
        result = calculate_ats_score(parsed)
        assert result["score"] < 60

    def test_score_always_within_bounds(self):
        parsed = {"text": "x" * 5000, "skills": ["Python"] * 50, "extraction_warning": None}
        result = calculate_ats_score(parsed)
        assert 0 <= result["score"] <= 100



