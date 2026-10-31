"""
Statistical significance helpers for the research scripts: bootstrap
confidence intervals, a paired bootstrap significance test, and Cohen's d
effect size. Uses numpy (already a project dependency via scikit-learn) --
no new hard dependency. scipy is used opportunistically for a
Wilcoxon signed-rank p-value if installed, with a clear fallback message
if it isn't (mirrors how sbert_score in matching_lib.py handles its
optional dependency).
"""
import numpy as np


def bootstrap_ci(values, n_boot=5000, ci=0.95, seed=42):
    """95% (by default) bootstrap CI for the mean of `values` (e.g. per-job
    nDCG@K scores for one model). Returns (mean, lower, upper)."""
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return 0.0, 0.0, 0.0
    rng = np.random.default_rng(seed)
    n = len(values)
    boot_means = np.empty(n_boot)
    for i in range(n_boot):
        sample = values[rng.integers(0, n, size=n)]
        boot_means[i] = sample.mean()
    alpha = 1 - ci
    lower = np.percentile(boot_means, 100 * alpha / 2)
    upper = np.percentile(boot_means, 100 * (1 - alpha / 2))
    return float(values.mean()), float(lower), float(upper)


def paired_bootstrap_pvalue(diffs, n_boot=5000, seed=42):
    """Two-sided bootstrap p-value for H0: mean(diffs) == 0, where `diffs`
    is a list of per-job (or per-pair) score differences between two
    models on the SAME items (e.g. model_a_ndcg[j] - model_b_ndcg[j] for
    each job j). Non-parametric -- doesn't assume normality, appropriate
    for small sample sizes like "10 jobs"."""
    diffs = np.asarray(diffs, dtype=float)
    n = len(diffs)
    if n == 0:
        return None
    observed = diffs.mean()
    # Shift the sample to have mean 0 (simulate the null), then resample
    # and see how often we get a mean at least as extreme as observed.
    shifted = diffs - observed
    rng = np.random.default_rng(seed)
    boot_means = np.empty(n_boot)
    for i in range(n_boot):
        sample = shifted[rng.integers(0, n, size=n)]
        boot_means[i] = sample.mean()
    p = float(np.mean(np.abs(boot_means) >= np.abs(observed)))
    return max(p, 1.0 / n_boot)  # never report exactly 0 from a finite resample


def cohens_d_paired(diffs):
    """Effect size for a paired comparison: mean difference / stdev of
    differences. ~0.2 small, ~0.5 medium, ~0.8 large (Cohen's conventional
    thresholds) -- report alongside the p-value, since a tiny p-value on a
    tiny, consistent effect is a different finding than a large one."""
    diffs = np.asarray(diffs, dtype=float)
    if len(diffs) < 2 or diffs.std(ddof=1) == 0:
        return 0.0
    return float(diffs.mean() / diffs.std(ddof=1))


def wilcoxon_pvalue(diffs):
    """Optional: exact/asymptotic Wilcoxon signed-rank p-value via scipy,
    as a second (parametric-assumption-free, but different) check against
    the bootstrap p-value above. Returns None if scipy isn't installed."""
    try:
        from scipy.stats import wilcoxon
    except ImportError:
        return None
    diffs = np.asarray(diffs, dtype=float)
    diffs = diffs[diffs != 0]
    if len(diffs) < 1:
        return None
    try:
        _, p = wilcoxon(diffs)
        return float(p)
    except ValueError:
        return None


def effect_size_label(d):
    ad = abs(d)
    if ad < 0.2:
        return "negligible"
    if ad < 0.5:
        return "small"
    if ad < 0.8:
        return "medium"
    return "large"
