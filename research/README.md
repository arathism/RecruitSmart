# RecruitSmart: research addendum

This folder turns the matching feature from "a software feature" into
something with a defensible research write-up: a stated contribution, a
baseline comparison, an ablation study, evaluation metrics beyond
accuracy, and a fairness audit methodology. It's a companion to the live
app's matcher (`app/utils/ai_parser.py`, `app/utils/ml_match.py`,
`app/utils/skill_ontology.py`) -- everything here evaluates that same
code, it doesn't reimplement a separate model.

## 1. The research contribution, stated plainly

> We propose and evaluate a hybrid person-job matching model combining
> semantic similarity (TF-IDF + cosine) with structured candidate
> attributes (exact skill-tag overlap, experience-range fit, and a
> lightweight skill ontology for related-but-not-exact skills), and
> compare it against three baselines: keyword overlap, TF-IDF alone, and
> (optionally) SBERT sentence embeddings.

That's a claim you can only defend with a number, not documentation
prose -- see `baseline_comparison.py`.

## 2. Explainable AI (live in the app)

`app/utils/ai_parser.py`'s `explain_match()` and
`counterfactual_suggestions()`, surfaced in
`app/templates/candidate/match_result.html`, add:
- **"Why this score"**: plain-language reasons derived directly from the
  score components (not invented after the fact).
- **Counterfactual "what would improve this"**: re-runs the real scoring
  formula with one missing skill hypothetically added, e.g. "Add Docker ->
  estimated 76%".
- **Skill ontology transparency**: when a required skill isn't held
  exactly but a related skill in the same category is (see below), that's
  shown explicitly rather than the candidate just seeing "missing: Docker".

## 3. Skill ontology / knowledge graph (live in the app)

`app/utils/skill_ontology.py` -- a hand-built, inspectable category tree
(Machine Learning, Cloud Computing, Frontend Development, ...) used to
give small partial credit for related-but-not-identical skills, and to
generate the "related skills detected" explanation. See that module's
docstring for the honest scope limitation versus a real external
ontology (e.g. ESCO).

## 4. Fairness experiment

`fairness_test.py` -- controlled resume-pair audit (identical
qualifications, only a name signal changed). Reports demographic parity
difference, equal opportunity difference, and the raw paired score gap
with a significance check. Framed as "fairness-aware candidate
evaluation", never as "bias-free recruitment" -- see that script's
docstring for why, and for how to extend it to other demographic axes.

## 5. Research dataset

`dataset_schema.md` documents what to collect and report (resume/job
counts, categories, skills vocabulary, data source, cleaning procedure,
train/test split, annotation procedure) and the exact CSV shape expected
by the scripts below. `generate_synthetic_dataset.py` produces a
runnable-but-synthetic example -- **replace `research/data/labels.csv`
with real human-annotated relevance judgements before citing any
numbers**.

## 6. Evaluation metrics

`evaluation_metrics.py` -- classification (precision/recall/F1) AND
ranking metrics (Precision@K, Recall@K, MRR, nDCG@K), since recruitment
matching is fundamentally a ranking problem, not just a yes/no
classification. Also fairness metrics (demographic parity difference,
equal opportunity difference).

## 7. Ablation study

`ablation_study.py` -- runs the hybrid matcher with each component
(semantic matching, skill ontology, experience score, skill score)
removed in turn and reports the nDCG@K delta versus the full system, so
you can say *how much* each component is actually contributing, not just
that it's present.

## 8. Recruiter/user study

Not automatable from here -- it needs real participants. The live app's
UI (job matching, match results page with explanations) is already the
instrument; a suggested protocol:
- Recruit ~10-20 students/job seekers and, if possible, ~5-10
  recruiters/HR professionals.
- Give them tasks against System A (keyword-only baseline -- see
  `matching_lib.keyword_overlap_score`) vs System B (RecruitSmart).
- Ask: which ranking is more useful? Which explanation is easier to
  understand? Do explanations increase trust? Can they tell why a
  candidate was recommended? Does the skill-gap/counterfactual
  recommendation help?
- That gives you human-evaluation data to report alongside the automatic
  metrics above.

## 9. Scope discipline

Deliberately NOT done here: no new "AI feature" was added just to pad the
feature list. Every addition above is in direct service of making the
existing hybrid matcher's claim measurable, explainable, and auditable.

---

## Running everything

```bash
cd recruit_smart_PUBLICATION
pip install -r research/requirements-research.txt   # matplotlib + scipy, research-only

# 1. Generate the (synthetic, placeholder) dataset -- skip this once
#    research/data/ holds real human-annotated data instead
python research/generate_synthetic_dataset.py --resumes 40 --jobs 12

# 2. Full ranking + classification report (Precision@K, Recall@K, MRR, nDCG@K, P/R/F1)
python research/full_evaluation.py --json-out research/data/full_evaluation_results.json

# 3. Baseline comparison (Keyword / TF-IDF / SBERT / Hybrid) -- nDCG@K only
python research/baseline_comparison.py

# 4. Ablation study
python research/ablation_study.py

# 5. Fairness audit
python research/fairness_test.py

# 6. Statistical significance: bootstrap CIs, paired p-values, effect sizes
python research/significance_report.py --json-out research/data/significance_results.json

# 7. Publication-quality figures (PNG, 300 DPI) -> research/figures/
python research/generate_figures.py
```

All evaluation scripts import directly from `app/utils/...` (no Flask
app context or database needed -- see `matching_lib.py`), so they stay in
sync with the live matcher automatically as it evolves. `matching_lib.py`
is kept byte-for-byte consistent with `app/utils/ai_parser.match_resume_to_job`'s
`overall` formula (`skill*0.55 + semantic*0.20 + experience*0.25`, no
ontology term) -- see that module's docstring if you ever change the live
weighting, so the two don't drift apart again.

## Bringing in real human-labelled data

`research/real_data_tools.py` has three subcommands -- `template`
(generate a blank sheet for annotators), `agreement` (Cohen's kappa
between two annotators), and `finalize` (install a completed file as
`labels.csv` and flip `dataset_metadata.json` to `label_source: "human"`).
See `RESULTS.md` section 7 for the full walkthrough. Every script above
prints a provenance banner at the top of its output stating whether the
data it's about to evaluate is confirmed human-labelled, synthetic, or
unknown -- so a real, citable number can never quietly trace back to
synthetic data without that being obvious.

**`RESULTS.md` in this folder is a run log**: the actual output of every
script above against the synthetic dataset shipped in `research/data/`,
plus an honest reading of what each number does and doesn't show, and
exactly what to redo once `labels.csv` holds real human-annotated data
instead of synthetic labels. Read it before writing the paper's results
section -- it's written to be dropped in directly.
