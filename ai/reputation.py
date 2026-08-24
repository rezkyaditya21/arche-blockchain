"""
ARCHE AI Reputation System — Phase 8

Reputation adalah scoring layer di atas verification history.
Tidak digunakan sebagai satu-satunya security mechanism.

Faktor yang diperhitungkan:
- successful_jobs    → naik
- failed_jobs        → turun
- disputed_jobs      → turun lebih besar
- uptime             → naik perlahan
- response_time      → bonus kecil
- verification_accuracy → khusus untuk verifier

Security notes:
- Sybil attack: attacker register banyak worker baru (score 100 semua)
  Mitigasi: minimum stake atau minimum history sebelum dapat job mahal
- Reputation manipulation: collude untuk kasih fake good jobs
  Mitigasi: reputation weight turun kalau pattern mencurigakan
- New node disadvantage: worker baru susah dapat job
  Mitigasi: ada tier "probation" untuk worker baru

Status: PRODUCTION feature (scoring layer, bukan consensus)
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Score Event — setiap kejadian yang mempengaruhi reputation
# ---------------------------------------------------------------------------

class EventType:
    JOB_SUCCESS         = "JOB_SUCCESS"
    JOB_FAILED          = "JOB_FAILED"
    JOB_DISPUTED        = "JOB_DISPUTED"
    DISPUTE_WON         = "DISPUTE_WON"       # worker menang dispute
    DISPUTE_LOST        = "DISPUTE_LOST"       # worker kalah dispute
    CHALLENGE_UPHELD    = "CHALLENGE_UPHELD"   # challenge terbukti benar
    CHALLENGE_DISMISSED = "CHALLENGE_DISMISSED"
    FAST_RESPONSE       = "FAST_RESPONSE"      # selesai jauh sebelum deadline
    LATE_RESPONSE       = "LATE_RESPONSE"      # hampir melewati deadline
    TIMEOUT             = "TIMEOUT"            # tidak respond sama sekali
    UPTIME_BONUS        = "UPTIME_BONUS"       # heartbeat konsisten

# Delta score per event
SCORE_DELTA: Dict[str, float] = {
    EventType.JOB_SUCCESS:          +5.0,
    EventType.JOB_FAILED:           -10.0,
    EventType.JOB_DISPUTED:         -8.0,
    EventType.DISPUTE_WON:          +3.0,
    EventType.DISPUTE_LOST:         -15.0,
    EventType.CHALLENGE_UPHELD:     -20.0,
    EventType.CHALLENGE_DISMISSED:  +2.0,
    EventType.FAST_RESPONSE:        +1.0,
    EventType.LATE_RESPONSE:        -2.0,
    EventType.TIMEOUT:              -25.0,
    EventType.UPTIME_BONUS:         +0.5,
}

SCORE_MIN = 0.0
SCORE_MAX = 100.0
INITIAL_SCORE = 60.0   # Worker baru mulai di 60, bukan 100 (mencegah Sybil)


@dataclass
class ScoreEvent:
    event_id: str
    address: str
    event_type: str
    delta: float
    score_before: float
    score_after: float
    job_id: Optional[str]
    timestamp: int
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ScoreEvent":
        return ScoreEvent(**d)


# ---------------------------------------------------------------------------
# Reputation Record per address
# ---------------------------------------------------------------------------

@dataclass
class ReputationRecord:
    address: str
    score: float
    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    disputed_jobs: int
    timeouts: int
    disputes_won: int
    disputes_lost: int
    created_at: int
    updated_at: int
    last_job_at: Optional[int] = None
    tier: str = "PROBATION"   # PROBATION → STANDARD → TRUSTED → ELITE
    is_banned: bool = False
    ban_reason: str = ""
    history: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ReputationRecord":
        return ReputationRecord(**d)

    @property
    def success_rate(self) -> float:
        if self.total_jobs == 0:
            return 0.0
        return self.successful_jobs / self.total_jobs

    @property
    def failure_rate(self) -> float:
        if self.total_jobs == 0:
            return 0.0
        return (self.failed_jobs + self.disputed_jobs) / self.total_jobs


# ---------------------------------------------------------------------------
# Tier thresholds
# ---------------------------------------------------------------------------

TIER_THRESHOLDS = {
    "PROBATION": {"min_score": 0,  "min_jobs": 0,  "max_job_price": 100_000},
    "STANDARD":  {"min_score": 50, "min_jobs": 5,  "max_job_price": 1_000_000},
    "TRUSTED":   {"min_score": 70, "min_jobs": 20, "max_job_price": 10_000_000},
    "ELITE":     {"min_score": 90, "min_jobs": 50, "max_job_price": None},
}

def compute_tier(score: float, total_jobs: int) -> str:
    """Hitung tier berdasarkan score dan jumlah jobs."""
    for tier in ["ELITE", "TRUSTED", "STANDARD", "PROBATION"]:
        t = TIER_THRESHOLDS[tier]
        if score >= t["min_score"] and total_jobs >= t["min_jobs"]:
            return tier
    return "PROBATION"


# ---------------------------------------------------------------------------
# Reputation Store
# ---------------------------------------------------------------------------

class ReputationStore:
    def __init__(self, data_dir: str) -> None:
        self.path = os.path.join(data_dir, "ai_reputation.json")
        os.makedirs(data_dir, exist_ok=True)
        self._data: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}

    def _save(self) -> None:
        import tempfile
        dir_ = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception:
            os.unlink(tmp)
            raise
        os.replace(tmp, self.path)

    def get(self, address: str) -> Optional[ReputationRecord]:
        d = self._data.get(address)
        return ReputationRecord.from_dict(d) if d else None

    def put(self, record: ReputationRecord) -> None:
        self._data[record.address] = record.to_dict()
        self._save()

    def all(self) -> List[ReputationRecord]:
        return [ReputationRecord.from_dict(d) for d in self._data.values()]

    def leaderboard(self, limit: int = 20) -> List[ReputationRecord]:
        active = [r for r in self.all() if not r.is_banned]
        return sorted(active, key=lambda r: (-r.score, -r.total_jobs))[:limit]


# ---------------------------------------------------------------------------
# Reputation Manager
# ---------------------------------------------------------------------------

class ReputationManager:
    """
    Manages reputation scores for workers and agents.

    Security design:
    - New addresses start at INITIAL_SCORE=60, not 100
      → Sybil attacker registering new workers gets mediocre score
    - Ban threshold: score <= 10 for 3+ consecutive timeouts
    - Score decay: inactive addresses lose 0.1/day (prevents hoarding)
    - History is append-only (audit trail)
    """

    BAN_THRESHOLD = 10.0
    DECAY_PER_DAY = 0.1
    MAX_HISTORY   = 100   # Keep last 100 events per address

    def __init__(self, store: ReputationStore) -> None:
        self.store = store

    def get_or_create(self, address: str) -> ReputationRecord:
        """Get existing record or create new one."""
        rec = self.store.get(address)
        if rec is None:
            rec = ReputationRecord(
                address=address,
                score=INITIAL_SCORE,
                total_jobs=0,
                successful_jobs=0,
                failed_jobs=0,
                disputed_jobs=0,
                timeouts=0,
                disputes_won=0,
                disputes_lost=0,
                created_at=int(time.time()),
                updated_at=int(time.time()),
            )
            self.store.put(rec)
        return rec

    def record_event(
        self,
        address: str,
        event_type: str,
        job_id: Optional[str] = None,
        note: str = "",
        custom_delta: Optional[float] = None,
    ) -> ReputationRecord:
        """Apply a reputation event to an address."""
        rec = self.get_or_create(address)

        if rec.is_banned:
            return rec  # Banned addresses don't accumulate more events

        delta = custom_delta if custom_delta is not None else SCORE_DELTA.get(event_type, 0.0)
        score_before = rec.score
        rec.score = max(SCORE_MIN, min(SCORE_MAX, rec.score + delta))

        # Update counters
        if event_type == EventType.JOB_SUCCESS:
            rec.successful_jobs += 1
            rec.total_jobs += 1
            rec.last_job_at = int(time.time())
        elif event_type == EventType.JOB_FAILED:
            rec.failed_jobs += 1
            rec.total_jobs += 1
        elif event_type == EventType.JOB_DISPUTED:
            rec.disputed_jobs += 1
            rec.total_jobs += 1
        elif event_type == EventType.TIMEOUT:
            rec.timeouts += 1
            rec.total_jobs += 1
        elif event_type == EventType.DISPUTE_WON:
            rec.disputes_won += 1
        elif event_type == EventType.DISPUTE_LOST:
            rec.disputes_lost += 1

        # Update tier
        rec.tier = compute_tier(rec.score, rec.total_jobs)

        # Check ban threshold
        if rec.score <= self.BAN_THRESHOLD and rec.timeouts >= 3:
            rec.is_banned = True
            rec.ban_reason = f"Score {rec.score:.1f} with {rec.timeouts} timeouts"

        # Append to history
        import uuid
        event = ScoreEvent(
            event_id=str(uuid.uuid4()),
            address=address,
            event_type=event_type,
            delta=delta,
            score_before=score_before,
            score_after=rec.score,
            job_id=job_id,
            timestamp=int(time.time()),
            note=note,
        )
        rec.history.append(event.to_dict())
        # Trim history
        if len(rec.history) > self.MAX_HISTORY:
            rec.history = rec.history[-self.MAX_HISTORY:]

        rec.updated_at = int(time.time())
        self.store.put(rec)
        return rec

    def apply_decay(self) -> List[str]:
        """
        Apply daily score decay to inactive addresses.
        Call this once per day (e.g. via cron or block event).
        Returns list of addresses affected.
        """
        affected = []
        now = int(time.time())
        for rec in self.store.all():
            if rec.is_banned:
                continue
            if rec.last_job_at is None:
                continue
            days_inactive = (now - rec.last_job_at) / 86400
            if days_inactive < 1:
                continue
            decay = self.DECAY_PER_DAY * days_inactive
            if decay < 0.1:
                continue
            rec.score = max(SCORE_MIN, rec.score - decay)
            rec.tier = compute_tier(rec.score, rec.total_jobs)
            rec.updated_at = now
            self.store.put(rec)
            affected.append(rec.address)
        return affected

    def unban(self, address: str, reason: str = "") -> ReputationRecord:
        """Manually unban an address (admin action)."""
        rec = self.get_or_create(address)
        rec.is_banned = False
        rec.ban_reason = ""
        rec.score = INITIAL_SCORE  # Reset to initial
        rec.tier = compute_tier(rec.score, rec.total_jobs)
        rec.updated_at = int(time.time())
        self.store.put(rec)
        return rec

    def get_score(self, address: str) -> float:
        rec = self.store.get(address)
        return rec.score if rec else INITIAL_SCORE

    def is_banned(self, address: str) -> bool:
        rec = self.store.get(address)
        return rec.is_banned if rec else False

    def get_tier(self, address: str) -> str:
        rec = self.store.get(address)
        return rec.tier if rec else "PROBATION"

    def can_take_job(self, address: str, job_price: int) -> bool:
        """Check apakah worker boleh ambil job dengan harga ini."""
        rec = self.store.get(address)
        if rec is None:
            return job_price <= TIER_THRESHOLDS["PROBATION"]["max_job_price"]
        if rec.is_banned:
            return False
        max_price = TIER_THRESHOLDS[rec.tier]["max_job_price"]
        if max_price is None:
            return True
        return job_price <= max_price

    def leaderboard(self, limit: int = 20) -> List[ReputationRecord]:
        return self.store.leaderboard(limit)
