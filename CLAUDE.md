# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TrustMesh is a blockchain-enabled distributed computing framework for trustless heterogeneous IoT environments. It implements a three-layer architecture combining permissioned blockchain (Hyperledger Sawtooth) with multi-phase PBFT consensus for secure task scheduling and execution. A key extension adds **consensus-validated federated learning**: model aggregation (FedAvg) is computed inside a Sawtooth Transaction Processor and independently re-verified by all validators before acceptance.

## Architecture

### Three-Layer Structure

**Network Management Layer**
- `auto-docker-deployment/` — Application image lifecycle (docker-image-tp + docker-image-client)
- `manage-dependency-workflow/` — DAG workflow orchestration (dependency-management-tp + workflow-creation-client)

**Computation Layer**
- `compute-node/` — Docker-in-Docker nodes that react to blockchain events and execute tasks
- `scheduling/` — All Transaction Processors for task scheduling and FL aggregation
- `peer-registry/` — Node registration and discovery

**Perception Layer**
- `iot-node/` — IoT simulation: submits transactions, trains locally, receives aggregated models
- `sample-apps/` — Demo apps: cold-chain monitoring (3-task DAG) and MNIST federated learning

### Event-Driven Execution Pattern

The entire system is driven by blockchain events rather than direct RPC:

```
IoT node submits transaction
    ↓ (Sawtooth network propagates + validates)
Transaction Processor: validates, updates state, emits EventList
    ↓
Event handler on compute node (via Sawtooth Stream subscription)
    ↓
Handler fetches full state from blockchain, executes business logic
    ↓
May submit a follow-on transaction (e.g., confirmation TP)
```

Each component's `event_handlers/` directory contains handlers that subscribe to specific transaction family events. This means **no direct node-to-node calls for task dispatch** — all coordination flows through blockchain consensus.

### Federated Learning Round State Machine

```
collecting → locked → confirmed
                   ↘ failed
```

- `aggregation-request-tp`: collects local weights (metadata → blockchain, weights → CouchDB), manages timeout window
- `aggregation-confirmation-tp`: performs FedAvg, validates against test set, broadcasts global model
- These two TPs share overlapping namespaces, forcing serialized execution across validators
- Round state and sample counts are stored in blockchain state; weight tensors (MB-scale) go to CouchDB

### Shared Components

`shared/models/mnist_model.py` defines the canonical model architectures (`MNISTNet`, `CIFAR10Net`). The **build script copies `shared/` into each component's Docker build context** before building, then removes it. Any model architecture change must be consistent across all components — mismatches cause weight-loading failures at aggregation time.

`observation-metrics/fl-timing/` is similarly injected into `iot-node/` at build time for per-phase timing instrumentation.

### Storage Responsibilities

| Store | What goes there |
|-------|----------------|
| Sawtooth blockchain state | Round status, participating nodes, content hashes, scheduling metadata |
| CouchDB | Model weight tensors (JSON documents), MNIST validation dataset |
| Redis cluster | Node resource tracking, task coordination queues, aggregation state |
| ZMQ (CURVE-authenticated) | Synchronous compute ↔ IoT communication (training results, aggregated models) |

### Scheduling Algorithm

`compute-node/event_handlers/helper/scheduler.py` implements **LCDWRR** (Least-Connected Dynamic Weighted Round Robin): selects from the 3 least-loaded nodes, weighted by inverse load.

## Development Commands

### Build and Deploy
```bash
# Build all 14+ Docker images (update DOCKER_USERNAME in script first, then docker login)
chmod +x build-project.sh && ./build-project.sh

# Deploy entire network to K3s (prompts for node counts, timeouts, data distribution params)
chmod +x build-and-deploy-network.sh && ./build-and-deploy-network.sh

# Clean up all Kubernetes resources
chmod +x clean-k8s-environment.sh && ./clean-k8s-environment.sh
```

### Cluster Setup
```bash
cd k3s-cluster-setup-guide
chmod +x setup-k3s-server.sh && ./setup-k3s-server.sh   # control node
chmod +x setup-k3s-agent.sh && ./setup-k3s-agent.sh     # each worker node
```

### Verification
```bash
kubectl get pods                  # all should be Running
kubectl describe pods             # diagnose failures
kubectl logs <pod> -f             # stream logs
kubectl logs <pod> -c <container> # multi-container pods (e.g., compute-node)
```

### Running Experiments
```bash
cd experiments
chmod +x run_experiment.sh && ./run_experiment.sh configs/<config>.yaml
chmod +x collect_results.sh && ./collect_results.sh

# Analysis plots
python analysis/plot_convergence.py
python analysis/plot_scalability.py
python analysis/plot_byzantine.py
python analysis/generate_tables.py
```

Experiment configs in `experiments/configs/` cover: IID/non-IID convergence, scalability (4/8/10 nodes), Byzantine fault tolerance, and overhead measurement.

### Deploying an Application
```bash
kubectl exec -it network-management-console-xxxxx -c application-deployment-client bash
python docker_image_client.py deploy_image application.tar app_requirements.json
# Then create the workflow DAG via workflow-creation-client with graph.json
```

## Transaction Processors

| TP | Purpose |
|----|---------|
| `peer-registry-tp` | Node registration |
| `docker-image-tp` | Application image deployment |
| `dependency-management-tp` | Workflow DAG validation |
| `scheduling-request-tp` | Task scheduling requests |
| `schedule-confirmation-tp` | Schedule validation |
| `status-update-tp` | Task status updates |
| `iot-data-tp` | IoT data ingestion |
| `aggregation-request-tp` | FL: collect local weights, manage rounds |
| `aggregation-confirmation-tp` | FL: FedAvg computation, consensus validation |
| `validation-dataset-distributor` | FL: MNIST test set distribution to nodes |

Each TP follows the same pattern: subclass `TransactionHandler`, declare `namespaces`, implement `apply()` to validate → update state → emit events.

## Key Files for Orientation

- `FEDERATED_LEARNING_DESIGN.md` — Design decisions and rationale for the FL extension
- `RUN_MNIST_FEDERATED_LEARNING.md` — Complete tutorial for running FL experiments
- `compute-node/event_handlers/aggregation_event_handler.py` — Central FL aggregation logic
- `scheduling/aggregation-confirmation-tp/` — Consensus-validated FedAvg
- `shared/models/mnist_model.py` — Canonical model definitions (must stay consistent)
- `iot-node/transaction_initiator/transaction_initiator.py` — Blockchain client pattern
- `compute-node/event_handlers/helper/scheduler.py` — LCDWRR scheduling

## Technology Stack

- **Blockchain**: Hyperledger Sawtooth with PBFT consensus
- **ML**: PyTorch (CPU) — MNIST and CIFAR-10 support
- **Containerization**: Docker-in-Docker + Kubernetes (K3s)
- **Databases**: CouchDB (weights/validation data), Redis cluster (coordination)
- **Messaging**: ZMQ CURVE (authenticated point-to-point), Sawtooth Stream (event pub/sub)
- **Language**: Python 3.8

## System Requirements

- **Compute Nodes**: Min 1 CPU core, 4GB RAM
- **Control Nodes**: Min 8 cores, 32GB RAM recommended
- **IoT Nodes**: Min 1 CPU core, 4GB RAM
- **Minimum viable cluster**: 6 nodes (1 control + 1 IoT + 4 compute)

## Development Notes

- No centralized test framework — testing is integration-level via experiment configs
- Sawtooth validator keys are generated in each component's Dockerfile at `/root/.sawtooth/keys/`
- `build-project.sh` handles `shared/` injection automatically; do not manually copy shared modules
- FL configuration (timeouts, min nodes, non-IID alpha) is set via environment variables at deploy time
- `observation-metrics/` provides timing instrumentation modules — import patterns follow `fl-timing/`
- Performance: Framework overhead is 3.25–4.19 seconds for typical workflows
