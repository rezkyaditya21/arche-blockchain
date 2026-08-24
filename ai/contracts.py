"""
ARCHE AI-Native Smart Contracts — Phase 12

Bukan EVM clone. Ini adalah programmable transaction layer
yang bisa trigger AI computation dan execute berdasarkan hasilnya.

Prinsip:
- Contract tidak mengeksekusi arbitrary code di blockchain node
- Contract hanya mendefinisikan: trigger, AI request, condition, action
- AI result HARUS melewati verification policy sebelum contract execute
- Contract state disimpan off-chain (hash on-chain)

Contoh use case:
1. AI Oracle         → contract trigger jika AI predict harga > X
2. Autonomous DAO    → AI analyze proposal → vote otomatis
3. AI Pricing        → harga dinamis berdasarkan AI prediction
4. Risk Analysis     → transfer hanya jika AI approve risk level
5. Agent Payment     → agent A bayar agent B setelah AI verify task selesai

Flow:
    Deploy Contract → ACTIVE
    Trigger Event   → EVALUATING
    AI Job Created  → WAITING_AI
    AI Result       → VERIFIED
    Condition Check → EXECUTING / REJECTED
    Action Done     → COMPLETED / FAILED
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Contract Status
# ---------------------------------------------------------------------------

class ContractStatus(str, Enum):
    ACTIVE      = "ACTIVE"
    EVALUATING  = "EVALUATING"
    WAITING_AI  = "WAITING_AI"
    EXECUTING   = "EXECUTING"
    COMPLETED   = "COMPLETED"
    FAILED      = "FAILED"
    EXPIRED     = "EXPIRED"
    PAUSED      = "PAUSED"


class ActionType(str, Enum):
    TRANSFER_ARC    = "TRANSFER_ARC"    # Transfer ARC ke address
    RELEASE_ESCROW  = "RELEASE_ESCROW"  # Release escrow payment
    REFUND_ESCROW   = "REFUND_ESCROW"   # Refund escrow ke requester
    EMIT_EVENT      = "EMIT_EVENT"      # Emit event (log only, no state change)
    TRIGGER_JOB     = "TRIGGER_JOB"     # Trigger AI job lain


# ---------------------------------------------------------------------------
# Contract Definition
# ---------------------------------------------------------------------------

@dataclass
class ContractCondition:
    """
    Kondisi yang harus dipenuhi dari AI result untuk contract execute.

    field    : field dari AI result yang dicek (e.g. "prediction", "score")
    operator : "eq", "gt", "lt", "gte", "lte", "contains", "not_null"
    value    : nilai pembanding
    """
    field: str
    operator: str
    value: Any

    VALID_OPERATORS = {"eq", "gt", "lt", "gte", "lte", "contains", "not_null"}

    def evaluate(self, ai_result: dict) -> bool:
        """Evaluate condition against AI result."""
        val = ai_result.get(self.field)
        if val is None and self.operator != "not_null":
            return False
        try:
            if self.operator == "eq":
                return val == self.value
            elif self.operator == "gt":
                return float(val) > float(self.value)
            elif self.operator == "lt":
                return float(val) < float(self.value)
            elif self.operator == "gte":
                return float(val) >= float(self.value)
            elif self.operator == "lte":
                return float(val) <= float(self.value)
            elif self.operator == "contains":
                return str(self.value) in str(val)
            elif self.operator == "not_null":
                return val is not None
            else:
                return False
        except (TypeError, ValueError):
            return False

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ContractCondition":
        return ContractCondition(**d)


@dataclass
class ContractAction:
    """
    Aksi yang dieksekusi jika kondisi terpenuhi.
    """
    action_type: ActionType
    params: dict    # Depends on action_type

    def to_dict(self) -> dict:
        return {"action_type": self.action_type.value, "params": self.params}

    @staticmethod
    def from_dict(d: dict) -> "ContractAction":
        return ContractAction(
            action_type=ActionType(d["action_type"]),
            params=d["params"],
        )


@dataclass
class AIContract:
    contract_id: str
    name: str
    owner: str              # ARC address
    model_id: str           # Model yang digunakan untuk evaluasi
    trigger_description: str  # Human-readable trigger description
    conditions: List[ContractCondition]   # ALL conditions must be true
    on_success: List[ContractAction]      # Actions if all conditions met
    on_failure: List[ContractAction]      # Actions if conditions not met
    verification_level: int  # 1=hash, 2=redundant, 3=challenge
    max_executions: int      # 0 = unlimited
    execution_count: int
    created_at: int
    expires_at: Optional[int]
    status: ContractStatus
    last_triggered_at: Optional[int] = None
    last_job_id: Optional[str] = None
    last_result: Optional[dict] = None
    last_executed_at: Optional[int] = None
    error_message: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["conditions"] = [c.to_dict() for c in self.conditions]
        d["on_success"] = [a.to_dict() for a in self.on_success]
        d["on_failure"] = [a.to_dict() for a in self.on_failure]
        return d

    @staticmethod
    def from_dict(d: dict) -> "AIContract":
        d = dict(d)
        d["status"] = ContractStatus(d["status"])
        d["conditions"] = [ContractCondition.from_dict(c) for c in d["conditions"]]
        d["on_success"] = [ContractAction.from_dict(a) for a in d["on_success"]]
        d["on_failure"] = [ContractAction.from_dict(a) for a in d["on_failure"]]
        return AIContract(**d)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return int(time.time()) > self.expires_at

    def can_execute(self) -> bool:
        if self.status not in (ContractStatus.ACTIVE, ContractStatus.EVALUATING):
            return False
        if self.is_expired():
            return False
        if self.max_executions > 0 and self.execution_count >= self.max_executions:
            return False
        return True

    def evaluate_conditions(self, ai_result: dict) -> bool:
        """All conditions must be True for contract to execute."""
        if not self.conditions:
            return True
        return all(c.evaluate(ai_result) for c in self.conditions)

    def compute_hash(self) -> str:
        """Hash of contract definition — for tamper detection."""
        data = json.dumps({
            "contract_id": self.contract_id,
            "model_id": self.model_id,
            "conditions": [c.to_dict() for c in self.conditions],
            "on_success": [a.to_dict() for a in self.on_success],
            "on_failure": [a.to_dict() for a in self.on_failure],
        }, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Contract Execution Result
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    execution_id: str
    contract_id: str
    job_id: Optional[str]
    conditions_met: bool
    actions_executed: List[dict]
    executed_at: int
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Contract Store
# ---------------------------------------------------------------------------

class ContractStore:
    def __init__(self, data_dir: str) -> None:
        self.path = os.path.join(data_dir, "ai_contracts.json")
        os.makedirs(data_dir, exist_ok=True)
        self._contracts: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._contracts = json.load(f)
            except Exception:
                self._contracts = {}

    def _save(self) -> None:
        import tempfile
        dir_ = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._contracts, f, indent=2)
        except Exception:
            os.unlink(tmp)
            raise
        os.replace(tmp, self.path)

    def put(self, contract: AIContract) -> None:
        self._contracts[contract.contract_id] = contract.to_dict()
        self._save()

    def get(self, contract_id: str) -> Optional[AIContract]:
        d = self._contracts.get(contract_id)
        return AIContract.from_dict(d) if d else None

    def all(self) -> List[AIContract]:
        return [AIContract.from_dict(d) for d in self._contracts.values()]

    def active(self) -> List[AIContract]:
        return [c for c in self.all() if c.status == ContractStatus.ACTIVE]

    def by_owner(self, owner: str) -> List[AIContract]:
        return [c for c in self.all() if c.owner == owner]


# ---------------------------------------------------------------------------
# Contract Engine
# ---------------------------------------------------------------------------

class ContractEngine:
    """
    Evaluasi dan eksekusi AI contracts.

    Security notes:
    - AI result TIDAK langsung dipercaya — harus melewati verification
    - Actions yang melibatkan transfer ARC tidak dieksekusi langsung di sini
      Engine hanya membuat execution record + instruction
      Actual ARCHE transaction dibuat oleh wallet/node secara terpisah
    - Contract tidak bisa mengeksekusi arbitrary code
    - Semua actions terbatas pada ActionType yang sudah didefinisikan
    """

    def __init__(self, store: ContractStore) -> None:
        self.store = store

    def deploy(
        self,
        owner: str,
        name: str,
        model_id: str,
        trigger_description: str,
        conditions: List[ContractCondition],
        on_success: List[ContractAction],
        on_failure: Optional[List[ContractAction]] = None,
        verification_level: int = 2,
        max_executions: int = 0,
        expires_at: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> AIContract:
        """Deploy a new AI contract."""
        if not conditions:
            raise ValueError("Contract must have at least one condition")
        if not on_success:
            raise ValueError("Contract must have at least one success action")
        if verification_level not in (1, 2, 3, 4):
            raise ValueError("verification_level must be 1-4")

        contract = AIContract(
            contract_id=str(uuid.uuid4()),
            name=name,
            owner=owner,
            model_id=model_id,
            trigger_description=trigger_description,
            conditions=conditions,
            on_success=on_success,
            on_failure=on_failure or [],
            verification_level=verification_level,
            max_executions=max_executions,
            execution_count=0,
            created_at=int(time.time()),
            expires_at=expires_at,
            status=ContractStatus.ACTIVE,
            metadata=metadata or {},
        )
        self.store.put(contract)
        return contract

    def trigger(self, contract_id: str, job_id: str) -> AIContract:
        """Mark contract as waiting for AI result."""
        contract = self._get_or_raise(contract_id)
        if not contract.can_execute():
            raise ValueError(f"Contract {contract_id} cannot be triggered")
        contract.status = ContractStatus.WAITING_AI
        contract.last_triggered_at = int(time.time())
        contract.last_job_id = job_id
        self.store.put(contract)
        return contract

    def evaluate(
        self,
        contract_id: str,
        ai_result: dict,
        verified: bool = False,
    ) -> ExecutionResult:
        """
        Evaluate AI result against contract conditions.

        Parameters
        ----------
        contract_id : contract to evaluate
        ai_result   : result from AI job
        verified    : whether result passed verification policy
                      If False, contract will NOT execute (security)
        """
        contract = self._get_or_raise(contract_id)

        if not verified:
            contract.status = ContractStatus.FAILED
            contract.error_message = "AI result not verified — contract refused to execute"
            self.store.put(contract)
            return ExecutionResult(
                execution_id=str(uuid.uuid4()),
                contract_id=contract_id,
                job_id=contract.last_job_id,
                conditions_met=False,
                actions_executed=[],
                executed_at=int(time.time()),
                error="AI result not verified",
            )

        contract.last_result = ai_result
        conditions_met = contract.evaluate_conditions(ai_result)
        actions_to_run = contract.on_success if conditions_met else contract.on_failure

        executed_actions = []
        error = None

        try:
            contract.status = ContractStatus.EXECUTING
            self.store.put(contract)

            for action in actions_to_run:
                result = self._execute_action(action, contract, ai_result)
                executed_actions.append({
                    "action_type": action.action_type.value,
                    "params": action.params,
                    "result": result,
                })

            contract.execution_count += 1
            contract.last_executed_at = int(time.time())

            # Check if max executions reached
            if contract.max_executions > 0 and contract.execution_count >= contract.max_executions:
                contract.status = ContractStatus.COMPLETED
            else:
                contract.status = ContractStatus.ACTIVE  # Ready for next trigger

        except Exception as e:
            error = str(e)
            contract.status = ContractStatus.FAILED
            contract.error_message = error

        self.store.put(contract)

        return ExecutionResult(
            execution_id=str(uuid.uuid4()),
            contract_id=contract_id,
            job_id=contract.last_job_id,
            conditions_met=conditions_met,
            actions_executed=executed_actions,
            executed_at=int(time.time()),
            error=error,
        )

    def _execute_action(
        self,
        action: ContractAction,
        contract: AIContract,
        ai_result: dict,
    ) -> dict:
        """
        Execute a single action.

        NOTE: TRANSFER_ARC and RELEASE_ESCROW actions return instructions only.
        Actual blockchain transactions must be created by the node/wallet separately.
        This prevents arbitrary code execution on the blockchain node.
        """
        if action.action_type == ActionType.EMIT_EVENT:
            return {
                "status": "emitted",
                "event": action.params.get("event_name", "contract_event"),
                "data": action.params,
                "timestamp": int(time.time()),
            }

        elif action.action_type == ActionType.TRANSFER_ARC:
            # Return instruction — actual transfer done by node
            return {
                "status": "instruction_created",
                "instruction": "TRANSFER_ARC",
                "from": contract.owner,
                "to": action.params.get("to"),
                "amount": action.params.get("amount"),
                "note": "Create ARCHE transaction to execute this transfer",
            }

        elif action.action_type == ActionType.RELEASE_ESCROW:
            return {
                "status": "instruction_created",
                "instruction": "RELEASE_ESCROW",
                "job_id": action.params.get("job_id"),
                "note": "Call /ai/payments/{job_id}/release to execute",
            }

        elif action.action_type == ActionType.REFUND_ESCROW:
            return {
                "status": "instruction_created",
                "instruction": "REFUND_ESCROW",
                "job_id": action.params.get("job_id"),
                "note": "Call /ai/payments/{job_id}/refund to execute",
            }

        elif action.action_type == ActionType.TRIGGER_JOB:
            return {
                "status": "instruction_created",
                "instruction": "TRIGGER_JOB",
                "model_id": action.params.get("model_id"),
                "note": "Create new AI job with this model",
            }

        else:
            raise ValueError(f"Unknown action type: {action.action_type}")

    def pause(self, contract_id: str, owner: str) -> AIContract:
        contract = self._get_or_raise(contract_id)
        if contract.owner != owner:
            raise ValueError("Only owner can pause contract")
        contract.status = ContractStatus.PAUSED
        self.store.put(contract)
        return contract

    def resume(self, contract_id: str, owner: str) -> AIContract:
        contract = self._get_or_raise(contract_id)
        if contract.owner != owner:
            raise ValueError("Only owner can resume contract")
        if contract.status != ContractStatus.PAUSED:
            raise ValueError("Contract is not paused")
        contract.status = ContractStatus.ACTIVE
        self.store.put(contract)
        return contract

    def expire_contracts(self) -> List[str]:
        """Mark expired contracts."""
        expired = []
        for c in self.store.active():
            if c.is_expired():
                c.status = ContractStatus.EXPIRED
                self.store.put(c)
                expired.append(c.contract_id)
        return expired

    def _get_or_raise(self, contract_id: str) -> AIContract:
        c = self.store.get(contract_id)
        if c is None:
            raise ValueError(f"Contract {contract_id} not found")
        return c
