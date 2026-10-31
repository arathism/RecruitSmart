"""
Ablation study: run the RecruitSmart hybrid matcher with each component
removed in turn, and compare nDCG@K, to show how much each piece actually
contributes.

    Full RecruitSmart
      -> Remove semantic matching (TF-IDF)
      -> Remove skill ontology
      -> Remove experience score
      -> Remove skill score   (i.e. skill-tag matching entirely)

Usage:
    python research/generate_synthetic_dataset.py   # if research/data/ doesn't exist yet
    python research/ablation_study.py [--data-dir research/data] [--k 10]
"""
import argparse
import os

from dataset_loader import load_dataset, print_provenance_banner
from evaluation_metrics import mean_ndcg_at_k
from matching_lib import hybrid_recruitsmart_score

VARIANTS = [
    ("Full RecruitSmart", dict()),
    ("Remove semantic matching", dict(use_semantic=False)),
    ("Remove skill ontology", dict(use_ontology=False)),
    ("Remove experience score", dict(use_experience=False)),
    ("Remove skill score", dict(use_skill=False)),
]


def rank_resumes_for_each_job(resumes, jobs, **flags):
    ranked_lists = []
    for job in jobs.values():
        scored = [
            (rid, hybrid_recruitsmart_score(resume, job, **flags)["overall"])
            for rid, resume in resumes.items()
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        ranked_lists.append([rid for rid, _ in scored])
    return ranked_lists


def run(data_dir, k):
    print_provenance_banner(data_dir)
    resumes, jobs, relevance_by_job = load_dataset(data_dir)
    relevance_dicts_in_job_order = [relevance_by_job[jid] for jid in jobs]

    print(f"Dataset: {len(resumes)} resumes x {len(jobs)} jobs\n")
    print(f"{'Variant':<30}{'nDCG@' + str(k):>10}    delta vs full")
    print("-" * 56)

    full_score = None
    for name, flags in VARIANTS:
        ranked_lists = rank_resumes_for_each_job(resumes, jobs, **flags)
        score = mean_ndcg_at_k(ranked_lists, relevance_dicts_in_job_order, k)
        if full_score is None:
            full_score = score
            delta_str = "--"
        else:
            delta = score - full_score
            delta_str = f"{delta:+.3f}"
        print(f"{name:<30}{score:>10.3f}    {delta_str}")

    print(
        "\nA large negative delta means removing that component hurts ranking quality "
        "a lot (i.e. it's pulling real weight in the model); a delta near 0 means that "
        "component isn't contributing much on THIS dataset and either needs a bigger "
        "role, more/better data to show its value, or an honest note in your report "
        "that its contribution wasn't measurable here.\n"
        "NOTE on 'Remove skill ontology': the live app's overall score (see "
        "app/utils/ai_parser.match_resume_to_job) never adds ontology_score into the "
        "ranking score -- ontology only powers the 'related skills detected' "
        "explainability text in the UI. So this row's delta is 0.000 by construction, "
        "not because ontology's contribution is unmeasurable on this dataset -- it "
        "genuinely doesn't affect ranking in the current live weighting. Report this as "
        "a stated limitation/design choice, not as an ablation finding.\n"
        "As with baseline_comparison.py: replace the synthetic labels.csv with real, "
        "human-annotated labels before citing these numbers."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "data"))
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()
    run(args.data_dir, args.k)
