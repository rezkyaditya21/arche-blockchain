"""
ARCHE AI Smart Contracts — Test Suite (Phase 12)
"""
import sys, os, time, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from ai.contracts import (
    ContractEngine, ContractStore, ContractStatus,
    ContractCondition, ContractAction, ActionType, AIContract,
)

OWNER  = "aa" * 20
ADDR_B = "bb" * 20
VALID_HASH = "a" * 64


@pytest.fixture
def engine():
    d = tempfile.mkdtemp()
    yield ContractEngine(ContractStore(d))
    shutil.rmtree(d)


def make_contract(engine, conditions=None, on_success=None, max_exec=0):
    conditions = conditions or [
        ContractCondition(field="score", operator="gte", value=0.8)
    ]
    on_success = on_success or [
        ContractAction(ActionType.EMIT_EVENT, {"event_name": "threshold_met"})
    ]
    return engine.deploy(
        owner=OWNER,
        name="Test Contract",
        model_id="model-1",
        trigger_description="Trigger when score >= 0.8",
        conditions=conditions,
        on_success=on_success,
        max_executions=max_exec,
    )


class TestContractDeploy:

    def test_deploy_contract(self, engine):
        c = make_contract(engine)
        assert c.status == ContractStatus.ACTIVE
        assert c.owner == OWNER

    def test_no_conditions_rejected(self, engine):
        with pytest.raises(ValueError):
            engine.deploy(OWNER, "C", "m", "trigger", [],
                          [ContractAction(ActionType.EMIT_EVENT, {})])

    def test_no_success_actions_rejected(self, engine):
        with pytest.raises(ValueError):
            engine.deploy(OWNER, "C", "m", "trigger",
                          [ContractCondition("f", "eq", 1)], [])

    def test_invalid_verification_level_rejected(self, engine):
        with pytest.raises(ValueError):
            engine.deploy(OWNER, "C", "m", "trigger",
                          [ContractCondition("f", "eq", 1)],
                          [ContractAction(ActionType.EMIT_EVENT, {})],
                          verification_level=99)

    def test_contract_hash_deterministic(self, engine):
        c = make_contract(engine)
        assert c.compute_hash() == c.compute_hash()

    def test_contract_persists(self, engine):
        c = make_contract(engine)
        store2 = ContractStore(os.path.dirname(engine.store.path))
        loaded = store2.get(c.contract_id)
        assert loaded is not None
        assert loaded.owner == OWNER


class TestConditionEvaluation:

    def test_gte_condition_true(self):
        c = ContractCondition("score", "gte", 0.8)
        assert c.evaluate({"score": 0.9}) is True

    def test_gte_condition_false(self):
        c = ContractCondition("score", "gte", 0.8)
        assert c.evaluate({"score": 0.5}) is False

    def test_eq_condition(self):
        c = ContractCondition("status", "eq", "approved")
        assert c.evaluate({"status": "approved"}) is True
        assert c.evaluate({"status": "rejected"}) is False

    def test_contains_condition(self):
        c = ContractCondition("text", "contains", "hello")
        assert c.evaluate({"text": "hello world"}) is True
        assert c.evaluate({"text": "goodbye"}) is False

    def test_not_null_condition(self):
        c = ContractCondition("result", "not_null", None)
        assert c.evaluate({"result": "something"}) is True
        assert c.evaluate({"result": None}) is False
        assert c.evaluate({}) is False

    def test_missing_field_returns_false(self):
        c = ContractCondition("score", "gt", 0.5)
        assert c.evaluate({}) is False

    def test_lt_condition(self):
        c = ContractCondition("risk", "lt", 0.3)
        assert c.evaluate({"risk": 0.1}) is True
        assert c.evaluate({"risk": 0.5}) is False

    def test_all_conditions_must_pass(self, engine):
        """Contract with 2 conditions — both must be True."""
        conditions = [
            ContractCondition("score", "gte", 0.8),
            ContractCondition("risk", "lt", 0.3),
        ]
        c = make_contract(engine, conditions=conditions)
        # Only first condition met
        assert c.evaluate_conditions({"score": 0.9, "risk": 0.5}) is False
        # Both met
        assert c.evaluate_conditions({"score": 0.9, "risk": 0.1}) is True


class TestContractExecution:

    def test_unverified_result_rejected(self, engine):
        c = make_contract(engine)
        engine.trigger(c.contract_id, "job-1")
        result = engine.evaluate(c.contract_id, {"score": 0.9}, verified=False)
        assert result.conditions_met is False
        assert result.error is not None
        loaded = engine.store.get(c.contract_id)
        assert loaded.status == ContractStatus.FAILED

    def test_verified_result_conditions_met(self, engine):
        c = make_contract(engine)
        engine.trigger(c.contract_id, "job-1")
        result = engine.evaluate(c.contract_id, {"score": 0.9}, verified=True)
        assert result.conditions_met is True
        assert len(result.actions_executed) == 1
        assert result.error is None

    def test_verified_result_conditions_not_met(self, engine):
        success_action = ContractAction(ActionType.EMIT_EVENT, {"event": "success"})
        failure_action = ContractAction(ActionType.EMIT_EVENT, {"event": "failure"})
        c = engine.deploy(
            OWNER, "C", "m", "t",
            [ContractCondition("score", "gte", 0.8)],
            [success_action],
            on_failure=[failure_action],
        )
        engine.trigger(c.contract_id, "job-1")
        result = engine.evaluate(c.contract_id, {"score": 0.3}, verified=True)
        assert result.conditions_met is False
        # on_failure should execute
        assert any(a["action_type"] == "EMIT_EVENT" for a in result.actions_executed)

    def test_transfer_arc_creates_instruction(self, engine):
        action = ContractAction(ActionType.TRANSFER_ARC, {"to": ADDR_B, "amount": 1000})
        c = engine.deploy(
            OWNER, "C", "m", "t",
            [ContractCondition("approved", "eq", True)],
            [action],
        )
        engine.trigger(c.contract_id, "job-1")
        result = engine.evaluate(c.contract_id, {"approved": True}, verified=True)
        assert result.conditions_met is True
        assert result.actions_executed[0]["result"]["instruction"] == "TRANSFER_ARC"

    def test_execution_count_increments(self, engine):
        c = make_contract(engine)
        engine.trigger(c.contract_id, "job-1")
        engine.evaluate(c.contract_id, {"score": 0.9}, verified=True)
        loaded = engine.store.get(c.contract_id)
        assert loaded.execution_count == 1

    def test_max_executions_completes_contract(self, engine):
        c = make_contract(engine, max_exec=1)
        engine.trigger(c.contract_id, "job-1")
        engine.evaluate(c.contract_id, {"score": 0.9}, verified=True)
        loaded = engine.store.get(c.contract_id)
        assert loaded.status == ContractStatus.COMPLETED

    def test_unlimited_executions_stays_active(self, engine):
        c = make_contract(engine, max_exec=0)
        engine.trigger(c.contract_id, "job-1")
        engine.evaluate(c.contract_id, {"score": 0.9}, verified=True)
        loaded = engine.store.get(c.contract_id)
        assert loaded.status == ContractStatus.ACTIVE


class TestContractLifecycle:

    def test_trigger_sets_waiting_ai(self, engine):
        c = make_contract(engine)
        engine.trigger(c.contract_id, "job-1")
        loaded = engine.store.get(c.contract_id)
        assert loaded.status == ContractStatus.WAITING_AI
        assert loaded.last_job_id == "job-1"

    def test_pause_and_resume(self, engine):
        c = make_contract(engine)
        engine.pause(c.contract_id, OWNER)
        assert engine.store.get(c.contract_id).status == ContractStatus.PAUSED
        engine.resume(c.contract_id, OWNER)
        assert engine.store.get(c.contract_id).status == ContractStatus.ACTIVE

    def test_only_owner_can_pause(self, engine):
        c = make_contract(engine)
        with pytest.raises(ValueError):
            engine.pause(c.contract_id, ADDR_B)

    def test_expired_contract_cannot_trigger(self, engine):
        c = engine.deploy(
            OWNER, "C", "m", "t",
            [ContractCondition("score", "gte", 0.5)],
            [ContractAction(ActionType.EMIT_EVENT, {})],
            expires_at=int(time.time()) - 1,  # Already expired
        )
        assert not c.can_execute()

    def test_expire_contracts_marks_expired(self, engine):
        c = engine.deploy(
            OWNER, "C", "m", "t",
            [ContractCondition("score", "gte", 0.5)],
            [ContractAction(ActionType.EMIT_EVENT, {})],
            expires_at=int(time.time()) - 1,
        )
        expired = engine.expire_contracts()
        assert c.contract_id in expired
        assert engine.store.get(c.contract_id).status == ContractStatus.EXPIRED
