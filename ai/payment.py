"""
ARCHE ARC Payment System — Phase 3

Menggunakan UTXO ARCHE yang sudah ada untuk escrow dan pembayaran.
Tidak membuat sistem pembayaran baru.

Flow:
1. User buat job → escrow ARC ke address khusus (lock address)
2. Job selesai diverifikasi → ARC di-release ke worker
3. Job gagal/cancelled → ARC di-refund ke requester
4. Dispute → ARC ditahan sampai resolved

Catatan keamanan:
- Double payment: dicegah dengan tracking txid
- Replay attack: dicegah dengan chain_id di signing domain
- Unauthorized claim: hanya worker yang assigned bisa claim
- Timeout: job expired → auto-refund
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Escrow Record
# ---------------------------------------------------------------------------

class EscrowStatus(str, Enum):
    LOCKED    = "LOCKED"
    RELEASED  = "RELEASED"
    REFUNDED  = "REFUNDED"
    DISPUTED  = "DISPUTED"
    EXPIRED   = "EXPIRED"


@dataclass
class EscrowRecord:
    escrow_id: str
    job_id: str
    requester: str       # ARC address
    worker: str          # ARC address
    amount: int          # ARC base units
    lock_txid: str       # ARCHE transaction ID untuk lock
    release_txid: Optional[str]   # ARCHE txid untuk release ke worker
    refund_txid: Optional[str]    # ARCHE txid untuk refund ke requester
    status: EscrowStatus
    created_at: int
    updated_at: int
    expires_at: int      # Unix timestamp — setelah ini auto-refund
    dispute_reason: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "EscrowRecord":
        d = dict(d)
        d["status"] = EscrowStatus(d["status"])
        return EscrowRecord(**d)

    def is_expired(self) -> bool:
        return (
            self.status == EscrowStatus.LOCKED
            and int(time.time()) > self.expires_at
        )


# ---------------------------------------------------------------------------
# Payment Store
# ---------------------------------------------------------------------------

class PaymentStore:
    def __init__(self, data_dir: str) -> None:
        self.path = os.path.join(data_dir, "ai_payments.json")
        os.makedirs(data_dir, exist_ok=True)
        self._records: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._records = json.load(f)
            except Exception:
                self._records = {}

    def _save(self) -> None:
        import tempfile
        dir_ = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._records, f, indent=2)
        except Exception:
            os.unlink(tmp)
            raise
        os.replace(tmp, self.path)

    def put(self, record: EscrowRecord) -> None:
        self._records[record.escrow_id] = record.to_dict()
        self._save()

    def get(self, escrow_id: str) -> Optional[EscrowRecord]:
        d = self._records.get(escrow_id)
        return EscrowRecord.from_dict(d) if d else None

    def get_by_job(self, job_id: str) -> Optional[EscrowRecord]:
        for d in self._records.values():
            if d.get("job_id") == job_id:
                return EscrowRecord.from_dict(d)
        return None

    def all(self) -> List[EscrowRecord]:
        return [EscrowRecord.from_dict(d) for d in self._records.values()]

    def locked(self) -> List[EscrowRecord]:
        return [r for r in self.all() if r.status == EscrowStatus.LOCKED]


# ---------------------------------------------------------------------------
# Payment Manager
# ---------------------------------------------------------------------------

class PaymentManager:
    """
    Mengelola escrow ARC untuk AI Jobs.

    Penting: PaymentManager tidak membuat ARCHE transaction secara langsung.
    Ia menerima txid dari transaksi yang sudah dibuat oleh wallet/node,
    dan menyimpan record escrow untuk tracking.

    Untuk membuat transaksi ARCHE, gunakan wallet.cli_wallet atau node HTTP API.
    """

    def __init__(self, store: PaymentStore) -> None:
        self.store = store

    def create_escrow(
        self,
        job_id: str,
        requester: str,
        worker: str,
        amount: int,
        lock_txid: str,
        expires_at: int,
    ) -> EscrowRecord:
        """
        Record escrow setelah user sudah membuat ARCHE transaction.

        Parameters
        ----------
        job_id    : ID job yang dibayar
        requester : ARC address pembayar
        worker    : ARC address penerima (worker)
        amount    : jumlah ARC yang di-escrow (base units)
        lock_txid : txid dari ARCHE transaction yang mengunci ARC
        expires_at: deadline — setelah ini auto-refund
        """
        # Cek duplicate escrow untuk job yang sama
        existing = self.store.get_by_job(job_id)
        if existing and existing.status == EscrowStatus.LOCKED:
            raise ValueError(f"Job {job_id} already has an active escrow")

        # Validasi dasar
        if amount <= 0:
            raise ValueError("amount must be > 0")
        if not lock_txid or len(lock_txid) != 64:
            raise ValueError("lock_txid must be valid 64-char txid")

        import uuid
        record = EscrowRecord(
            escrow_id=str(uuid.uuid4()),
            job_id=job_id,
            requester=requester,
            worker=worker,
            amount=amount,
            lock_txid=lock_txid,
            release_txid=None,
            refund_txid=None,
            status=EscrowStatus.LOCKED,
            created_at=int(time.time()),
            updated_at=int(time.time()),
            expires_at=expires_at,
        )
        self.store.put(record)
        return record

    def release_to_worker(
        self,
        job_id: str,
        release_txid: str,
        authorized_by: str,
    ) -> EscrowRecord:
        """
        Release ARC ke worker setelah job COMPLETED.
        authorized_by harus = requester atau system verifier.
        """
        record = self._get_by_job_or_raise(job_id)
        if record.status != EscrowStatus.LOCKED:
            raise ValueError(f"Escrow for job {job_id} is not LOCKED (status={record.status})")
        if authorized_by not in (record.requester, "system"):
            raise ValueError("Only requester or system can release escrow")
        if not release_txid or len(release_txid) != 64:
            raise ValueError("release_txid must be valid 64-char txid")
        # Prevent double payment
        if record.release_txid is not None:
            raise ValueError("Payment already released (double payment attempt)")

        record.release_txid = release_txid
        record.status = EscrowStatus.RELEASED
        record.updated_at = int(time.time())
        self.store.put(record)
        return record

    def refund_to_requester(
        self,
        job_id: str,
        refund_txid: str,
        reason: str = "",
    ) -> EscrowRecord:
        """Refund ARC ke requester (job failed/cancelled/expired)."""
        record = self._get_by_job_or_raise(job_id)
        if record.status not in (
            EscrowStatus.LOCKED, EscrowStatus.DISPUTED, EscrowStatus.EXPIRED
        ):
            raise ValueError(f"Cannot refund escrow with status={record.status}")
        if record.refund_txid is not None:
            raise ValueError("Refund already processed (double refund attempt)")
        if not refund_txid or len(refund_txid) != 64:
            raise ValueError("refund_txid must be valid 64-char txid")

        record.refund_txid = refund_txid
        record.status = EscrowStatus.REFUNDED
        record.updated_at = int(time.time())
        if reason:
            record.dispute_reason = reason
        self.store.put(record)
        return record

    def open_dispute(self, job_id: str, reason: str) -> EscrowRecord:
        """Buka dispute — ARC ditahan sampai resolved."""
        record = self._get_by_job_or_raise(job_id)
        if record.status != EscrowStatus.LOCKED:
            raise ValueError(f"Can only dispute LOCKED escrow, got {record.status}")
        record.status = EscrowStatus.DISPUTED
        record.dispute_reason = reason
        record.updated_at = int(time.time())
        self.store.put(record)
        return record

    def expire_overdue(self) -> List[str]:
        """Mark expired escrows dan return list job_ids yang expired."""
        expired_jobs = []
        for record in self.store.locked():
            if record.is_expired():
                record.status = EscrowStatus.EXPIRED
                record.updated_at = int(time.time())
                self.store.put(record)
                expired_jobs.append(record.job_id)
        return expired_jobs

    def get_escrow(self, job_id: str) -> Optional[EscrowRecord]:
        return self.store.get_by_job(job_id)

    def worker_earnings(self, worker_address: str) -> int:
        """Total ARC yang sudah di-release ke worker ini."""
        total = 0
        for r in self.store.all():
            if r.worker == worker_address and r.status == EscrowStatus.RELEASED:
                total += r.amount
        return total

    def _get_by_job_or_raise(self, job_id: str) -> EscrowRecord:
        record = self.store.get_by_job(job_id)
        if record is None:
            raise ValueError(f"No escrow found for job {job_id}")
        return record
