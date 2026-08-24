"""
ARCHE AI Model Registry — Phase 4

Blockchain hanya menyimpan metadata, ownership, hash, version, reference.
Model besar TIDAK disimpan di blockchain.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class AIModel:
    model_id: str
    name: str
    owner: str              # ARC address
    model_hash: str         # SHA256 hash of model file
    version: str            # e.g. "1.0.0"
    framework: str          # "onnx", "pytorch", "tensorflow", "gguf"
    architecture: str       # e.g. "transformer", "cnn", "resnet"
    task: str               # e.g. "text-generation", "classification", "embedding"
    requirements: dict      # {"min_ram_gb": 4, "gpu": false}
    metadata: dict          # Description, tags, license, etc.
    storage_reference: str  # IPFS hash / URL / storage location (off-chain)
    price_per_call: int     # ARC base units per inference call (0 = free)
    registered_at: int
    updated_at: int
    is_active: bool = True
    total_calls: int = 0
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "AIModel":
        return AIModel(**d)


class ModelStore:
    def __init__(self, data_dir: str) -> None:
        self.path = os.path.join(data_dir, "ai_models.json")
        os.makedirs(data_dir, exist_ok=True)
        self._models: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._models = json.load(f)
            except Exception:
                self._models = {}

    def _save(self) -> None:
        import tempfile
        dir_ = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._models, f, indent=2)
        except Exception:
            os.unlink(tmp)
            raise
        os.replace(tmp, self.path)

    def put(self, model: AIModel) -> None:
        self._models[model.model_id] = model.to_dict()
        self._save()

    def get(self, model_id: str) -> Optional[AIModel]:
        d = self._models.get(model_id)
        return AIModel.from_dict(d) if d else None

    def all(self) -> List[AIModel]:
        return [AIModel.from_dict(d) for d in self._models.values()]

    def active(self) -> List[AIModel]:
        return [m for m in self.all() if m.is_active]

    def by_owner(self, address: str) -> List[AIModel]:
        return [m for m in self.all() if m.owner == address]

    def search(
        self,
        task: Optional[str] = None,
        framework: Optional[str] = None,
        tags: Optional[List[str]] = None,
        max_price: Optional[int] = None,
        gpu_required: Optional[bool] = None,
    ) -> List[AIModel]:
        results = self.active()
        if task:
            results = [m for m in results if m.task == task]
        if framework:
            results = [m for m in results if m.framework == framework]
        if tags:
            results = [m for m in results if any(t in m.tags for t in tags)]
        if max_price is not None:
            results = [m for m in results if m.price_per_call <= max_price]
        if gpu_required is not None:
            results = [m for m in results
                       if m.requirements.get("gpu", False) == gpu_required]
        return results


class ModelRegistry:
    def __init__(self, store: ModelStore) -> None:
        self.store = store

    def register(
        self,
        owner: str,
        name: str,
        model_hash: str,
        version: str,
        framework: str,
        architecture: str,
        task: str,
        requirements: dict,
        storage_reference: str,
        price_per_call: int = 0,
        metadata: Optional[dict] = None,
        tags: Optional[List[str]] = None,
    ) -> AIModel:
        if not model_hash or len(model_hash) != 64:
            raise ValueError("model_hash must be 64-char hex SHA256")
        if price_per_call < 0:
            raise ValueError("price_per_call cannot be negative")

        model = AIModel(
            model_id=str(uuid.uuid4()),
            name=name,
            owner=owner,
            model_hash=model_hash,
            version=version,
            framework=framework,
            architecture=architecture,
            task=task,
            requirements=requirements or {},
            metadata=metadata or {},
            storage_reference=storage_reference,
            price_per_call=price_per_call,
            registered_at=int(time.time()),
            updated_at=int(time.time()),
            tags=tags or [],
        )
        self.store.put(model)
        return model

    def update(
        self,
        model_id: str,
        owner: str,
        **kwargs,
    ) -> AIModel:
        model = self._get_or_raise(model_id)
        if model.owner != owner:
            raise ValueError("Only model owner can update it")
        allowed = {"name", "version", "storage_reference", "price_per_call",
                   "metadata", "tags", "is_active", "requirements"}
        for k, v in kwargs.items():
            if k in allowed:
                setattr(model, k, v)
        model.updated_at = int(time.time())
        self.store.put(model)
        return model

    def deactivate(self, model_id: str, owner: str) -> AIModel:
        model = self._get_or_raise(model_id)
        if model.owner != owner:
            raise ValueError("Only model owner can deactivate it")
        model.is_active = False
        model.updated_at = int(time.time())
        self.store.put(model)
        return model

    def increment_calls(self, model_id: str) -> None:
        model = self._get_or_raise(model_id)
        model.total_calls += 1
        model.updated_at = int(time.time())
        self.store.put(model)

    def _get_or_raise(self, model_id: str) -> AIModel:
        m = self.store.get(model_id)
        if m is None:
            raise ValueError(f"Model {model_id} not found")
        return m
