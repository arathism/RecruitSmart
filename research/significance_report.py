"""
Statistical significance report: for each model, a bootstrap 95% CI on
mean nDCG@K across jobs; then for RecruitSmart Hybrid vs each baseline,
a paired comparison (mean difference, 95% CI of the difference, a
bootstrap p-value, a Wilcoxon signed-rank p-value if scipy is installed,
and Cohen's d effect size).

This is the piece baseline_comparison.py / full_evaluation.py don't
cover: those print point estimates only ("Hybrid: 0.993, TF-IDF: 0.829")
with no measure of whether that gap is a real, reliable difference or
could plausibly be noise given only ~10 jobs.

Usage:
    python research/significance_report.py [--data-dir research/data] [--k 10] [--n-boot 5000]
"""
import argparse
import json
import os

from dataset_loader import load_dataset, print_provenance_banner
from evaluation_metrics import ndcg_at_k
from matching_lib import (
    keyword_overlap_score,
    tfidf_cosine_score,
    sbert_score,
    hybrid_recruitsmart_score,
)
from statistical_tests import (
    bootstrap_ci,
    paired_bootstrap_pvalue,
    cohens_d_paired,
    wilcoxon_pvalue,
    effect_size_label,
)

MODEL_SCORERS = {
    "Baseline 1: Keyword": keyword_overlap_score,
    "Baseline 2: TF-IDF + cosine": tfidf_cosine_score,
    "Baseline 3: SBERT": sbert_score,
    "RecruitSmart Hybrid": lambda r, j: hybrid_recruitsmart_score(r, j)["overall"],
}
HYBRID_NAME = "RecruitSmart Hybrid"


def per_job_ndcg(resumes, jobs, relevance_by_job, scorer, k):
    """Returns one nDCG@K per job (a list, in job-iteration order) -- the
    per-job granularity the significance tests below need, instead of the
    single pre-averaged number baseline_comparison.py prints."""
    scores = []
    for job_id, job in jobs.items():
        ranked = sorted(resumes.items(), key=lambda kv: scorer(kv[1], job), reverse=True)
        ranked_ids = [rid for rid, _ in ranked]
        scores.append(ndcg_at_k(ranked_ids, relevance_by_job[job_id], k))
    return scores


def run(data_dir, k, n_boot):
    print_provenance_banner(data_dir)
    resumes, jobs, relevance_by_job = load_dataset(data_dir)

    per_model_scores = {}
    for name, scorer in MODEL_SCORERS.items():
        probe = scorer(next(iter(resumes.values())), next(iter(jobs.values())))
        if probe is None:
            print(f"{name}: skipped (sentence-transformers not installed)\n")
            continue
        per_model_scores[name] = per_job_ndcg(resumes, jobs, relevance_by_job, scorer, k)

    print(f"Per-model mean nDCG@{k} with bootstrap 95% CI (n_boot={n_boot}, {len(jobs)} jobs):\n")
    header = f"{'Model':<30}{'mean':>8}{'95% CI':>20}"
    print(header)
    print("-" * len(header))
    results = {"k": k, "n_boot": n_boot, "n_jobs": len(jobs), "per_model": {}, "pairwise_vs_hybrid": {}}
    for name, scores in per_model_scores.items():
        mean, lo, hi = bootstrap_ci(scores, n_boot=n_boot)
        print(f"{name:<30}{mean:>8.3f}   [{lo:.3f}, {hi:.3f}]")
        results["per_model"][name] = {"mean": round(mean, 4), "ci_lower": round(lo, 4), "ci_upper": round(hi, 4)}

    if HYBRID_NAME not in per_model_scores:
        print(f"\n'{HYBRID_NAME}' scores unavailable -- cannot run pairwise comparisons.")
        return results

    hybrid_scores = per_model_scores[HYBRID_NAME]
    print(f"\nPairwise: {HYBRID_NAME} vs each baseline (paired by job):\n")
    cohens_d_label = "Cohen's d"
    header2 = f"{'Baseline':<30}{'mean diff':>10}{'95% CI of diff':>22}{'boot p':>10}{'wilcoxon p':>12}{cohens_d_label:>12}{'effect':>12}"
    print(header2)
    print("-" * len(header2))
    for name, scores in per_model_scores.items():
        if name == HYBRID_NAME:
            continue
        diffs = [h - b for h, b in zip(hybrid_scores, scores)]
        mean_diff, lo, hi = bootstrap_ci(diffs, n_boot=n_boot)
        p_boot = paired_bootstrap_pvalue(diffs, n_boot=n_boot)
        p_wil = wilcoxon_pvalue(diffs)
        d = cohens_d_paired(diffs)
        p_wil_str = f"{p_wil:.4f}" if p_wil is not None else "scipy n/a"
        print(f"{name:<30}{mean_diff:>10.3f}   [{lo:.3f}, {hi:.3f}]{p_boot:>10.4f}{p_wil_str:>12}{d:>12.2f}{effect_size_label(d):>12}")
        results["pairwise_vs_hybrid"][name] = {
            "mean_diff": round(mean_diff, 4), "ci_lower": round(lo, 4), "ci_upper": round(hi, 4),
            "bootstrap_p_value": round(p_boot, 4) if p_boot is not None else None,
            "wilcoxon_p_value": round(p_wil, 4) if p_wil is not None else None,
            "cohens_d": round(d, 4), "effect_size": effect_size_label(d),
        }

    print(
        "\nHow to read this: a small bootstrap/Wilcoxon p-value (conventionally < 0.05) means "
        "the observed gap is unlikely under 'no real difference'; Cohen's d tells you whether "
        "that gap is actually large in practice, not just statistically detectable -- report "
        "both, not p-value alone. With only "
        f"{len(jobs)} jobs, these intervals are naturally wide; more labelled jobs will "
        "narrow them. As with every other script here: these numbers are only citable once "
        "labels.csv holds real human-annotated data (see the provenance banner above)."
    )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "data"))
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--n-boot", type=int, default=5000)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()
    results = run(args.data_dir, args.k, args.n_boot)
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nJSON written to {args.json_out}")
