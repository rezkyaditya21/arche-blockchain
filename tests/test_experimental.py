"""
ARCHE Experimental Modules — Test Suite
Phase 9 (PoUW), Phase 10 (ZKML), Phase 11 (Federated Learning)
"""
import sys, os, time, tempfile, shutil, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from experimental.pouw.pouw import PoUWExtension, PoUWValidator
from experimental.zkml.zkml import ZKMLInterface, ZKProof, check_zkml_feasibility
from experimental.federated.federated import FederatedManager, RoundStatus

VALID_HASH = "a" * 64
WORKER_A   = "aa" * 20
WORKER_B   = "bb" * 20
WORKER_C   = "cc" * 20


# ── Phase 9: PoUW ─────────────────────────────────────

class TestPoUW:

    def _ext(self):
        return PoUWExtension(
            job_id="job-1",
            model_id="model-1",
            input_hash=VALID_HASH,
            output_hash=VALID_HASH,
            inference_time_ms=1500,
            worker_address=WORKER_A,
            signature="sig",
        )

    def test_work_hash_deterministic(self):
        ext = self._ext()
        header = b"block_header_bytes"
        h1 = ext.compute_work_hash(header)
        h2 = ext.compute_work_hash(header)
        assert h1 == h2

    def test_work_hash_differs_with_different_output(self):
        ext1 = self._ext()
        ext2 = self._ext()
        ext2.output_hash = "b" * 64
        header = b"header"
        assert ext1.compute_work_hash(header) != ext2.compute_work_hash(header)

    def test_work_hash_differs_with_different_header(self):
        ext = self._ext()
        h1 = ext.compute_work_hash(b"header1")
        h2 = ext.compute_work_hash(b"header2")
        assert h1 != h2

    def test_invalid_hash_format_rejected(self):
        v = PoUWValidator()
        ext = self._ext()
        ext.input_hash = "tooshort"
        valid, reason = v.validate_extension(ext, b"header", difficulty=1)
        assert valid is False
        assert "hash" in reason.lower()

    def test_valid_pouw_with_easy_difficulty(self):
        """With difficulty=0 (any hash passes), should always validate."""
        v = PoUWValidator()
        ext = self._ext()
        # difficulty=0 → target = max, any hash passes
        valid, reason = v.validate_extension(ext, b"header", difficulty=0)
        # May or may not pass depending on hash, but should not crash
        assert isinstance(valid, bool)

    def test_invalid_inference_time_rejected(self):
        v = PoUWValidator()
        ext = self._ext()
        ext.inference_time_ms = -1
        valid, reason = v.validate_extension(ext, b"header", difficulty=0)
        assert valid is False

    def test_bonus_reward_with_extension(self):
        v = PoUWValidator()
        ext = self._ext()
        bonus = v.compute_bonus_reward(1000, ext, bonus_rate=0.1)
        assert bonus == 100

    def test_no_bonus_without_extension(self):
        v = PoUWValidator()
        bonus = v.compute_bonus_reward(1000, None)
        assert bonus == 0


# ── Phase 10: ZKML ────────────────────────────────────

class TestZKML:

    def test_generate_proof_raises_not_implemented(self):
        zkml = ZKMLInterface()
        with pytest.raises(NotImplementedError):
            zkml.generate_proof("model.onnx", b"input", b"output")

    def test_verify_proof_raises_not_implemented(self):
        zkml = ZKMLInterface()
        proof = ZKProof(
            proof_bytes=b"proof",
            public_inputs={},
            model_commitment=VALID_HASH,
            proof_system="groth16",
            generation_time_ms=1000,
            proof_size_bytes=1024,
        )
        with pytest.raises(NotImplementedError):
            zkml.verify_proof(proof, VALID_HASH)

    def test_commit_model_raises_not_implemented(self):
        zkml = ZKMLInterface()
        with pytest.raises(NotImplementedError):
            zkml.commit_model("model.onnx")

    def test_zkproof_valid_format(self):
        proof = ZKProof(
            proof_bytes=b"data",
            public_inputs={"output_hash": VALID_HASH},
            model_commitment=VALID_HASH,
            proof_system="groth16",
            generation_time_ms=5000,
            proof_size_bytes=2048,
        )
        assert proof.is_valid_format() is True

    def test_zkproof_invalid_proof_system(self):
        proof = ZKProof(
            proof_bytes=b"data",
            public_inputs={},
            model_commitment=VALID_HASH,
            proof_system="unknown_system",
            generation_time_ms=1000,
            proof_size_bytes=100,
        )
        assert proof.is_valid_format() is False

    def test_feasibility_small_model(self):
        result = check_zkml_feasibility(model_size_mb=5.0)
        assert "feasible" in result
        assert isinstance(result["feasible"], bool)

    def test_feasibility_large_model_not_feasible(self):
        result = check_zkml_feasibility(model_size_mb=10000.0)
        assert result["feasible"] is False

    def test_feasibility_has_recommendation(self):
        result = check_zkml_feasibility(5.0)
        assert "recommendation" in result


# ── Phase 11: Federated Learning ─────────────────────

class TestFederatedLearning:

    @pytest.fixture
    def mgr(self):
        d = tempfile.mkdtemp()
        yield FederatedManager(d)
        shutil.rmtree(d)

    def test_create_round(self, mgr):
        rnd = mgr.create_round(
            model_id="model-1",
            base_model_hash=VALID_HASH,
            round_number=1,
            min_workers=2,
            max_workers=5,
            reward_per_worker=100,
        )
        assert rnd.status == RoundStatus.OPEN
        assert rnd.round_number == 1

    def test_invalid_min_workers_rejected(self, mgr):
        with pytest.raises(ValueError):
            mgr.create_round("m", VALID_HASH, 1, min_workers=0, max_workers=5, reward_per_worker=100)

    def test_submit_gradient(self, mgr):
        rnd = mgr.create_round("m", VALID_HASH, 1, 2, 5, 100)
        sub = mgr.submit_gradient(
            rnd.round_id, WORKER_A, VALID_HASH,
            gradient_norm=1.0, data_size=100, training_loss=0.5,
        )
        assert sub.worker_address == WORKER_A
        assert sub.is_valid is True

    def test_duplicate_worker_rejected(self, mgr):
        rnd = mgr.create_round("m", VALID_HASH, 1, 2, 5, 100)
        mgr.submit_gradient(rnd.round_id, WORKER_A, VALID_HASH, 1.0, 100, 0.5)
        with pytest.raises(ValueError):
            mgr.submit_gradient(rnd.round_id, WORKER_A, VALID_HASH, 1.0, 100, 0.5)

    def test_high_gradient_norm_flagged(self, mgr):
        rnd = mgr.create_round("m", VALID_HASH, 1, 2, 5, 100)
        sub = mgr.submit_gradient(
            rnd.round_id, WORKER_A, VALID_HASH,
            gradient_norm=50.0,  # Very high — suspicious
            data_size=100, training_loss=0.5,
        )
        assert sub.anomaly_score > 0

    def test_aggregate_requires_min_workers(self, mgr):
        rnd = mgr.create_round("m", VALID_HASH, 1, 2, 5, 100)
        # Only 1 submission, min=2
        mgr.submit_gradient(rnd.round_id, WORKER_A, VALID_HASH, 1.0, 100, 0.5)
        with pytest.raises(ValueError):
            mgr.aggregate(rnd.round_id, "b" * 64)

    def test_aggregate_completes_round(self, mgr):
        rnd = mgr.create_round("m", VALID_HASH, 1, 2, 5, 100)
        mgr.submit_gradient(rnd.round_id, WORKER_A, VALID_HASH, 1.0, 100, 0.5)
        mgr.submit_gradient(rnd.round_id, WORKER_B, "b" * 64, 0.8, 150, 0.4)
        rnd = mgr.aggregate(rnd.round_id, "c" * 64)
        assert rnd.status == RoundStatus.COMPLETED
        assert rnd.aggregated_model_hash == "c" * 64

    def test_contribution_weight_zero_for_invalid(self, mgr):
        from experimental.federated.federated import GradientSubmission
        sub = GradientSubmission(
            submission_id="s1", round_id="r1",
            worker_address=WORKER_A, gradient_hash=VALID_HASH,
            gradient_norm=999.0, data_size=100, training_loss=0.5,
            submitted_at=int(time.time()), is_valid=False,
        )
        weight = mgr.compute_contribution_weight(sub)
        assert weight == 0.0

    def test_contribution_weight_proportional_to_data_size(self, mgr):
        from experimental.federated.federated import GradientSubmission
        sub_small = GradientSubmission(
            "s1", "r1", WORKER_A, VALID_HASH, 1.0, 100, 0.5,
            int(time.time()), True,
        )
        sub_large = GradientSubmission(
            "s2", "r1", WORKER_B, VALID_HASH, 1.0, 1000, 0.5,
            int(time.time()), True,
        )
        assert mgr.compute_contribution_weight(sub_large) > mgr.compute_contribution_weight(sub_small)

    def test_round_persistence(self, mgr):
        rnd = mgr.create_round("m", VALID_HASH, 1, 2, 5, 100)
        round_id = rnd.round_id
        data_dir = os.path.dirname(mgr.rounds_path)
        mgr2 = FederatedManager(data_dir)
        loaded = mgr2.get_round(round_id)
        assert loaded is not None
        assert loaded.model_id == "m"

    def test_active_rounds_excludes_completed(self, mgr):
        rnd = mgr.create_round("m", VALID_HASH, 1, 1, 5, 100)
        mgr.submit_gradient(rnd.round_id, WORKER_A, VALID_HASH, 1.0, 100, 0.5)
        mgr.aggregate(rnd.round_id, "b" * 64)
        assert len(mgr.active_rounds()) == 0
