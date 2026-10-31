"""
Compares RecruitSmart's hybrid matcher against three baselines, ranked by
nDCG@10 against the human_relevance labels:

    Baseline 1 -> Keyword matching
    Baseline 2 -> TF-IDF + cosine similarity
    Baseline 3 -> SBERT semantic matching (skipped if sentence-transformers
                  isn't installed -- see matching_lib.sbert_score)
    RecruitSmart -> Hybrid (skill match + TF-IDF semantic + experience fit
                            + skill-ontology nudge)

This is the evidence behind the research-paper framing: "we propose and
evaluate a hybrid person-job matching model combining semantic similarity
with structured candidate attributes" is a claim you can only defend by
showing the hybrid actually outperforms each simpler baseline on the same
labelled data -- this script produces that table.

Usage:
    python research/generate_synthetic_dataset.py   # if research/data/ doesn't exist yet
    python research/baseline_comparison.py [--data-dir research/data] [--k 10]
"""
import argparse
import os

from dataset_loader import load_dataset, print_provenance_banner
from evaluation_metrics import mean_ndcg_at_k
from matching_lib import (
    keyword_overlap_score,
    tfidf_cosine_score,
    sbert_score,
    hybrid_recruitsmart_score,
)

MODEL_SCORERS = {
    "Baseline 1: Keyword": keyword_overlap_score,
    "Baseline 2: TF-IDF + cosine": tfidf_cosine_score,
    "Baseline 3: SBERT": sbert_score,
    "RecruitSmart Hybrid": lambda r, j: hybrid_recruitsmart_score(r, j)["overall"],
}


def rank_resumes_for_each_job(resumes, jobs, scorer):
    """Returns (list_of_ranked_resume_id_lists, list_of_relevance_dicts) in
    a fixed job order, for use with evaluation_metrics.mean_ndcg_at_k."""
    ranked_lists = []
    for job in jobs.values():
        scored = [(rid, scorer(resume, job)) for rid, resume in resumes.items()]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        ranked_lists.append([rid for rid, _ in scored])
    return ranked_lists


def run(data_dir, k):
    print_provenance_banner(data_dir)
    resumes, jobs, relevance_by_job = load_dataset(data_dir)
    relevance_dicts_in_job_order = [relevance_by_job[jid] for jid in jobs]

    print(f"Dataset: {len(resumes)} resumes x {len(jobs)} jobs "
          f"({sum(len(v) for v in relevance_by_job.values())} labelled pairs)\n")
    print(f"{'Model':<30}{'nDCG@' + str(k):>10}")
    print("-" * 40)

    for name, scorer in MODEL_SCORERS.items():
        # Skip SBERT cleanly if the optional dependency isn't installed.
        probe = scorer(next(iter(resumes.values())), next(iter(jobs.values())))
        if probe is None:
            print(f"{name:<30}{'skipped (sentence-transformers not installed)':>10}")
            continue
        ranked_lists = rank_resumes_for_each_job(resumes, jobs, scorer)
        score = mean_ndcg_at_k(ranked_lists, relevance_dicts_in_job_order, k)
        print(f"{name:<30}{score:>10.3f}")

    print(
        "\nThese numbers are computed against research/data/labels.csv. If that file "
        "still holds the synthetic labels from generate_synthetic_dataset.py, do NOT "
        "cite these numbers as real evaluation results -- regenerate/replace labels.csv "
        "with human-annotated data first (see dataset_schema.md)."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "data"))
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()
    run(args.data_dir, args.k)
