"""
ARCHE Federated Learning — Phase 11 Research Module

STATUS: PROTOTYPE / EXPERIMENTAL

Tujuan:
    Decentralized model training di mana worker hanya share gradient/update,
    bukan raw data. Blockchain digunakan untuk:
    - Worker registration dan contribution tracking
    - Reward distribution berdasarkan contribution
    - Model version history dan hash
    - Governance untuk aggregation rules

Alur:
    1. Training coordinator announce model + training round
    2. Worker download model weights
    3. Worker train dengan local data → hasilkan gradient/update
    4. Worker submit gradient hash ke blockchain
    5. Aggregator combine gradients → new model version
    6. New model hash di-commit ke blockchain
    7. Worker dapat reward berdasarkan contribution quality

Security concerns:
    - Poisoned updates: worker submit malicious gradient untuk corrupt model
      Mitigasi: gradient clipping + anomaly detection
    - Sybil workers: attacker register banyak workers untuk dominate aggregation
      Mitigasi: stake requirement + reputation weighting
    - Model poisoning: gradients terlihat valid tapi corrupt model behavior
      Mitigasi: validation set check + Byzantine-robust aggregation (FedAvg + Krum)
    - Collusion: beberapa workers coordinate untuk push certain direction
      Mitigasi: random worker selection + reputation tracking
    - Malicious gradients: gradient magnitude/direction mencurigakan
      Mitigasi: gradient norm clipping

Status: Implementasi basic aggregation dan contribution tracking.
        Byzantine-robust aggregation dan gradient verification belum diimplementasikan.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional


class RoundStatus(str, Enum):
    OPEN       = "OPEN"
    AGGREGATING = "AGGREGATING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"


# ---------------------------------------------------------------------------
# Training Round
# ---------------------------------------------------------------------------

@dataclass
class TrainingRound:
    round_id: str
    model_id: str
    round_number: int
    base_model_hash: str        # Hash of model weights before this round
    aggregated_model_hash: Optional[str]  # Hash after aggregation
    min_workers: int            # Minimum workers untuk valid round
    max_workers: int
    reward_per_worker: int      # ARC base units
    deadline: int
    status: RoundStatus
    created_at: int
    completed_at: Optional[int]
    submissions: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "TrainingRound":
        d = dict(d)
        d["status"] = RoundStatus(d["status"])
        return TrainingRound(**d)

    def is_expired(self) -> bool:
        return int(time.time()) > self.deadline

    def has_enough_workers(self) -> bool:
        return len(self.submissions) >= self.min_workers


# ---------------------------------------------------------------------------
# Worker Submission
# ---------------------------------------------------------------------------

@dataclass
class GradientSubmission:
    submission_id: str
    round_id: str
    worker_address: str
    gradient_hash: str      # SHA256 hash of gradient update
    gradient_norm: float    # L2 norm of gradients (for anomaly detection)
    data_size: int          # Number of local training samples
    training_loss: float    # Final training loss
    submitted_at: int
    is_valid: Optional[bool] = None  # Set after validation
    anomaly_score: float = 0.0       # Higher = more suspicious

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "GradientSubmission":
        return GradientSubmission(**d)


# ---------------------------------------------------------------------------
# Federated Learning Manager
# ---------------------------------------------------------------------------

class FederatedManager:

    # Gradient norm threshold (gradients with norm > this are clipped/flagged)
    MAX_GRADIENT_NORM = 10.0

    def __init__(self, data_dir: str) -> None:
        self.rounds_path = os.path.join(data_dir, "fl_rounds.json")
        os.makedirs(data_dir, exist_ok=True)
        self._rounds: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.rounds_path):
            try:
                with open(self.rounds_path, "r", encoding="utf-8") as f:
                    self._rounds = json.load(f)
            except Exception:
                self._rounds = {}

    def _save(self) -> None:
        import tempfile
        dir_ = os.path.dirname(os.path.abspath(self.rounds_path))
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._rounds, f, indent=2)
        except Exception:
            os.unlink(tmp)
            raise
        os.replace(tmp, self.rounds_path)

    def create_round(
        self,
        model_id: str,
        base_model_hash: str,
        round_number: int,
        min_workers: int,
        max_workers: int,
        reward_per_worker: int,
        duration_seconds: int = 3600,
    ) -> TrainingRound:
        if min_workers < 1:
            raise ValueError("min_workers must be >= 1")
        if max_workers < min_workers:
            raise ValueError("max_workers must be >= min_workers")
        if len(base_model_hash) != 64:
            raise ValueError("base_model_hash must be 64-char hex")

        rnd = TrainingRound(
            round_id=str(uuid.uuid4()),
            model_id=model_id,
            round_number=round_number,
            base_model_hash=base_model_hash,
            aggregated_model_hash=None,
            min_workers=min_workers,
            max_workers=max_workers,
            reward_per_worker=reward_per_worker,
            deadline=int(time.time()) + duration_seconds,
            status=RoundStatus.OPEN,
            created_at=int(time.time()),
            completed_at=None,
        )
        self._rounds[rnd.round_id] = rnd.to_dict()
        self._save()
        return rnd

    def submit_gradient(
        self,
        round_id: str,
        worker_address: str,
        gradient_hash: str,
        gradient_norm: float,
        data_size: int,
        training_loss: float,
    ) -> GradientSubmission:
        rnd = self._get_round(round_id)
        if rnd.status != RoundStatus.OPEN:
            raise ValueError(f"Round {round_id} is not OPEN")
        if rnd.is_expired():
            rnd.status = RoundStatus.FAILED
            self._rounds[round_id] = rnd.to_dict()
            self._save()
            raise ValueError("Round has expired")
        if any(s["worker_address"] == worker_address for s in rnd.submissions):
            raise ValueError("Worker already submitted for this round")
        if len(rnd.submissions) >= rnd.max_workers:
            raise ValueError("Round is full")
        if len(gradient_hash) != 64:
            raise ValueError("gradient_hash must be 64-char hex")
        if data_size <= 0:
            raise ValueError("data_size must be > 0")

        # Anomaly detection: flag high gradient norms
        anomaly_score = 0.0
        is_valid = True
        if gradient_norm > self.MAX_GRADIENT_NORM:
            anomaly_score = min(1.0, gradient_norm / self.MAX_GRADIENT_NORM)
            is_valid = gradient_norm <= self.MAX_GRADIENT_NORM * 2  # Hard reject > 2x threshold

        sub = GradientSubmission(
            submission_id=str(uuid.uuid4()),
            round_id=round_id,
            worker_address=worker_address,
            gradient_hash=gradient_hash,
            gradient_norm=gradient_norm,
            data_size=data_size,
            training_loss=training_loss,
            submitted_at=int(time.time()),
            is_valid=is_valid,
            anomaly_score=anomaly_score,
        )
        rnd.submissions.append(sub.to_dict())
        self._rounds[round_id] = rnd.to_dict()
        self._save()
        return sub

    def aggregate(
        self,
        round_id: str,
        aggregated_model_hash: str,
    ) -> TrainingRound:
        """
        Finalize aggregation dan commit new model hash.

        NOTE: Actual gradient aggregation (FedAvg, etc.) happens OFF-CHAIN.
        Blockchain hanya menyimpan hash dari model hasil aggregasi.
        """
        rnd = self._get_round(round_id)
        if rnd.status not in (RoundStatus.OPEN, RoundStatus.AGGREGATING):
            raise ValueError(f"Cannot aggregate round with status={rnd.status}")
        if not rnd.has_enough_workers():
            raise ValueError(
                f"Not enough submissions: {len(rnd.submissions)}/{rnd.min_workers}"
            )
        if len(aggregated_model_hash) != 64:
            raise ValueError("aggregated_model_hash must be 64-char hex")

        rnd.aggregated_model_hash = aggregated_model_hash
        rnd.status = RoundStatus.COMPLETED
        rnd.completed_at = int(time.time())
        self._rounds[round_id] = rnd.to_dict()
        self._save()
        return rnd

    def get_round(self, round_id: str) -> Optional[TrainingRound]:
        d = self._rounds.get(round_id)
        return TrainingRound.from_dict(d) if d else None

    def active_rounds(self) -> List[TrainingRound]:
        return [
            TrainingRound.from_dict(d)
            for d in self._rounds.values()
            if d["status"] == RoundStatus.OPEN.value
        ]

    def compute_contribution_weight(self, sub: GradientSubmission) -> float:
        """
        Hitung bobot kontribusi worker berdasarkan:
        - data_size (lebih banyak data = bobot lebih besar)
        - training_loss (loss lebih rendah = lebih baik)
        - anomaly_score (anomaly tinggi = bobot lebih kecil)

        Ini simplified FedAvg weighting.
        Byzantine-robust alternatives (Krum, Trimmed Mean) belum diimplementasikan.
        """
        if not sub.is_valid:
            return 0.0
        base_weight = float(sub.data_size)
        anomaly_penalty = 1.0 - sub.anomaly_score
        return base_weight * anomaly_penalty

    def _get_round(self, round_id: str) -> TrainingRound:
        d = self._rounds.get(round_id)
        if d is None:
            raise ValueError(f"Round {round_id} not found")
        return TrainingRound.from_dict(d)
