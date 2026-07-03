#!/usr/bin/env python3
"""Generate LaTeX-formatted tables for the TrustMesh-FL paper."""

import argparse
import json
import os
import glob
import re
from datetime import datetime, timezone
from collections import Counter, defaultdict

import numpy as np

# --- Model payloads for communication cost ---
# MNISTNet payload is the measured size of a stored CouchDB weight document
# (JSON-serialised state dict); CIFAR10Net is scaled by parameter count.
MNIST_PARAMS = 257_162
CIFAR_PARAMS = 620_810
MNIST_PAYLOAD_BYTES = 5_525_730  # measured
CIFAR_PAYLOAD_BYTES = int(MNIST_PAYLOAD_BYTES * CIFAR_PARAMS / MNIST_PARAMS)
MODELS = {
    'MNISTNet': {'params': MNIST_PARAMS, 'payload_bytes': MNIST_PAYLOAD_BYTES},
    'CIFAR10Net': {'params': CIFAR_PARAMS, 'payload_bytes': CIFAR_PAYLOAD_BYTES},
}

ATTACKS = {
    'byzantine-noise-1': 'Random Noise',
    'byzantine-noise-2': 'Random Noise (2 nodes)',
    'byzantine-flip-1': 'Sign Flip',
    'byzantine-scale-1': 'Scaling Attack',
}

# Map the confirmation TP's internal check names to reader-facing labels.
CHECK_LABELS = {
    'weight_magnitude': 'Weight magnitude bound',
    'weight_distribution': 'Weight distribution',
    'model_sanity': 'NaN/Inf sanity',
    'mnist_validation': 'Validation-set accuracy',
}

TP_LOG_TS = re.compile(r'^\[?(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})')
# The rejection is echoed on several lines (error, re-raise, traceback);
# match only the primary ERROR line so each rejection is counted once per validator.
FAILED_CHECKS = re.compile(r'- ERROR - Model validation failed: Failed checks: ([a-z_,\s]+)')


def load_jsonl(path):
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def run_time_window(run_dir):
    """(min start, max end) epoch seconds across a run's timing records."""
    starts, ends = [], []
    for jf in glob.glob(os.path.join(run_dir, 'iot-simulation_*.jsonl')):
        for rec in load_jsonl(jf):
            if 'start' in rec:
                starts.append(rec['start'])
            if 'end' in rec:
                ends.append(rec['end'])
    if not starts:
        return None
    return min(starts), max(ends)


def get_accuracy_by_round(results_dir, experiment):
    """{round: mean accuracy across nodes and runs}"""
    acc = defaultdict(list)
    for run_dir in sorted(glob.glob(os.path.join(results_dir, experiment, 'run_*'))):
        round_acc = defaultdict(list)
        for jf in glob.glob(os.path.join(run_dir, 'iot-simulation_*.jsonl')):
            for rec in load_jsonl(jf):
                if rec.get('phase') == 'local_validation' and \
                        rec.get('extra', {}).get('accuracy') is not None:
                    round_acc[rec['round']].append(rec['extra']['accuracy'])
        for r, vals in round_acc.items():
            acc[r].append(np.mean(vals))
    return {r: np.mean(v) for r, v in acc.items()}


def get_detection_stats(results_dir, experiment):
    """(submitted, rejected) Byzantine update counts from simulation events."""
    submitted, rejected = 0, 0
    for run_dir in sorted(glob.glob(os.path.join(results_dir, experiment, 'run_*'))):
        for jf in glob.glob(os.path.join(run_dir, 'iot-simulation_*.jsonl')):
            for rec in load_jsonl(jf):
                if rec.get('event') == 'byzantine_update_submitted':
                    submitted += 1
                elif rec.get('event') == 'byzantine_update_rejected':
                    rejected += 1
    return submitted, rejected


def get_observed_checks(results_dir, experiment):
    """Which validation checks actually failed during this experiment's runs.

    Parses the collected aggregation-confirmation-tp logs, scoped to each
    run's time window (the pod logs span the pod lifetime, not one run).
    """
    counts = Counter()
    for run_dir in sorted(glob.glob(os.path.join(results_dir, experiment, 'run_*'))):
        window = run_time_window(run_dir)
        if window is None:
            continue
        t0, t1 = window
        for lf in glob.glob(os.path.join(run_dir, 'logs',
                                         '*aggregation-confirmation-tp.log')):
            with open(lf, errors='replace') as f:
                for line in f:
                    m = FAILED_CHECKS.search(line)
                    if not m:
                        continue
                    ts = TP_LOG_TS.match(line)
                    if ts:
                        t = datetime.strptime(ts.group(1).replace('T', ' '),
                                              '%Y-%m-%d %H:%M:%S')
                        t = t.replace(tzinfo=timezone.utc).timestamp()
                        if not (t0 - 60 <= t <= t1 + 60):
                            continue
                    for name in m.group(1).split(','):
                        counts[name.strip()] += 1
    return counts


def generate_byzantine_table(results_dir):
    """Byzantine detection results, baseline matched to the attack's final round."""
    baseline_by_round = get_accuracy_by_round(results_dir, 'convergence-moderate')

    lines = [
        r'\begin{table}[t]',
        r'\centering',
        r'\caption{Byzantine Attack Detection Results}',
        r'\label{tab:byzantine}',
        r'\begin{tabular}{lcccc}',
        r'\toprule',
        r'Attack & Det.\ Rate & Observed Check & Acc.\ w/ Attack & Acc.\ w/o \\',
        r'\midrule',
    ]
    for exp, attack_name in ATTACKS.items():
        submitted, rejected = get_detection_stats(results_dir, exp)
        det_s = f'{100.0 * rejected / submitted:.1f}\\%' if submitted else '--'

        acc_by_round = get_accuracy_by_round(results_dir, exp)
        if acc_by_round:
            last_round = max(acc_by_round.keys())
            att_s = f'{100 * acc_by_round[last_round]:.1f}\\%'
            base = baseline_by_round.get(last_round)
            base_s = f'{100 * base:.1f}\\%' if base is not None else '--'
        else:
            att_s, base_s = '--', '--'

        checks = get_observed_checks(results_dir, exp)
        if checks:
            top = checks.most_common(1)[0][0]
            check_s = CHECK_LABELS.get(top, top.replace('_', ' '))
        else:
            check_s = '--'
        lines.append(f'{attack_name} & {det_s} & {check_s} & {att_s} & {base_s} \\\\')

    lines += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
    return '\n'.join(lines)


def generate_comm_table():
    """Communication cost per round vs. node count.

    Per-round weight transfers: N uploads + 1 confirmation broadcast + N IoT
    deliveries = 2N + 1 payload-sized messages (PBFT consensus messages carry
    block metadata and content hashes, not model payloads).
    """
    node_counts = [4, 6, 8, 10]

    lines = [
        r'\begin{table}[t]',
        r'\centering',
        r'\caption{Communication Cost per FL Round}',
        r'\label{tab:commcost-scaling}',
        r'\begin{tabular}{lccccc}',
        r'\toprule',
        r'Model & Params & Payload (MB) & Nodes & Msgs/Round & Total (MB) \\',
        r'\midrule',
    ]
    for model_name, spec in MODELS.items():
        payload_mb = spec['payload_bytes'] / 1e6
        for i, n in enumerate(node_counts):
            msgs = 2 * n + 1
            total_mb = msgs * payload_mb
            name_col = model_name if i == 0 else ''
            params_col = f'{spec["params"]:,}' if i == 0 else ''
            payload_col = f'{payload_mb:.1f}' if i == 0 else ''
            lines.append(
                f'{name_col} & {params_col} & {payload_col} & '
                f'{n} & {msgs} & {total_mb:.1f} \\\\'
            )
        if model_name != list(MODELS.keys())[-1]:
            lines.append(r'\midrule')

    lines += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', default='experiments/results/')
    parser.add_argument('--output-dir', default='experiments/analysis/figures/')
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    table1 = generate_byzantine_table(args.results_dir)
    path1 = os.path.join(args.output_dir, 'table_byzantine.tex')
    with open(path1, 'w') as f:
        f.write(table1 + '\n')
    print(f"Table 1 (Byzantine detection):\n{table1}\n")
    print(f"Saved to {path1}\n")

    table2 = generate_comm_table()
    path2 = os.path.join(args.output_dir, 'table_commcost.tex')
    with open(path2, 'w') as f:
        f.write(table2 + '\n')
    print(f"Table 2 (Communication cost):\n{table2}\n")
    print(f"Saved to {path2}")


if __name__ == '__main__':
    main()
