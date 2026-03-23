# Federated Learning Design for TrustMesh-FL

## Overview

This document describes the design and architecture of the federated learning extension to TrustMesh. The extension enables consensus-validated federated learning across heterogeneous IoT nodes while preserving the existing three-layer architecture and backward compatibility with non-federated workflows.

The core design principle is that **model aggregation is a blockchain transaction** — every validator independently re-computes FedAvg and validates the result before the aggregated model is accepted into blockchain state. This provides trust guarantees that standard federated learning (which relies on an honest aggregation server) cannot offer.

## Design Decisions

### Why Separate Aggregation TPs (Not Modified iot-data-tp)

An early design considered modifying `iot-data-tp` to accumulate federated data in Redis lists and triggering aggregation from the scheduler. This was rejected because:

1. **Separation of concerns**: Aggregation is fundamentally different from IoT data ingestion — it involves ML model validation, not data routing
2. **Consensus requirements**: FedAvg must be deterministically verifiable by all validators, which requires dedicated transaction processor logic
3. **Backward compatibility**: Existing TPs remain untouched; federated learning is purely additive
4. **Independent round lifecycle**: Aggregation rounds have their own state machine (collecting → locked → confirmed/failed), separate from scheduling state

### Why Time-Windowed Collection (Not Coordinator-Based)

An early design used a coordinator node that created a shared `schedule_id` for all participants. This was replaced with time-windowed collection because:

1. **No single point of failure**: Any node can initiate or join a round independently
2. **Asynchronous participation**: Nodes submit at their own pace within a configurable timeout window
3. **Simpler protocol**: No need for schedule_id broadcasting or coordinator election at the IoT layer
4. **Realistic IoT modeling**: IoT nodes may come online at different times — the time window naturally handles this

### Why CouchDB for Model Weights (Not Blockchain State or Redis)

Model weights (several MB as JSON) are stored in CouchDB rather than blockchain state or Redis:

1. **Blockchain state**: Has size constraints and would bloat the Merkle tree — blockchain state stores only metadata (document IDs, content hashes, participation records)
2. **Redis**: Ephemeral and not designed for large document storage — Redis is used for node resource tracking and coordination only
3. **CouchDB**: Already part of the TrustMesh stack, supports large documents, provides replication across the cluster, and enables integrity verification via content hashes

## Architecture

### Component Overview

```
IoT Nodes                    Compute Nodes                  Blockchain (Sawtooth)
─────────                    ─────────────                  ─────────────────────

mnist-federated-             aggregation_event_handler      aggregation-request-tp
  learning-simulation          ├─ FederatedAggregator          ├─ Collects weights
  ├─ Local training            ├─ CouchDB storage             ├─ Selects aggregator
  ├─ Weight submission         └─ FedAvg computation           ├─ Manages rounds
  └─ Model reception                                          └─ Emits events

federated_response_manager                                  aggregation-confirmation-tp
  ├─ ZMQ model reception                                       ├─ Re-computes FedAvg
  ├─ Training result caching                                   ├─ Validates model
  └─ Convergence tracking                                      └─ Confirms/rejects

                                                            validation-dataset-distributor
                                                               └─ Stores MNIST test set
                                                                  in CouchDB
```

### Data Flow

#### Phase 1: Local Training

```
IoT Node                    TrustMesh Core              Compute Node
────────                    ──────────────              ────────────
Submit training data  ──►   iot-data-tp stores     ──►  schedule_event_handler
  (x_train, y_train,        in Redis                    picks up schedule
   initial_weights)                                           │
                                                              ▼
                                                        task_executor runs
                                                        federated-training-task
                                                              │
Receive trained       ◄──   ZMQ response           ◄──  Returns trained weights
  weights via ZMQ            manager                     (state_dict format)
```

#### Phase 2: Federated Aggregation

```
IoT Node                    Blockchain Validators           Aggregator Compute Node
────────                    ─────────────────────           ────────────────────────
Submit trained         ──►  aggregation-request-tp
  weights + metadata         ├─ First node: creates
                             │   new round + selects
                             │   aggregator via Redis
                             ├─ Later nodes: join
                             │   existing round
                             └─ Emits aggregation-
                                request event
                                      │
                                      ▼
                             aggregation_event_handler  ◄── Receives event
                               ├─ Stores weights in CouchDB
                               ├─ Starts collection timer
                               │   (AGGREGATION_TIMEOUT seconds)
                               └─ On timer expiry:
                                    ├─ Locks round (via confirmation-tp)
                                    ├─ Fetches all weights from CouchDB
                                    ├─ Computes sample-weighted FedAvg
                                    └─ Submits confirmation transaction
                                              │
                                              ▼
                             aggregation-confirmation-tp
                               ├─ Re-computes FedAvg independently
                               ├─ Verifies weights match (tolerance: 1e-6)
                               ├─ Validates model on MNIST test set
                               │   (must achieve ≥30% accuracy)
                               └─ If valid: confirms + emits event
                                              │
                                              ▼
                             aggregation_event_handler
                               └─ Broadcasts global model to
Receive global model   ◄──        all participating IoT nodes
  via ZMQ                         via ZMQ
```

### Blockchain State Layout

All state is stored under two namespaces for serialized execution:

**Aggregation Request Namespace** (`sha512('aggregation-request')[:6]`):

| Address Key | Content |
|---|---|
| `{workflow_id}_active_round` | Pointer to current active aggregation round |
| `{workflow_id}_global_round_counter` | Monotonic round counter |
| `{workflow_id}_agg_{round_number}` | Round data: status, participating nodes, contribution metadata (no weights) |

**Aggregation Confirmation Namespace** (`sha512('aggregation-confirmation')[:6]`):

| Address Key | Content |
|---|---|
| `{aggregation_id}_confirmation` | Confirmed aggregated weights, validation results, participating nodes |

Both TPs declare overlapping namespaces to force Sawtooth to serialize their transactions, preventing concurrent reads/writes to shared state.

### Round State Machine

```
collecting ──► locked ──► confirmed
    │              │
    └──► expired   └──► failed
```

- **collecting**: Accepting node contributions. Transitions to `locked` when the aggregation timer expires.
- **locked**: No new contributions accepted. Aggregator computes FedAvg and submits confirmation.
- **confirmed**: FedAvg verified and model validated by consensus. Terminal state.
- **failed**: Insufficient nodes or validation failure. Terminal state.
- **expired**: Round was in `collecting` for longer than `AGGREGATION_TIMEOUT * 2` without being locked. A new round can be created.

### CouchDB Storage

**Database: `model_weights`**

Per-node model weights stored by the aggregator compute node after receiving `aggregation-request` events:

```json
{
  "_id": "{aggregation_id}_{node_id}_weights",
  "aggregation_id": "workflow_agg_1",
  "node_id": "iot-0",
  "model_weights": {"conv1.weight": [...], "conv1.bias": [...], ...},
  "content_hash": "sha256_hex_digest",
  "timestamp": 1700000000
}
```

**Database: `validation_datasets`**

Shared MNIST validation dataset distributed by `validation-dataset-distributor` at deployment time:

```json
{
  "_id": "mnist_validation_dataset",
  "x_data": [[...], ...],
  "y_data": [7, 2, 1, ...],
  "metadata": {
    "total_samples": 1000,
    "data_hash": "sha256_of_x_data_bytes",
    "x_dtype": "float32",
    "y_dtype": "int64",
    "seed": 42
  }
}
```

### Data Partitioning

Training data is partitioned across IoT nodes using a **Dirichlet distribution** for configurable non-IID levels:

```python
# For each MNIST class, draw proportions from Dir(alpha, ..., alpha)
proportions = np.random.dirichlet(np.repeat(NON_IID_ALPHA, TOTAL_NODES))
```

- The global seed (42) ensures all nodes compute identical partitions deterministically
- Each node selects its own slice based on `node_index`
- Lower alpha → more heterogeneous (each node sees fewer classes)
- Higher alpha → more homogeneous (approaches IID)

### FedAvg Aggregation

The aggregation uses **sample-weighted averaging**:

```
w_global[layer] = Σ (n_k / n_total) * w_k[layer]
```

Where `n_k` is the number of training samples from node `k` and `n_total` is the sum across all participating nodes. If sample counts are unavailable in the contribution metadata, equal weighting is used as fallback.

The confirmation TP independently re-computes this and verifies the aggregator's result within a tolerance of `1e-6`.

### Model Validation Pipeline

The `aggregation-confirmation-tp` performs four validation checks before accepting an aggregated model:

1. **Weight magnitude**: No parameter exceeds `MAX_WEIGHT_MAGNITUDE` (10.0)
2. **Weight distribution**: No NaN/Inf values; standard deviation between 0.01 and 2.0
3. **Model sanity**: Non-empty weights with recognizable layer names (contains "weight" or "kernel")
4. **MNIST accuracy**: Model must achieve ≥30% accuracy on the shared validation dataset stored in CouchDB

All four checks must pass. If the validation dataset is unavailable in CouchDB, the MNIST accuracy check **fails** (does not degrade gracefully) to prevent unvalidated models from entering blockchain state.

### Shared Model Architecture

The `MNISTNet` CNN architecture is defined once in `shared/models/mnist_model.py` and imported by all components that need it:

- `iot-node/mnist-federated-learning-simulation.py` (local evaluation)
- `sample-apps/mnist-federated-learning/federated-training-task/process.py` (training)
- `scheduling/aggregation-confirmation-tp/aggregation_confirmation_tp.py` (validation)

This prevents architecture drift — if any component used a different model definition, `load_state_dict()` would fail with shape mismatches. The `build-project.sh` script copies the `shared/` directory into each component's Docker build context before building.

### Security

- **SSL/TLS**: Redis connections use TLS with certificate verification when CA certificates are provided; verification is disabled only as a development fallback (with a warning log)
- **ZMQ CURVE**: IoT node ZMQ sockets use CURVE authentication. When `CURVE_AUTHORIZED_KEYS_DIR` is set, only keys from that directory are accepted; otherwise falls back to allowing any key (with a warning log)
- **Content hashing**: Model weights stored in CouchDB include SHA-256 content hashes, verified during FedAvg re-computation
- **Duplicate prevention**: The aggregation request TP rejects duplicate contributions from the same node within a round

## Configuration Reference

| Variable | Default | Component | Description |
|---|---|---|---|
| `TOTAL_NODES` | `5` | IoT node | Number of IoT nodes in the federation |
| `NON_IID_ALPHA` | `0.5` | IoT node | Dirichlet alpha for data partitioning |
| `AGGREGATION_TIMEOUT` | `180` | Aggregation TPs, event handler | Seconds before aggregation timer expires |
| `MIN_NODES_FOR_AGGREGATION` | `1` | Aggregation TPs, event handler | Minimum nodes required to proceed |
| `MIN_ACCURACY_THRESHOLD` | `0.3` | Confirmation TP | Minimum MNIST accuracy for model acceptance |
| `MAX_WEIGHT_MAGNITUDE` | `10.0` | Confirmation TP | Maximum allowed parameter magnitude |
| `VALIDATION_SEED` | `42` | Confirmation TP | Seed for deterministic validation |
| `CURVE_AUTHORIZED_KEYS_DIR` | *(unset)* | Federated response manager | Directory of authorized ZMQ CURVE keys |

## Backward Compatibility

- Non-federated workflows (e.g., cold-chain monitoring) are unaffected — the aggregation TPs only activate when aggregation-request transactions are submitted
- The existing transaction processors (`iot-data-tp`, `scheduling-request-tp`, `schedule-confirmation-tp`, `status-update-tp`) are unchanged
- The two-phase federated protocol uses the existing TrustMesh task execution pipeline for Phase 1 (local training) and adds Phase 2 (aggregation) as an independent flow

## Known Limitations and Future Work

1. **Single model architecture**: Currently hardcoded to MNISTNet — extending to multiple model types requires a model registry
2. **JSON weight serialization**: Model weights are serialized as JSON lists, which is ~3-4x larger than binary formats — migrating to a binary format (e.g., MessagePack or Protocol Buffers) would reduce communication overhead
3. **Synchronous aggregation**: All nodes must submit within the same time window — asynchronous FL (e.g., FedBuff) would improve utilization
4. **No differential privacy**: Model updates are submitted as-is — adding Gaussian noise before submission would strengthen privacy guarantees
5. **Limited Byzantine detection**: Current validation checks (magnitude, distribution, accuracy) catch corrupted models but may not detect sophisticated model poisoning attacks
6. **Aggregator selection via Redis**: The aggregator is selected based on available resources read from Redis, which is external to blockchain state — if Redis returns different results on different validators, the aggregation IDs will still match (they're deterministic from workflow_id + round number), but the aggregator identity could theoretically differ
