#!/usr/bin/env python3
"""Plot round completion time vs number of IoT nodes."""

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

SCALE_EXPERIMENTS = {
    'scale-4': 4,
    'scale-6': 6,
    'scale-8': 8,
    'scale-10': 10,
}


def load_jsonl(path):
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def get_round_times(results_dir, experiment):
    """Compute average round completion time across all runs."""
    pattern = os.path.join(results_dir, experiment, 'run_*')
    run_dirs = sorted(glob.glob(pattern))
    run_avgs = []

    for run_dir in run_dirs:
        round_times = defaultdict(lambda: {'start': float('inf'), 'end': 0})
        for jf in glob.glob(os.path.join(run_dir, 'iot-simulation_*.jsonl')):
            for rec in load_jsonl(jf):
                if 'phase' not in rec:
                    continue
                r = rec['round']
                round_times[r]['start'] = min(round_times[r]['start'], rec['start'])
                round_times[r]['end'] = max(round_times[r]['end'], rec['end'])
        durations = [v['end'] - v['start'] for v in round_times.values()
                     if v['end'] > v['start']]
        if durations:
            run_avgs.append(np.mean(durations))

    return run_avgs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', default='experiments/results/')
    parser.add_argument('--output-dir', default='experiments/analysis/figures/')
    args = parser.parse_args()

    nodes, means, stds = [], [], []
    for exp, n_nodes in sorted(SCALE_EXPERIMENTS.items(), key=lambda x: x[1]):
        run_avgs = get_round_times(args.results_dir, exp)
        if run_avgs:
            nodes.append(n_nodes)
            means.append(np.mean(run_avgs))
            stds.append(np.std(run_avgs))

    if not nodes:
        print(f"Warning: no data found in {args.results_dir}. "
              "Expected directories like scale-*/run_*/iot-simulation_*.jsonl")

    fig, ax = plt.subplots()
    ax.errorbar(nodes, means, yerr=stds, marker='o', capsize=4,
                linestyle='-', linewidth=1.5, markersize=6, color='#4878d0')
    ax.set_xlabel('Number of IoT Nodes')
    ax.set_ylabel('Average Round Time (seconds)')
    ax.set_xticks(nodes if nodes else [4, 6, 8, 10])
    ax.grid(True, linestyle='--', alpha=0.5)

    os.makedirs(args.output_dir, exist_ok=True)
    for ext in ['pdf', 'png']:
        fig.savefig(os.path.join(args.output_dir, f'scalability.{ext}'))
    plt.close(fig)
    print(f"Saved scalability.pdf/png to {args.output_dir}")


if __name__ == '__main__':
    main()
