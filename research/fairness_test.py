"""
Fairness audit: controlled resume-pair testing.
--------------------------------------------------
Standard resume-audit-study methodology (the same idea used in real hiring
discrimination research: hold every substantive qualification identical
and change ONLY a demographic-associated signal, then see if the outcome
changes). Do NOT claim "bias-free recruitment" from this or any test --
report it as "fairness-aware candidate evaluation": here is what we
tested, on what data, and here is what we found (see module docstring in
research/evaluation_metrics.py for the same framing applied to the
metrics themselves).

What this script does:
  1. Builds N matched resume pairs. Each pair has IDENTICAL skills,
     experience, and education -- the only thing that differs is a name
     inserted at the top of the resume text, drawn from two name lists
     commonly associated with different demographic groups (here: a
     first-pass on gender-associated first names; extend NAME_GROUPS with
     other axes -- e.g. racially-associated names, as in the classic
     Bertrand & Mullainathan 2004 audit study methodology -- following the
     same pattern if you need that for your report).
  2. Scores every resume against a fixed pool of jobs using the real
     hybrid matcher.
  3. Reports:
       - demographic parity difference (selection-rate gap at a score
         threshold)
       - equal opportunity difference (true-positive-rate gap among
         candidates who are equally qualified per the label data)
       - the raw paired score gap (mean/stdev/t-statistic) between the two
         names in each pair, which is the most direct signal: if match
         score is a function of skills/experience/education only, this
         gap should be ~0.

Usage:
    python research/generate_synthetic_dataset.py   # if research/data/ doesn't exist yet
    python research/fairness_test.py [--data-dir research/data] [--threshold 70]
"""
import argparse
import os

from dataset_loader import load_dataset, print_provenance_banner
from evaluation_metrics import (
    demographic_parity_difference,
    equal_opportunity_difference,
    paired_score_gap_stats,
)
from matching_lib import hybrid_recruitsmart_score

# Commonly gender-associated first names used in prior resume-audit
# literature. This is ONE demographic axis as a worked example -- add
# further NAME_GROUPS entries (e.g. name lists associated with different
# racial/ethnic groups, as in real audit studies) to extend the same test.
NAME_GROUPS = {
    "Group A": ["Emily", "Anne", "Laurie", "Kristen", "Meredith"],
    "Group B": ["Greg", "Brad", "Brendan", "Todd", "Matthew"],
}


def build_paired_resumes(base_resumes, name_groups, rng_seed=0):
    """For each base resume, create one variant per name group, identical
    except for the inserted name. Returns dict {resume_id: resume_dict}."""
    paired = {}
    group_names = list(name_groups.items())
    for base_id, base in base_resumes.items():
        for group_label, names in group_names:
            name = names[hash(base_id + group_label) % len(names)]
            variant_id = f"{base_id}__{group_label.replace(' ', '_')}"
            paired[variant_id] = {
                "id": variant_id,
                "text": f"{name}. " + base["text"],
                "skills": list(base["skills"]),
                "experience_years": base["experience_years"],
                "_base_id": base_id,
                "_group": group_label,
            }
    return paired


def run(data_dir, threshold):
    print_provenance_banner(data_dir)
    resumes, jobs, relevance_by_job = load_dataset(data_dir)
    paired_resumes = build_paired_resumes(resumes, NAME_GROUPS)

    group_scores = {label: [] for label in NAME_GROUPS}
    group_labels = {label: [] for label in NAME_GROUPS}  # human_relevance, for equal-opportunity
    paired_deltas = []  # score(Group B) - score(Group A), matched by base resume + job

    scores_by_variant_and_job = {}  # (variant_id, job_id) -> score

    for job_id, job in jobs.items():
        per_base = {}  # base_id -> {group_label: score}
        for variant_id, resume in paired_resumes.items():
            result = hybrid_recruitsmart_score(resume, job)
            score = result["overall"]
            scores_by_variant_and_job[(variant_id, job_id)] = score
            group_scores[resume["_group"]].append(score)
            group_labels[resume["_group"]].append(relevance_by_job.get(job_id, {}).get(resume["_base_id"], 0))
            per_base.setdefault(resume["_base_id"], {})[resume["_group"]] = score

        labels = list(NAME_GROUPS.keys())
        if len(labels) == 2:
            a_label, b_label = labels
            for base_id, scores in per_base.items():
                if a_label in scores and b_label in scores:
                    paired_deltas.append(scores[b_label] - scores[a_label])

    print(f"Fairness audit over {len(resumes)} base resumes x {len(jobs)} jobs "
          f"({len(paired_resumes)} name-variant resumes)\n")

    labels = list(NAME_GROUPS.keys())
    dp_diff = demographic_parity_difference(group_scores[labels[0]], group_scores[labels[1]], threshold=threshold)
    print(f"Demographic parity difference (threshold={threshold}): {dp_diff:.4f}")

    eo_diff = equal_opportunity_difference(
        group_scores[labels[0]], group_labels[labels[0]],
        group_scores[labels[1]], group_labels[labels[1]],
        threshold=threshold,
    )
    print(f"Equal opportunity difference (threshold={threshold}): {eo_diff:.4f}")

    stats = paired_score_gap_stats(paired_deltas)
    print(f"\nPaired score gap ({labels[1]} minus {labels[0]}, same skills/experience/education):")
    print(f"  n={stats['n']}  mean={stats['mean']:+.3f}  stdev={stats['stdev']:.3f}  "
          f"t-statistic={stats['t_statistic']}")
    print(
        "\nInterpretation: all three numbers close to 0 means changing only the name did not "
        "change the score -- i.e. this test found no evidence that the matcher's output is "
        "sensitive to this name signal, on this dataset. That is a narrow, specific finding: "
        "it does NOT mean the system is 'bias-free' overall (see module docstring) -- other "
        "axes, other proxies for demographic information, and real-world resume variation "
        "were not tested here."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "data"))
    parser.add_argument("--threshold", type=int, default=70)
    args = parser.parse_args()
    run(args.data_dir, args.threshold)
