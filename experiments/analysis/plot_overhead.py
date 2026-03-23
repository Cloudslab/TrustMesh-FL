#!/usr/bin/env python3
"""Plot consensus validation overhead comparison."""

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
    'figure.figsize': (5.0, 4.0),
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
})

EXPERIMENTS = {
    'overhead-validated': 'With Consensus\nValidation',
    'overhead-passthrough': 'Without\nValidation',
}

SUB_PHASES = ['training_wait', 'tx_submit_aggregation', 'aggregation_wait',
              'local_validation']
SUB_LABELS = ['Training', 'TX Submit', 'Aggregation', 'Validation']
COLORS = ['#4878d0', '#ee854a', '#6acc64', '#d65f5f']
HATCHES = ['///', '\\\\\\', '...', 'xxx']


def load_jsonl(path):
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def get_phase_means(results_dir, experiment):
    """Get mean duration per phase across all rounds, nodes, and runs."""
    pattern = os.path.join(results_dir, experiment, 'run_*')
    run_dirs = sorted(glob.glob(pattern))
    phase_vals = defaultdict(list)

    for run_dir in run_dirs:
        for jf in glob.glob(os.path.join(run_dir, 'iot-simulation_*.jsonl')):
            for rec in load_jsonl(jf):
                if 'phase' in rec and rec['phase'] in SUB_PHASES:
                    phase_vals[rec['phase']].append(rec['duration_ms'] / 1000.0)

    return {p: np.mean(phase_vals[p]) if phase_vals[p] else 0 for p in SUB_PHASES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', default='experiments/results/')
    parser.add_argument('--output-dir', default='experiments/analysis/figures/')
    parser.add_argument('--breakdown', action='store_true',
                        help='Show per-phase breakdown as stacked bars')
    args = parser.parse_args()

    fig, ax = plt.subplots()
    labels = list(EXPERIMENTS.values())
    x = np.arange(len(labels))
    width = 0.45

    if args.breakdown:
        bottoms = np.zeros(len(labels))
        for pi, phase in enumerate(SUB_PHASES):
            vals = []
            for exp in EXPERIMENTS:
                pm = get_phase_means(args.results_dir, exp)
                vals.append(pm[phase])
            ax.bar(x, vals, width, bottom=bottoms, label=SUB_LABELS[pi],
                   color=COLORS[pi], hatch=HATCHES[pi], edgecolor='black',
                   linewidth=0.5)
            bottoms += np.array(vals)
    else:
        totals = []
        for exp in EXPERIMENTS:
            pm = get_phase_means(args.results_dir, exp)
            totals.append(sum(pm.values()))
        bars = ax.bar(x, totals, width, color=['#4878d0', '#6acc64'],
                      edgecolor='black', linewidth=0.5)
        for bar, val in zip(bars, totals):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                        f'{val:.2f}s', ha='center', va='bottom', fontsize=9)

    ax.set_ylabel('Average Round Time (seconds)')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.grid(True, axis='y', linestyle='--', alpha=0.5)
    if args.breakdown:
        ax.legend(frameon=True, fancybox=False, edgecolor='black')

    if not any(get_phase_means(args.results_dir, e) for e in EXPERIMENTS):
        print(f"Warning: no data found in {args.results_dir}")

    os.makedirs(args.output_dir, exist_ok=True)
    suffix = '_breakdown' if args.breakdown else ''
    for ext in ['pdf', 'png']:
        fig.savefig(os.path.join(args.output_dir, f'overhead{suffix}.{ext}'))
    plt.close(fig)
    print(f"Saved overhead{suffix}.pdf/png to {args.output_dir}")


if __name__ == '__main__':
    main()
