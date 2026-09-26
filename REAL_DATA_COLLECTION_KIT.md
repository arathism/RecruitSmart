# RecruitSmart — Real Data Collection Kit (do this to move from ~8/10 toward 9.5)

This is the ONE remaining step that actually changes your project's rating.
Everything else (code, security, tests) is done. This is not.

---

## Step 1 — Ask 8-10 people (5 minutes each)

Send this to seniors who got placed, friends job-hunting, or your guide:

> "Hi! For my final year project I need real human judgment on resume-job
> fit (not AI-generated). Could you look at 5 resume/job description pairs
> and just mark each as Relevant / Not Relevant? Takes 5 minutes, really
> helps my evaluation section. I'll send you a simple form."

Aim for **~10 people × 5-10 pairs each = 50-100 real labelled pairs
minimum**. More is better, but even 50 real labels beats 0.

---

## Step 2 — What to give them (the actual pairs)

Use REAL, anonymized resumes and REAL job postings — e.g.:
- Your own resume + 5 different real job postings (LinkedIn/Naukri) → rate each
- 2-3 friends' resumes (with their permission) + a few job postings each
- Real job postings you already have from your `research/data/jobs.csv` structure

For each pair, ask the rater: **"Would this candidate reasonably be
considered for this role? Yes / No"** — that becomes `human_relevance` = 1 or 0.

---

## Step 3 — Format their answers into labels.csv

```
resume_id,job_id,human_relevance
R001,J001,1
R001,J002,0
R002,J001,1
```

(Matches `research/dataset_schema.md` exactly — your `resumes.csv` and
`jobs.csv` need matching `resume_id`/`job_id` values too.)

---

## Step 4 — Run your own tooling (already built, just unused)

```bash
python research/real_data_tools.py template     # generates the annotation sheet
# ... collect real answers, fill in labels.csv ...
python research/real_data_tools.py agreement     # if 2+ people rated the same pairs
python research/real_data_tools.py finalize      # locks in the real dataset
python research/full_evaluation.py               # re-runs baselines + significance tests on REAL data
```

Your `research/RESULTS.md` will now report REAL, citable numbers instead
of synthetic ones — this is what actually gets you to 9/9.5, not any more
code changes.

---

## Step 5 — Update the one honesty line everywhere

Once labels.csv is real, update this line (currently in your Master
Guide, README, RESULTS.md, and abstract):

> ~~"labels are synthetic, not validated against real hiring outcomes"~~
> → "evaluated on N real human-annotated resume-job pairs from M annotators,
> inter-annotator agreement (Cohen's κ) = X"

That single sentence change is what a paper reviewer is actually looking for.

---

**Bottom line: this is a data-collection task, not a coding task. I can't
do it for you — but if you get even 50 real labelled pairs this week, you
have a genuinely citable evaluation, and that's the real 9-9.5.**
