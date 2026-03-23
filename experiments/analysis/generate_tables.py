#!/usr/bin/env python3
"""Generate LaTeX-formatted tables for the TrustMesh-FL paper."""

import argparse
import json
import os
import glob
import numpy as np
from collections import defaultdict

# --- Model specifications for communication cost ---
MODELS = {
    'MNISTNet': {'params': 62_006, 'param_bytes': 4},   # float32
    'CIFAR10Net': {'params': 200_074, 'param_bytes': 4},
}

ATTACK_MAP = {
    'byzantine-noise-1': ('Random Noise', 'Weight divergence check'),
    'byzantine-flip-1': ('Sign Flip', 'Gradient sign consistency'),
    'byzantine-scale-1': ('Scaling Attack', 'Weight magnitude bound'),
}


def load_jsonl(path):
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def get_final_accuracy(results_dir, experiment):
    """Get the mean final-round accuracy across runs."""
    pattern = os.path.join(results_dir, experiment, 'run_*')
    run_dirs = sorted(glob.glob(pattern))
    run_finals = []

    for run_dir in run_dirs:
        round_acc = defaultdict(list)
        for jf in glob.glob(os.path.join(run_dir, 'iot-simulation_*.jsonl')):
            for rec in load_jsonl(jf):
                if rec.get('phase') == 'local_validation' and 'extra' in rec:
                    if 'accuracy' in rec['extra']:
                        round_acc[rec['round']].append(rec['extra']['accuracy'])
        if round_acc:
            last_round = max(round_acc.keys())
            run_finals.append(np.mean(round_acc[last_round]))

    return np.mean(run_finals) * 100 if run_finals else float('nan')


def get_detection_rate(results_dir, experiment):
    """Estimate detection rate from event records (rejection events)."""
    pattern = os.path.join(results_dir, experiment, 'run_*')
    run_dirs = sorted(glob.glob(pattern))
    total_attacks, detected = 0, 0

    for run_dir in run_dirs:
        for jf in glob.glob(os.path.join(run_dir, '*.jsonl')):
            for rec in load_jsonl(jf):
                if rec.get('event') == 'byzantine_update_submitted':
                    total_attacks += 1
                if rec.get('event') == 'byzantine_update_rejected':
                    detected += 1

    if total_attacks == 0:
        return float('nan')
    return (detected / total_attacks) * 100


def generate_byzantine_table(results_dir):
    """Generate Table 1: Byzantine detection results."""
    baseline_acc = get_final_accuracy(results_dir, 'convergence-moderate')

    rows = []
    for exp, (attack_name, check) in ATTACK_MAP.items():
        det_rate = get_detection_rate(results_dir, exp)
        attack_acc = get_final_accuracy(results_dir, exp)
        rows.append((attack_name, det_rate, check, attack_acc, baseline_acc))

    lines = [
        r'\begin{table}[t]',
        r'\centering',
        r'\caption{Byzantine Attack Detection Results}',
        r'\label{tab:byzantine}',
        r'\begin{tabular}{lcccc}',
        r'\toprule',
        r'Attack Type & Det.\ Rate (\%) & Primary Check & Acc.\ w/ Attack & Acc.\ w/o \\',
        r'\midrule',
    ]
    for name, det, check, a_att, a_base in rows:
        det_s = f'{det:.1f}' if not np.isnan(det) else '--'
        att_s = f'{a_att:.1f}\\%' if not np.isnan(a_att) else '--'
        base_s = f'{a_base:.1f}\\%' if not np.isnan(a_base) else '--'
        lines.append(f'{name} & {det_s} & {check} & {att_s} & {base_s} \\\\')
    lines += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
    return '\n'.join(lines)


def generate_comm_table():
    """Generate Table 2: Communication cost per round (analytical)."""
    node_counts = [4, 6, 8, 10]

    lines = [
        r'\begin{table}[t]',
        r'\centering',
        r'\caption{Communication Cost per FL Round}',
        r'\label{tab:commcost}',
        r'\begin{tabular}{lccccc}',
        r'\toprule',
        r'Model & Params & Payload (KB) & Nodes & Msgs/Round & Total (MB) \\',
        r'\midrule',
    ]
    for model_name, spec in MODELS.items():
        payload_bytes = spec['params'] * spec['param_bytes']
        payload_kb = payload_bytes / 1024
        for i, n in enumerate(node_counts):
            # Messages per round: n uploads + 1 broadcast = n+1
            # Plus PBFT consensus: ~3*n messages (pre-prepare, prepare, commit)
            msgs = n + 1 + 3 * n
            total_mb = (msgs * payload_bytes) / (1024 * 1024)
            name_col = model_name if i == 0 else ''
            params_col = f'{spec["params"]:,}' if i == 0 else ''
            payload_col = f'{payload_kb:.1f}' if i == 0 else ''
            lines.append(
                f'{name_col} & {params_col} & {payload_col} & '
                f'{n} & {msgs} & {total_mb:.2f} \\\\'
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
