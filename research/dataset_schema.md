# RecruitSmart research dataset schema

This documents what a "proper research dataset" for the matching model
needs to contain, per the checklist below. `generate_synthetic_dataset.py`
produces a dataset in exactly this shape, but with **synthetically
generated** resumes/jobs/labels -- it exists so the evaluation scripts
(`evaluate_dataset.py`, `baseline_comparison.py`, `ablation_study.py`)
have something runnable out of the box. **Replace it with a real,
human-labelled dataset before citing any numbers in a paper** -- synthetic
labels prove the code runs, they do not prove the model works.

## What to document about the dataset

| Field | This synthetic set | What to fill in for a real dataset |
|---|---|---|
| Number of resumes | see `resumes.csv` | your actual count |
| Number of jobs | see `jobs.csv` | your actual count |
| Job categories | Software/Data/Cloud/Security (synthetic templates) | your actual category breakdown |
| Skills vocabulary | reuses `app.utils.ai_parser.SKILL_DATABASE` | same, or your extended list |
| Resume formats | plain text only | PDF/DOCX/text mix, if applicable |
| Data source | synthetically generated, see script | e.g. "public resume dataset X", "recruiter-donated postings", "self-collected with consent" |
| Cleaning procedure | none needed (generated clean) | de-duplication, PII scrubbing, encoding fixes, etc. |
| Train/test split | not split (evaluation-only set) | document the split ratio and whether it's random or stratified by job category |
| Annotation procedure | synthetic rule (skill overlap ratio -> relevance), NOT human judgement | describe your human annotators, instructions, and inter-annotator agreement |

## File formats

### `resumes.csv`
```
resume_id,text,skills,experience_years
R001,"...",python;sql;machine learning,2
```
- `skills` is a `;`-separated list of skill strings (already extracted --
  mirrors what `Resume.get_skills_list()` stores in the live app).

### `jobs.csv`
```
job_id,text,required_skills,preferred_skills,experience_min,experience_max
J001,"...",python;sql;docker,aws,1,4
```

### `labels.csv` -- the human-labelled ground truth
```
resume_id,job_id,human_relevance
R001,J001,1
R001,J002,0
R002,J001,1
R002,J003,0
```
- `human_relevance` is 1 ("a human evaluator judged this resume relevant
  to this job") or 0 (not relevant). This is what turns "we computed a
  score" into "we can measure whether the score is *right*" --
  precision/recall/F1/nDCG all need this column and cannot be computed
  without it.
- Every scoring model can then be judged against the SAME `labels.csv`,
  which is what makes baseline_comparison.py's model-vs-model table a fair
  comparison rather than each model grading its own homework.

## Recommended dataset size for a course/thesis-level evaluation

There's no universal minimum, but as a rough floor for numbers that are
worth putting in a table: at least ~30-50 resumes x ~10-15 jobs (i.e.
several hundred labelled resume-job pairs), with every pair labelled by
at least one human evaluator and, ideally, a second evaluator on a subset
to report inter-annotator agreement (e.g. Cohen's kappa).
