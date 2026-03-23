# TrustMesh-FL

TrustMesh-FL extends the [TrustMesh](https://doi.org/10.1109/ICSA65012.2025.00022) blockchain-enabled distributed computing framework with **consensus-validated federated learning** for trustless heterogeneous IoT environments. It builds on the original three-layer architecture — combining permissioned blockchain (Hyperledger Sawtooth) with multi-phase PBFT consensus — and adds a two-phase federated learning protocol where model aggregation is independently verified by every blockchain validator before acceptance.

## Key Features

- **Three-Layer Architecture**:
   - Network Management Layer for application deployment and workflow orchestration
   - Computation Layer with blockchain-based consensus and federated aggregation
   - Perception Layer for IoT device integration and local model training

- **Consensus-Validated Federated Learning**: Model aggregation (FedAvg) is executed inside blockchain transaction processors and independently verified by all validators — a malicious aggregator cannot tamper with weights

- **Two-Phase FL Protocol**: Clean separation of local training (Phase 1) and global aggregation (Phase 2) with time-windowed collection and blockchain consensus validation

- **Configurable Non-IID Data Partitioning**: Dirichlet-based data distribution across nodes with tunable heterogeneity (`NON_IID_ALPHA` parameter)

- **Sample-Weighted FedAvg**: Proper weighted averaging based on per-node sample counts, with equal-weight fallback

- **Byzantine Fault Tolerance**: Maintains security and consensus while supporting non-deterministic scheduling algorithms

- **Shared Model Architecture**: Single canonical model definition (`shared/models/mnist_model.py`) used across all components to prevent architecture drift

- **Efficient Resource Allocation**: Uses Least-Connected Dynamic Weighted Round Robin (LCDWRR) scheduling

## Pre-requisites

The framework has been extensively tested on Ubuntu machines but should support macOS and Windows. For the development environment, you'll need:
* Docker
* K3s Kubernetes Cluster (instructions provided in `k3s-cluster-setup-guide/`)
* Python 3.8

### System Requirements

- **Compute Nodes**: Minimum 1 CPU core, 4GB RAM
- **Control Nodes**: Minimum 1 CPU core, 8GB RAM | Recommended 8 CPU cores, 32GB RAM
- **IoT Nodes**: Minimum 1 CPU core, 4GB RAM
- **Minimum viable cluster**: 6 nodes (1 control + 1 IoT + 4 compute)
- **Federated learning cluster**: 10+ nodes (1 control + 5 IoT + 4 compute)

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Cloudslab/TrustMesh-FL.git
cd TrustMesh-FL
```

### 2. Set Up K3s Cluster

If you don't have a K3s cluster already configured:

1. Navigate to the cluster setup guide:
```bash
cd k3s-cluster-setup-guide
```

2. Follow the detailed instructions in `K3S_CLUSTER_SETUP.md` for:
   - Cluster initialization
   - Node configuration
   - Network setup
   - Required naming conventions

### 3. Build and Deploy

Once your K3s cluster is ready, follow these steps:

#### 3.1 Build Project Images

This step is required for first-time setup or when code changes are made.

**Prerequisites:**
- Update `DOCKER_USERNAME` in `build-project.sh` with your DockerHub username
- Login to Docker CLI using `docker login`

Run the build script:
```bash
chmod +x build-project.sh && ./build-project.sh
```

> **Note:** The build script automatically copies the shared model module (`shared/`) into component build contexts and cleans up after building. It builds all core TrustMesh components plus the federated learning transaction processors (`aggregation-request-tp`, `aggregation-confirmation-tp`, `validation-dataset-distributor`) and the `federated-training-task` application.

#### 3.2 Deploy the Network

**Prerequisites:**
- Update the image URLs for the containers based on your `DOCKER_USERNAME`

After successful image building, deploy the network:

```bash
chmod +x build-and-deploy-network.sh && ./build-and-deploy-network.sh
```

> **Important:** The deployment script will prompt for several configuration options. Have your network configuration details ready.

### 4. Verify Installation

After deployment, verify your installation:

```bash
kubectl get pods
```
> **Important:** All the pods should be in Running state. This may take a couple of minutes.

For troubleshooting and additional configuration options, please contact the authors.

### 5. Cleanup

To delete all network components and clean-up the environment:
```bash
chmod +x clean-k8s-environment.sh && ./clean-k8s-environment.sh
```

## Usage

TrustMesh-FL supports two modes of operation:

### Standard Task Processing (Cold-Chain Monitoring)

See [RUN_SAMPLE_APP.md](RUN_SAMPLE_APP.md) for step-by-step instructions on running the cold-chain monitoring sample application.

### Federated Learning (MNIST)

See [RUN_MNIST_FEDERATED_LEARNING.md](RUN_MNIST_FEDERATED_LEARNING.md) for comprehensive instructions on running the MNIST federated learning application, including cluster setup, deployment, and monitoring.

### General Workflow

For both modes, the general workflow is:

1. **Deploy applications** via the application deployment client
2. **Create workflows** using DAG-based dependency graphs
3. **Initiate processing** from IoT nodes

Refer to the mode-specific guides above for detailed instructions.

## Architecture

TrustMesh-FL implements a three-layer architecture:

### Network Management Layer
- `auto-docker-deployment/` — Application deployment infrastructure
- `manage-dependency-workflow/` — Workflow orchestration and dependency management

### Computation Layer
- `compute-node/` — Docker-in-Docker compute nodes with blockchain consensus
- `scheduling/` — Task scheduling and federated learning transaction processors:
  - `scheduling-request-tp` / `schedule-confirmation-tp` — Task scheduling with PBFT consensus
  - `aggregation-request-tp` — Collects model weights from IoT nodes, selects aggregator
  - `aggregation-confirmation-tp` — Performs FedAvg, validates model against MNIST test set
  - `validation-dataset-distributor` — Distributes shared validation dataset to CouchDB
  - `status-update-tp` / `iot-data-tp` — Task status and IoT data processing
- `peer-registry/` — Node registration and discovery

### Perception Layer
- `iot-node/` — IoT device simulation, local training, and federated learning coordination
- `sample-apps/` — Demo applications (cold-chain monitoring, MNIST federated learning)

### Shared Components
- `shared/models/` — Canonical model architectures (MNISTNet) shared across all layers

## Technology Stack

- **Blockchain**: Hyperledger Sawtooth with PBFT consensus
- **Containerization**: Docker + Kubernetes (K3s)
- **Language**: Python 3.8
- **ML Framework**: PyTorch (CPU)
- **Database**: CouchDB cluster (model weights, validation datasets)
- **Message Queue**: Redis cluster (coordination, resource tracking)
- **Security**: ZMQ CURVE authentication, SSL/TLS certificates

## Configuration

### Federated Learning Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TOTAL_NODES` | `5` | Number of IoT nodes participating in FL |
| `NON_IID_ALPHA` | `0.5` | Dirichlet alpha for data partitioning (lower = more non-IID) |
| `AGGREGATION_TIMEOUT` | `180` | Seconds to wait for node contributions before aggregating |
| `MIN_NODES_FOR_AGGREGATION` | `1` | Minimum nodes required to proceed with aggregation |
| `CURVE_AUTHORIZED_KEYS_DIR` | *(unset)* | Directory of authorized CURVE keys (if unset, allows any key) |

## Performance

Based on our experimental evaluation with a 21-node testbed and the cold-chain application:
- Request Round Trip (RRT) time: 33.54 - 36.34 seconds
- Framework Overhead: 3.25 - 4.19 seconds
- Scales effectively up to 16 computation nodes

> **Note:** These results are from the base TrustMesh framework. Federated learning performance characteristics are documented in [RUN_MNIST_FEDERATED_LEARNING.md](RUN_MNIST_FEDERATED_LEARNING.md).

## License

This project is licensed under the GNU General Public License - see the [LICENSE](LICENSE) file for details.

## Citation

If you use TrustMesh in your research, please cite:
```
@INPROCEEDINGS{10978934,
  author={Rangwala, Murtaza and Buyya, Rajkumar},
  booktitle={2025 IEEE 22nd International Conference on Software Architecture (ICSA)},
  title={TrustMesh: A Blockchain-Enabled Trusted Distributed Computing Framework for Open Heterogeneous IoT Environments},
  year={2025},
  volume={},
  number={},
  pages={131-141},
  keywords={Fault tolerance;Trusted computing;Technological innovation;Software architecture;Scheduling algorithms;Fault tolerant systems;Trustless services;Internet of Things;Security;Resource management;Internet of Things;Distributed Systems;Edge Computing;Blockchains;Decentralized Applications;Trusted Computing},
  doi={10.1109/ICSA65012.2025.00022}}
```

## Authors

- Murtaza Rangwala - [Email](mailto:mrangwala@student.unimelb.edu.au)
- Rajkumar Buyya - [Email](mailto:rbuyya@unimelb.edu.au)

Cloud Computing and Distributed Systems (CLOUDS) Laboratory
School of Computing and Information Systems
The University of Melbourne, Australia
