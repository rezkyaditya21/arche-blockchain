"""
ARCHE AI Agent Registry — Phase 6

Agent adalah participant otonom yang bisa:
- Punya ARC wallet sendiri
- Bayar AI Job
- Terima payment
- Berinteraksi dengan agent lain

Blockchain hanya menyimpan: agent_id, public_key, owner, metadata hash.
Memory dan state agent disimpan off-chain.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional


class AgentStatus(str, Enum):
    ACTIVE   = "ACTIVE"
    INACTIVE = "INACTIVE"
    BANNED   = "BANNED"


@dataclass
class AgentCapability:
    """Kemampuan yang diumumkan agent."""
    can_request_jobs: bool = True
    can_execute_jobs: bool = False
    can_verify_jobs: bool = False
    supported_tasks: List[str] = field(default_factory=list)
    max_concurrent_requests: int = 1
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "AgentCapability":
        return AgentCapability(**d)


@dataclass
class AgentMemoryRef:
    """Reference ke memory agent (disimpan off-chain)."""
    memory_hash: str    # SHA256 hash of memory snapshot
    timestamp: int
    version: int
    storage_ref: str    # IPFS / URL / path

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "AgentMemoryRef":
        return AgentMemoryRef(**d)


@dataclass
class AIAgent:
    agent_id: str
    name: str
    owner: str              # ARC address of human owner
    public_key: str         # Agent's own public key
    address: str            # Agent's own ARC address (untuk bayar/terima)
    capabilities: AgentCapability
    status: AgentStatus
    registered_at: int
    last_active: int
    reputation_score: float = 100.0
    total_jobs_requested: int = 0
    total_jobs_completed: int = 0
    total_spent: int = 0        # Total ARC yang dikeluarkan agent
    total_earned: int = 0       # Total ARC yang diterima agent
    memory_ref: Optional[AgentMemoryRef] = None
    metadata: dict = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["capabilities"] = self.capabilities.to_dict()
        if self.memory_ref:
            d["memory_ref"] = self.memory_ref.to_dict()
        return d

    @staticmethod
    def from_dict(d: dict) -> "AIAgent":
        d = dict(d)
        d["status"] = AgentStatus(d["status"])
        d["capabilities"] = AgentCapability.from_dict(d["capabilities"])
        if d.get("memory_ref"):
            d["memory_ref"] = AgentMemoryRef.from_dict(d["memory_ref"])
        return AIAgent(**d)


class AgentStore:
    def __init__(self, data_dir: str) -> None:
        self.path = os.path.join(data_dir, "ai_agents.json")
        os.makedirs(data_dir, exist_ok=True)
        self._agents: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._agents = json.load(f)
            except Exception:
                self._agents = {}

    def _save(self) -> None:
        import tempfile
        dir_ = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._agents, f, indent=2)
        except Exception:
            os.unlink(tmp)
            raise
        os.replace(tmp, self.path)

    def put(self, agent: AIAgent) -> None:
        self._agents[agent.agent_id] = agent.to_dict()
        self._save()

    def get(self, agent_id: str) -> Optional[AIAgent]:
        d = self._agents.get(agent_id)
        return AIAgent.from_dict(d) if d else None

    def get_by_address(self, address: str) -> Optional[AIAgent]:
        for d in self._agents.values():
            if d.get("address") == address:
                return AIAgent.from_dict(d)
        return None

    def by_owner(self, owner: str) -> List[AIAgent]:
        return [AIAgent.from_dict(d) for d in self._agents.values()
                if d.get("owner") == owner]

    def all(self) -> List[AIAgent]:
        return [AIAgent.from_dict(d) for d in self._agents.values()]

    def active(self) -> List[AIAgent]:
        return [a for a in self.all() if a.status == AgentStatus.ACTIVE]


class AgentRegistry:
    def __init__(self, store: AgentStore) -> None:
        self.store = store

    def register(
        self,
        owner: str,
        name: str,
        public_key: str,
        address: str,
        capabilities: Optional[AgentCapability] = None,
        metadata: Optional[dict] = None,
        tags: Optional[List[str]] = None,
    ) -> AIAgent:
        """Register AI agent baru."""
        # Satu address hanya bisa punya satu agent
        existing = self.store.get_by_address(address)
        if existing:
            raise ValueError(f"Address {address} already has a registered agent")

        agent = AIAgent(
            agent_id=str(uuid.uuid4()),
            name=name,
            owner=owner,
            public_key=public_key,
            address=address,
            capabilities=capabilities or AgentCapability(),
            status=AgentStatus.ACTIVE,
            registered_at=int(time.time()),
            last_active=int(time.time()),
            metadata=metadata or {},
            tags=tags or [],
        )
        self.store.put(agent)
        return agent

    def update_memory(
        self,
        agent_id: str,
        owner: str,
        memory_hash: str,
        storage_ref: str,
    ) -> AIAgent:
        """Update memory reference agent (off-chain data, on-chain hash)."""
        agent = self._get_or_raise(agent_id)
        if agent.owner != owner:
            raise ValueError("Only owner can update agent memory")
        if not memory_hash or len(memory_hash) != 64:
            raise ValueError("memory_hash must be 64-char hex SHA256")

        current_version = (agent.memory_ref.version + 1) if agent.memory_ref else 1
        agent.memory_ref = AgentMemoryRef(
            memory_hash=memory_hash,
            timestamp=int(time.time()),
            version=current_version,
            storage_ref=storage_ref,
        )
        agent.last_active = int(time.time())
        self.store.put(agent)
        return agent

    def record_job_request(self, agent_id: str, spent: int = 0) -> AIAgent:
        agent = self._get_or_raise(agent_id)
        agent.total_jobs_requested += 1
        agent.total_spent += spent
        agent.last_active = int(time.time())
        self.store.put(agent)
        return agent

    def record_job_completed(self, agent_id: str, earned: int = 0) -> AIAgent:
        agent = self._get_or_raise(agent_id)
        agent.total_jobs_completed += 1
        agent.total_earned += earned
        agent.last_active = int(time.time())
        self.store.put(agent)
        return agent

    def deactivate(self, agent_id: str, owner: str) -> AIAgent:
        agent = self._get_or_raise(agent_id)
        if agent.owner != owner:
            raise ValueError("Only owner can deactivate agent")
        agent.status = AgentStatus.INACTIVE
        self.store.put(agent)
        return agent

    def _get_or_raise(self, agent_id: str) -> AIAgent:
        a = self.store.get(agent_id)
        if a is None:
            raise ValueError(f"Agent {agent_id} not found")
        return a
