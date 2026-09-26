"""
Tools for bringing REAL human-labelled data into the research pipeline.
Three subcommands:

  template   Generate a blank annotation CSV (resume_id, job_id,
             human_relevance, annotator_id) for your annotators to fill
             in, from the resumes.csv / jobs.csv already in --data-dir.
             Full cross-product for small datasets, or a random sample
             of pairs (--max-pairs) for larger ones so annotators aren't
             asked to judge every resume against every job.

  agreement  Given two filled-in annotation CSVs from two different
             annotators (same shape as labels.csv), computes Cohen's
             kappa (inter-annotator agreement) on the pairs they both
             labelled, and reports simple percent agreement too.

  finalize   Given ONE annotator's file (or an already-merged/adjudicated
             file), copies it into research/data/labels.csv and writes
             research/data/dataset_metadata.json with label_source:
             "human" plus whatever annotator/agreement info you pass in
             -- this is what makes print_provenance_banner() (called by
             every eval script) stop warning that the data is synthetic.

Usage:
    python research/real_data_tools.py template --data-dir research/data --out research/data/annotation_template.csv [--max-pairs 500]
    python research/real_data_tools.py agreement --file-a annotator1.csv --file-b annotator2.csv
    python research/real_data_tools.py finalize --labels-file real_labels.csv --data-dir research/data --annotators "A. Name, B. Name" --agreement 0.81
"""
import argparse
import csv
import json
import os
import random
import shutil
import sys

from dataset_loader import _read_csv, load_dataset


def cmd_template(args):
    resumes, jobs, _ = load_dataset(args.data_dir)
    pairs = [(rid, jid) for rid in resumes for jid in jobs]
    if args.max_pairs and len(pairs) > args.max_pairs:
        rng = random.Random(args.seed)
        pairs = rng.sample(pairs, args.max_pairs)
        pairs.sort()

    with open(args.out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["resume_id", "job_id", "human_relevance", "annotator_id"])
        for rid, jid in pairs:
            writer.writerow([rid, jid, "", ""])

    print(f"Wrote {len(pairs)} blank pairs to {args.out}")
    print("Fill in human_relevance as 0 or 1 (and annotator_id) per row, then run "
          "'finalize' to install it as research/data/labels.csv.")
    if args.max_pairs and len(pairs) < len(resumes) * len(jobs):
        print(f"(Sampled {len(pairs)} of {len(resumes) * len(jobs)} possible pairs -- "
              f"raise --max-pairs to cover more.)")


def _cohens_kappa(labels_a, labels_b):
    """labels_a/labels_b: dict[(resume_id, job_id)] -> 0/1, restricted by
    the caller to keys present in both. Standard 2-rater, 2-category
    Cohen's kappa."""
    keys = sorted(set(labels_a) & set(labels_b))
    n = len(keys)
    if n == 0:
        return None, 0
    agree = sum(1 for k in keys if labels_a[k] == labels_b[k])
    po = agree / n

    a1 = sum(1 for k in keys if labels_a[k] == 1) / n
    a0 = 1 - a1
    b1 = sum(1 for k in keys if labels_b[k] == 1) / n
    b0 = 1 - b1
    pe = (a1 * b1) + (a0 * b0)

    if pe == 1.0:
        kappa = 1.0 if po == 1.0 else 0.0
    else:
        kappa = (po - pe) / (1 - pe)
    return kappa, n


def _kappa_interpretation(kappa):
    if kappa is None:
        return "no overlapping pairs to compare"
    if kappa < 0:
        return "worse than chance agreement -- annotation guidelines likely need revising"
    if kappa < 0.20:
        return "slight agreement"
    if kappa < 0.40:
        return "fair agreement"
    if kappa < 0.60:
        return "moderate agreement"
    if kappa < 0.80:
        return "substantial agreement"
    return "almost perfect agreement"


def cmd_agreement(args):
    def load_labels(path):
        rows = _read_csv(path)
        return {(r["resume_id"], r["job_id"]): int(r["human_relevance"]) for r in rows if r["human_relevance"] != ""}

    labels_a = load_labels(args.file_a)
    labels_b = load_labels(args.file_b)
    kappa, n_overlap = _cohens_kappa(labels_a, labels_b)

    overlap_keys = sorted(set(labels_a) & set(labels_b))
    pct_agree = (sum(1 for k in overlap_keys if labels_a[k] == labels_b[k]) / n_overlap) if n_overlap else 0.0

    print(f"Annotator A: {len(labels_a)} labelled pairs ({args.file_a})")
    print(f"Annotator B: {len(labels_b)} labelled pairs ({args.file_b})")
    print(f"Overlapping pairs labelled by both: {n_overlap}")
    if n_overlap == 0:
        print("No overlap -- annotators need to double-label at least a shared subset to measure agreement.")
        return
    print(f"Percent agreement: {pct_agree:.1%}")
    print(f"Cohen's kappa: {kappa:.3f} -- {_kappa_interpretation(kappa)}")
    print(
        "\nReport both the percent agreement and kappa in the paper (kappa corrects for "
        "chance agreement, percent agreement alone can look high even with weak real "
        "agreement on an imbalanced label set)."
    )
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump({"n_overlap": n_overlap, "percent_agreement": pct_agree, "cohens_kappa": kappa,
                       "interpretation": _kappa_interpretation(kappa)}, f, indent=2)
        print(f"JSON written to {args.json_out}")


def cmd_finalize(args):
    labels_path = os.path.join(args.data_dir, "labels.csv")
    rows = _read_csv(args.labels_file)
    if not rows:
        print(f"ERROR: {args.labels_file} has no rows.", file=sys.stderr)
        sys.exit(1)
    missing_vals = [r for r in rows if r.get("human_relevance", "") == ""]
    if missing_vals:
        print(f"ERROR: {len(missing_vals)} row(s) still have an empty human_relevance -- "
              f"fill in every row before finalizing (or remove unlabelled rows).", file=sys.stderr)
        sys.exit(1)
    bad_vals = [r for r in rows if r["human_relevance"] not in ("0", "1")]
    if bad_vals:
        print(f"ERROR: {len(bad_vals)} row(s) have a human_relevance that isn't 0 or 1.", file=sys.stderr)
        sys.exit(1)

    if os.path.exists(labels_path):
        backup_path = labels_path + ".bak"
        shutil.copy(labels_path, backup_path)
        print(f"Backed up existing {labels_path} -> {backup_path}")

    with open(labels_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["resume_id", "job_id", "human_relevance"])
        for r in rows:
            writer.writerow([r["resume_id"], r["job_id"], r["human_relevance"]])
    print(f"Installed {len(rows)} human-labelled rows as {labels_path}")

    metadata_path = os.path.join(args.data_dir, "dataset_metadata.json")
    metadata = {
        "label_source": "human",
        "generated_by": f"real_data_tools.py finalize (source file: {os.path.basename(args.labels_file)})",
        "annotators": args.annotators or "(not recorded -- pass --annotators next time)",
        "inter_annotator_agreement": args.agreement,
        "notes": args.notes or "",
    }
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Wrote {metadata_path} with label_source: \"human\" -- "
          f"every research script's provenance banner will now say this data is citable.")
    print("Re-run full_evaluation.py / baseline_comparison.py / ablation_study.py / "
          "fairness_test.py to get real, citable numbers.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_template = sub.add_parser("template", help="Generate a blank annotation CSV")
    p_template.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "data"))
    p_template.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data", "annotation_template.csv"))
    p_template.add_argument("--max-pairs", type=int, default=None)
    p_template.add_argument("--seed", type=int, default=42)
    p_template.set_defaults(func=cmd_template)

    p_agree = sub.add_parser("agreement", help="Compute inter-annotator agreement (Cohen's kappa)")
    p_agree.add_argument("--file-a", required=True)
    p_agree.add_argument("--file-b", required=True)
    p_agree.add_argument("--json-out", default=None)
    p_agree.set_defaults(func=cmd_agreement)

    p_final = sub.add_parser("finalize", help="Install a completed human-labelled file as labels.csv")
    p_final.add_argument("--labels-file", required=True, help="Completed CSV: resume_id,job_id,human_relevance[,annotator_id]")
    p_final.add_argument("--data-dir", default=os.path.join(os.path.dirname(__file__), "data"))
    p_final.add_argument("--annotators", default=None, help="e.g. \"Jane Doe, John Smith\"")
    p_final.add_argument("--agreement", type=float, default=None, help="Cohen's kappa from the 'agreement' command, if measured")
    p_final.add_argument("--notes", default=None)
    p_final.set_defaults(func=cmd_finalize)

    args = parser.parse_args()
    args.func(args)
