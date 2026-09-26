"""
Standalone matching functions for the research/ scripts.
----------------------------------------------------------
Everything in here is a *duck-typed reimplementation* of the same scoring
logic that lives in app/utils/ai_parser.py and app/utils/ml_match.py, so
that the research scripts (baseline_comparison.py, ablation_study.py,
fairness_test.py, evaluate_dataset.py) can run standalone -- no Flask
app context, no database, no SQLAlchemy models -- against a plain CSV
dataset (see generate_synthetic_dataset.py / dataset_schema.md).

IMPORTANT: this module intentionally re-imports the *real* skill list,
synonym map, and TF-IDF similarity function from the live app package
(app.utils.ai_parser, app.utils.ml_match, app.utils.skill_ontology) --
those don't touch Flask/the DB, so importing them here is safe and keeps
the research numbers honest (they're testing the same skill vocabulary
and semantic-similarity code the live product uses, not a reimplementation
that could silently drift out of sync). Only the "resume/job as a
SQLAlchemy model" plumbing is reimplemented here, using plain dicts
instead.

Each candidate/job is a plain dict:
    resume = {
        "id": "R001",
        "text": "... full resume text ...",
        "skills": ["python", "sql", "machine learning"],   # already extracted
        "experience_years": 2,
    }
    job = {
        "id": "J001",
        "text": "... title + description + requirements ...",
        "required_skills": ["python", "sql", "docker"],
        "preferred_skills": ["aws"],
        "experience_min": 1,
        "experience_max": 4,
    }
"""
import importlib.util
import os

# These research scripts are meant to run standalone (`python
# research/xxx.py`), with no Flask app, database, or `pip install -r
# requirements.txt` required beyond scikit-learn/numpy. A plain
# `from app.utils.ai_parser import ...` would import the `app` PACKAGE
# first, which runs app/__init__.py, which imports Flask/Flask-SQLAlchemy/
# etc. -- dependencies these research scripts don't need and shouldn't
# require just to reuse three dependency-free helper functions. Instead,
# each module is loaded directly from its file path, bypassing the `app`
# package's __init__.py entirely. This is safe specifically because
# ai_parser.py, ml_match.py, and skill_ontology.py have no *module-level*
# Flask/DB imports themselves (their Flask-adjacent imports, e.g. inside
# match_resume_to_job(), are deferred to function-call time and are never
# invoked from here).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_module(module_name, relative_path):
    path = os.path.join(_PROJECT_ROOT, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ai_parser = _load_module("_research_ai_parser", "app/utils/ai_parser.py")
_ml_match = _load_module("_research_ml_match", "app/utils/ml_match.py")
_skill_ontology = _load_module("_research_skill_ontology", "app/utils/skill_ontology.py")

normalize_skill = _ai_parser.normalize_skill
compute_semantic_similarity = _ml_match.compute_semantic_similarity
ontology_score = _skill_ontology.ontology_score


def keyword_overlap_score(resume, job):
    """Baseline 1: naive keyword overlap. Counts exact (post-normalization)
    skill-string matches only -- no semantics, no partial credit."""
    resume_skills = {normalize_skill(s) for s in resume.get("skills", [])}
    required = {normalize_skill(s) for s in job.get("required_skills", [])}
    if not required:
        return 0
    matched = resume_skills & required
    return int(round((len(matched) / len(required)) * 100))


def tfidf_cosine_score(resume, job):
    """Baseline 2: TF-IDF + cosine similarity over the full free text,
    ignoring the structured skill lists entirely."""
    return compute_semantic_similarity(resume.get("text", ""), job.get("text", ""))


def sbert_score(resume, job):
    """Baseline 3: sentence-embedding (SBERT-style) semantic similarity.

    Requires the optional `sentence-transformers` package (NOT in
    requirements.txt -- it pulls in torch and is heavy, so it's kept
    optional rather than a hard dependency of the live product). If it
    isn't installed, this baseline is skipped everywhere it's used and the
    comparison report says so explicitly rather than silently faking a
    number.
    """
    try:
        from sentence_transformers import SentenceTransformer, util
    except ImportError:
        return None

    global _SBERT_MODEL
    if "_SBERT_MODEL" not in globals() or _SBERT_MODEL is None:
        _SBERT_MODEL = SentenceTransformer("all-MiniLM-L6-v2")

    resume_text = (resume.get("text") or "").strip()
    job_text = (job.get("text") or "").strip()
    if not resume_text or not job_text:
        return 0

    emb = _SBERT_MODEL.encode([resume_text, job_text], convert_to_tensor=True)
    similarity = util.cos_sim(emb[0], emb[1]).item()
    return int(round(max(0.0, min(1.0, similarity)) * 100))


def _experience_score(resume, job):
    exp_years = resume.get("experience_years") or 0
    min_exp = job.get("experience_min") or 0
    max_exp = job.get("experience_max") or 10
    if exp_years >= max_exp:
        return 100
    elif exp_years >= min_exp:
        span = max(max_exp - min_exp, 1)
        return 70 + int(30 * (exp_years - min_exp) / span)
    else:
        return max(0, int((exp_years / max(min_exp, 1)) * 65))


def hybrid_recruitsmart_score(resume, job, use_semantic=True, use_ontology=True,
                               use_experience=True, use_skill=True):
    """The platform's real hybrid model, reimplemented over plain dicts so
    it can run outside Flask/DB. Each `use_*` flag can switch a component
    OFF for the ablation study (see ablation_study.py) -- when a component
    is off its contribution is simply excluded from the weighted sum, and
    the remaining weights are NOT renormalized, so you can see the direct
    score impact of removing that component (matching how
    app/utils/ai_parser.match_resume_to_job actually blends signals).

    IMPORTANT -- kept in sync with app/utils/ai_parser.match_resume_to_job:
    the live app's `overall` is exactly
        skill_score * 0.55 + semantic_score * 0.20 + experience_score * 0.25
    Ontology score is computed by the live app too, but only for the
    explainability UI ("related skills detected") -- it is NEVER added into
    `overall` there. This function used to add `ontology_score * 0.05` on
    top, which the live app does not do; that has been removed so the
    number returned here is the same ranking score the live app actually
    produces. `use_ontology=False` therefore has no effect on `overall`
    (by design, matching the live app) -- it only suppresses the
    `ontology_score` field in the returned dict, which is kept for
    explainability reporting, not for ranking.
    """
    resume_skills = {normalize_skill(s) for s in resume.get("skills", [])}
    required_skills = {normalize_skill(s) for s in job.get("required_skills", [])}

    skill_score = 0
    if required_skills:
        matched = resume_skills & required_skills
        skill_score = int((len(matched) / len(required_skills)) * 100)

    semantic_score = tfidf_cosine_score(resume, job) if use_semantic else 0
    experience_score = _experience_score(resume, job) if use_experience else 0
    onto_score = ontology_score(resume_skills, required_skills) if use_ontology else 0

    overall = 0
    if use_skill:
        overall += skill_score * 0.55
    if use_semantic:
        overall += semantic_score * 0.20
    if use_experience:
        overall += experience_score * 0.25
    # NOTE: ontology is deliberately NOT added to `overall` -- see docstring
    # above. It's returned below purely for explainability reporting.

    return {
        "overall": int(round(min(100, overall))),
        "skill_score": skill_score,
        "semantic_score": semantic_score,
        "experience_score": experience_score,
        "ontology_score": onto_score,
    }


MODELS = {
    "Baseline 1: Keyword": lambda r, j: keyword_overlap_score(r, j),
    "Baseline 2: TF-IDF + cosine": lambda r, j: tfidf_cosine_score(r, j),
    "Baseline 3: SBERT": lambda r, j: sbert_score(r, j),
    "RecruitSmart Hybrid": lambda r, j: hybrid_recruitsmart_score(r, j)["overall"],
}
