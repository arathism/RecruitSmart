"""
Full evaluation report: Precision@K, Recall@K, MRR, nDCG@K (ranking) AND
Precision/Recall/F1 (classification, score>=threshold as the decision
rule) for every model in baseline_comparison.py, on one run.

This exists because baseline_comparison.py only prints nDCG@K (enough to
support the "hybrid beats the baselines" ranking claim) but a paper
write-up usually wants the fuller metric table. Nothing here re-scores
candidates differently -- it reuses matching_lib.py and
evaluation_metrics.py exactly as the other three scripts do, so the
numbers stay consistent with baseline_comparison.py / ablation_study.py.

Usage:
    python research/full_evaluation.py [--data-dir research/data] [--k 10] [--threshold 70]

WARNING (same caveat as the other three scripts): if research/data/labels.csv
still holds the synthetic labels from generate_synthetic_dataset.py, these
numbers demonstrate that the pipeline runs correctly -- they are NOT real
evaluation results and must not be cited in a paper. Replace labels.csv
with real human-annotated relevance judgements first (see dataset_schema.md).
"""
import argparse
import json
import os

from dataset_loader import load_dataset, print_provenance_banner
from evaluation_metrics import (
    mean_ndcg_at_k,
    precision_at_k,
    recall_at_k,
    mean_reciprocal_rank,
    precision_recall_f1,
)
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


def rank_and_score(resumes, jobs, scorer):
    """Returns (ranked_id_lists, raw_score_lists) in a fixed job order."""
    ranked_lists, score_lists = [], []
    for job in jobs.values():
        scored = [(rid, scorer(resume, job)) for rid, resume in resumes.items()]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        ranked_lists.append([rid for rid, _ in scored])
        score_lists.append({rid: s for rid, s in scored})
    return ranked_lists, score_lists


def run(data_dir, k, threshold):
    print_provenance_banner(data_dir)
    resumes, jobs, relevance_by_job = load_dataset(data_dir)
    relevance_dicts_in_job_order = [relevance_by_job[jid] for jid in jobs]
    n_pairs = sum(len(v) for v in relevance_by_job.values())

    print(f"Dataset: {len(resumes)} resumes x {len(jobs)} jobs ({n_pairs} labelled pairs)")
    print(f"Ranking metrics @K={k}, classification metrics at score >= {threshold}\n")

    header = f"{'Model':<30}{'P@'+str(k):>8}{'R@'+str(k):>8}{'MRR':>8}{'nDCG@'+str(k):>10}{'Prec':>8}{'Recall':>8}{'F1':>8}"
    print(header)
    print("-" * len(header))

    results = {"k": k, "threshold": threshold, "n_resumes": len(resumes),
               "n_jobs": len(jobs), "n_labelled_pairs": n_pairs, "models": {}}

    for name, scorer in MODEL_SCORERS.items():
        probe = scorer(next(iter(resumes.values())), next(iter(jobs.values())))
        if probe is None:
            print(f"{name:<30}{'skipped (sentence-transformers not installed)':>10}")
            continue

        ranked_lists, score_lists = rank_and_score(resumes, jobs, scorer)

        p_at_k = sum(precision_at_k(r, rel, k) for r, rel in zip(ranked_lists, relevance_dicts_in_job_order)) / len(ranked_lists)
        r_at_k = sum(recall_at_k(r, rel, k) for r, rel in zip(ranked_lists, relevance_dicts_in_job_order)) / len(ranked_lists)
        mrr = mean_reciprocal_rank(ranked_lists, relevance_dicts_in_job_order)
        ndcg = mean_ndcg_at_k(ranked_lists, relevance_dicts_in_job_order, k)

        y_true, y_pred = [], []
        for rel, scores in zip(relevance_dicts_in_job_order, score_lists):
            for rid, label in rel.items():
                y_true.append(label)
                y_pred.append(1 if scores.get(rid, 0) >= threshold else 0)
        prec, rec, f1 = precision_recall_f1(y_true, y_pred)

        print(f"{name:<30}{p_at_k:>8.3f}{r_at_k:>8.3f}{mrr:>8.3f}{ndcg:>10.3f}{prec:>8.3f}{rec:>8.3f}{f1:>8.3f}")
        results["models"][name] = {
            f"precision@{k}": round(p_at_k, 4), f"recall@{k}": round(r_at_k, 4),
            "mrr": round(mrr, 4), f"ndcg@{k}": round(ndcg, 4),
            "classification_precision": round(prec, 4), "classification_recall": round(rec, 4),
            "classification_f1": round(f1, 4),
        }

    print(
        "\nCAVEAT: these numbers are computed against research/data/labels.csv. If that "
        "file still holds the synthetic labels from generate_synthetic_dataset.py, this "
        "run only demonstrates the pipeline works end-to-end -- do NOT cite these numbers "
        "as real evaluation results. Replace labels.csv with human-annotated data first."
    )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "data"))
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=70)
    parser.add_argument("--json-out", default=None, help="Optional path to also dump results as JSON")
    args = parser.parse_args()
    results = run(args.data_dir, args.k, args.threshold)
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nJSON written to {args.json_out}")
