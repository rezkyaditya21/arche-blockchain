"""
ARCHE AI Job System — Phase 1

AI Job adalah unit kerja komputasi yang dibayar menggunakan ARC.
Disimpan terpisah dari blockchain — blockchain hanya menyimpan
payment transaction, bukan job data.

Flow:
User → create_job() → PENDING
Worker → assign_job() → ASSIGNED
Worker → start_job()  → RUNNING
Worker → submit_result() → VERIFYING
Verifier → verify_job() → COMPLETED / FAILED / DISPUTED
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


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    PENDING    = "PENDING"
    ASSIGNED   = "ASSIGNED"
    RUNNING    = "RUNNING"
    VERIFYING  = "VERIFYING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"
    CANCELLED  = "CANCELLED"
    DISPUTED   = "DISPUTED"


class PaymentStatus(str, Enum):
    UNPAID    = "UNPAID"
    ESCROWED  = "ESCROWED"
    RELEASED  = "RELEASED"
    REFUNDED  = "REFUNDED"


class VerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED   = "VERIFIED"
    FAILED     = "FAILED"
    DISPUTED   = "DISPUTED"


# ---------------------------------------------------------------------------
# AI Job
# ---------------------------------------------------------------------------

@dataclass
class AIJob:
    job_id: str
    requester: str          # ARC address of requester
    model_id: str           # ID dari Model Registry
    input_hash: str         # SHA256 hash of input data
    input_reference: str    # URL / IPFS / path ke input data (off-chain)
    compute_requirement: dict  # {"min_ram_gb": 4, "gpu": false, "framework": "onnx"}
    max_price: int          # Maximum ARC willing to pay (base units)
    deadline: int           # Unix timestamp deadline
    created_at: int         # Unix timestamp created

    # Mutable fields
    status: JobStatus = JobStatus.PENDING
    assigned_worker: Optional[str] = None   # Worker ARC address
    assigned_at: Optional[int] = None
    started_at: Optional[int] = None
    result_hash: Optional[str] = None       # SHA256 hash of result
    result_reference: Optional[str] = None  # URL / IPFS ke result (off-chain)
    completed_at: Optional[int] = None
    agreed_price: Optional[int] = None      # Price agreed dengan worker
    escrow_txid: Optional[str] = None       # ARCHE txid untuk escrow
    payment_txid: Optional[str] = None      # ARCHE txid untuk payment release
    payment_status: PaymentStatus = PaymentStatus.UNPAID
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    error_message: Optional[str] = None
    dispute_reason: Optional[str] = None
    verifiers: List[str] = field(default_factory=list)  # Addresses of verifiers

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["payment_status"] = self.payment_status.value
        d["verification_status"] = self.verification_status.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "AIJob":
        d = dict(d)
        d["status"] = JobStatus(d["status"])
        d["payment_status"] = PaymentStatus(d["payment_status"])
        d["verification_status"] = VerificationStatus(d["verification_status"])
        return AIJob(**d)

    def is_expired(self) -> bool:
        return int(time.time()) > self.deadline

    def can_be_assigned(self) -> bool:
        return self.status == JobStatus.PENDING and not self.is_expired()

    def can_be_cancelled(self) -> bool:
        return self.status in (JobStatus.PENDING, JobStatus.ASSIGNED)


# ---------------------------------------------------------------------------
# Job Store — persistence (JSON, dapat diganti dengan DB)
# ---------------------------------------------------------------------------

class JobStore:
    """
    Persistent store untuk AI jobs.
    Terpisah dari blockchain storage.
    """

    def __init__(self, data_dir: str) -> None:
        self.path = os.path.join(data_dir, "ai_jobs.json")
        os.makedirs(data_dir, exist_ok=True)
        self._jobs: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._jobs = json.load(f)
            except Exception:
                self._jobs = {}

    def _save(self) -> None:
        import tempfile
        dir_ = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._jobs, f, indent=2)
        except Exception:
            os.unlink(tmp)
            raise
        os.replace(tmp, self.path)

    def put(self, job: AIJob) -> None:
        self._jobs[job.job_id] = job.to_dict()
        self._save()

    def get(self, job_id: str) -> Optional[AIJob]:
        d = self._jobs.get(job_id)
        if d is None:
            return None
        return AIJob.from_dict(d)

    def all(self) -> List[AIJob]:
        return [AIJob.from_dict(d) for d in self._jobs.values()]

    def by_status(self, status: JobStatus) -> List[AIJob]:
        return [j for j in self.all() if j.status == status]

    def by_requester(self, address: str) -> List[AIJob]:
        return [j for j in self.all() if j.requester == address]

    def by_worker(self, address: str) -> List[AIJob]:
        return [j for j in self.all() if j.assigned_worker == address]

    def delete(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)
        self._save()


# ---------------------------------------------------------------------------
# Job Manager — business logic
# ---------------------------------------------------------------------------

class JobManager:
    def __init__(self, store: JobStore) -> None:
        self.store = store

    def create_job(
        self,
        requester: str,
        model_id: str,
        input_hash: str,
        input_reference: str,
        compute_requirement: dict,
        max_price: int,
        deadline: int,
    ) -> AIJob:
        """Create a new AI job."""
        if max_price <= 0:
            raise ValueError("max_price must be > 0")
        if deadline <= int(time.time()):
            raise ValueError("deadline must be in the future")
        if not input_hash or len(input_hash) != 64:
            raise ValueError("input_hash must be 64-char hex SHA256")

        job = AIJob(
            job_id=str(uuid.uuid4()),
            requester=requester,
            model_id=model_id,
            input_hash=input_hash,
            input_reference=input_reference,
            compute_requirement=compute_requirement,
            max_price=max_price,
            deadline=deadline,
            created_at=int(time.time()),
        )
        self.store.put(job)
        return job

    def assign_job(self, job_id: str, worker: str, agreed_price: int) -> AIJob:
        """Worker claims a job."""
        job = self._get_or_raise(job_id)
        if not job.can_be_assigned():
            raise ValueError(f"Job {job_id} cannot be assigned (status={job.status})")
        if agreed_price > job.max_price:
            raise ValueError(f"agreed_price {agreed_price} exceeds max_price {job.max_price}")
        job.status = JobStatus.ASSIGNED
        job.assigned_worker = worker
        job.agreed_price = agreed_price
        job.assigned_at = int(time.time())
        self.store.put(job)
        return job

    def start_job(self, job_id: str, worker: str) -> AIJob:
        """Worker starts executing the job."""
        job = self._get_or_raise(job_id)
        if job.status != JobStatus.ASSIGNED:
            raise ValueError(f"Job {job_id} is not in ASSIGNED state")
        if job.assigned_worker != worker:
            raise ValueError("Only assigned worker can start the job")
        if job.is_expired():
            job.status = JobStatus.FAILED
            job.error_message = "Job expired before execution started"
            self.store.put(job)
            raise ValueError("Job has expired")
        job.status = JobStatus.RUNNING
        job.started_at = int(time.time())
        self.store.put(job)
        return job

    def submit_result(
        self,
        job_id: str,
        worker: str,
        result_hash: str,
        result_reference: str,
    ) -> AIJob:
        """Worker submits result for verification."""
        job = self._get_or_raise(job_id)
        if job.status != JobStatus.RUNNING:
            raise ValueError(f"Job {job_id} is not RUNNING")
        if job.assigned_worker != worker:
            raise ValueError("Only assigned worker can submit result")
        if not result_hash or len(result_hash) != 64:
            raise ValueError("result_hash must be 64-char hex SHA256")
        job.status = JobStatus.VERIFYING
        job.result_hash = result_hash
        job.result_reference = result_reference
        self.store.put(job)
        return job

    def verify_job(
        self,
        job_id: str,
        verifier: str,
        success: bool,
        reason: str = "",
    ) -> AIJob:
        """Verifier approves or rejects the result."""
        job = self._get_or_raise(job_id)
        if job.status != JobStatus.VERIFYING:
            raise ValueError(f"Job {job_id} is not in VERIFYING state")
        if verifier not in job.verifiers and verifier != job.requester:
            job.verifiers.append(verifier)
        if success:
            job.status = JobStatus.COMPLETED
            job.verification_status = VerificationStatus.VERIFIED
            job.completed_at = int(time.time())
        else:
            job.status = JobStatus.DISPUTED
            job.verification_status = VerificationStatus.DISPUTED
            job.dispute_reason = reason
        self.store.put(job)
        return job

    def cancel_job(self, job_id: str, requester: str, reason: str = "") -> AIJob:
        """Requester cancels a job."""
        job = self._get_or_raise(job_id)
        if job.requester != requester:
            raise ValueError("Only requester can cancel the job")
        if not job.can_be_cancelled():
            raise ValueError(f"Job {job_id} cannot be cancelled (status={job.status})")
        job.status = JobStatus.CANCELLED
        job.error_message = reason or "Cancelled by requester"
        self.store.put(job)
        return job

    def fail_job(self, job_id: str, reason: str = "") -> AIJob:
        """Mark job as failed (e.g. worker timeout)."""
        job = self._get_or_raise(job_id)
        job.status = JobStatus.FAILED
        job.error_message = reason
        self.store.put(job)
        return job

    def expire_jobs(self) -> List[str]:
        """Check all pending/assigned jobs and fail expired ones."""
        expired = []
        now = int(time.time())
        for job in self.store.by_status(JobStatus.PENDING):
            if job.is_expired():
                self.fail_job(job.job_id, "Deadline exceeded")
                expired.append(job.job_id)
        for job in self.store.by_status(JobStatus.ASSIGNED):
            if job.is_expired():
                self.fail_job(job.job_id, "Deadline exceeded after assignment")
                expired.append(job.job_id)
        return expired

    def set_escrow(self, job_id: str, txid: str) -> AIJob:
        """Record the escrow transaction ID for a job."""
        job = self._get_or_raise(job_id)
        job.escrow_txid = txid
        job.payment_status = PaymentStatus.ESCROWED
        self.store.put(job)
        return job

    def release_payment(self, job_id: str, payment_txid: str) -> AIJob:
        """Record the payment release transaction."""
        job = self._get_or_raise(job_id)
        if job.status != JobStatus.COMPLETED:
            raise ValueError("Payment can only be released for COMPLETED jobs")
        job.payment_txid = payment_txid
        job.payment_status = PaymentStatus.RELEASED
        self.store.put(job)
        return job

    def refund_payment(self, job_id: str, refund_txid: str) -> AIJob:
        """Record payment refund to requester."""
        job = self._get_or_raise(job_id)
        job.payment_txid = refund_txid
        job.payment_status = PaymentStatus.REFUNDED
        self.store.put(job)
        return job

    def _get_or_raise(self, job_id: str) -> AIJob:
        job = self.store.get(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        return job


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def hash_input(data: bytes) -> str:
    """SHA256 hash of input data for input_hash field."""
    return hashlib.sha256(data).hexdigest()
