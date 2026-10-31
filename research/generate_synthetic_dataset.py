"""
Generates a SYNTHETIC resumes/jobs/labels dataset in the shape documented
in dataset_schema.md, so the evaluation scripts have something runnable
out of the box.

*** This is not a substitute for a real, human-labelled dataset. ***
`human_relevance` here is assigned by a fixed rule (skill-overlap ratio
above a threshold => relevant), not by an actual human judgement -- it is
a stand-in that exercises the same code path a real annotation file would,
nothing more. Say so explicitly in any report that uses it.

Usage:
    python research/generate_synthetic_dataset.py [--resumes N] [--jobs N] [--seed S]

Writes resumes.csv, jobs.csv, labels.csv into research/data/.
"""
import argparse
import csv
import os
import random

TEMPLATES = {
    "Software Engineer": {
        "skills": ["python", "javascript", "sql", "git", "react", "node.js", "docker"],
        "text": "Experienced software engineer skilled in building and shipping web applications, "
                "writing clean maintainable code, and collaborating in agile teams.",
    },
    "Data Scientist": {
        "skills": ["python", "machine learning", "pandas", "numpy", "sql", "scikit-learn", "statistics"],
        "text": "Data scientist with a background in statistical analysis, predictive modelling, "
                "and turning raw data into actionable business insight.",
    },
    "Cloud/DevOps Engineer": {
        "skills": ["aws", "docker", "kubernetes", "terraform", "linux", "ci/cd", "bash"],
        "text": "DevOps engineer focused on cloud infrastructure automation, containerized "
                "deployments, and reliable CI/CD pipelines.",
    },
    "Security Analyst": {
        "skills": ["cybersecurity", "network security", "penetration testing", "siem", "linux", "wireshark"],
        "text": "Security analyst experienced in vulnerability assessment, incident response, "
                "and defending production infrastructure against intrusion.",
    },
    "Frontend Developer": {
        "skills": ["html", "css", "javascript", "react", "typescript", "tailwind"],
        "text": "Frontend developer who builds accessible, responsive, well-tested user interfaces.",
    },
}

CATEGORIES = list(TEMPLATES.keys())


def _sample_skills(base_skills, extra_pool, rng, drop=0.3, add=0.2):
    """Simulate an imperfect resume/job: drop a fraction of the template's
    skills and sprinkle in a few unrelated ones, so overlap isn't trivially
    100% or 0% for every pair."""
    kept = [s for s in base_skills if rng.random() > drop]
    if not kept:
        kept = [rng.choice(base_skills)]
    extras = [s for s in extra_pool if rng.random() < add]
    return sorted(set(kept + extras))


def generate(num_resumes, num_jobs, seed, out_dir):
    rng = random.Random(seed)
    all_skills = sorted({s for tmpl in TEMPLATES.values() for s in tmpl["skills"]})

    resumes = []
    for i in range(1, num_resumes + 1):
        category = rng.choice(CATEGORIES)
        tmpl = TEMPLATES[category]
        skills = _sample_skills(tmpl["skills"], all_skills, rng)
        resumes.append({
            "resume_id": f"R{i:03d}",
            "text": tmpl["text"] + f" ({category} background.)",
            "skills": ";".join(skills),
            "experience_years": rng.randint(0, 8),
            "_category": category,  # internal only, not written to CSV
        })

    jobs = []
    for j in range(1, num_jobs + 1):
        category = rng.choice(CATEGORIES)
        tmpl = TEMPLATES[category]
        required = _sample_skills(tmpl["skills"], [], rng, drop=0.2, add=0.0)
        preferred = _sample_skills(all_skills, [], rng, drop=0.9, add=0.0)
        exp_min = rng.randint(0, 3)
        jobs.append({
            "job_id": f"J{j:03d}",
            "text": f"{category} role. " + tmpl["text"],
            "required_skills": ";".join(required),
            "preferred_skills": ";".join(preferred),
            "experience_min": exp_min,
            "experience_max": exp_min + rng.randint(2, 5),
            "_category": category,
        })

    labels = []
    for r in resumes:
        for j in jobs:
            r_skills = set(r["skills"].split(";"))
            j_required = set(s for s in j["required_skills"].split(";") if s)
            overlap = (len(r_skills & j_required) / len(j_required)) if j_required else 0
            same_category_bonus = 0.15 if r["_category"] == j["_category"] else 0
            relevance_signal = overlap + same_category_bonus
            # Fixed synthetic rule, not a human judgement -- see module docstring.
            human_relevance = 1 if relevance_signal >= 0.5 else 0
            labels.append({
                "resume_id": r["resume_id"],
                "job_id": j["job_id"],
                "human_relevance": human_relevance,
            })

    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "resumes.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["resume_id", "text", "skills", "experience_years"])
        writer.writeheader()
        for r in resumes:
            writer.writerow({k: r[k] for k in writer.fieldnames})

    with open(os.path.join(out_dir, "jobs.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "job_id", "text", "required_skills", "preferred_skills", "experience_min", "experience_max"])
        writer.writeheader()
        for j in jobs:
            writer.writerow({k: j[k] for k in writer.fieldnames})

    with open(os.path.join(out_dir, "labels.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["resume_id", "job_id", "human_relevance"])
        writer.writeheader()
        writer.writerows(labels)

    print(f"Wrote {len(resumes)} resumes, {len(jobs)} jobs, {len(labels)} labelled pairs to {out_dir}/")
    print("Reminder: human_relevance in labels.csv is SYNTHETIC (rule-based), not human-annotated. "
          "See dataset_schema.md before using these numbers in a report.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resumes", type=int, default=40)
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data"))
    args = parser.parse_args()
    generate(args.resumes, args.jobs, args.seed, args.out)
