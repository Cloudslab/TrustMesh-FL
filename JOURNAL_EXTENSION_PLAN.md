# TrustMesh-FL Journal Extension: Implementation Plan

## Context

TrustMesh was published at IEEE ICSA 2025 as a blockchain-enabled distributed computing framework for trustless IoT. This repository extends it with consensus-validated federated learning, where FedAvg is re-computed by every PBFT validator before acceptance — a genuine differentiator over blockchain+FL papers that only log hashes on-chain.

**Target venue**: IEEE Transactions on Parallel and Distributed Systems (TPDS). This means experiments should emphasize **system architecture, overhead analysis, and scalability** — TPDS reviewers care about rigorous systems evaluation, not just ML accuracy curves.

**Cluster**: 10+ physical K3s nodes available — full experiment matrix is feasible.

The goal is to implement the experiment infrastructure needed to produce a rigorous journal paper. The system's FL protocol is already functional; what's missing is attack simulation, instrumentation, automation, and visualization.

## Decisions

- **CIFAR-10 support**: Add CIFAR-10 as a second dataset to demonstrate generality. Requires a new model architecture (CIFAR10Net), updated validation dataset distributor, and configurable dataset selection across all components.
- **No differential privacy**: Discuss as future work only. Doesn't strengthen the core contribution.
- **Target experiments**: 14 configurations × 3 runs = 42 total experiment runs.
- **TPDS framing**: Lead with overhead breakdown and scalability; Byzantine resilience and convergence as supporting evidence.

## Bug Fix (Must Do First)

**Sample-weighted FedAvg is broken due to a key name mismatch.**

- IoT node sends `samples_count` (`mnist-federated-learning-simulation.py:319`)
- Training task outputs `samples_count` (`process.py:266`)
- Confirmation TP reads `metadata.sample_count` (`aggregation_confirmation_tp.py:345`) — **mismatched key, always gets 0, falls back to equal weighting**
- Event handler uses hardcoded equal weighting (`aggregation_event_handler.py:673`) — **must be updated to match confirmation TP's sample-weighted logic**

**Fix**: Standardize on `sample_count` everywhere. Update the event handler's `_compute_fedavg` to accept `node_contributions` and use sample weighting (matching the confirmation TP).

Files to modify:
- `iot-node/mnist-federated-learning-simulation.py` — rename `samples_count` → `sample_count`
- `sample-apps/mnist-federated-learning/federated-training-task/process.py` — rename `samples_count` → `sample_count`
- `compute-node/event_handlers/aggregation_event_handler.py` — update `_compute_fedavg` to use sample-weighted averaging

## Phase A: Byzantine Attack Simulation

**New file**: `iot-node/byzantine/attack_simulator.py`

```
class ByzantineAttackSimulator:
    - random_noise(weights)     → replace with Gaussian noise
    - sign_flip(weights)        → negate all values
    - scaling(weights, factor)  → multiply by large factor (default 100x)
```

**Modify**: `iot-node/mnist-federated-learning-simulation.py`
- Add `--byzantine-mode` CLI arg (values: `none`, `random_noise`, `sign_flip`, `scaling`)
- Inject attack between Phase 1 result and Phase 2 submission (in `submit_aggregation_phase`)

**Expected detection mapping**:
| Attack | Caught By |
|---|---|
| Random noise | `_check_weight_distributions` (bad std) + MNIST accuracy (<30%) |
| Sign flip | MNIST accuracy check (<30%) |
| Scaling (100x) | `_check_weight_magnitudes` (>10.0 threshold) |

## Phase B: Performance Instrumentation

**New file**: `observation-metrics/fl-timing/fl_timer.py`

A lightweight `FLTimer` class that records `(round, phase, node_id, start, end, duration_ms)` events and writes JSON lines to a file.

**Instrument these timing points**:

| Phase | Where | File |
|---|---|---|
| `data_prep` | Data partition selection | `mnist-federated-learning-simulation.py` |
| `tx_submit_training` | Training transaction submission | `mnist-federated-learning-simulation.py` |
| `training` | Model training | `process.py` |
| `training_wait` | Wait for trained weights | `mnist-federated-learning-simulation.py` |
| `tx_submit_aggregation` | Aggregation transaction submission | `mnist-federated-learning-simulation.py` |
| `collection_window` | Timer-based weight collection | `aggregation_event_handler.py` |
| `fedavg_compute` | FedAvg computation | `aggregation_event_handler.py` |
| `consensus_validate` | Re-compute + validate in TP | `aggregation_confirmation_tp.py` |
| `model_broadcast` | ZMQ broadcast to IoT nodes | `aggregation_event_handler.py` |
| `aggregation_wait` | Wait for global model | `mnist-federated-learning-simulation.py` |
| `local_validation` | Local test evaluation | `mnist-federated-learning-simulation.py` |
| `round_total` | End-to-end round | `mnist-federated-learning-simulation.py` |

## Phase C: Experiment Runner

**New directory**: `experiments/`

**Scripts**:
- `experiments/run_experiment.sh` — Generic runner: takes a config YAML, sets env vars on pods, launches FL on all IoT nodes, waits for completion, collects logs
- `experiments/collect_results.sh` — `kubectl cp` to gather timing JSONs, pod logs, resource CSVs
- `experiments/configs/` — One YAML per experiment configuration

**Experiment matrix**:

| Experiment | IoT Nodes | Alpha | Rounds | Byzantine | Purpose |
|---|---|---|---|---|---|
| convergence-iid | 5 | 10.0 | 10 | 0 | Baseline IID |
| convergence-mild | 5 | 1.0 | 10 | 0 | Mild non-IID |
| convergence-moderate | 5 | 0.5 | 10 | 0 | Default non-IID |
| convergence-extreme | 5 | 0.1 | 10 | 0 | Extreme non-IID |
| scale-4 | 4 | 0.5 | 5 | 0 | Scalability |
| scale-6 | 6 | 0.5 | 5 | 0 | Scalability |
| scale-8 | 8 | 0.5 | 5 | 0 | Scalability |
| scale-10 | 10 | 0.5 | 5 | 0 | Scalability |
| byzantine-noise-1 | 5 | 0.5 | 5 | 1 noise | Attack detection |
| byzantine-flip-1 | 5 | 0.5 | 5 | 1 sign_flip | Attack detection |
| byzantine-scale-1 | 5 | 0.5 | 5 | 1 scaling | Attack detection |
| byzantine-noise-2 | 5 | 0.5 | 5 | 2 noise | Multi-attacker |
| overhead-validated | 5 | 0.5 | 5 | 0 | Consensus cost |
| overhead-passthrough | 5 | 0.5 | 5 | 0 | Baseline (skip validation) |

3 runs each for error bars. Total: 42 runs.

For the overhead experiment, add a `SKIP_VALIDATION` env var to `aggregation_confirmation_tp.py` that bypasses the 4-check validation pipeline (for measurement only).

## Phase D: Results Analysis and Visualization

**New directory**: `experiments/analysis/`

| Script | Output | Paper Figure |
|---|---|---|
| `plot_convergence.py` | Accuracy vs rounds (4 alpha curves + error bars) | Fig. 1 |
| `plot_convergence.py` | Loss vs rounds | Fig. 2 |
| `plot_timing_breakdown.py` | Stacked bar: per-phase time breakdown | Fig. 3 |
| `plot_overhead.py` | Bar chart: validated vs passthrough round time | Fig. 4 |
| `plot_scalability.py` | Round time vs number of nodes | Fig. 5 |
| `plot_byzantine.py` | Accuracy with/without attackers over rounds | Fig. 6 |
| `generate_tables.py` | Byzantine detection rate per attack type | Table 1 |
| `generate_tables.py` | Communication cost per round | Table 2 |

All plots: matplotlib, IEEE-compatible fonts, grayscale-safe color scheme.

Communication cost (Table 2) can be computed analytically: MNISTNet has ~62K parameters, JSON-serialized ~600-900KB per model. Per round with N nodes: N training responses + N aggregation submissions + 1 confirmation + N broadcasts ≈ (3N+1) × model_size.

## Implementation Order

1. Fix the `sample_count` key mismatch bug + event handler FedAvg weighting
2. Create `ByzantineAttackSimulator` and wire into IoT simulation
3. Create `FLTimer` and instrument all components
4. Create experiment runner scripts and configs
5. Create analysis/visualization scripts

## Verification

- **Bug fix**: Run a 2-node FL round and check confirmation TP logs for `weight_factor` values — should reflect sample proportions, not 0.5/0.5
- **Byzantine attacks**: Run with `--byzantine-mode random_noise` on 1 node, verify confirmation TP logs show `Model validation failed` and the round is rejected
- **Timing**: Run 1 round and check that timing JSON file is produced with all 12 phases recorded
- **Experiment runner**: Run the smallest config (scale-4, 2 rounds, 1 run) end-to-end and verify results collection works
- **Plots**: Generate all figures from a single experiment's data to validate the visualization pipeline
