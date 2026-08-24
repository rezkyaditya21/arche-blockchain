"""
ARCHE AI Marketplace — Phase 5

Central hub untuk user mencari model dan worker.
Menggabungkan Model Registry + Worker Registry + Job System.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from dataclasses import dataclass

from ai.registry import AIModel, ModelRegistry
from ai.worker import AIWorker, WorkerManager
from ai.job import AIJob, JobManager


@dataclass
class MarketplaceListing:
    """Combined listing: model + compatible workers."""
    model: AIModel
    available_workers: List[AIWorker]
    min_price: int      # Cheapest worker price
    max_price: int      # Most expensive worker price
    avg_reputation: float


@dataclass
class JobQuote:
    """Quote dari satu worker untuk satu job."""
    worker: AIWorker
    model: AIModel
    price: int
    estimated_seconds: Optional[int]
    reputation_score: float


class AIMarketplace:
    def __init__(
        self,
        model_registry: ModelRegistry,
        worker_manager: WorkerManager,
        job_manager: JobManager,
    ) -> None:
        self.models = model_registry
        self.workers = worker_manager
        self.jobs = job_manager

    def search_models(
        self,
        task: Optional[str] = None,
        framework: Optional[str] = None,
        tags: Optional[List[str]] = None,
        max_price: Optional[int] = None,
        gpu_required: Optional[bool] = None,
    ) -> List[AIModel]:
        """Cari model berdasarkan filter."""
        return self.models.store.search(
            task=task,
            framework=framework,
            tags=tags,
            max_price=max_price,
            gpu_required=gpu_required,
        )

    def search_workers(
        self,
        compute_req: dict,
        max_price: int,
        min_reputation: float = 0.0,
    ) -> List[AIWorker]:
        """Cari worker yang cocok untuk requirement tertentu."""
        return self.workers.find_suitable_workers(
            compute_req=compute_req,
            max_price=max_price,
            min_reputation=min_reputation,
        )

    def get_quotes(
        self,
        model_id: str,
        max_price: int,
        min_reputation: float = 0.0,
    ) -> List[JobQuote]:
        """
        Dapatkan daftar quote dari semua worker yang bisa handle model ini.
        Diurutkan: reputation desc, price asc.
        """
        model = self.models.store.get(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")

        workers = self.workers.find_suitable_workers(
            compute_req=model.requirements,
            max_price=max_price,
            min_reputation=min_reputation,
        )

        quotes = []
        for w in workers:
            # Total price = worker fee + model call fee
            total_price = w.price_per_job + model.price_per_call
            if total_price > max_price:
                continue
            quotes.append(JobQuote(
                worker=w,
                model=model,
                price=total_price,
                estimated_seconds=None,  # bisa diisi dari history nanti
                reputation_score=w.reputation_score,
            ))

        quotes.sort(key=lambda q: (-q.reputation_score, q.price))
        return quotes

    def get_listings(self) -> List[MarketplaceListing]:
        """
        Semua model aktif beserta worker yang available.
        """
        listings = []
        for model in self.models.store.active():
            workers = self.workers.find_suitable_workers(
                compute_req=model.requirements,
                max_price=999_999_999,
            )
            if not workers:
                continue
            prices = [w.price_per_job for w in workers]
            avg_rep = sum(w.reputation_score for w in workers) / len(workers)
            listings.append(MarketplaceListing(
                model=model,
                available_workers=workers,
                min_price=min(prices),
                max_price=max(prices),
                avg_reputation=round(avg_rep, 1),
            ))
        return listings

    def submit_job(
        self,
        requester: str,
        model_id: str,
        input_hash: str,
        input_reference: str,
        max_price: int,
        deadline: int,
        preferred_worker: Optional[str] = None,
    ) -> AIJob:
        """
        User submit job ke marketplace.
        Otomatis pilih worker terbaik jika tidak ada preferensi.
        """
        model = self.models.store.get(model_id)
        if not model:
            raise ValueError(f"Model {model_id} not found")
        if not model.is_active:
            raise ValueError(f"Model {model_id} is not active")

        # Buat job
        job = self.jobs.create_job(
            requester=requester,
            model_id=model_id,
            input_hash=input_hash,
            input_reference=input_reference,
            compute_requirement=model.requirements,
            max_price=max_price,
            deadline=deadline,
        )

        # Auto-assign worker jika ada preferred_worker atau best worker
        worker = None
        if preferred_worker:
            w = self.workers.store.get_by_address(preferred_worker)
            if w and w.is_available() and w.can_handle(model.requirements):
                worker = w
        if not worker:
            candidates = self.workers.find_suitable_workers(
                compute_req=model.requirements,
                max_price=max_price,
            )
            if candidates:
                worker = candidates[0]

        if worker:
            agreed_price = min(worker.price_per_job + model.price_per_call, max_price)
            self.jobs.assign_job(job.job_id, worker.address, agreed_price)
            self.workers.assign_job(worker.worker_id, job.job_id)

        return self.jobs.store.get(job.job_id)  # type: ignore

    def get_stats(self) -> dict:
        """Statistik marketplace."""
        all_jobs = self.jobs.store.all()
        all_workers = self.workers.store.all()
        all_models = self.models.store.all()
        from ai.job import JobStatus
        from ai.worker import WorkerStatus
        return {
            "total_models": len(all_models),
            "active_models": len([m for m in all_models if m.is_active]),
            "total_workers": len(all_workers),
            "active_workers": len([w for w in all_workers
                                   if w.status == WorkerStatus.ACTIVE]),
            "total_jobs": len(all_jobs),
            "pending_jobs": len([j for j in all_jobs
                                 if j.status == JobStatus.PENDING]),
            "completed_jobs": len([j for j in all_jobs
                                   if j.status == JobStatus.COMPLETED]),
            "failed_jobs": len([j for j in all_jobs
                                if j.status == JobStatus.FAILED]),
        }
