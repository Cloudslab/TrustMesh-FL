#!/usr/bin/env python3
"""Plot convergence curves for different non-IID levels."""

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

EXPERIMENTS = {
    'convergence-extreme': r'$\alpha=0.1$ (Extreme)',
    'convergence-moderate': r'$\alpha=0.5$ (Moderate)',
    'convergence-mild': r'$\alpha=1.0$ (Mild)',
    'convergence-iid': r'$\alpha=10.0$ (IID)',
}
MARKERS = ['o', 's', '^', 'D']
STYLES = ['-', '--', '-.', ':']


def load_jsonl(path):
    """Load all JSON records from a JSONL file."""
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def extract_metrics(results_dir, experiment):
    """Extract per-round accuracy and loss across runs."""
    pattern = os.path.join(results_dir, experiment, 'run_*')
    run_dirs = sorted(glob.glob(pattern))
    acc_by_round = defaultdict(list)
    loss_by_round = defaultdict(list)

    for run_dir in run_dirs:
        jsonl_files = glob.glob(os.path.join(run_dir, 'iot-simulation_*.jsonl'))
        round_acc = {}
        round_loss = {}
        for jf in jsonl_files:
            for rec in load_jsonl(jf):
                if rec.get('phase') == 'local_validation' and 'extra' in rec:
                    r = rec['round']
                    if 'accuracy' in rec['extra']:
                        round_acc.setdefault(r, []).append(rec['extra']['accuracy'])
                    if rec['extra'].get('loss') is not None:
                        round_loss.setdefault(r, []).append(rec['extra']['loss'])
        # Average across nodes within a single run
        for r, vals in round_acc.items():
            acc_by_round[r].append(np.mean(vals))
        for r, vals in round_loss.items():
            loss_by_round[r].append(np.mean(vals))

    return acc_by_round, loss_by_round


def build_series(metric_by_round):
    """Convert {round: [values_per_run]} to sorted arrays of (rounds, means, stds)."""
    if not metric_by_round:
        return np.array([]), np.array([]), np.array([])
    rounds = sorted(metric_by_round.keys())
    means = np.array([np.mean(metric_by_round[r]) for r in rounds])
    stds = np.array([np.std(metric_by_round[r]) for r in rounds])
    return np.array(rounds), means, stds


def plot_metric(all_data, ylabel, filename, fig_dir):
    """Plot a single metric (accuracy or loss) for all experiments."""
    fig, ax = plt.subplots()
    for idx, (exp, label) in enumerate(EXPERIMENTS.items()):
        rounds, means, stds = all_data.get(exp, (np.array([]), np.array([]), np.array([])))
        if len(rounds) == 0:
            continue
        ax.errorbar(rounds, means, yerr=stds, label=label,
                     marker=MARKERS[idx % len(MARKERS)],
                     linestyle=STYLES[idx % len(STYLES)],
                     capsize=3, markersize=5, linewidth=1.5)
    ax.set_xlabel('Communication Round')
    ax.set_ylabel(ylabel)
    ax.legend(frameon=True, fancybox=False, edgecolor='black')
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.set_xticks(ax.get_xticks())  # force integer ticks
    os.makedirs(fig_dir, exist_ok=True)
    for ext in ['pdf', 'png']:
        fig.savefig(os.path.join(fig_dir, f'{filename}.{ext}'))
    plt.close(fig)
    print(f"Saved {filename}.pdf/png to {fig_dir}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', default='experiments/results/')
    parser.add_argument('--output-dir', default='experiments/analysis/figures/')
    args = parser.parse_args()

    acc_data, loss_data = {}, {}
    for exp in EXPERIMENTS:
        acc_by_round, loss_by_round = extract_metrics(args.results_dir, exp)
        acc_data[exp] = build_series(acc_by_round)
        loss_data[exp] = build_series(loss_by_round)

    found = any(len(v[0]) > 0 for v in acc_data.values())
    if not found:
        print(f"Warning: no data found in {args.results_dir}. "
              "Expected directories like convergence-*/run_*/iot-simulation_*.jsonl")

    plot_metric(acc_data, 'Test Accuracy', 'convergence_accuracy', args.output_dir)
    plot_metric(loss_data, 'Validation Loss', 'convergence_loss', args.output_dir)


if __name__ == '__main__':
    main()
