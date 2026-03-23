"""
Shared model architectures for TrustMesh Federated Learning.

This module defines the canonical model architectures used across all components:
- IoT nodes (local training and evaluation)
- Compute nodes (federated training task)
- Transaction processors (aggregation validation)

Supported datasets: MNIST, CIFAR-10

Any architectural changes must be made here to ensure consistency.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class MNISTNet(nn.Module):
    """PyTorch CNN model for MNIST federated learning.

    Architecture:
        conv1 (1->32, 3x3, pad=1) -> MaxPool(2) -> ReLU
        conv2 (32->64, 3x3, pad=1) -> MaxPool(2) -> ReLU
        conv3 (64->64, 3x3, pad=1) -> ReLU
        fc1 (64*7*7 -> 64) -> ReLU -> Dropout(0.2)
        fc2 (64 -> num_classes)

    Input shape: (N, 1, 28, 28)
    Output shape: (N, num_classes) — raw logits
    """

    def __init__(self, num_classes=10):
        super(MNISTNet, self).__init__()
        self.conv1 = nn.Conv2d(1, 32, kernel_size=3, padding=1)
        self.pool1 = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.pool2 = nn.MaxPool2d(2, 2)
        self.conv3 = nn.Conv2d(64, 64, kernel_size=3, padding=1)
        self.flatten = nn.Flatten()
        self.fc1 = nn.Linear(64 * 7 * 7, 64)  # 28x28 -> 14x14 -> 7x7 after pooling
        self.fc2 = nn.Linear(64, num_classes)
        self.dropout = nn.Dropout(0.2)

    def forward(self, x):
        x = self.pool1(F.relu(self.conv1(x)))
        x = self.pool2(F.relu(self.conv2(x)))
        x = F.relu(self.conv3(x))
        x = self.flatten(x)
        x = self.dropout(F.relu(self.fc1(x)))
        x = self.fc2(x)  # Return raw logits for CrossEntropyLoss
        return x


class CIFAR10Net(nn.Module):
    """PyTorch CNN model for CIFAR-10 federated learning.

    Architecture:
        conv1 (3->32, 3x3, pad=1) -> BatchNorm -> ReLU -> MaxPool(2)
        conv2 (32->64, 3x3, pad=1) -> BatchNorm -> ReLU -> MaxPool(2)
        conv3 (64->128, 3x3, pad=1) -> BatchNorm -> ReLU -> MaxPool(2)
        fc1 (128*4*4 -> 256) -> ReLU -> Dropout(0.3)
        fc2 (256 -> num_classes)

    Input shape: (N, 3, 32, 32)
    Output shape: (N, num_classes) — raw logits
    """

    def __init__(self, num_classes=10):
        super(CIFAR10Net, self).__init__()
        self.conv1 = nn.Conv2d(3, 32, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(32)
        self.pool1 = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(64)
        self.pool2 = nn.MaxPool2d(2, 2)
        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm2d(128)
        self.pool3 = nn.MaxPool2d(2, 2)
        self.flatten = nn.Flatten()
        self.fc1 = nn.Linear(128 * 4 * 4, 256)  # 32->16->8->4 after 3 pooling layers
        self.fc2 = nn.Linear(256, num_classes)
        self.dropout = nn.Dropout(0.3)

    def forward(self, x):
        x = self.pool1(F.relu(self.bn1(self.conv1(x))))
        x = self.pool2(F.relu(self.bn2(self.conv2(x))))
        x = self.pool3(F.relu(self.bn3(self.conv3(x))))
        x = self.flatten(x)
        x = self.dropout(F.relu(self.fc1(x)))
        x = self.fc2(x)
        return x


def get_model(dataset_name: str, num_classes: int = 10):
    """Factory function to get the appropriate model for a dataset.

    Args:
        dataset_name: 'mnist' or 'cifar10'
        num_classes: Number of output classes (default 10)

    Returns:
        An instance of the appropriate model
    """
    models = {
        'mnist': MNISTNet,
        'cifar10': CIFAR10Net,
    }
    if dataset_name not in models:
        raise ValueError(f"Unknown dataset: {dataset_name}. Supported: {list(models.keys())}")
    return models[dataset_name](num_classes=num_classes)


# Dataset configuration
DATASET_CONFIGS = {
    'mnist': {
        'input_channels': 1,
        'input_size': 28,
        'num_classes': 10,
        'normalize_mean': (0.1307,),
        'normalize_std': (0.3081,),
    },
    'cifar10': {
        'input_channels': 3,
        'input_size': 32,
        'num_classes': 10,
        'normalize_mean': (0.4914, 0.4822, 0.4465),
        'normalize_std': (0.2470, 0.2435, 0.2616),
    },
}
