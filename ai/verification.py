"""
ARCHE AI Verification Layer — Phase 7

5 level verifikasi, dari yang paling simpel sampai paling kuat.

Level 1 — Hash Verification
    Bandingkan result_hash dengan expected hash.
    Cepat, murah, tapi hanya cocok kalau output deterministik.

Level 2 — Redundant Execution
    Beberapa worker menjalankan job yang sama, bandingkan hasilnya.
    Majority vote menentukan hasil yang benar.

Level 3 — Challenge / Dispute
    Requester atau verifier bisa challenge result.
    Worker wajib menyediakan bukti (intermediate steps, logs).

Level 4 — Proof of Logits (PoL) — Research
    Output-level verification menggunakan logits distribution.
    Hanya berlaku untuk model yang mendukung logits export.
    BUKAN zero-knowledge — worker masih bisa fake logits.
    Security assumption: worker tidak bisa fake exact logits
    distribution tanpa benar-benar menjalankan model.
    Limitations: tidak berlaku untuk model yang tidak export logits,
    tidak proving model identity secara kriptografis.

Level 5 — ZKML — Research
    Zero-knowledge proof bahwa inferensi benar-benar dijalankan.
    Blockchain hanya verifikasi proof, tidak melihat input/output.
    Status: NOT IMPLEMENTED — research placeholder.

Security notes per level:
- L1: Mudah di-fake jika worker tahu expected hash
- L2: Butuh minimal 3 workers untuk majority vote yang bermakna
- L3: Worker bisa collude untuk fake challenge response
- L4: Asumsi keamanan lemah — lihat dokumentasi PoL
- L5: Kuat tapi computational cost sangat tinggi (belum feasible)
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Verification Level
# ---------------------------------------------------------------------------

class VerificationLevel(int, Enum):
    HASH        = 1   # Compare result hashes
    REDUNDANT   = 2   # Multiple workers, majority vote
    CHALLENGE   = 3   # Challenge/dispute with proof
    PROOF_LOGITS= 4   # Proof-of-Logits (research)
    ZKML        = 5   # Zero-knowledge ML proof (not implemented)


class VerificationResult(str, Enum):
    VERIFIED  = "VERIFIED"
    FAILED    = "FAILED"
    PENDING   = "PENDING"
    DISPUTED  = "DISPUTED"
    SKIPPED   = "SKIPPED"   # Level not applicable for this job


# ---------------------------------------------------------------------------
# Verification Record
# ---------------------------------------------------------------------------

@dataclass
class VerificationRecord:
    verification_id: str
    job_id: str
    level: VerificationLevel
    result: VerificationResult
    verifier: str           # Address atau "system"
    created_at: int
    completed_at: Optional[int]
    details: dict           # Level-specific details
    error: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["level"] = self.level.value
        d["result"] = self.result.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "VerificationRecord":
        d = dict(d)
        d["level"] = VerificationLevel(d["level"])
        d["result"] = VerificationResult(d["result"])
        return VerificationRecord(**d)


# ---------------------------------------------------------------------------
# Level 1 — Hash Verification
# ---------------------------------------------------------------------------

class HashVerifier:
    """
    Level 1: Bandingkan result_hash dengan hash yang diharapkan.

    Cocok untuk:
    - Deterministik output (sama input → sama output)
    - Ketika requester sudah tahu expected hash sebelumnya

    Limitations:
    - Worker bisa fake hash jika tahu expected value
    - Tidak berlaku untuk non-deterministic models (LLM dengan temperature > 0)
    """

    def verify(
        self,
        job_id: str,
        result_hash: str,
        expected_hash: str,
        verifier: str = "system",
    ) -> VerificationRecord:
        matched = result_hash.lower() == expected_hash.lower()
        return VerificationRecord(
            verification_id=str(uuid.uuid4()),
            job_id=job_id,
            level=VerificationLevel.HASH,
            result=VerificationResult.VERIFIED if matched else VerificationResult.FAILED,
            verifier=verifier,
            created_at=int(time.time()),
            completed_at=int(time.time()),
            details={
                "result_hash": result_hash,
                "expected_hash": expected_hash,
                "matched": matched,
            },
        )

    def hash_output(self, output_bytes: bytes) -> str:
        """Compute SHA256 hash of output data."""
        return hashlib.sha256(output_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Level 2 — Redundant Execution
# ---------------------------------------------------------------------------

@dataclass
class WorkerSubmission:
    worker_address: str
    result_hash: str
    submitted_at: int
    metadata: dict = field(default_factory=dict)


class RedundantVerifier:
    """
    Level 2: Beberapa worker menjalankan job yang sama.
    Majority vote menentukan hasil yang benar.

    Security assumptions:
    - Majority of workers are honest
    - Workers cannot collude at scale

    Attack surface:
    - Sybil attack: attacker registers many fake workers
    - Collusion: workers coordinate to submit same wrong hash
    - Mitigation: reputation system + stake requirement

    Minimum workers untuk meaningful verification: 3
    """

    MIN_WORKERS = 3

    def add_submission(
        self,
        submissions: List[WorkerSubmission],
        worker: str,
        result_hash: str,
    ) -> List[WorkerSubmission]:
        """Add a worker's submission to the pool."""
        # Prevent duplicate from same worker
        if any(s.worker_address == worker for s in submissions):
            raise ValueError(f"Worker {worker} already submitted for this job")
        submissions.append(WorkerSubmission(
            worker_address=worker,
            result_hash=result_hash,
            submitted_at=int(time.time()),
        ))
        return submissions

    def evaluate(
        self,
        job_id: str,
        submissions: List[WorkerSubmission],
        verifier: str = "system",
    ) -> Tuple[VerificationRecord, Optional[str]]:
        """
        Evaluate submissions via majority vote.

        Returns:
            (VerificationRecord, winning_hash or None)
        """
        if len(submissions) < self.MIN_WORKERS:
            rec = VerificationRecord(
                verification_id=str(uuid.uuid4()),
                job_id=job_id,
                level=VerificationLevel.REDUNDANT,
                result=VerificationResult.PENDING,
                verifier=verifier,
                created_at=int(time.time()),
                completed_at=None,
                details={
                    "submissions": len(submissions),
                    "required": self.MIN_WORKERS,
                    "reason": "Not enough submissions yet",
                },
            )
            return rec, None

        # Count votes per hash
        votes: Dict[str, List[str]] = {}
        for s in submissions:
            h = s.result_hash.lower()
            if h not in votes:
                votes[h] = []
            votes[h].append(s.worker_address)

        # Find majority
        majority_hash = None
        majority_count = 0
        for h, workers in votes.items():
            if len(workers) > majority_count:
                majority_count = len(workers)
                majority_hash = h

        total = len(submissions)
        has_majority = majority_count > total / 2

        # Identify dishonest workers
        dishonest = []
        if majority_hash:
            for s in submissions:
                if s.result_hash.lower() != majority_hash:
                    dishonest.append(s.worker_address)

        result = VerificationResult.VERIFIED if has_majority else VerificationResult.DISPUTED
        rec = VerificationRecord(
            verification_id=str(uuid.uuid4()),
            job_id=job_id,
            level=VerificationLevel.REDUNDANT,
            result=result,
            verifier=verifier,
            created_at=int(time.time()),
            completed_at=int(time.time()),
            details={
                "total_submissions": total,
                "majority_hash": majority_hash,
                "majority_count": majority_count,
                "has_majority": has_majority,
                "vote_distribution": {h: len(w) for h, w in votes.items()},
                "dishonest_workers": dishonest,
            },
        )
        return rec, majority_hash if has_majority else None


# ---------------------------------------------------------------------------
# Level 3 — Challenge / Dispute
# ---------------------------------------------------------------------------

class ChallengeStatus(str, Enum):
    OPEN      = "OPEN"
    RESPONDED = "RESPONDED"
    RESOLVED  = "RESOLVED"
    TIMEOUT   = "TIMEOUT"


@dataclass
class Challenge:
    challenge_id: str
    job_id: str
    challenger: str     # Address yang challenge
    challenged: str     # Worker yang di-challenge
    reason: str
    status: ChallengeStatus
    created_at: int
    deadline: int       # Worker harus respond sebelum ini
    response: Optional[dict] = None
    resolved_at: Optional[int] = None
    resolution: Optional[str] = None  # "UPHELD" atau "DISMISSED"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "Challenge":
        d = dict(d)
        d["status"] = ChallengeStatus(d["status"])
        return Challenge(**d)


class ChallengeVerifier:
    """
    Level 3: Challenge/Dispute mechanism.

    Requester atau verifier bisa challenge result worker.
    Worker wajib respond dengan bukti (intermediate outputs, logs).

    Attack surface:
    - Worker bisa fabricate logs/proofs
    - Challenger bisa spam challenges (griefing)
    - Mitigation: challenge fee + reputation penalty untuk false challenges

    Security: Depends on honest arbiters (not cryptographically secure)
    """

    CHALLENGE_RESPONSE_WINDOW = 3600  # 1 jam

    def open_challenge(
        self,
        job_id: str,
        challenger: str,
        challenged_worker: str,
        reason: str,
    ) -> Challenge:
        return Challenge(
            challenge_id=str(uuid.uuid4()),
            job_id=job_id,
            challenger=challenger,
            challenged=challenged_worker,
            reason=reason,
            status=ChallengeStatus.OPEN,
            created_at=int(time.time()),
            deadline=int(time.time()) + self.CHALLENGE_RESPONSE_WINDOW,
        )

    def respond_to_challenge(
        self,
        challenge: Challenge,
        worker: str,
        proof: dict,
    ) -> Challenge:
        """Worker merespond challenge dengan bukti."""
        if challenge.challenged != worker:
            raise ValueError("Only challenged worker can respond")
        if challenge.status != ChallengeStatus.OPEN:
            raise ValueError(f"Challenge is not OPEN (status={challenge.status})")
        if int(time.time()) > challenge.deadline:
            challenge.status = ChallengeStatus.TIMEOUT
            raise ValueError("Challenge response deadline passed")
        challenge.response = proof
        challenge.status = ChallengeStatus.RESPONDED
        return challenge

    def resolve_challenge(
        self,
        challenge: Challenge,
        arbiter: str,
        upheld: bool,
        reasoning: str = "",
    ) -> Tuple[Challenge, VerificationRecord]:
        """
        Arbiter (requester, trusted verifier, atau system) resolve challenge.

        upheld=True  → worker cheated, result invalid
        upheld=False → challenge was wrong, worker honest
        """
        # Auto-resolve timeout
        if challenge.status == ChallengeStatus.OPEN and int(time.time()) > challenge.deadline:
            upheld = True  # No response = assume cheating
            reasoning = "Worker did not respond within deadline"
            challenge.status = ChallengeStatus.TIMEOUT

        challenge.resolution = "UPHELD" if upheld else "DISMISSED"
        challenge.resolved_at = int(time.time())
        challenge.status = ChallengeStatus.RESOLVED

        rec = VerificationRecord(
            verification_id=str(uuid.uuid4()),
            job_id=challenge.job_id,
            level=VerificationLevel.CHALLENGE,
            result=VerificationResult.FAILED if upheld else VerificationResult.VERIFIED,
            verifier=arbiter,
            created_at=int(time.time()),
            completed_at=int(time.time()),
            details={
                "challenge_id": challenge.challenge_id,
                "challenger": challenge.challenger,
                "challenged": challenge.challenged,
                "upheld": upheld,
                "reasoning": reasoning,
                "had_response": challenge.response is not None,
            },
        )
        return challenge, rec


# ---------------------------------------------------------------------------
# Level 4 — Proof of Logits (Research)
# ---------------------------------------------------------------------------

class ProofOfLogits:
    """
    Level 4: Output-level verification menggunakan logits distribution.

    PENTING — Baca security assumptions:

    Asumsi keamanan:
    - Worker tidak bisa fake exact logits distribution tanpa
      benar-benar menjalankan model yang dimaksud
    - Requester sudah punya reference logits dari trusted run

    Attack surface:
    - Worker yang punya akses model bisa run model sendiri dan fake logits
    - Tidak membuktikan MODEL IDENTITY secara kriptografis
    - Tidak membuktikan INPUT yang digunakan
    - Temperature/sampling membuat output non-deterministic

    Kapan valid digunakan:
    - Model deterministik (temperature=0, greedy decoding)
    - Requester punya trusted reference logits untuk perbandingan
    - Sebagai sanity check, bukan sebagai hard security guarantee

    Kapan TIDAK valid:
    - LLM dengan temperature > 0
    - Model yang tidak export logits
    - Ketika worker identity perlu dibuktikan secara kriptografis
    - Production security-critical applications

    Status: RESEARCH / EXPERIMENTAL
    """

    def __init__(self, tolerance: float = 1e-4):
        """
        tolerance: Maximum allowed difference per logit value.
        Kecil berarti lebih ketat, tapi rentan terhadap floating-point differences.
        """
        self.tolerance = tolerance

    def verify_logits(
        self,
        job_id: str,
        submitted_logits: List[float],
        reference_logits: List[float],
        verifier: str = "system",
    ) -> VerificationRecord:
        """
        Bandingkan submitted logits dengan reference logits.

        Parameters
        ----------
        submitted_logits : logits yang dikirim worker
        reference_logits : logits dari trusted reference run
        """
        if len(submitted_logits) != len(reference_logits):
            return VerificationRecord(
                verification_id=str(uuid.uuid4()),
                job_id=job_id,
                level=VerificationLevel.PROOF_LOGITS,
                result=VerificationResult.FAILED,
                verifier=verifier,
                created_at=int(time.time()),
                completed_at=int(time.time()),
                details={
                    "error": "Logits length mismatch",
                    "submitted_len": len(submitted_logits),
                    "reference_len": len(reference_logits),
                },
                error="Logits length mismatch",
            )

        diffs = [abs(a - b) for a, b in zip(submitted_logits, reference_logits)]
        max_diff = max(diffs) if diffs else 0.0
        avg_diff = sum(diffs) / len(diffs) if diffs else 0.0
        passed = max_diff <= self.tolerance

        return VerificationRecord(
            verification_id=str(uuid.uuid4()),
            job_id=job_id,
            level=VerificationLevel.PROOF_LOGITS,
            result=VerificationResult.VERIFIED if passed else VerificationResult.FAILED,
            verifier=verifier,
            created_at=int(time.time()),
            completed_at=int(time.time()),
            details={
                "max_diff": max_diff,
                "avg_diff": avg_diff,
                "tolerance": self.tolerance,
                "passed": passed,
                "num_logits": len(submitted_logits),
                "security_note": (
                    "PoL is a research feature. "
                    "It does not cryptographically prove model identity or input. "
                    "Use only for deterministc models with trusted reference logits."
                ),
            },
        )

    def compute_logits_hash(self, logits: List[float], precision: int = 4) -> str:
        """
        Hash logits dengan precision tertentu untuk comparison.
        Mengurangi floating-point noise saat precision > 0.
        """
        rounded = [round(v, precision) for v in logits]
        data = json.dumps(rounded, separators=(",", ":")).encode()
        return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Level 5 — ZKML (Research Stub)
# ---------------------------------------------------------------------------

class ZKMLVerifier:
    """
    Level 5: Zero-knowledge ML proof verification.

    STATUS: NOT IMPLEMENTED — Research placeholder.

    Target interface (untuk implementasi masa depan):
        verify_proof(proof_bytes, public_inputs) → bool

    Tujuan:
    - User submit private input ke worker
    - Worker jalankan model
    - Worker generate ZK proof bahwa output dihasilkan dari model + input
    - Blockchain verify proof (tanpa melihat input atau output)

    Tantangan yang belum terpecahkan:
    - Proof generation sangat lambat untuk model besar (jam, bukan detik)
    - Proof size bisa sangat besar
    - Quantization dan approximation mengubah model behavior
    - Model weights bisa berubah → proof bisa invalid

    Library yang sedang dikembangkan di industri:
    - EZKL (https://ezkl.xyz)
    - Risc0
    - Axiom

    Jangan gunakan di production sebelum:
    1. Library ZK sudah production-ready
    2. Proof generation time < 10 detik untuk model yang digunakan
    3. Proof size < 1 MB
    4. Security assumptions sudah diaudit

    Ini adalah placeholder untuk interface yang akan diimplementasikan
    ketika teknologi sudah cukup matang.
    """

    def verify_proof(
        self,
        job_id: str,
        proof_bytes: bytes,
        public_inputs: dict,
        verifier: str = "system",
    ) -> VerificationRecord:
        """
        STUB — Belum diimplementasikan.
        Akan raise NotImplementedError sampai teknologi siap.
        """
        return VerificationRecord(
            verification_id=str(uuid.uuid4()),
            job_id=job_id,
            level=VerificationLevel.ZKML,
            result=VerificationResult.SKIPPED,
            verifier=verifier,
            created_at=int(time.time()),
            completed_at=int(time.time()),
            details={
                "status": "NOT_IMPLEMENTED",
                "reason": (
                    "ZKML verification is a research placeholder. "
                    "It will be implemented when ZK proof generation "
                    "is fast enough for practical use."
                ),
            },
            error="ZKML not implemented",
        )


# ---------------------------------------------------------------------------
# Verification Manager — orchestrates all levels
# ---------------------------------------------------------------------------

class VerificationPolicy:
    """Policy yang menentukan level verifikasi mana yang digunakan per job."""

    def __init__(
        self,
        min_level: VerificationLevel = VerificationLevel.HASH,
        require_redundant_workers: int = 1,
        enable_pol: bool = False,
        enable_zkml: bool = False,
    ) -> None:
        self.min_level = min_level
        self.require_redundant_workers = require_redundant_workers
        self.enable_pol = enable_pol
        self.enable_zkml = enable_zkml  # Always False for now


class VerificationManager:
    """
    Orchestrator untuk semua level verifikasi.
    Pilih level berdasarkan policy dan job requirement.
    """

    def __init__(self, policy: Optional[VerificationPolicy] = None) -> None:
        self.policy = policy or VerificationPolicy()
        self.hash_verifier = HashVerifier()
        self.redundant_verifier = RedundantVerifier()
        self.challenge_verifier = ChallengeVerifier()
        self.pol_verifier = ProofOfLogits()
        self.zkml_verifier = ZKMLVerifier()

    def verify_hash(
        self,
        job_id: str,
        result_hash: str,
        expected_hash: str,
        verifier: str = "system",
    ) -> VerificationRecord:
        """Level 1 verification."""
        return self.hash_verifier.verify(job_id, result_hash, expected_hash, verifier)

    def evaluate_redundant(
        self,
        job_id: str,
        submissions: List[WorkerSubmission],
        verifier: str = "system",
    ) -> Tuple[VerificationRecord, Optional[str]]:
        """Level 2 verification."""
        return self.redundant_verifier.evaluate(job_id, submissions, verifier)

    def open_challenge(
        self,
        job_id: str,
        challenger: str,
        worker: str,
        reason: str,
    ) -> Challenge:
        """Level 3 — open a challenge."""
        return self.challenge_verifier.open_challenge(job_id, challenger, worker, reason)

    def resolve_challenge(
        self,
        challenge: Challenge,
        arbiter: str,
        upheld: bool,
        reasoning: str = "",
    ) -> Tuple[Challenge, VerificationRecord]:
        """Level 3 — resolve a challenge."""
        return self.challenge_verifier.resolve_challenge(challenge, arbiter, upheld, reasoning)

    def verify_logits(
        self,
        job_id: str,
        submitted_logits: List[float],
        reference_logits: List[float],
        verifier: str = "system",
    ) -> VerificationRecord:
        """Level 4 — Proof of Logits (research)."""
        if not self.policy.enable_pol:
            return VerificationRecord(
                verification_id=str(uuid.uuid4()),
                job_id=job_id,
                level=VerificationLevel.PROOF_LOGITS,
                result=VerificationResult.SKIPPED,
                verifier=verifier,
                created_at=int(time.time()),
                completed_at=int(time.time()),
                details={"reason": "PoL not enabled in policy"},
            )
        return self.pol_verifier.verify_logits(
            job_id, submitted_logits, reference_logits, verifier
        )

    def verify_zkml(
        self,
        job_id: str,
        proof_bytes: bytes,
        public_inputs: dict,
        verifier: str = "system",
    ) -> VerificationRecord:
        """Level 5 — ZKML (not implemented)."""
        return self.zkml_verifier.verify_proof(
            job_id, proof_bytes, public_inputs, verifier
        )

    def select_level(self, job: dict) -> VerificationLevel:
        """
        Pilih level verifikasi yang tepat berdasarkan job metadata.
        """
        compute_req = job.get("compute_requirement", {})
        # Jika job punya expected_hash → Level 1
        if job.get("expected_result_hash"):
            return VerificationLevel.HASH
        # Jika ada multiple workers → Level 2
        if len(job.get("verifiers", [])) >= self.redundant_verifier.MIN_WORKERS:
            return VerificationLevel.REDUNDANT
        # Default: Level 1 hash
        return self.policy.min_level
