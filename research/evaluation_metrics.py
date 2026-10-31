"""
Evaluation metrics for the person-job matching research scripts.
------------------------------------------------------------------
Standard-library only (no scipy/pandas dependency) so these run anywhere
requirements.txt already gets you (numpy is already a dependency of the
live app for scikit-learn, so it's used here too).

Covers:
  - Classification: precision, recall, F1 (treating "human_relevance"
    labels as the ground truth and a score threshold as the decision rule)
  - Ranking: Precision@K, Recall@K, MRR, nDCG@K (recruitment
    recommendation is fundamentally a ranking problem -- a single
    accuracy number hides whether the *right* candidates end up near the
    top of the list, which is what actually matters to a recruiter
    scanning a shortlist)
  - Fairness: demographic parity difference, equal opportunity difference

All functions operate on plain Python lists/dicts -- no framework
dependency -- so they can be unit tested and reused by
baseline_comparison.py, ablation_study.py and fairness_test.py alike.
"""
import math
from statistics import mean, stdev


def precision_recall_f1(y_true, y_pred):
    """y_true / y_pred: parallel lists of 0/1. Returns (precision, recall, f1)."""
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def _ranked_relevance(ranked_ids, relevance_by_id):
    """Returns the relevance (0/1, default 0 if unlabeled) for each id in
    ranked_ids, in rank order."""
    return [relevance_by_id.get(i, 0) for i in ranked_ids]


def precision_at_k(ranked_ids, relevance_by_id, k):
    rels = _ranked_relevance(ranked_ids, relevance_by_id)[:k]
    return sum(rels) / k if k else 0.0


def recall_at_k(ranked_ids, relevance_by_id, k):
    total_relevant = sum(1 for v in relevance_by_id.values() if v == 1)
    if not total_relevant:
        return 0.0
    rels = _ranked_relevance(ranked_ids, relevance_by_id)[:k]
    return sum(rels) / total_relevant


def reciprocal_rank(ranked_ids, relevance_by_id):
    """1 / rank-of-first-relevant-item, or 0 if none found. This function
    scores ONE query; average it across queries for MRR."""
    for rank, item_id in enumerate(ranked_ids, start=1):
        if relevance_by_id.get(item_id, 0) == 1:
            return 1.0 / rank
    return 0.0


def mean_reciprocal_rank(list_of_ranked_ids, list_of_relevance_by_id):
    """MRR across multiple queries (e.g. one ranking per job posting)."""
    scores = [
        reciprocal_rank(ranked, rel)
        for ranked, rel in zip(list_of_ranked_ids, list_of_relevance_by_id)
    ]
    return mean(scores) if scores else 0.0


def dcg_at_k(ranked_ids, relevance_by_id, k):
    rels = _ranked_relevance(ranked_ids, relevance_by_id)[:k]
    return sum(rel / math.log2(idx + 2) for idx, rel in enumerate(rels))


def ndcg_at_k(ranked_ids, relevance_by_id, k):
    """Normalized DCG@K for one query (one job's ranked candidate list)."""
    dcg = dcg_at_k(ranked_ids, relevance_by_id, k)
    ideal_order = sorted(relevance_by_id.keys(), key=lambda i: relevance_by_id[i], reverse=True)
    idcg = dcg_at_k(ideal_order, relevance_by_id, k)
    return dcg / idcg if idcg > 0 else 0.0


def mean_ndcg_at_k(list_of_ranked_ids, list_of_relevance_by_id, k):
    scores = [
        ndcg_at_k(ranked, rel, k)
        for ranked, rel in zip(list_of_ranked_ids, list_of_relevance_by_id)
    ]
    return mean(scores) if scores else 0.0


def demographic_parity_difference(scores_group_a, scores_group_b, threshold=70):
    """|selection_rate(A) - selection_rate(B)| at a given score threshold
    ("selected" = score >= threshold). 0 = perfect parity."""
    rate_a = sum(1 for s in scores_group_a if s >= threshold) / len(scores_group_a) if scores_group_a else 0
    rate_b = sum(1 for s in scores_group_b if s >= threshold) / len(scores_group_b) if scores_group_b else 0
    return abs(rate_a - rate_b)


def equal_opportunity_difference(scores_group_a, labels_group_a, scores_group_b, labels_group_b, threshold=70):
    """|TPR(A) - TPR(B)| among the truly-qualified (label==1) candidates in
    each group. 0 = perfect parity in who gets correctly selected among
    equally-qualified candidates."""
    def tpr(scores, labels):
        qualified = [s for s, l in zip(scores, labels) if l == 1]
        if not qualified:
            return 0.0
        return sum(1 for s in qualified if s >= threshold) / len(qualified)

    return abs(tpr(scores_group_a, labels_group_a) - tpr(scores_group_b, labels_group_b))


def paired_score_gap_stats(paired_deltas):
    """Simple stdlib-only significance check for a list of (score_b -
    score_a) deltas from matched resume pairs (see fairness_test.py):
    mean, stdev, and a one-sample t-statistic against a null of 0 (no
    difference). No scipy dependency -- for a real paper, look up the
    p-value for the returned t-statistic against a t-distribution with
    n-1 degrees of freedom, or install scipy and use scipy.stats.ttest_1samp
    directly on the same list for a decision-ready p-value.
    """
    n = len(paired_deltas)
    if n < 2:
        return {"n": n, "mean": 0.0, "stdev": 0.0, "t_statistic": None}
    m = mean(paired_deltas)
    sd = stdev(paired_deltas)
    t_stat = (m / (sd / math.sqrt(n))) if sd > 0 else None
    return {"n": n, "mean": m, "stdev": sd, "t_statistic": t_stat}
