#!/usr/bin/env python3
"""Backfill validation loss into timing JSONLs from simulation logs.

Older IoT images recorded only accuracy in the local_validation timing record,
but every run's simulation log prints both accuracy and loss per round:

    ✅ LOCAL EVALUATION COMPLETED
       • Overall accuracy: 0.5181 (51.81%)
       • Loss: 2.2954

This script pairs each local_validation record in
<run_dir>/iot-simulation_iot-N.jsonl with the corresponding evaluation block in
<run_dir>/logs/iot-N_simulation.log (in order, cross-checked by the rounded
accuracy value) and writes extra.loss back into the JSONL in place.
Idempotent: records that already carry a non-null loss are left untouched.
"""

import argparse
import glob
import json
import os
import re

ACC_RE = re.compile(r"Overall accuracy: ([0-9.]+) \(")
LOSS_RE = re.compile(r"Loss: ([0-9.]+)")


def parse_log_pairs(log_path):
    """Return [(accuracy, loss), ...] in evaluation order from a simulation log."""
    pairs = []
    acc = None
    with open(log_path, errors="replace") as f:
        for line in f:
            m = ACC_RE.search(line)
            if m:
                acc = float(m.group(1))
                continue
            m = LOSS_RE.search(line)
            if m and acc is not None:
                pairs.append((acc, float(m.group(1))))
                acc = None
    return pairs


def backfill_file(jsonl_path, log_path):
    records = [json.loads(l) for l in open(jsonl_path) if l.strip()]
    pairs = parse_log_pairs(log_path)
    todo = [r for r in records
            if r.get("phase") == "local_validation"
            and r.get("extra", {}).get("loss") is None]
    if not todo:
        return 0
    if len(pairs) < len(todo):
        print(f"  WARNING: {jsonl_path}: {len(todo)} records need loss but log "
              f"has only {len(pairs)} evaluation blocks; skipping")
        return 0
    filled = 0
    pi = 0
    for rec in records:
        if rec.get("phase") != "local_validation":
            continue
        if rec.get("extra", {}).get("loss") is not None:
            pi += 1  # keep log blocks aligned with records
            continue
        acc_log, loss = pairs[pi]
        acc_rec = rec.get("extra", {}).get("accuracy")
        if acc_rec is None or abs(round(acc_rec, 4) - acc_log) > 5e-4:
            print(f"  WARNING: {jsonl_path}: accuracy mismatch at record round "
                  f"{rec.get('round')} (jsonl {acc_rec} vs log {acc_log}); skipping file")
            return 0
        rec.setdefault("extra", {})["loss"] = loss
        filled += 1
        pi += 1
    with open(jsonl_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return filled


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", default="experiments/results/")
    args = parser.parse_args()

    total = 0
    for run_dir in sorted(glob.glob(os.path.join(args.results_dir, "*", "run_*"))):
        for jsonl_path in sorted(glob.glob(os.path.join(run_dir, "iot-simulation_iot-*.jsonl"))):
            node = re.search(r"iot-simulation_(iot-\d+)\.jsonl", jsonl_path).group(1)
            log_path = os.path.join(run_dir, "logs", f"{node}_simulation.log")
            if not os.path.exists(log_path):
                print(f"  WARNING: no log for {jsonl_path}; skipping")
                continue
            n = backfill_file(jsonl_path, log_path)
            if n:
                print(f"  {jsonl_path}: filled {n} loss values")
                total += n
    print(f"Backfilled {total} loss values.")


if __name__ == "__main__":
    main()
