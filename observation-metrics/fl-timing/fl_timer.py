"""
Federated Learning Performance Timer for TrustMesh-FL.

Provides structured per-phase timing instrumentation that writes JSON lines
to a log file for post-experiment analysis. Designed to be lightweight enough
for use inside blockchain transaction processors.

Usage:
    timer = FLTimer(node_id="iot-0", output_dir="/tmp/fl-timing")

    timer.start("training", round_num=1)
    # ... do training ...
    timer.stop("training", round_num=1, extra={"samples": 500})

    # Or use context manager:
    with timer.phase("training", round_num=1):
        # ... do training ...
"""

import json
import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class FLTimer:
    """Records structured timing events and writes them to a JSON lines file."""

    def __init__(self, node_id: str, component: str, output_dir: str = "/tmp/fl-timing"):
        """
        Args:
            node_id: Identifier for this node (e.g., 'iot-0', 'pbft-0')
            component: Component name (e.g., 'iot-simulation', 'training-task',
                       'aggregation-event-handler', 'aggregation-confirmation-tp')
            output_dir: Directory to write timing logs
        """
        self.node_id = node_id
        self.component = component
        self.output_dir = output_dir
        self._active_phases = {}  # phase_key -> start_time

        os.makedirs(output_dir, exist_ok=True)
        self._output_file = os.path.join(output_dir, f"{component}_{node_id}.jsonl")
        logger.info(f"FLTimer initialized: {self._output_file}")

    def start(self, phase: str, round_num: int = 0):
        """Start timing a phase."""
        key = f"{phase}_{round_num}"
        self._active_phases[key] = time.time()

    def stop(self, phase: str, round_num: int = 0, extra: Optional[Dict[str, Any]] = None):
        """Stop timing a phase and write the record."""
        key = f"{phase}_{round_num}"
        start_time = self._active_phases.pop(key, None)
        if start_time is None:
            logger.warning(f"FLTimer: stop called for unstarted phase {key}")
            return

        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        record = {
            "round": round_num,
            "phase": phase,
            "node_id": self.node_id,
            "component": self.component,
            "start": start_time,
            "end": end_time,
            "duration_ms": round(duration_ms, 2),
        }
        if extra:
            record["extra"] = extra

        self._write_record(record)
        return duration_ms

    @contextmanager
    def phase(self, phase: str, round_num: int = 0, extra: Optional[Dict[str, Any]] = None):
        """Context manager for timing a phase."""
        self.start(phase, round_num)
        try:
            yield
        finally:
            self.stop(phase, round_num, extra)

    def record_event(self, event_name: str, round_num: int = 0,
                     extra: Optional[Dict[str, Any]] = None):
        """Record a point-in-time event (not a duration)."""
        record = {
            "round": round_num,
            "event": event_name,
            "node_id": self.node_id,
            "component": self.component,
            "timestamp": time.time(),
        }
        if extra:
            record["extra"] = extra
        self._write_record(record)

    def _write_record(self, record: Dict):
        """Append a JSON record to the output file."""
        try:
            with open(self._output_file, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"FLTimer: failed to write record: {e}")
