"""Loads resumes.csv / jobs.csv / labels.csv (see dataset_schema.md) into
the plain-dict shape matching_lib.py expects."""
import csv
import json
import os


def _read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_dataset(data_dir):
    resumes = {}
    for row in _read_csv(os.path.join(data_dir, "resumes.csv")):
        resumes[row["resume_id"]] = {
            "id": row["resume_id"],
            "text": row["text"],
            "skills": [s for s in row["skills"].split(";") if s],
            "experience_years": int(row["experience_years"]) if row["experience_years"] else 0,
        }

    jobs = {}
    for row in _read_csv(os.path.join(data_dir, "jobs.csv")):
        jobs[row["job_id"]] = {
            "id": row["job_id"],
            "text": row["text"],
            "required_skills": [s for s in row["required_skills"].split(";") if s],
            "preferred_skills": [s for s in row["preferred_skills"].split(";") if s],
            "experience_min": int(row["experience_min"]) if row["experience_min"] else 0,
            "experience_max": int(row["experience_max"]) if row["experience_max"] else 10,
        }

    # relevance_by_job[job_id][resume_id] = 0/1
    relevance_by_job = {job_id: {} for job_id in jobs}
    for row in _read_csv(os.path.join(data_dir, "labels.csv")):
        job_id, resume_id = row["job_id"], row["resume_id"]
        if job_id in relevance_by_job:
            relevance_by_job[job_id][resume_id] = int(row["human_relevance"])

    return resumes, jobs, relevance_by_job


def load_provenance(data_dir):
    """Reads dataset_metadata.json next to the CSVs, if present. Returns a
    dict with at least a `label_source` key ("human", "synthetic", or
    "unknown" if the file is missing -- an unlabelled dataset is treated
    as NOT verified human data, never assumed to be)."""
    path = os.path.join(data_dir, "dataset_metadata.json")
    if not os.path.exists(path):
        return {"label_source": "unknown", "notes": "No dataset_metadata.json found next to this data."}
    with open(path) as f:
        return json.load(f)


def print_provenance_banner(data_dir):
    """Prints a loud, impossible-to-miss banner at the top of every
    research script's output stating whether labels.csv is confirmed
    human-annotated. Exists so a real published number can never quietly
    trace back to synthetic or AI-generated labels without the person
    running the script seeing this first."""
    prov = load_provenance(data_dir)
    source = prov.get("label_source", "unknown")
    print("=" * 72)
    if source == "human":
        annot = prov.get("annotators") or "(not recorded)"
        agreement = prov.get("inter_annotator_agreement")
        print(f"DATASET PROVENANCE: human-annotated labels (annotators: {annot})")
        if agreement is not None:
            print(f"  Inter-annotator agreement: {agreement}")
        print("  These numbers ARE citable, subject to your own review of the annotation quality.")
    elif source == "synthetic":
        print("DATASET PROVENANCE: SYNTHETIC labels (rule-generated, not human judgement).")
        print("  DO NOT cite the numbers from this run in a publication.")
        print("  Run research/real_data_tools.py once real human annotations exist.")
    else:
        print("DATASET PROVENANCE: UNKNOWN (no research/data/dataset_metadata.json found).")
        print("  Treating this as NOT verified human data -- do not cite these numbers.")
    print("=" * 72 + "\n")
    return prov

