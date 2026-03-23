#!/usr/bin/env python3
"""Plot per-phase timing breakdown as a stacked bar chart."""

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
    'figure.figsize': (6.0, 4.0),
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
})

PHASES = ['training_wait', 'tx_submit_aggregation', 'aggregation_wait',
          'local_validation', 'round_overhead']
PHASE_LABELS = ['Training', 'TX Submit', 'Aggregation Wait',
                'Validation', 'Overhead']
HATCHES = ['///', '\\\\\\', '...', 'xxx', '---']
COLORS = ['#4878d0', '#ee854a', '#6acc64', '#d65f5f', '#956cb4']


def load_jsonl(path):
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def compute_round_phases(records, target_round):
    """Compute per-phase durations for a specific round from one node's records."""
    phase_dur = {}
    round_start, round_end = None, None
    for rec in records:
        if rec.get('round') != target_round or 'phase' not in rec:
            continue
        phase = rec['phase']
        dur_s = rec['duration_ms'] / 1000.0
        phase_dur[phase] = dur_s
        if round_start is None or rec['start'] < round_start:
            round_start = rec['start']
        if round_end is None or rec['end'] > round_end:
            round_end = rec['end']

    if round_start is not None and round_end is not None:
        total = round_end - round_start
        accounted = sum(phase_dur.get(p, 0) for p in PHASES if p != 'round_overhead')
        phase_dur['round_overhead'] = max(0, total - accounted)
    return phase_dur


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', default='experiments/results/')
    parser.add_argument('--experiment', default='convergence-moderate')
    parser.add_argument('--round', type=int, default=1, help='Round number to plot')
    parser.add_argument('--output-dir', default='experiments/analysis/figures/')
    args = parser.parse_args()

    pattern = os.path.join(args.results_dir, args.experiment, 'run_*')
    run_dirs = sorted(glob.glob(pattern))

    # Collect per-phase durations across all nodes and runs
    phase_values = defaultdict(list)
    for run_dir in run_dirs:
        for jf in glob.glob(os.path.join(run_dir, 'iot-simulation_*.jsonl')):
            recs = load_jsonl(jf)
            pd = compute_round_phases(recs, args.round)
            for phase in PHASES:
                if phase in pd:
                    phase_values[phase].append(pd[phase])

    if not phase_values:
        print(f"Warning: no timing data found for {args.experiment} round {args.round}")

    means = [np.mean(phase_values.get(p, [0])) for p in PHASES]
    stds = [np.std(phase_values.get(p, [0])) for p in PHASES]

    fig, ax = plt.subplots()
    bottom = 0
    bars = []
    for i, (m, s, label) in enumerate(zip(means, stds, PHASE_LABELS)):
        b = ax.bar('Round Timing', m, bottom=bottom, label=label,
                    color=COLORS[i], hatch=HATCHES[i], edgecolor='black',
                    linewidth=0.5, width=0.5)
        bars.append(b)
        bottom += m

    ax.set_ylabel('Time (seconds)')
    ax.set_title(f'Phase Breakdown — {args.experiment} (Round {args.round})')
    ax.legend(loc='upper right', frameon=True, fancybox=False, edgecolor='black')
    ax.grid(True, axis='y', linestyle='--', alpha=0.5)

    os.makedirs(args.output_dir, exist_ok=True)
    for ext in ['pdf', 'png']:
        fig.savefig(os.path.join(args.output_dir, f'timing_breakdown.{ext}'))
    plt.close(fig)
    print(f"Saved timing_breakdown.pdf/png to {args.output_dir}")


if __name__ == '__main__':
    main()
