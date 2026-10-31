"""
Generates publication-quality figures (PNG, 300 DPI) from the research
pipeline's results: baseline comparison bar chart, ablation delta chart,
fairness parity chart, and full-metric grouped bar chart. Re-runs the
underlying scoring itself (cheap -- no training involved) rather than
depending on you having run the other scripts first with matching flags.

Requires matplotlib (see research/requirements-research.txt -- kept
separate from the live app's requirements.txt since the Flask app never
needs a plotting library).

Usage:
    python research/generate_figures.py [--data-dir research/data] [--k 10] [--out-dir research/figures]
"""
import argparse
import os

import matplotlib
matplotlib.use("Agg")  # no display available / needed
import matplotlib.pyplot as plt

from dataset_loader import load_dataset, print_provenance_banner
from evaluation_metrics import mean_ndcg_at_k
from matching_lib import (
    keyword_overlap_score,
    tfidf_cosine_score,
    sbert_score,
    hybrid_recruitsmart_score,
)
from ablation_study import VARIANTS
from fairness_test import NAME_GROUPS, build_paired_resumes

plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

BASELINE_SCORERS = {
    "Keyword": keyword_overlap_score,
    "TF-IDF + cosine": tfidf_cosine_score,
    "SBERT": sbert_score,
    "RecruitSmart\nHybrid": lambda r, j: hybrid_recruitsmart_score(r, j)["overall"],
}


def _rank_lists(resumes, jobs, scorer):
    ranked_lists = []
    for job in jobs.values():
        scored = [(rid, scorer(resume, job)) for rid, resume in resumes.items()]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        ranked_lists.append([rid for rid, _ in scored])
    return ranked_lists


def fig_baseline_comparison(resumes, jobs, relevance_by_job, k, out_dir):
    relevance_dicts = [relevance_by_job[jid] for jid in jobs]
    names, scores = [], []
    for name, scorer in BASELINE_SCORERS.items():
        probe = scorer(next(iter(resumes.values())), next(iter(jobs.values())))
        if probe is None:
            continue
        ranked = _rank_lists(resumes, jobs, scorer)
        names.append(name)
        scores.append(mean_ndcg_at_k(ranked, relevance_dicts, k))

    fig, ax = plt.subplots(figsize=(6, 4.5))
    colors = ["#9CA3AF"] * (len(names) - 1) + ["#2563EB"]
    bars = ax.bar(names, scores, color=colors, width=0.6)
    ax.set_ylabel(f"nDCG@{k}")
    ax.set_ylim(0, 1.05)
    ax.set_title("Ranking quality: RecruitSmart Hybrid vs. baselines")
    for bar, score in zip(bars, scores):
        ax.text(bar.get_x() + bar.get_width() / 2, score + 0.02, f"{score:.3f}", ha="center", fontsize=10)
    fig.tight_layout()
    path = os.path.join(out_dir, "baseline_comparison.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_ablation(resumes, jobs, relevance_by_job, k, out_dir):
    relevance_dicts = [relevance_by_job[jid] for jid in jobs]
    names, scores = [], []
    for name, flags in VARIANTS:
        ranked = []
        for job in jobs.values():
            scored = [(rid, hybrid_recruitsmart_score(resume, job, **flags)["overall"])
                      for rid, resume in resumes.items()]
            scored.sort(key=lambda pair: pair[1], reverse=True)
            ranked.append([rid for rid, _ in scored])
        names.append(name.replace("Remove ", "- "))
        scores.append(mean_ndcg_at_k(ranked, relevance_dicts, k))

    full_score = scores[0]
    deltas = [s - full_score for s in scores]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    colors = ["#2563EB"] + ["#DC2626" if d < 0 else "#9CA3AF" for d in deltas[1:]]
    bars = ax.bar(names, scores, color=colors, width=0.6)
    ax.axhline(full_score, color="#2563EB", linestyle="--", linewidth=1, alpha=0.6)
    ax.set_ylabel(f"nDCG@{k}")
    ax.set_ylim(0, 1.05)
    ax.set_title("Ablation study: component contribution to ranking quality")
    for bar, score, delta in zip(bars, scores, deltas):
        label = f"{score:.3f}" if delta == 0 else f"{score:.3f}\n({delta:+.3f})"
        ax.text(bar.get_x() + bar.get_width() / 2, score + 0.02, label, ha="center", fontsize=9)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    path = os.path.join(out_dir, "ablation_study.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_fairness(resumes, jobs, threshold, out_dir):
    paired_resumes = build_paired_resumes(resumes, NAME_GROUPS)
    group_scores = {label: [] for label in NAME_GROUPS}
    for job in jobs.values():
        for variant_id, resume in paired_resumes.items():
            score = hybrid_recruitsmart_score(resume, job)["overall"]
            group_scores[resume["_group"]].append(score)

    fig, axes = plt.subplots(1, 2, figsize=(9, 4.5))

    means = [sum(v) / len(v) if v else 0 for v in group_scores.values()]
    axes[0].bar(list(group_scores.keys()), means, color=["#2563EB", "#F59E0B"], width=0.5)
    axes[0].set_ylabel("Mean match score")
    axes[0].set_title("Mean score by name group")
    axes[0].set_ylim(0, 100)
    for i, m in enumerate(means):
        axes[0].text(i, m + 1.5, f"{m:.1f}", ha="center", fontsize=10)

    rate_a = sum(1 for s in group_scores["Group A"] if s >= threshold) / len(group_scores["Group A"])
    rate_b = sum(1 for s in group_scores["Group B"] if s >= threshold) / len(group_scores["Group B"])
    axes[1].bar(["Group A", "Group B"], [rate_a, rate_b], color=["#2563EB", "#F59E0B"], width=0.5)
    axes[1].set_ylabel(f"Selection rate (score >= {threshold})")
    axes[1].set_title("Demographic parity check")
    axes[1].set_ylim(0, 1.05)
    for i, r in enumerate([rate_a, rate_b]):
        axes[1].text(i, r + 0.02, f"{r:.1%}", ha="center", fontsize=10)

    fig.suptitle("Fairness audit: name-signal sensitivity")
    fig.tight_layout()
    path = os.path.join(out_dir, "fairness_audit.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def run(data_dir, k, threshold, out_dir):
    print_provenance_banner(data_dir)
    os.makedirs(out_dir, exist_ok=True)
    resumes, jobs, relevance_by_job = load_dataset(data_dir)

    paths = [
        fig_baseline_comparison(resumes, jobs, relevance_by_job, k, out_dir),
        fig_ablation(resumes, jobs, relevance_by_job, k, out_dir),
        fig_fairness(resumes, jobs, threshold, out_dir),
    ]
    print("Figures written:")
    for p in paths:
        print(f"  {p}")
    print(
        "\nThese are generated from the CURRENT research/data/ dataset -- if it's still "
        "synthetic (see the banner above), regenerate these figures after installing real "
        "labelled data via real_data_tools.py before using them in a paper."
    )
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "data"))
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=70)
    parser.add_argument("--out-dir", default=os.path.join(os.path.dirname(__file__), "figures"))
    args = parser.parse_args()
    run(args.data_dir, args.k, args.threshold, args.out_dir)
