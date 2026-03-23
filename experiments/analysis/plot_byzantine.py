#!/usr/bin/env python3
"""Plot accuracy under different Byzantine attack scenarios."""

import argparse
import json
import os
import glob
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import defaultdict

plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 10,
    'axes.labelsize': 11,
    'axes.titlesize': 11,
    'legend.fontsize': 9,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'figure.figsize': (5.5, 4.0),
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
})

SCENARIOS = {
    'convergence-moderate': 'No Attack (Baseline)',
    'byzantine-noise-1': 'Random Noise (1 attacker)',
    'byzantine-flip-1': 'Sign Flip (1 attacker)',
    'byzantine-scale-1': 'Scaling (1 attacker)',
}
MARKERS = ['o', 'X', 'v', 'D']
STYLES = ['-', '--', '-.', ':']


def load_jsonl(path):
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def extract_accuracy(results_dir, experiment):
    """Extract per-round accuracy aggregated across runs (honest nodes only)."""
    pattern = os.path.join(results_dir, experiment, 'run_*')
    run_dirs = sorted(glob.glob(pattern))
    acc_by_round = defaultdict(list)

    for run_dir in run_dirs:
        round_acc = defaultdict(list)
        for jf in glob.glob(os.path.join(run_dir, 'iot-simulation_*.jsonl')):
            for rec in load_jsonl(jf):
                if rec.get('phase') == 'local_validation' and 'extra' in rec:
                    if 'accuracy' in rec['extra']:
                        round_acc[rec['round']].append(rec['extra']['accuracy'])
        for r, vals in round_acc.items():
            acc_by_round[r].append(np.mean(vals))

    if not acc_by_round:
        return np.array([]), np.array([]), np.array([])
    rounds = sorted(acc_by_round.keys())
    means = np.array([np.mean(acc_by_round[r]) for r in rounds])
    stds = np.array([np.std(acc_by_round[r]) for r in rounds])
    return np.array(rounds), means, stds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', default='experiments/results/')
    parser.add_argument('--output-dir', default='experiments/analysis/figures/')
    args = parser.parse_args()

    fig, ax = plt.subplots()
    for idx, (exp, label) in enumerate(SCENARIOS.items()):
        rounds, means, stds = extract_accuracy(args.results_dir, exp)
        if len(rounds) == 0:
            continue
        ax.errorbar(rounds, means, yerr=stds, label=label,
                     marker=MARKERS[idx], linestyle=STYLES[idx],
                     capsize=3, markersize=5, linewidth=1.5)

    ax.set_xlabel('Communication Round')
    ax.set_ylabel('Test Accuracy')
    ax.legend(frameon=True, fancybox=False, edgecolor='black')
    ax.grid(True, linestyle='--', alpha=0.5)

    if not any(extract_accuracy(args.results_dir, e)[0].size for e in SCENARIOS):
        print(f"Warning: no data found in {args.results_dir}")

    os.makedirs(args.output_dir, exist_ok=True)
    for ext in ['pdf', 'png']:
        fig.savefig(os.path.join(args.output_dir, f'byzantine_accuracy.{ext}'))
    plt.close(fig)
    print(f"Saved byzantine_accuracy.pdf/png to {args.output_dir}")


if __name__ == '__main__':
    main()
