# Running the Cold-Chain Sample Application on TrustMesh-FL

This guide provides step-by-step instructions for deploying and testing the cold-chain monitoring sample application on TrustMesh-FL. For the MNIST federated learning application, see [RUN_MNIST_FEDERATED_LEARNING.md](RUN_MNIST_FEDERATED_LEARNING.md).

## System Requirements

### Minimum Cluster Configuration

A minimum of 6 nodes are required to deploy the framework. These may be virtual machines or physical devices.

- 1 Control Node: 4 CPU cores, 16GB RAM (recommended)
- 1 IoT Node: 1 CPU core, 4GB RAM
- 4 Compute Nodes: 1 CPU core, 4GB RAM each

### Software Prerequisites
- Ubuntu (recommended), macOS, or Windows
- Docker
- K3s Kubernetes Cluster
- Python 3.8

## Installation Steps

### 1. Clone Repository
```bash
git clone https://github.com/Cloudslab/TrustMesh-FL.git
cd TrustMesh-FL
```

### 2. Set Up K3s Cluster

1. Navigate to cluster setup guide:
   ```bash
   cd k3s-cluster-setup-guide
   ```
2. Follow instructions in `K3S_CLUSTER_SETUP.md` for:
    - Cluster initialization
    - Node configuration
    - Network setup

### 3. Deploy Framework

Perform all operations from this step onwards on the server node of the K3s cluster.

#### Option 1: Using Pre-built Images (Recommended for Quick Start)

1. Skip the build step (by default, the deployment script will pull images from the author's Docker registry)
2. Deploy the network:
   ```bash
   chmod +x build-and-deploy-network.sh
   ./build-and-deploy-network.sh
   ```
   When prompted:
    - Specify 4 compute nodes
    - Specify 1 IoT node

> **Note:** The script may take a few minutes to complete the deployment.

#### Option 2: Building Custom Images

1. Update `DOCKER_USERNAME` in `build-project.sh` with your username
2. Login to Docker:
   ```bash
   docker login -u <username>
   ```
3. Build images:
   ```bash
   chmod +x build-project.sh
   ./build-project.sh
   ```
4. Update the image addresses in `build-and-deploy-network.sh`
5. Follow deployment steps from Option 1

### 4. Verify Installation

Check pod status:
```bash
kubectl get pods
```

All pods except `couchdb-setup-xxxxx` should show "Running" status within a few minutes.

## Running the Cold-Chain Application

### 1. Deploy the Cold-Chain Applications

```bash
kubectl exec -it network-management-console-xxxxx -c application-deployment-client -- bash
python docker_image_client.py deploy_image process-sensor-data.tar app_requirements.json
python docker_image_client.py deploy_image anomaly-detection.tar app_requirements.json
python docker_image_client.py deploy_image generate-alerts.tar app_requirements.json
```

- A sample `app_requirements.json` is provided in the `sample-apps/sample_jsons/` directory. You may use that or create one yourself using a command-line text editor (e.g., nano, vim).
- After each application's deployment, a unique application ID will be printed to the console. Save that for the later steps.
- After you log the application ID, you may have to Ctrl+C to get back access to the terminal.

### 2. Create the Workflow

```bash
kubectl exec -it network-management-console-xxxxx -c workflow-creation-client -- bash
python workflow_creation_client.py dependency_graph.json
```

The `dependency_graph.json` file specifies the workflow as a DAG where each node is an application and edges represent the flow of data or order of execution. For the cold-chain use case:

```json
{
   "start": "<Process Sensor Data ID>",
   "nodes": {
      "<Process Sensor Data ID>": {"next": ["<Detect Anomalies ID>"]},
      "<Detect Anomalies ID>": {"next": ["<Generate Alerts ID>"]},
      "<Generate Alerts ID>": {"next": []}
   }
}
```

- A sample `dependency_graph.json` is provided in the `sample-apps/sample_jsons/` directory.
- A workflow ID will be printed to the console on successful creation. Record it for the next step.

### 3. Initiate Data Processing from IoT Node

```bash
kubectl exec -it iot-0-xxxxx -c iot-node -- bash
python cold-chain-data-simulation.py <workflowID>
```

**Expected output:**
- You should see data processing requests being sent to the network.
- In 3-5 seconds you should see the result of the processed data being printed to the console.

## Cleanup

To delete all network components and clean up the environment:
```bash
chmod +x clean-k8s-environment.sh && ./clean-k8s-environment.sh
```

## Troubleshooting

If pods aren't running:

1. Check node status:
   ```bash
   kubectl get nodes
   ```
2. Verify resource availability:
   ```bash
   kubectl describe nodes
   ```
3. Check pod logs:
   ```bash
   kubectl logs <pod-name>
   ```

For additional support, contact mrangwala@student.unimelb.edu.au
