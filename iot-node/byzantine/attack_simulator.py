"""
Byzantine Attack Simulator for TrustMesh-FL Federated Learning.

Provides configurable attack strategies that corrupt model weights before
submission to the aggregation pipeline. Used for evaluating the framework's
Byzantine resilience through the consensus-validated aggregation mechanism.

Attack types:
    - random_noise: Replace weights with Gaussian noise
    - sign_flip: Negate all weight values
    - scaling: Multiply weights by a large factor

Each attack targets a specific validation check in aggregation-confirmation-tp:
    - random_noise → _check_weight_distributions + MNIST/CIFAR accuracy check
    - sign_flip → accuracy check (sign-flipped model performs poorly)
    - scaling → _check_weight_magnitudes (exceeds MAX_WEIGHT_MAGNITUDE=10.0)
"""

import logging
import numpy as np
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ByzantineAttackSimulator:
    """Simulates Byzantine attacks on federated learning model weights."""

    SUPPORTED_ATTACKS = ['random_noise', 'sign_flip', 'scaling']

    def __init__(self, attack_mode: str, seed: Optional[int] = None):
        """
        Args:
            attack_mode: One of 'random_noise', 'sign_flip', 'scaling'
            seed: Random seed for reproducible attacks
        """
        if attack_mode not in self.SUPPORTED_ATTACKS:
            raise ValueError(
                f"Unknown attack mode: {attack_mode}. "
                f"Supported: {self.SUPPORTED_ATTACKS}"
            )
        self.attack_mode = attack_mode
        self.rng = np.random.RandomState(seed)
        logger.warning(f"Byzantine attack simulator initialized: mode={attack_mode}")

    def apply(self, weights: Dict[str, list]) -> Dict[str, list]:
        """Apply the configured attack to model weights.

        Args:
            weights: Model state_dict as {layer_name: weight_values_as_lists}

        Returns:
            Corrupted weights in the same format
        """
        if self.attack_mode == 'random_noise':
            return self._random_noise_attack(weights)
        elif self.attack_mode == 'sign_flip':
            return self._sign_flip_attack(weights)
        elif self.attack_mode == 'scaling':
            return self._scaling_attack(weights)

    def _random_noise_attack(self, weights: Dict[str, list]) -> Dict[str, list]:
        """Replace all weights with Gaussian noise.

        Expected detection: _check_weight_distributions (abnormal std) and
        accuracy check (random weights give ~10% on MNIST/CIFAR-10).
        """
        corrupted = {}
        total_params = 0
        for layer_name, layer_weights in weights.items():
            arr = np.array(layer_weights)
            noise = self.rng.randn(*arr.shape).astype(arr.dtype)
            corrupted[layer_name] = noise.tolist()
            total_params += arr.size

        logger.warning(
            f"BYZANTINE ATTACK [random_noise]: Replaced {total_params} parameters "
            f"with Gaussian noise"
        )
        return corrupted

    def _sign_flip_attack(self, weights: Dict[str, list]) -> Dict[str, list]:
        """Negate all weight values.

        Expected detection: accuracy check (sign-flipped model performs poorly,
        typically worse than random chance).
        """
        corrupted = {}
        total_params = 0
        for layer_name, layer_weights in weights.items():
            arr = np.array(layer_weights)
            corrupted[layer_name] = (-arr).tolist()
            total_params += arr.size

        logger.warning(
            f"BYZANTINE ATTACK [sign_flip]: Negated {total_params} parameters"
        )
        return corrupted

    def _scaling_attack(self, weights: Dict[str, list], factor: float = 100.0) -> Dict[str, list]:
        """Multiply all weights by a large scaling factor.

        Expected detection: _check_weight_magnitudes (exceeds
        MAX_WEIGHT_MAGNITUDE=10.0 threshold).

        Args:
            factor: Scaling factor (default 100x)
        """
        corrupted = {}
        total_params = 0
        max_magnitude = 0.0
        for layer_name, layer_weights in weights.items():
            arr = np.array(layer_weights)
            scaled = arr * factor
            corrupted[layer_name] = scaled.tolist()
            total_params += arr.size
            layer_max = np.max(np.abs(scaled))
            max_magnitude = max(max_magnitude, layer_max)

        logger.warning(
            f"BYZANTINE ATTACK [scaling]: Scaled {total_params} parameters "
            f"by {factor}x (max magnitude: {max_magnitude:.2f})"
        )
        return corrupted
