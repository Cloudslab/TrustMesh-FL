# Running MNIST Federated Learning on TrustMesh-FL

This guide provides complete instructions for deploying and running the MNIST federated learning application on TrustMesh-FL with **consensus-validated aggregation**, **configurable non-IID data distribution**, and **sample-weighted FedAvg**.

## Overview

The MNIST federated learning application demonstrates distributed machine learning across IoT nodes using a **two-phase architecture**:

### Phase 1: Local Training
- Each IoT node trains on its local MNIST data partition
- Training data is submitted to TrustMesh and processed as a standard workflow
- The compute node returns locally trained model weights to the IoT node

### Phase 2: Federated Aggregation
- IoT nodes submit trained weights to the `aggregation-request-tp`
- Time-windowed collection (configurable timeout, default 3 minutes)
- Sample-weighted FedAvg aggregation with blockchain consensus validation
- Every validator independently re-computes FedAvg and validates the model against a shared MNIST test set
- Confirmed global model is broadcast back to participating nodes via ZMQ

### Data Distribution

Data is partitioned across nodes using a **Dirichlet distribution** controlled by the `NON_IID_ALPHA` environment variable:

| Alpha Value | Distribution | Description |
|---|---|---|
| 0.1 | Extreme non-IID | Each node sees mostly 1-2 classes |
| 0.5 (default) | Moderate non-IID | Each node has a skewed but overlapping class distribution |
| 1.0 | Mild non-IID | Moderate skew across all classes |
| 10.0+ | Near-IID | Approximately uniform distribution |

The partitioning is deterministic (seeded) so all nodes get consistent, reproducible splits.

## Key Features

- **Consensus-Validated Aggregation**: FedAvg is executed inside the `aggregation-confirmation-tp` and independently verified by all blockchain validators before acceptance
- **Sample-Weighted FedAvg**: Nodes that contribute more training samples have proportionally more influence on the global model
- **Configurable Non-IID Partitioning**: Dirichlet-based distribution with tunable alpha parameter
- **Time-Windowed Collection**: Nodes participate independently; aggregation proceeds with whoever submits within the timeout window
- **Local Convergence Detection**: Each node tracks its own test accuracy and stops after 3 rounds without improvement
- **Blockchain Model Validation**: Aggregated model must achieve at least 30% accuracy on a shared MNIST validation dataset stored in CouchDB
- **Privacy Preserving**: Training data never leaves nodes — only model weights are shared
- **Shared Model Architecture**: A single `MNISTNet` definition in `shared/models/mnist_model.py` is used by all components to prevent architecture drift

## Prerequisites

### System Requirements

**Minimum Cluster Configuration:**
- **Control Node**: 4 CPU cores, 16GB RAM
- **Compute Nodes**: 1 CPU core, 4GB RAM each (minimum 4 nodes)
- **IoT Nodes**: 1 CPU core, 4GB RAM each (default 5 nodes, configurable via `TOTAL_NODES`)

### Software Requirements
- Docker
- K3s Kubernetes Cluster
- Python 3.8+
- Git

## Step 1: Clone and Setup Repository

```bash
git clone https://github.com/Cloudslab/TrustMesh-FL.git
cd TrustMesh-FL
```

## Step 2: Set Up K3s Cluster

### 2.1 Server Node Setup

On your designated server/control node:

```bash
cd k3s-cluster-setup-guide
chmod +x setup-k3s-server.sh
./setup-k3s-server.sh
```

Get the server token for agent nodes:
```bash
sudo cat /var/lib/rancher/k3s/server/node-token
```

### 2.2 Compute Node Setup

On each compute node (compute-node-1 through compute-node-4):

```bash
cd k3s-cluster-setup-guide
chmod +x setup-k3s-agent.sh

export K3S_URL=https://[SERVER_IP]:6443
export K3S_TOKEN=[TOKEN_FROM_SERVER]

./setup-k3s-agent.sh
```

### 2.3 IoT Node Setup

Set up IoT nodes with hostnames `iot-node-1` through `iot-node-5` (mapped to `iot-0` through `iot-4` in Kubernetes).

On each IoT node:
```bash
cd k3s-cluster-setup-guide
chmod +x setup-k3s-agent.sh

export K3S_URL=https://[SERVER_IP]:6443
export K3S_TOKEN=[TOKEN_FROM_SERVER]

./setup-k3s-agent.sh
```

### 2.4 Verify Cluster Setup

```bash
kubectl get nodes
```

All nodes should show `Ready` status.

## Step 3: Build and Deploy

### 3.1 Update Docker Username

```bash
# Edit build-project.sh and change DOCKER_USERNAME on line 6
nano build-project.sh
```

### 3.2 Build All Images

```bash
docker login
chmod +x build-project.sh
./build-project.sh
```

The build script:
- Copies the shared model module (`shared/`) into component build contexts
- Builds all TrustMesh core components
- Builds federated learning transaction processors (`aggregation-request-tp`, `aggregation-confirmation-tp`, `validation-dataset-distributor`)
- Builds the `federated-training-task` application
- Pushes everything to Docker registry
- Cleans up shared module copies from component directories

### 3.3 Deploy TrustMesh Network

```bash
chmod +x build-and-deploy-network.sh
./build-and-deploy-network.sh
```

Follow the prompts for:
- Number of compute nodes (minimum 4)
- Redis cluster configuration
- CouchDB setup
- SSL certificate generation

### 3.4 Verify Deployment

```bash
kubectl get pods
```

Wait for all pods to be in `Running` state. You should see:
- All TrustMesh core components running
- All compute nodes with aggregation TPs
- All IoT nodes ready
- MNIST validation dataset distribution job completed

Check federated learning components:
```bash
# Check aggregation TPs in compute nodes
kubectl logs pbft-0 -c aggregation-request-tp
kubectl logs pbft-0 -c aggregation-confirmation-tp

# Check validation dataset distribution
kubectl get jobs
kubectl logs job/mnist-validation-dataset-distributor
```

## Step 4: Deploy MNIST Federated Learning Application

### 4.1 Deploy the Training Application

```bash
kubectl exec -it network-management-console-xxxxx -c application-deployment-client -- bash
python docker_image_client.py deploy_image federated-training-task.tar.gz app_requirements.json
```

A sample `app_requirements.json` is provided in `sample-apps/mnist-federated-learning/sample_jsons/`.

### 4.2 Create Federated Learning Workflow

```bash
kubectl exec -it network-management-console-xxxxx -c workflow-creation-client -- bash
python workflow_creation_client.py federated_dependency_graph.json
```

A sample `federated_dependency_graph.json` is provided in `sample-apps/mnist-federated-learning/`. Record the returned workflow ID.

## Step 5: Run Federated Learning

### 5.1 Start IoT Nodes

On each IoT node, run the federated learning simulation. The script auto-detects the node ID from the hostname.

```bash
kubectl exec -it iot-0-xxxxx -- bash
cd /app
python mnist-federated-learning-simulation.py --workflow-id <WORKFLOW_ID> --max-rounds 5
```

Repeat for all IoT nodes (`iot-1` through `iot-4`).

> **Note:** The script automatically detects the node ID from the Kubernetes pod hostname (`iot-0-xxxxx` -> `iot-0`). Override with `--node-id` if needed.

### 5.2 Script Parameters

```
python mnist-federated-learning-simulation.py [OPTIONS]

Required:
  --workflow-id TEXT    Workflow ID for the federated learning experiment

Optional:
  --max-rounds INTEGER  Maximum number of federated rounds (default: 5)
  --node-id TEXT        Node ID override (default: auto-detect from hostname)
```

### 5.3 Environment Variables

These can be set before launching the script or configured in Kubernetes pod specs:

| Variable | Default | Description |
|---|---|---|
| `TOTAL_NODES` | `5` | Number of IoT nodes in the federation |
| `NON_IID_ALPHA` | `0.5` | Dirichlet alpha for data partitioning |
| `IOT_NODE_ID` | *(unset)* | Fallback node ID if hostname detection fails |

### 5.4 Monitor Progress

Each node logs its progress with structured output:

```
FEDERATED LEARNING ROUND 1/5 STARTED

PHASE 1: TRAINING PHASE
  Objective: Submit training data to TrustMesh for processing

TRAINING PHASE COMPLETED SUCCESSFULLY
  Schedule ID: schedule_abc123
  Training samples: 500

PHASE 2: AGGREGATION PHASE
  Objective: Submit trained weights for global aggregation

AGGREGATION SUBMISSION SUCCESSFUL
  Weights submitted to aggregation-request-tp

WAITING FOR GLOBAL MODEL AGGREGATION
GLOBAL MODEL RECEIVED SUCCESSFULLY
  Aggregation wait duration: 180.1s
  Aggregated weights: 10 layers

LOCAL VALIDATION COMPLETED
  Local accuracy: 0.8450 (84.50%)
```

## Step 6: Monitor and Troubleshoot

### 6.1 Monitor Aggregation Process

```bash
# Check aggregation requests
kubectl logs pbft-0 -c aggregation-request-tp -f

# Check FedAvg aggregation and validation
kubectl logs pbft-0 -c aggregation-confirmation-tp -f
```

### 6.2 Verify Blockchain Consensus

The blockchain performs deterministic validation against the shared MNIST test set:
```bash
kubectl logs pbft-0 -c aggregation-confirmation-tp | grep "MNIST validation"

# Expected output:
# MNIST validation - Accuracy: 0.8934, Loss: 0.3245, Passed: True
```

Models must achieve at least 30% accuracy to pass consensus validation.

### 6.3 Common Issues and Solutions

**Issue: Validation dataset not found**
```bash
# Check if the validation distribution job completed
kubectl get jobs
kubectl logs job/mnist-validation-dataset-distributor

# The validation dataset is stored in CouchDB (database: validation_datasets)
# If the job failed, check CouchDB connectivity and redeploy
```

**Issue: Aggregation timeout (no global model received)**
```bash
# Check if enough nodes submitted within the timeout window
# Default: at least 1 node within 3 minutes (configurable via MIN_NODES_FOR_AGGREGATION and AGGREGATION_TIMEOUT)
kubectl logs pbft-0 -c aggregation-request-tp | grep "Timer"
```

**Issue: Model validation fails at consensus**
```bash
# This means the aggregated model scored below the 30% accuracy threshold
# Check the validation details:
kubectl logs pbft-0 -c aggregation-confirmation-tp | grep "validation"
```

**Issue: ZMQ communication errors**
```bash
# Verify IoT node ZMQ socket is bound
kubectl exec -it iot-0-xxxxx -- netstat -tulpn | grep :5555
```

## Expected Results

### Accuracy Progression

With default settings (`NON_IID_ALPHA=0.5`, 5 nodes):

```
Round 1: Local accuracy ~0.65-0.75
Round 2: Local accuracy ~0.80-0.85
Round 3: Local accuracy ~0.85-0.90
Round 4: Local accuracy ~0.88-0.92
Round 5: Convergence detected or final round
```

Convergence is detected when a node sees no improvement in local test accuracy for 3 consecutive rounds.

### Performance Characteristics

- **Time per round**: ~3-5 minutes (including aggregation timeout window)
- **Network overhead**: Only model weights are transmitted (not raw data)
- **Convergence**: Typically 3-5 rounds for MNIST
- **Fault tolerance**: Aggregation proceeds with partial participation (minimum 1 node by default)

## Cleanup

To clean up the entire deployment:

```bash
chmod +x clean-k8s-environment.sh
./clean-k8s-environment.sh
```

This removes all TrustMesh components, federated learning TPs, jobs, secrets, and persistent volumes.

## Architecture Summary

| Component | Location | Purpose |
|---|---|---|
| `shared/models/mnist_model.py` | Shared | Canonical MNISTNet architecture |
| `aggregation-request-tp` | `scheduling/` | Collects model weights, selects aggregator, manages round lifecycle |
| `aggregation-confirmation-tp` | `scheduling/` | Performs FedAvg, validates model, achieves consensus |
| `validation-dataset-distributor` | `scheduling/` | Distributes MNIST validation data to CouchDB |
| `federated-training-task` | `sample-apps/` | Local model training on compute nodes |
| `mnist-federated-learning-simulation.py` | `iot-node/` | IoT node FL orchestration |
| `federated_response_manager.py` | `iot-node/` | ZMQ-based model reception and convergence tracking |
| `aggregation_event_handler.py` | `compute-node/` | Blockchain event handling for aggregation on compute nodes |
