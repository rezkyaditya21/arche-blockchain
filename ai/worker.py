"""
ARCHE AI Worker Node — Phase 2

Worker adalah node terpisah yang mendaftarkan diri ke network,
mengambil AI Job, menjalankan inferensi, dan menerima ARC.

Blockchain node biasa TIDAK perlu GPU.
Worker node adalah proses terpisah yang bisa dijalankan di mesin berbeda.

Flow:
Worker → register() → ACTIVE
Worker → find_jobs() → list of PENDING jobs
Worker → bid_job() → ASSIGNED
Worker → execute_job() → submit_result()
Worker → receive_payment()
"""
from __future__ import annotations

import json
import os
import platform
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Worker Status
# ---------------------------------------------------------------------------

class WorkerStatus(str, Enum):
    ACTIVE   = "ACTIVE"
    INACTIVE = "INACTIVE"
    BUSY     = "BUSY"
    BANNED   = "BANNED"


# ---------------------------------------------------------------------------
# Worker Capability
# ---------------------------------------------------------------------------

@dataclass
class WorkerCapability:
    """Kemampuan hardware dan software yang diumumkan worker."""
    cpu_cores: int
    ram_gb: float
    has_gpu: bool
    gpu_name: Optional[str]          # e.g. "NVIDIA RTX 3080"
    gpu_vram_gb: Optional[float]
    supported_frameworks: List[str]  # e.g. ["onnx", "pytorch", "tensorflow"]
    supported_models: List[str]      # List of model_ids yang bisa dijalankan
    max_concurrent_jobs: int
    bandwidth_mbps: Optional[float]
    os_info: str

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "WorkerCapability":
        return WorkerCapability(**d)

    @staticmethod
    def detect_local() -> "WorkerCapability":
        """Auto-detect capability dari mesin saat ini."""
        import psutil
        ram = psutil.virtual_memory().total / (1024 ** 3)
        cpu = psutil.cpu_count(logical=False) or 1
        has_gpu = False
        gpu_name = None
        gpu_vram = None
        try:
            import subprocess
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total",
                 "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0 and r.stdout.strip():
                parts = r.stdout.strip().split(",")
                has_gpu = True
                gpu_name = parts[0].strip()
                gpu_vram = float(parts[1].strip().split()[0]) / 1024
        except Exception:
            pass
        return WorkerCapability(
            cpu_cores=cpu,
            ram_gb=round(ram, 1),
            has_gpu=has_gpu,
            gpu_name=gpu_name,
            gpu_vram_gb=gpu_vram,
            supported_frameworks=["onnx"],
            supported_models=[],
            max_concurrent_jobs=2 if has_gpu else 1,
            bandwidth_mbps=None,
            os_info=platform.system() + " " + platform.release(),
        )


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

@dataclass
class AIWorker:
    worker_id: str
    address: str              # ARC address (untuk menerima pembayaran)
    public_key: str           # Public key untuk verifikasi
    endpoint: str             # "host:port" untuk menerima job requests
    capability: WorkerCapability
    price_per_job: int        # Minimum price per job (base ARC units)
    registered_at: int
    last_seen: int
    status: WorkerStatus = WorkerStatus.ACTIVE
    reputation_score: float = 100.0   # 0-100
    completed_jobs: int = 0
    failed_jobs: int = 0
    total_earned: int = 0     # Total ARC earned (base units)
    current_job: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["capability"] = self.capability.to_dict()
        return d

    @staticmethod
    def from_dict(d: dict) -> "AIWorker":
        d = dict(d)
        d["status"] = WorkerStatus(d["status"])
        d["capability"] = WorkerCapability.from_dict(d["capability"])
        return AIWorker(**d)

    def is_available(self) -> bool:
        return (
            self.status == WorkerStatus.ACTIVE
            and self.current_job is None
        )

    def can_handle(self, compute_req: dict) -> bool:
        """Check apakah worker bisa handle job dengan requirement ini."""
        cap = self.capability
        if compute_req.get("gpu") and not cap.has_gpu:
            return False
        min_ram = compute_req.get("min_ram_gb", 0)
        if cap.ram_gb < min_ram:
            return False
        framework = compute_req.get("framework")
        if framework and framework not in cap.supported_frameworks:
            return False
        return True

    def update_reputation(self, success: bool) -> None:
        """Update reputation score setelah job selesai."""
        if success:
            self.completed_jobs += 1
            # Naik perlahan, max 100
            self.reputation_score = min(
                100.0,
                self.reputation_score + (100 - self.reputation_score) * 0.05
            )
        else:
            self.failed_jobs += 1
            # Turun lebih cepat
            self.reputation_score = max(0.0, self.reputation_score * 0.85)


# ---------------------------------------------------------------------------
# Worker Registry Store
# ---------------------------------------------------------------------------

class WorkerStore:
    def __init__(self, data_dir: str) -> None:
        self.path = os.path.join(data_dir, "ai_workers.json")
        os.makedirs(data_dir, exist_ok=True)
        self._workers: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._workers = json.load(f)
            except Exception:
                self._workers = {}

    def _save(self) -> None:
        import tempfile
        dir_ = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._workers, f, indent=2)
        except Exception:
            os.unlink(tmp)
            raise
        os.replace(tmp, self.path)

    def put(self, worker: AIWorker) -> None:
        self._workers[worker.worker_id] = worker.to_dict()
        self._save()

    def get(self, worker_id: str) -> Optional[AIWorker]:
        d = self._workers.get(worker_id)
        return AIWorker.from_dict(d) if d else None

    def get_by_address(self, address: str) -> Optional[AIWorker]:
        for d in self._workers.values():
            if d.get("address") == address:
                return AIWorker.from_dict(d)
        return None

    def all(self) -> List[AIWorker]:
        return [AIWorker.from_dict(d) for d in self._workers.values()]

    def active(self) -> List[AIWorker]:
        return [w for w in self.all() if w.status == WorkerStatus.ACTIVE]

    def available(self) -> List[AIWorker]:
        return [w for w in self.active() if w.is_available()]


# ---------------------------------------------------------------------------
# Worker Manager
# ---------------------------------------------------------------------------

class WorkerManager:
    # Worker dianggap offline jika tidak heartbeat dalam 5 menit
    HEARTBEAT_TIMEOUT = 300

    def __init__(self, store: WorkerStore) -> None:
        self.store = store

    def register(
        self,
        address: str,
        public_key: str,
        endpoint: str,
        capability: WorkerCapability,
        price_per_job: int,
    ) -> AIWorker:
        """Register worker baru atau update yang sudah ada."""
        existing = self.store.get_by_address(address)
        if existing:
            # Update existing
            existing.endpoint = endpoint
            existing.capability = capability
            existing.price_per_job = price_per_job
            existing.last_seen = int(time.time())
            existing.status = WorkerStatus.ACTIVE
            self.store.put(existing)
            return existing

        worker = AIWorker(
            worker_id=str(uuid.uuid4()),
            address=address,
            public_key=public_key,
            endpoint=endpoint,
            capability=capability,
            price_per_job=price_per_job,
            registered_at=int(time.time()),
            last_seen=int(time.time()),
        )
        self.store.put(worker)
        return worker

    def heartbeat(self, worker_id: str) -> AIWorker:
        """Worker mengirim heartbeat untuk menandakan masih aktif."""
        worker = self._get_or_raise(worker_id)
        worker.last_seen = int(time.time())
        if worker.status == WorkerStatus.INACTIVE:
            worker.status = WorkerStatus.ACTIVE
        self.store.put(worker)
        return worker

    def deactivate(self, worker_id: str) -> AIWorker:
        """Worker menonaktifkan diri."""
        worker = self._get_or_raise(worker_id)
        worker.status = WorkerStatus.INACTIVE
        self.store.put(worker)
        return worker

    def assign_job(self, worker_id: str, job_id: str) -> AIWorker:
        """Tandai worker sedang mengerjakan job."""
        worker = self._get_or_raise(worker_id)
        if not worker.is_available():
            raise ValueError(f"Worker {worker_id} is not available")
        worker.status = WorkerStatus.BUSY
        worker.current_job = job_id
        self.store.put(worker)
        return worker

    def complete_job(self, worker_id: str, success: bool, earned: int = 0) -> AIWorker:
        """Job selesai — update stats dan reputation."""
        worker = self._get_or_raise(worker_id)
        worker.current_job = None
        worker.status = WorkerStatus.ACTIVE
        worker.update_reputation(success)
        if success and earned > 0:
            worker.total_earned += earned
        self.store.put(worker)
        return worker

    def find_suitable_workers(
        self,
        compute_req: dict,
        max_price: int,
        min_reputation: float = 0.0,
    ) -> List[AIWorker]:
        """Cari worker yang cocok untuk job ini."""
        candidates = []
        for w in self.store.available():
            if not w.can_handle(compute_req):
                continue
            if w.price_per_job > max_price:
                continue
            if w.reputation_score < min_reputation:
                continue
            # Tandai offline jika heartbeat sudah lama
            if int(time.time()) - w.last_seen > self.HEARTBEAT_TIMEOUT:
                w.status = WorkerStatus.INACTIVE
                self.store.put(w)
                continue
            candidates.append(w)
        # Sort by reputation desc, price asc
        candidates.sort(key=lambda w: (-w.reputation_score, w.price_per_job))
        return candidates

    def _get_or_raise(self, worker_id: str) -> AIWorker:
        w = self.store.get(worker_id)
        if w is None:
            raise ValueError(f"Worker {worker_id} not found")
        return w
